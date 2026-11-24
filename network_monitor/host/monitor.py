"""Receive real FPGA UDP images/telemetry and serve the monitor on this PC."""
import argparse
import csv
import errno
import hashlib
from collections import OrderedDict, deque
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import socket
import struct
import threading
import time
import webbrowser
import uuid
from urllib.parse import parse_qs, unquote, urlsplit
from receive_camera import FIELDS, Reassembler, png_gray, publish, frame_png, frame_jpeg
from legacy_server import CAMERA_FILENAME, camera_status, latest_camera_csv

ROOT=Path(__file__).resolve().parents[1]
EVENT_TYPES={'fall','danger','power_low','power_normal','wake_check'}

def event_key(event):
    if event.get('event_id'):return event['event_id']
    # Stable identifiers also cover events saved before live-web integration.
    person=event.get('person') or {}
    identity=[event.get('received_at'),event.get('type'),person.get('id'),person.get('events'),event.get('device_ms')]
    return hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]

def parse_status(data):
    if len(data)!=128 or data[:8]!=b'BMON0001':
        raise ValueError('Invalid BMON0001 packet')
    u=lambda at:struct.unpack_from('>I',data,at)[0]
    s=lambda at:struct.unpack_from('>i',data,at)[0]
    if u(28)&~3 or u(52)>4:
        raise ValueError('Invalid telemetry flags or mode')
    people=[]
    for i in range(2):
        at=64+i*24
        flags=u(at+4)
        box=list(struct.unpack_from('>4H',data,at+12))
        if flags&~15 or (flags&1 and not (box[0]<box[2]<=1280 and box[1]<box[3]<=720)):
            raise ValueError('Invalid person box')
        if u(at+8)>32768:
            raise ValueError('Invalid person confidence')
        people.append(dict(id=u(at),valid=bool(flags&1),alarm=bool(flags&2),warning=bool(flags&4),
                           pixels=bool(flags&8),score_q15=u(at+8),box=box,events=u(at+20)))
    return dict(sequence=u(8),device_ms=u(12),source_count=u(16),capture_ms=u(20),
                env_ms=u(24),environment_valid=bool(u(28)&1),infrared_valid=bool(u(28)&2),
                temperature_c=s(32)/100,humidity_percent=s(36)/100,
                ir_min_c=s(40)/100,ir_max_c=s(44)/100,ir_center_c=s(48)/100,
                power_mode=u(52),inference_ms=u(56),detection_hz=u(60)/10,
                env_delta_ms=s(112),ir_delta_ms=s(116),people=people)

