"""Existing monitor plus fall-only playback; original firmware/UI remain intact."""
import argparse
from collections import deque
from bisect import bisect_left
from contextlib import suppress
import json
from pathlib import Path
import re
import threading
import time
import struct
from urllib.parse import parse_qs, unquote, urlsplit
import webbrowser
import zipfile

import monitor
from fall_replay import AsyncRecorder, CLIP_ID
from monitor_view import render_page
from smart_assist import SmartAssist

ROOT = Path(__file__).resolve().parents[1]
VIEWER = re.compile(r'[0-9a-f]{16,40}\Z')


class State(monitor.State):
    def __init__(self, records):
        super().__init__(records)
        self.recordings = AsyncRecorder(self.records / 'fall_clips')
        self.play_lock = threading.Lock()
        self.playbacks = {}
        self._replay_events = []
        self.person_records = deque(maxlen=200)
        self.person_record_keys = deque(maxlen=400)
        self.assist = SmartAssist(self.records)

    def append_event(self, status, kind, person=None):
        super().append_event(status, kind, person)
        if kind == 'fall' and person and person.get('alarm'):
            self._replay_events.append(self.events[0].copy())

    def accept(self, data, now=None):
        previous_sequence = self.stream_sequence
        old_status = self.status
        super().accept(data, now)
        if self.status is not old_status and old_status:
            delta = (self.status['device_ms'] - old_status['device_ms']) & 0xffffffff
            if delta >= 0x80000000:
                self.recordings.offer('reset')
                self.person_record_keys.clear()
        if self.status is not old_status:
            summary = struct.unpack_from('>I', data, 124)[0]
            if summary >> 24 == 0xa1:
                self.status['thermal_presence'] = dict(version=1, normal_pixels=summary & 1023,
                    largest_region_pixels=(summary >> 10) & 1023)
            self._record_people(self.status)
            self.assist.observe(self.status)
        for event in self._replay_events:
            self.recordings.offer('event', event)
        self._replay_events.clear()
        if self.stream_sequence != previous_sequence:
            with self.lock:
                image = self.image.copy()
            # Reuse the JPEG already encoded for the live MJPEG stream.
            self.recordings.offer('frame', image)

    def _record_people(self, status):
        # Save genuine inference observations, not independently numbered UDP video frames.
        age=(status['device_ms']-status['capture_ms'])&0xffffffff
        if status['power_mode']==2 or age>1500:
            return
        key=(status['source_count'],status['capture_ms'])
        if key in self.person_record_keys:
            return
        self.person_record_keys.append(key)
        received=monitor.datetime.now(monitor.timezone.utc).isoformat()
        people=[p for p in status['people'] if p['id'] and p['valid']]
        rows=[]
        for person in people or [None]:
            box=person['box'] if person else None
            rows.append(dict(_board=True,_detection=True,_missing=person is None,
                _pixels=bool(person and person['pixels']),_alarm=bool(person and person['alarm']),
                event_id=f'person-{self.event_session}-{key[0]}-{key[1]}-{person["id"] if person else 0}',
                received_at=received,kind='BOARD_DETECTION',type='person' if person else 'no_person',
                id=person['id'] if person else '',confidence_pct=f'{person["score_q15"]*100/32768:.1f}' if person else '',
                x=(box[0]+box[2]+1)//2 if box else None,y=(box[1]+box[3]+1)//2 if box else None,
                device_ms=status['device_ms'],capture_ms=status['capture_ms']))
        with self.lock:
            self.person_records.extendleft(rows)

    def snapshot(self, now=None):
        result=super().snapshot(now)
        with self.lock:
            result['person_records']=[row.copy() for row in self.person_records]
        result['smart_assist'] = self.assist.snapshot()
        return result

    def close(self):
        self.assist.close()
        self.recordings.close()


SECTION = '''
<link rel="stylesheet" href="fall_replay.css">
<section class="panel history" id="fall-replay" aria-labelledby="fall-replay-heading">
 <div class="panel-head"><div><h2 id="fall-replay-heading">跌倒事件回放</h2>
 <div class="sub">仅保存板端真实跌倒前 5 秒、后 5 秒；普通画面仅作内存预缓存</div></div>
 <span class="pill blue" id="fall-storage">录像上限 512 MiB</span></div>
 <div class="fall-grid"><div><label for="fall-clips">选择跌倒录像</label>
 <select id="fall-clips"><option value="">暂无跌倒录像</option></select>
 <p class="sub" id="fall-list-state" role="status">正在读取录像列表</p>
 <div class="actions"><button class="btn small" id="fall-refresh">刷新录像</button>
 <a class="btn small" id="fall-download" hidden>下载录像包</a></div>
 <p class="sub">跌倒时刻采用板端首次报警对应的检测图像时间；缺帧或预缓存不足会明确标注。</p></div>
 <div><div class="video-stage fall-stage"><img id="fall-picture" alt="跌倒事件录像" hidden>
 <span class="empty-img" id="fall-empty">等待真实跌倒事件，网页演示按钮不会保存录像</span></div>
 <div class="fall-timeline"><input id="fall-timeline" type="range" min="0" max="0" value="0" disabled aria-label="跌倒录像时间轴">
 <span id="fall-event-mark" aria-hidden="true"></span></div>
 <div class="actions"><button class="btn small" id="fall-play" disabled>播放</button>
 <button class="btn small" id="fall-previous" disabled>上一帧</button>
 <button class="btn small" id="fall-next" disabled>下一帧</button>
 <button class="btn small danger" id="fall-jump" disabled>跌倒时刻</button>
 <select id="fall-speed" aria-label="回放速度"><option value="1">1 倍速</option><option value="0.5">0.5 倍速</option><option value="2">2 倍速</option></select>
 <span class="sub" id="fall-position">—</span></div>
 <p class="sub" id="fall-detail" role="status"></p></div></div>
</section>
<script src="fall_replay.js" defer></script>
'''


