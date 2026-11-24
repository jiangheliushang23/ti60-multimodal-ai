"""PC HTTP file service for camera receiver output; this is not a RISC-V server."""
import argparse
import csv
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

CAMERA_FILENAME = re.compile(r'camera_\d{8}_\d{6}\.csv')
CAMERA_FIELDS = {'received_at', 'source_ip', 'source_port', 'kind',
                 'display_frame_id', 'device_time_ms', 'width', 'height',
                 'format', 'preview_path'}


def latest_camera_csv(directory):
    files = sorted(p.name for p in Path(directory).glob('camera_*.csv')
                   if p.is_file() and CAMERA_FILENAME.fullmatch(p.name))
    return files[-1] if files else None


def camera_status(directory, filename=None, *, now=None):
    """Measure saved receipts, not camera FPS, inference FPS, or link liveness."""
    now = now or datetime.now(timezone.utc)
    if filename is not None and not CAMERA_FILENAME.fullmatch(filename):
        raise ValueError('Expected a camera_YYYYMMDD_HHMMSS.csv filename')
    filename = filename or latest_camera_csv(directory)
    result = {
        'state': 'no_data', 'filename': filename,
        'checked_at': now.isoformat(), 'offline_after_seconds': 5,
        'rate_window_seconds': 10,
        'expected_source': {'ip': '192.168.0.2', 'port': 8080},
        'record_count': 0, 'recent_record_count': 0, 'receive_fps': 0.0,
        'last_received_at': None, 'seconds_since_receipt': None,
        'last_display_frame_id': None, 'recent_ages_seconds': [],
    }
    if not filename:
        return result
    path = Path(directory) / filename
    latest = None
    try:
        text = path.read_text(encoding='utf-8-sig')
        # Export-Csv terminates each record with a newline. Ignore a final
        # unfinished record while the receiver is appending to the file.
        complete = text[:text.rfind('\n') + 1]
        reader = csv.DictReader(io.StringIO(complete), strict=True)
        if not CAMERA_FIELDS.issubset(reader.fieldnames or ()):
            result['state'] = 'read_error'
            return result
        for row in reader:
            if None in row or any(row.get(field) is None for field in CAMERA_FIELDS):
                continue
            if (row['kind'] != 'CAMERA_THUMB' or row['source_ip'] != '192.168.0.2'
                    or row['source_port'] != '8080' or (row['width'],row['height'],row['format']) not in
                    (('160','90','gray8'),('160','90','rgb565'),('640','360','rgb565'))):
                continue
            try:
                received = datetime.fromisoformat(row['received_at'])
                if received.utcoffset() is None:
                    continue
                frame = int(row['display_frame_id'])
                device_time = int(row['device_time_ms'])
                if not (0 <= frame <= 0xffffffff and 0 <= device_time <= 0xffffffff):
                    continue
            except (ValueError, OverflowError):
                continue
            result['record_count'] += 1
            age = (now - received).total_seconds()
            if 0 <= age < result['rate_window_seconds']:
                result['recent_ages_seconds'].append(age)
            if latest is None or received > latest:
                latest = received
                result['last_received_at'] = row['received_at']
                result['last_display_frame_id'] = frame
    except FileNotFoundError:
        return result
    except (OSError, UnicodeError, csv.Error):
        result.update(state='read_error', record_count=0,
                      recent_ages_seconds=[], last_received_at=None,
                      last_display_frame_id=None)
        return result
    result['recent_record_count'] = len(result['recent_ages_seconds'])
    result['receive_fps'] = result['recent_record_count'] / result['rate_window_seconds']
    if latest is not None:
        age = (now - latest).total_seconds()
        result['seconds_since_receipt'] = age
        result['state'] = ('clock_error' if age < -2 else
                           'online' if age <= result['offline_after_seconds'] else 'stale')
    return result

class MonitorHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Ti60-Monitor','camera-web-pc')
        super().end_headers()

    def send_json(self, value, status=200):
        data=json.dumps(value,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        request_path=urlsplit(self.path).path
        if request_path=='/api/health':
            return self.send_json({'service':'ti60-camera-web-monitor','http_host':'PC',
                                   'riscv_http_implemented':False})
        if request_path=='/api/latest-csv':
            return self.send_json({'filename':latest_camera_csv(self.directory),'source':'CAMERA_THUMB'})
        if request_path=='/api/camera-status':
            values=parse_qs(urlsplit(self.path).query,keep_blank_values=True).get('filename',[])
            if len(values)>1 or (values and not CAMERA_FILENAME.fullmatch(values[0])):
                return self.send_json({'error':'Expected one camera_YYYYMMDD_HHMMSS.csv filename'},400)
            return self.send_json(camera_status(self.directory,values[0] if values else None))
        if request_path=='/':
            self.send_response(302)
            self.send_header('Location','/monitor.html')
            self.end_headers()
            return
        super().do_GET()

def make_server(directory, bind='127.0.0.1', port=8002):
    return ThreadingHTTPServer((bind,port),partial(MonitorHandler,directory=str(directory)))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8002)
    parser.add_argument('--directory',type=Path,default=Path(__file__).resolve().parents[1]/'web')
    args=parser.parse_args()
    if not (args.directory/'monitor.html').is_file():
        parser.error('monitor.html is missing from the web directory')
    try:
        server=make_server(args.directory,args.bind,args.port)
    except OSError as error:
        raise SystemExit(f'Cannot start HTTP listener on {args.bind}:{args.port}: {error}')
    print(f'PC HTTP monitor: http://{args.bind}:{server.server_port}/monitor.html',flush=True)
    print('Sensors and AI events are not connected; RISC-V HTTP is pending.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
