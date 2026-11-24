"""Fall-only, bounded JPEG recordings. Ordinary video stays in a RAM prebuffer.

Camera and detection timestamps share the board's monotonic millisecond clock.
Disk IO runs in AsyncRecorder's worker, never in the live UDP/MJPEG path.
"""
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import shutil
import threading
import time
import uuid

LIMIT_BYTES = 512 * 1024 * 1024
PRE_MS = POST_MS = 5000
CLIP_ID = re.compile(r"fall_[0-9a-f]{32}\Z")
FRAME_NAME = re.compile(r"f_([0-9a-f]{16})_([0-9a-f]{8})\.jpg\Z")
RESERVE_BYTES = 256 * 1024


def signed_delta(a, b):
    return ((int(a) - int(b) + 0x80000000) & 0xffffffff) - 0x80000000


class Recorder:
    def __init__(self, root, limit_bytes=LIMIT_BYTES):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.limit = min(int(limit_bytes), LIMIT_BYTES)
        if self.limit < 512 * 1024:
            raise ValueError('Recording capacity must be at least 512 KiB')
        self.lock = threading.RLock()
        self.ring = deque()
        self.ring_bytes = 0
        self.pending = {}
        self.clips = {}
        self.pins = {}
        self.seen = set()
        self.latest = None
        self.last_frame_at = None
        self.dropped = 0
        self.last_error = None
        self.used = sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and not p.is_symlink())
        self._recover()
        self._space(0)

    def _recover(self):
        for directory in self.root.iterdir():
            if not CLIP_ID.fullmatch(directory.name) or not directory.is_dir() or directory.is_symlink():
                continue
            path = directory / 'clip.json'
            try:
                meta = json.loads(path.read_text(encoding='utf8'))
                if meta['id'] != directory.name:
                    continue
                if meta['state'] == 'recording':
                    meta['frames'] = []
                    for p in sorted(directory.glob('f_*.jpg')):
                        match = FRAME_NAME.fullmatch(p.name)
                        if match and not p.is_symlink():
                            ms, source = (int(value, 16) for value in match.groups())
                            meta['frames'].append(dict(file=p.name, ms=ms, source_count=source,
                                                       capture_ms=ms & 0xffffffff))
                    self._describe(meta, 'interrupted', 'service_restarted')
                    self._write(path, self._encode(meta), reserve=False)
                self.clips[meta['id']] = meta
                self.seen.add(meta['event']['event_id'])
            except (ValueError, KeyError, OSError, TypeError):
                # Keep unrecognised user files; never interpret them as recordings.
                continue

    @staticmethod
    def _encode(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf8')

    def _space(self, extra, protect=()):
        protected = set(protect) | set(self.pending) | {k for k, n in self.pins.items() if n}
        for clip in sorted(self.clips.values(), key=lambda m: m['created_at']):
            if self.used + extra <= self.limit:
                return True
            if clip['id'] in protected:
                continue
            directory = self.root / clip['id']
            size = sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
            shutil.rmtree(directory)
            self.used -= size
            del self.clips[clip['id']]
        return self.used + extra <= self.limit

    def _write(self, path, payload, reserve=True):
        reserved = RESERVE_BYTES * len(self.pending) if reserve else 0
        if not self._space(len(payload) + reserved, (path.parent.name,)):
            self.last_error = 'capacity_busy'
            return False
        temporary = path.with_suffix(path.suffix + '.tmp')
        old_size = path.stat().st_size if path.exists() else 0
        try:
            temporary.write_bytes(payload)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        self.used += len(payload) - old_size
        return True

    def _time(self, raw):
        raw = int(raw) & 0xffffffff
        if self.latest is None:
            # One extra epoch permits a negative prewindow near power-on.
            self.latest = 0x100000000 + raw
        value = self.latest + signed_delta(raw, self.latest & 0xffffffff)
        self.latest = max(self.latest, value)
        return value

    def reset(self):
        with self.lock:
            for identifier in list(self.pending):
                self._finish(identifier, 'interrupted', 'board_clock_reset')
            self.ring.clear()
            self.ring_bytes = 0
            self.latest = self.last_frame_at = None

    def frame(self, image, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if (self.latest is not None and signed_delta(image['capture_ms'], self.latest & 0xffffffff) < -2000
                    and self.last_frame_at is not None and now - self.last_frame_at >= 3):
                self.reset()
            stamp = self._time(image['capture_ms'])
            if self.ring and stamp <= self.ring[-1]['ms']:
                return
            frame = {k: image[k] for k in ('capture_ms', 'source_count', 'width', 'height', 'jpeg')}
            frame['ms'] = stamp
            self.ring.append(frame)
            self.ring_bytes += len(frame['jpeg'])
            # Eight seconds include telemetry/inference latency before the trigger arrives.
            while self.ring and (stamp - self.ring[0]['ms'] > 8000 or self.ring_bytes > 128 * 1024 * 1024):
                self.ring_bytes -= len(self.ring.popleft()['jpeg'])
            self.last_frame_at = now
            for identifier, meta in list(self.pending.items()):
                if meta['start_ms'] <= stamp <= meta['end_ms']:
                    self._save_frame(meta, frame)
                if stamp >= meta['end_ms']:
                    self._finish(identifier)

    def trigger(self, event, now=None):
        now = time.monotonic() if now is None else now
        if event.get('type') != 'fall' or event.get('source') != 'board':
            return None
        with self.lock:
            key = event['event_id']
            if key in self.seen:
                return None
            self.seen.add(key)
            if len(self.pending) >= 16:
                self.last_error = 'too_many_pending_events'
                return None
            raw = event['capture_ms']
            age = signed_delta(event['device_ms'], raw)
            basis = 'detection_capture_ms'
            if not 0 <= age <= 10000:
                raw = event['device_ms']
                basis = 'telemetry_device_ms_fallback'
                age = 0
            anchor = self._time(raw)
            identifier = 'fall_' + uuid.uuid4().hex
            meta = dict(id=identifier, state='recording', created_at=datetime.now(timezone.utc).isoformat(),
                        event=json.loads(json.dumps(event)), clock_basis=basis,
                        event_ms=anchor, start_ms=anchor - PRE_MS, end_ms=anchor + POST_MS,
                        requested_pre_ms=PRE_MS, requested_post_ms=POST_MS,
                        width=None, height=None, frames=[], dropped_frames=0)
            self.pending[identifier] = meta
            directory = self.root / identifier
            directory.mkdir()
            if not self._write(directory / 'clip.json', self._encode(meta)):
                del self.pending[identifier]
                directory.rmdir()
                return None
            self.clips[identifier] = meta
            # Receipt time is used only to stop waiting if the source disappears.
            meta['_deadline'] = now + max(0, POST_MS - age) / 1000 + 2
            for frame in self.ring:
                if meta['start_ms'] <= frame['ms'] <= meta['end_ms']:
                    self._save_frame(meta, frame)
            if self.ring and self.ring[-1]['ms'] >= meta['end_ms']:
                self._finish(identifier)
            return identifier

    def _save_frame(self, meta, frame):
        if meta['frames'] and frame['ms'] <= meta['frames'][-1]['ms']:
            return
        if len(meta['frames']) >= 1000:
            meta['dropped_frames'] += 1
            return
        name = f"f_{frame['ms']:016x}_{frame['source_count']:08x}.jpg"
        if self._write(self.root / meta['id'] / name, frame['jpeg']):
            meta['frames'].append(dict(file=name, ms=frame['ms'], capture_ms=frame['capture_ms'],
                                       source_count=frame['source_count']))
            meta['width'], meta['height'] = frame['width'], frame['height']
        else:
            meta['dropped_frames'] += 1

    @staticmethod
    def _describe(meta, state, reason=None):
        frames = meta['frames']
        meta['state'] = state
        meta['reason'] = reason
        meta['frame_count'] = len(frames)
        if frames:
            first, last = frames[0]['ms'], frames[-1]['ms']
            meta['duration_ms'] = last - first
            meta['actual_pre_ms'] = max(0, meta['event_ms'] - first)
            meta['actual_post_ms'] = max(0, last - meta['event_ms'])
            differences = [b['ms'] - a['ms'] for a, b in zip(frames, frames[1:])]
            cadence = sorted(differences)[len(differences) // 2] if differences else 33
            tolerance = max(40, min(250, cadence * 2))
            meta['pre_complete'] = first <= meta['start_ms'] + tolerance
            meta['post_complete'] = last >= meta['end_ms'] - tolerance
            meta['gaps_over_500ms'] = sum(gap > 500 for gap in differences)
            meta['event_frame_index'] = min(range(len(frames)), key=lambda i: abs(frames[i]['ms'] - meta['event_ms']))
            meta['event_frame_delta_ms'] = frames[meta['event_frame_index']]['ms'] - meta['event_ms']
            meta['fps'] = round((len(frames) - 1) * 1000 / (last - first), 2) if last > first else 0
        else:
            meta.update(duration_ms=0, actual_pre_ms=0, actual_post_ms=0, pre_complete=False,
                        post_complete=False, gaps_over_500ms=0, event_frame_index=None,
                        event_frame_delta_ms=None, fps=0)
        meta['complete'] = bool(state == 'ready' and meta['pre_complete'] and meta['post_complete']
                                and not meta['gaps_over_500ms'] and not meta['dropped_frames'])

    def _finish(self, identifier, state='ready', reason=None):
        meta = self.pending.pop(identifier)
        meta.pop('_deadline', None)
        self._describe(meta, state, reason)
        if not self._write(self.root / identifier / 'clip.json', self._encode(meta), reserve=False):
            self.last_error = 'metadata_write_failed'

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            for identifier, meta in list(self.pending.items()):
                if now >= meta['_deadline']:
                    self._finish(identifier, 'interrupted', 'source_timeout')

    def close(self):
        with self.lock:
            for identifier in list(self.pending):
                self._finish(identifier, 'interrupted', 'service_stopped')

    def snapshot(self):
        with self.lock:
            clips = []
            for meta in sorted(self.clips.values(), key=lambda m: m['created_at'], reverse=True):
                view = {k: v for k, v in meta.items() if k not in ('frames', '_deadline')}
                if meta['state'] == 'recording':
                    view['frame_count'] = len(meta['frames'])
                clips.append(view)
            return dict(version='fall_replay_v1', clips=clips, storage_bytes=self.used,
                        limit_bytes=self.limit, pending=len(self.pending), dropped_frames=self.dropped,
                        error=self.last_error, pre_ms=PRE_MS, post_ms=POST_MS, normal_video_saved=False)

    @contextmanager
    def pin(self, identifier):
        if not CLIP_ID.fullmatch(identifier):
            raise KeyError(identifier)
        with self.lock:
            meta = self.clips[identifier]
            if meta['state'] == 'recording':
                raise ValueError('Recording still in progress')
            self.pins[identifier] = self.pins.get(identifier, 0) + 1
            frozen = json.loads(json.dumps(meta))
        try:
            yield frozen, self.root / identifier
        finally:
            with self.lock:
                self.pins[identifier] -= 1


class AsyncRecorder:
    def __init__(self, root):
        self.store = Recorder(root)
        self.condition = threading.Condition()
        self.queue = deque()
        self.queued_bytes = 0
        self.stopping = False
        self.thread = threading.Thread(target=self._run, name='fall-recording-writer', daemon=True)
        self.thread.start()

    def offer(self, kind, payload=None, now=None):
        size = len(payload['jpeg']) if kind == 'frame' else 0
        with self.condition:
            if self.stopping:
                return
            if size and (self.queued_bytes + size > 64 * 1024 * 1024 or len(self.queue) >= 1000):
                self.store.dropped += 1
                return
            self.queued_bytes += size
            self.queue.append((kind, payload, time.monotonic() if now is None else now, size))
            self.condition.notify()

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.queue or self.stopping, timeout=.25)
                if not self.queue:
                    if self.stopping:
                        break
                    item = None
                else:
                    item = self.queue.popleft()
                    self.queued_bytes -= item[3]
            try:
                if item:
                    kind, payload, now, _ = item
                    if kind == 'frame': self.store.frame(payload, now)
                    elif kind == 'event': self.store.trigger(payload, now)
                    elif kind == 'reset': self.store.reset()
                else:
                    self.store.tick()
            except Exception as error:
                self.store.last_error = str(error)
        self.store.close()

    def close(self):
        with self.condition:
            self.stopping = True
            self.condition.notify_all()
        self.thread.join(timeout=15)