class Handler(monitor.Handler):
    def do_POST(self):
        if urlsplit(self.path).path != '/api/smart-assist/config':
            self.send_error(404)
            return
        # Browsers must use this server's same-origin JSON API, including on LAN HTTP.
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            self.send_data(dict(error='请从本系统页面保存设置'), status=403)
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 16384 or self.headers.get_content_type() != 'application/json':
                raise ValueError('请求应为 JSON，且不超过 16 KiB')
            self.connection.settimeout(5)
            value = json.loads(self.rfile.read(size))
            self.send_data(dict(saved=True, config=self.server.state.assist.configure(value)))
        except (ValueError, TypeError, UnicodeError) as error:
            self.send_data(dict(error=str(error)), status=400)
        except OSError:
            self.send_data(dict(error='配置文件写入失败，请检查电脑磁盘和权限'), status=500)

    def send_data(self, data, mime='application/json; charset=utf-8', status=200):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def playback_status(self, viewer, stop=False):
        with self.server.state.play_lock:
            values = self.server.state.playbacks
            result = values.get(viewer)
            if stop and result:
                result['running'] = False
            return dict(result or dict(running=False))

    def replay_stream(self, meta, directory, query):
        viewer = query.get('viewer', [''])[0]
        if not VIEWER.fullmatch(viewer):
            raise ValueError('Invalid playback viewer')
        speed = float(query.get('speed', ['1'])[0])
        if speed not in (.5, 1, 2):
            raise ValueError('Unsupported playback speed')
        offset = float(query.get('offset_ms', ['0'])[0])
        if not 0 <= offset <= meta['duration_ms']:
            raise ValueError('Playback offset out of range')
        frames = meta['frames']
        if not frames:
            raise KeyError('No recorded frames')
        first = frames[0]['ms']
        offsets = [f['ms'] - first for f in frames]
        index = min(bisect_left(offsets, offset), len(frames) - 1)
        state = self.server.state
        started = time.monotonic()
        run = dict(clip=meta['id'], running=True, index=index, offset_ms=offsets[index], speed=speed,
                   updated=started, token=time.monotonic_ns())
        with state.play_lock:
            for key in list(state.playbacks):
                if started - state.playbacks[key]['updated'] > 120:
                    del state.playbacks[key]
            if viewer not in state.playbacks and len(state.playbacks) >= 64:
                self.send_data({'error': 'Too many playback clients'}, status=503)
                return
            state.playbacks[viewer] = run
        self.connection.settimeout(5)
        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=fallframe')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        try:
            for i in range(index, len(frames)):
                deadline = started + (offsets[i] - offset) / (1000 * speed)
                while True:
                    with state.play_lock:
                        if state.playbacks.get(viewer) is not run or not run['running']:
                            return
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(.05, remaining))
                # Slow browser connections follow the source clock rather than growing a backlog.
                if i + 1 < len(frames) and time.monotonic() > started + (offsets[i + 1] - offset) / (1000 * speed):
                    continue
                jpeg = (directory / frames[i]['file']).read_bytes()
                header = (f'--fallframe\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n'
                          f'X-Frame-Index: {i}\r\nX-Offset-Ms: {offsets[i]}\r\n\r\n').encode()
                self.wfile.write(header + jpeg + b'\r\n')
                self.wfile.flush()
                with state.play_lock:
                    run.update(index=i, offset_ms=offsets[i], updated=time.monotonic())
            self.wfile.write(b'--fallframe--\r\n')
        finally:
            with state.play_lock:
                run['running'] = False
                run['updated'] = time.monotonic()

    def do_GET(self):
        request = urlsplit(self.path)
        path = request.path
        query = parse_qs(request.query)
        try:
            if path in ('/', '/monitor.html'):
                original = render_page((ROOT / 'web/monitor.html').read_bytes())
                from smart_page import enhance
                original = enhance(original)
                self.send_data(original.replace(b'</main>', SECTION.encode('utf8') + b'</main>', 1), 'text/html; charset=utf-8')
                return
            if path == '/api/smart-assist':
                self.send_data(self.server.state.assist.snapshot())
                return
            if path == '/mobile.html':
                from smart_page import SECTION as SMART_SECTION
                page = (ROOT / 'web/mobile.html').read_bytes().replace(b'<!--SMART_SECTION-->', SMART_SECTION.encode('utf8')).replace(b'<!--REPLAY_SECTION-->', SECTION.encode('utf8'))
                self.send_data(page, 'text/html; charset=utf-8')
                return
            if path == '/android/latest.apk':
                apk = ROOT.parent / 'mobile_app/dist/Ti60-Fall-Monitor.apk'
                if not apk.is_file():
                    raise FileNotFoundError(apk)
                self.send_data(apk.read_bytes(), 'application/vnd.android.package-archive')
                return
            if path == '/api/health':
                self.send_data(dict(service='best-test-ethernet-monitor', http_location='PC', http_host='PC',
                                    riscv_http_implemented=False, original_layout=True, live_events=True,
                                    fall_replay='fall_replay_v1', monitor_view='large_video_person_records_v1',
                                    smart_assist='smart_assist_v1', android_app=True,
                                    recording_limit_bytes=512 * 1024 * 1024))
                return
            if path == '/api/fall-clips':
                self.send_data(self.server.state.recordings.store.snapshot())
                return
            if path == '/api/fall-playback':
                viewer = query.get('viewer', [''])[0]
                if not VIEWER.fullmatch(viewer):
                    raise ValueError('Invalid playback viewer')
                self.send_data(self.playback_status(viewer, query.get('stop') == ['1']))
                return
            parts = path.strip('/').split('/')
            if len(parts) == 3 and parts[:2] == ['api', 'fall-clips']:
                with self.server.state.recordings.store.pin(parts[2]) as (meta, _):
                    self.send_data(meta)
                return
            if len(parts) >= 3 and parts[0] == 'fall-clips':
                with self.server.state.recordings.store.pin(parts[1]) as (meta, directory):
                    if len(parts) == 3 and parts[2] == 'stream.mjpg':
                        self.replay_stream(meta, directory, query)
                    elif len(parts) == 3 and parts[2] == 'download.zip':
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/zip')
                        self.send_header('Content-Disposition', f'attachment; filename="{meta["id"]}.zip"')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.close_connection = True
                        # Stream ZIP directly: no second recording or temporary disk copy.
                        with zipfile.ZipFile(self.wfile, 'w', compression=zipfile.ZIP_STORED) as archive:
                            archive.writestr('clip.json', json.dumps(meta, ensure_ascii=False, indent=2))
                            for f in meta['frames']:
                                archive.write(directory / f['file'], f['file'])
                    elif len(parts) == 4 and parts[2] == 'frame' and re.fullmatch(r'[0-9]{1,4}\.jpg', parts[3]):
                        index = int(parts[3][:-4])
                        self.send_data((directory / meta['frames'][index]['file']).read_bytes(), 'image/jpeg')
                    elif len(parts) == 3 and parts[2] == 'fall.jpg' and meta['event_frame_index'] is not None:
                        self.send_data((directory / meta['frames'][meta['event_frame_index']]['file']).read_bytes(), 'image/jpeg')
                    else:
                        raise KeyError(path)
                return
            # Recordings are reachable only through validated/pinned routes.
            if 'fall_clips' in unquote(path).lower() or path.startswith('/fall-clips'):
                raise KeyError(path)
            return super().do_GET()
        except (KeyError, IndexError, FileNotFoundError):
            self.send_error(404, 'Recording not found or already evicted')
        except (ValueError, OverflowError):
            self.send_error(409 if path.startswith('/api/fall-clips/') else 400, 'Recording unavailable or invalid parameter')
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            return


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bind', default='0.0.0.0')
    p.add_argument('--udp-port', type=int, default=8080)
    p.add_argument('--source', default='192.168.0.2')
    p.add_argument('--http-bind', default='127.0.0.1')
    p.add_argument('--http-port', type=int, default=8002)
    p.add_argument('--records', type=Path, default=ROOT / 'records')
    p.add_argument('--open-browser', action='store_true')
    args = p.parse_args()
    state = State(args.records)
    stop = threading.Event()
    try:
        server = monitor.ThreadingHTTPServer((args.http_bind, args.http_port), Handler)
    except OSError as error:
        state.close()
        p.error(str(error))
    server.state = state
    thread = threading.Thread(target=monitor.network_receiver,
                              args=(state, args.bind, args.udp_port, args.source, stop), daemon=True)
    thread.start()
    print(f'HTTP_READY http://127.0.0.1:{server.server_port}/monitor.html fall_replay=fall_replay_v1 pre=5s post=5s limit=512MiB', flush=True)
    if args.open_browser:
        webbrowser.open(f'http://127.0.0.1:{server.server_port}/monitor.html')
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        thread.join(timeout=2)
        state.close()


if __name__ == '__main__':
    main()