class State:
    def __init__(self, records):
        self.lock=threading.Lock()
        self.frame_ready=threading.Condition(self.lock)
        self.stream_sequence=0
        self.saved_image_at=-10
        self.frames=OrderedDict()
        self.assembler=Reassembler()
        self.status=None
        self.status_time=0
        self.statuses=OrderedDict()
        self.image=None
        self.image_time=0
        self.events=deque(maxlen=200)
        self.image_times=deque(maxlen=300)
        self.seen_events={}
        self.warning_ids=set()
        self.last_power_mode=None
        self.event_session=uuid.uuid4().hex[:12]
        self.event_sequence=0
        self.records=Path(records)
        self.records.mkdir(parents=True,exist_ok=True)
        self.camera_csv=self.records/datetime.now().strftime('camera_%Y%m%d_%H%M%S.csv')
        if not self.camera_csv.exists():
            with self.camera_csv.open('x',encoding='utf8',newline='') as output:
                csv.DictWriter(output,fieldnames=FIELDS,quoting=csv.QUOTE_ALL).writeheader()
        history=OrderedDict()
        for file in sorted(self.records.glob('events_*.jsonl'))[-8:]:
            for line in file.read_text(encoding='utf8').splitlines()[-200:]:
                try:
                    event=json.loads(line)
                    if event.get('type') in EVENT_TYPES and (event.get('type') not in ('fall','danger') or isinstance(event.get('person'),dict)):
                        key=event_key(event);event['event_id']=key
                        history[key]=event
                except (ValueError,TypeError):continue
        self.events.extend(reversed(list(history.values())[-200:]))
        self.log=self.records/(datetime.now().strftime('events_%Y%m%d_%H%M%S')+'.jsonl')
        self.started=time.monotonic()
        self.packets=self.rejected=0
        self.network=dict(receiver_running=False,pc_ip='192.168.0.3',pc_ip_configured=False,
                          listen_ip=None,udp_port=8080,error=None,fallback=False)

    def set_network(self,**values):
        with self.lock:self.network.update(values)

    def save_event(self,event):
        with self.log.open('a',encoding='utf8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')

    def attach_thumbnail(self,event):
        if (event.get('type') not in ('fall','danger') or event.get('thumbnail') or not self.image or
            (event['source_count'],event['capture_ms']) not in self.frames):return False
        name='event_'+hashlib.sha256(event_key(event).encode()).hexdigest()[:24]+'.png'
        (self.records/name).write_bytes(self.frames[(event['source_count'],event['capture_ms'])]);event['thumbnail']=name
        return True

    def append_event(self,status,kind,person=None):
        self.event_sequence+=1
        event=dict(event_id=f'{self.event_session}-{self.event_sequence}',type=kind,source='board',
                   received_at=datetime.now(timezone.utc).isoformat(),device_ms=status['device_ms'],
                   capture_ms=status['capture_ms'],source_count=status['source_count'],power_mode=status['power_mode'])
        if person is not None:event['person']=person.copy()
        self.attach_thumbnail(event)
        self.events.appendleft(event);self.save_event(event)

    def accept(self, data, now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            self.packets+=1
            if data[:8] in (b'TCAM1601',b'TCAM5651',b'TCAM6401'):
                frame=self.assembler.add(data,now)
                if frame:
                    png=frame_png(frame);jpeg=frame_jpeg(frame)
                    self.image=dict(source_count=frame.frame,capture_ms=frame.ms,png=png,jpeg=jpeg,
                                    width=frame.width,height=frame.height,format='rgb565' if frame.format==2 else 'gray8',
                                    received_at=datetime.now(timezone.utc).isoformat())
                    self.frames[(frame.frame,frame.ms)]=png
                    while len(self.frames)>60:self.frames.popitem(last=False)
                    self.image_time=now;self.image_times.append(now)
                    self.stream_sequence+=1;self.frame_ready.notify_all()
                    for event in self.events:
                        if self.attach_thumbnail(event):self.save_event(event)
                    if now-self.saved_image_at>=1:
                        publish(frame,self.records,self.camera_csv,('192.168.0.2',8080))
                        self.saved_image_at=now
            else:
                status=parse_status(data)
                if self.status and now-self.status_time<3:
                    delta=(status['sequence']-self.status['sequence'])&0xffffffff
                    if not 0<delta<0x80000000:
                        return
                elif self.status and status['device_ms']<self.status['device_ms']:
                    self.statuses.clear()
                    self.seen_events.clear()
                    self.warning_ids.clear()
                    self.last_power_mode=None
                self.status=status
                self.status_time=now
                self.statuses[status['source_count']]=(now,status)
                self.statuses.move_to_end(status['source_count'])
                while len(self.statuses)>48:self.statuses.popitem(last=False)
                for p in status['people']:
                    previous=self.seen_events.get(p['id'],0)
                    if p['id'] and p['events']>previous:
                        self.append_event(status,'fall',p)
                    if p['id'] and p['valid'] and p['warning'] and not p['alarm'] and p['id'] not in self.warning_ids:
                        self.append_event(status,'danger',p)
                    if p['id']:self.seen_events[p['id']]=p['events']
                self.warning_ids={p['id'] for p in status['people'] if p['id'] and p['valid'] and p['warning'] and not p['alarm']}
                if self.last_power_mode is not None and self.last_power_mode!=status['power_mode']:
                    kind={0:'power_normal',2:'power_low',4:'wake_check'}.get(status['power_mode'])
                    if kind:self.append_event(status,kind)
                self.last_power_mode=status['power_mode']

    def snapshot(self, now=None):
        now=time.monotonic() if now is None else now
        with self.lock:
            image={k:v for k,v in self.image.items() if k not in ('png','jpeg')} if self.image else None
            boxes=None
            if image:
                matched=self.statuses.get(image['source_count'])
                if matched and matched[1]['capture_ms']==image['capture_ms']:
                    boxes=matched[1]['people']
            recent=[t for t in self.image_times if now-t<10]
            hz=(len(recent)-1)/(recent[-1]-recent[0]) if len(recent)>1 and recent[-1]>recent[0] else 0
            return dict(online=bool(self.status and now-self.status_time<3),
                        status_age_ms=int((now-self.status_time)*1000) if self.status else None,
                        image_age_ms=int((now-self.image_time)*1000) if image else None,
                        image=image,image_boxes=boxes,status=self.status,events=[e.copy() for e in self.events],
                        received_image_hz=round(hz,2),stream_sequence=self.stream_sequence,
                        camera_frames=len(self.image_times),incomplete_images=self.assembler.expired,packets=self.packets,rejected=self.rejected,
                        network=self.network.copy(),
                        architecture='FPGA UDP -> PC HTTP',board_validation='pending')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass

    def stream_camera(self):
        self.connection.settimeout(5)
        self.send_response(200)
        self.send_header('Content-Type','multipart/x-mixed-replace; boundary=ti60frame')
        self.send_header('Cache-Control','no-store, no-cache, must-revalidate')
        self.send_header('X-Accel-Buffering','no');self.end_headers()
        previous=-1;state=self.server.state
        try:
            while True:
                with state.frame_ready:
                    ready=state.frame_ready.wait_for(lambda:state.stream_sequence!=previous and state.image is not None,timeout=2)
                    if not ready:
                        # Heartbeat does not repeat an old image as a new frame.
                        self.wfile.write(b'\r\n');self.wfile.flush();continue
                    image=state.image;sequence=state.stream_sequence
                    jpeg=image['jpeg'];count=image['source_count'];captured=image['capture_ms']
                self.wfile.write((f'--ti60frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n'
                                  f'X-Frame-Id: {count}\r\nX-Capture-Ms: {captured}\r\n\r\n').encode()+jpeg+b'\r\n')
                self.wfile.flush();previous=sequence
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,TimeoutError,OSError):
            return

    def do_GET(self):
        request=urlsplit(self.path)
        path=request.path
        if path=='/stream.mjpg':self.stream_camera();return
        if path in ('/','/monitor.html'):
            data=(ROOT/'web/monitor.html').read_bytes();mime='text/html; charset=utf-8'
        elif path=='/api/status':
            data=json.dumps(self.server.state.snapshot(),ensure_ascii=False).encode();mime='application/json; charset=utf-8'
        elif path=='/api/health':
            data=b'{"service":"best-test-ethernet-monitor","http_location":"PC","http_host":"PC","riscv_http_implemented":false,"original_layout":true,"live_events":true}';mime='application/json'
        elif path=='/api/latest-csv':
            data=json.dumps(dict(filename=latest_camera_csv(self.server.state.records),source='CAMERA_THUMB')).encode()
            mime='application/json'
        elif path=='/api/camera-status':
            values=parse_qs(request.query,keep_blank_values=True).get('filename',[])
            if len(values)>1 or (values and not CAMERA_FILENAME.fullmatch(values[0])):
                self.send_error(400,'Expected one camera_YYYYMMDD_HHMMSS.csv filename');return
            status=camera_status(self.server.state.records,values[0] if values else None)
            with self.server.state.lock:status['network']=self.server.state.network.copy()
            data=json.dumps(status).encode();mime='application/json'
        elif path=='/camera.png':
            with self.server.state.lock:
                image=self.server.state.image
                data=image['png'] if image else None
                query=parse_qs(request.query)
                if image and query.get('v') and query['v']!=[str(image['source_count'])+':'+str(image['capture_ms'])]:
                    self.send_error(409,'Image has advanced; retry with latest metadata');return
            if not data:self.send_error(404,'No camera frame received');return
            mime='image/png'
        elif path.startswith('/events/'):
            name=path.removeprefix('/events/')
            if '/' in name or '\\' in name or not name.startswith('event_') or not name.endswith('.png'):
                self.send_error(404);return
            file=self.server.state.records/name
            if not file.is_file():self.send_error(404);return
            data=file.read_bytes();mime='image/png'
        else:
            # Serve only public image/CSV assets, never host source, logs or
            # arbitrary paths. The original page can select relative files.
            name=unquote(path).lstrip('/')
            file=None
            for directory in (self.server.state.records,ROOT/'web'):
                base=directory.resolve();candidate=(base/name).resolve()
                if (candidate.is_relative_to(base) and candidate.is_file() and
                    candidate.suffix.lower() in ('.csv','.png','.jpg','.jpeg','.gif','.webp','.svg','.css','.js','.ico')):
                    file=candidate;break
            if file is None:self.send_error(404);return
            data=file.read_bytes()
            mime='text/csv; charset=utf-8' if file.suffix.lower()=='.csv' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
        self.send_response(200);self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(data)

def has_local_address(address):
    # Binding an ephemeral socket checks the local address without modifying
    # Windows adapter, DHCP, routes, DNS or firewall settings.
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:probe.bind((address,0))
        return True
    except OSError:return False

def open_udp_listener(address,port):
    listener=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024*1024)
        fallback=False
        try:listener.bind((address,port))
        except OSError as error:
            missing_address=error.errno in (errno.EADDRNOTAVAIL,10049) or getattr(error,'winerror',None)==10049
            if address=='0.0.0.0' or not missing_address:raise
            listener.bind(('0.0.0.0',port));fallback=True
        listener.settimeout(.5)
        return listener,fallback
    except Exception:
        listener.close();raise

def network_receiver(state,address,port,source,stop):
    last_error=None
    while not stop.is_set():
        try:
            listener,fallback=open_udp_listener(address,port)
            with listener:
                actual=listener.getsockname()
                state.set_network(receiver_running=True,listen_ip=actual[0],udp_port=actual[1],
                                  error=None,fallback=fallback)
                print(f'UDP_READY listen={actual[0]}:{actual[1]} source={source}:8080 fallback={int(fallback)}',flush=True)
                last_error=None;last_probe=-10
                while not stop.is_set():
                    now=time.monotonic()
                    if now-last_probe>=2:
                        state.set_network(pc_ip_configured=has_local_address('192.168.0.3'));last_probe=now
                    try:data,peer=listener.recvfrom(65535)
                    except socket.timeout:continue
                    if peer!=(source,8080):continue
                    try:state.accept(data)
                    except (ValueError,struct.error):
                        with state.lock:state.rejected+=1
        except OSError as error:
            message=str(error)
            state.set_network(receiver_running=False,error=message,
                              pc_ip_configured=has_local_address('192.168.0.3'))
            if message!=last_error:print(f'UDP_WAIT {message}; webpage stays available; retry in 2s.',flush=True)
            last_error=message;stop.wait(2)
    state.set_network(receiver_running=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bind',default='0.0.0.0',help='UDP listen address; default all local adapters')
    p.add_argument('--udp-port',type=int,default=8080)
    p.add_argument('--source',default='192.168.0.2');p.add_argument('--http-bind',default='127.0.0.1')
    p.add_argument('--http-port',type=int,default=8002)
    p.add_argument('--records',type=Path,default=ROOT/'records')
    p.add_argument('--open-browser',action='store_true')
    a=p.parse_args();state=State(a.records);stop=threading.Event()
    # Start HTTP independently of UDP or a missing static NIC address. The user
    # can always open the page to see the actual network diagnostic.
    try:server=ThreadingHTTPServer((a.http_bind,a.http_port),Handler)
    except OSError as error:p.error(f'Cannot listen on HTTP {a.http_bind}:{a.http_port}: {error}. Stop the previous monitor or choose another --http-port.')
    server.state=state
    thread=threading.Thread(target=network_receiver,args=(state,a.bind,a.udp_port,a.source,stop),daemon=True);thread.start()
    print(f'HTTP_READY http://127.0.0.1:{server.server_port}/monitor.html ; HTTP runs on PC, Ctrl+C stops.',flush=True)
    if not has_local_address('192.168.0.3'):
        print('NETWORK_CONFIG: PC has no 192.168.0.3 address. For a direct cable, configure the wired adapter as 192.168.0.3/24, no gateway. Page remains available.',flush=True)
    if a.open_browser:webbrowser.open(f'http://127.0.0.1:{server.server_port}/monitor.html')
    try:server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close();thread.join(timeout=2)

if __name__=='__main__':main()
