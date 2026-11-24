"""TCAM1601 receiver; bounded complete-frame assembly, standard library only."""
import argparse
from collections import OrderedDict
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import os
from pathlib import Path
import socket
import struct
import time
import zlib

WIDTH, HEIGHT, CHUNKS, CHUNK_BYTES = 160, 90, 15, 960
HEADER = struct.Struct('>8sIIHHHHHHB3s')
MAGIC = b'TCAM1601'
COLOR_MAGIC = b'TCAM5651'
HARDWARE_MAGIC=b'TCAM6401'
HARDWARE_HEADER=struct.Struct('>8sIIHHHHIHBB')
PROTOCOLS = {MAGIC:(15,960,1),COLOR_MAGIC:(20,1440,2),HARDWARE_MAGIC:(320,1440,2)}


def parse_packet(data):
    if len(data)<HEADER.size:raise ValueError('Truncated camera header')
    if data[:8]==HARDWARE_MAGIC:
        magic,frame,ms,width,height,index,count,offset,length,fmt,reserved=HARDWARE_HEADER.unpack_from(data)
        reserved=bytes([reserved])*3
    else:
        magic, frame, ms, width, height, index, count, offset, length, fmt, reserved = HEADER.unpack_from(data)
    expected=PROTOCOLS.get(magic)
    if (expected is None or (width,height)!=((640,360) if magic==HARDWARE_MAGIC else (WIDTH,HEIGHT)) or (count,length,fmt)!=expected
            or len(data)!=HEADER.size+length or index>=count or offset!=index*length or reserved!=b'\0\0\0'):
        raise ValueError('Invalid camera header or pixel length')
    return frame, ms, index, data[HEADER.size:]


@dataclass(frozen=True)
class Frame:
    frame: int
    ms: int
    pixels: bytes
    format: int = 1
    width: int = WIDTH
    height: int = HEIGHT


class Reassembler:
    """Tolerate reordering and identical duplicates; never publish partial images."""
    def __init__(self, timeout=3.0, max_frames=4):
        self.timeout, self.max_frames = timeout, max_frames
        self.pending = OrderedDict()
        self.finished = OrderedDict()
        self.last_published = None
        self.expired = self.rejected = self.duplicates = 0

    def expire(self, now):
        for key, (started, _) in list(self.pending.items()):
            if now - started >= self.timeout:
                del self.pending[key]
                self.expired += 1
        for key, finished_at in list(self.finished.items()):
            if now - finished_at >= self.timeout:
                del self.finished[key]

    def add(self, data, now=None):
        now = time.monotonic() if now is None else now
        self.expire(now)
        frame, ms, index, pixels = parse_packet(data)
        magic=data[:8];count,_,fmt=PROTOCOLS[magic]
        key = (frame, ms, magic)
        if key in self.finished:
            self.duplicates += 1
            return None
        if self.last_published:
            old_frame, old_ms, published_at = self.last_published
            delta_frame = (frame - old_frame) & 0xffffffff
            delta_ms = (ms - old_ms) & 0xffffffff
            newer = 0 < delta_frame < 0x80000000 and delta_ms < 0x80000000
            # Permit counter resets after silence, but suppress ordinary late
            # frames while a newer stream is being published.
            if not newer and now - published_at < self.timeout:
                self.rejected += 1
                return None
        if key not in self.pending:
            if len(self.pending) >= self.max_frames:
                self.pending.popitem(last=False)
                self.expired += 1
            self.pending[key] = (now, {})
        _, parts = self.pending[key]
        if index in parts:
            if parts[index] != pixels:
                del self.pending[key]
                self.finished[key] = now
                while len(self.finished) > 64:
                    self.finished.popitem(last=False)
                self.rejected += 1
            else:
                self.duplicates += 1
            return None
        parts[index] = pixels
        if len(parts) != count:
            return None
        image = b''.join(parts[i] for i in range(count))
        del self.pending[key]
        self.finished[key] = now
        while len(self.finished) > 64:
            self.finished.popitem(last=False)
        self.last_published = (frame, ms, now)
        return Frame(frame, ms, image, fmt,*struct.unpack_from('>HH',data,16))


def png_gray(width, height, pixels):
    if len(pixels) != width * height:
        raise ValueError('Pixel length mismatch')
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    scan = b''.join(b'\0' + pixels[y * width:(y + 1) * width] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(scan)) + chunk(b'IEND', b''))


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(data)
    for attempt in range(6):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(.02)


FIELDS = ['received_at', 'source_ip', 'source_port', 'kind', 'display_frame_id',
          'device_time_ms', 'width', 'height', 'format', 'preview_path']


def frame_image(frame):
    from PIL import Image
    if frame.format==2:
        return Image.frombytes('RGB',(frame.width,frame.height),frame.pixels,'raw','BGR;16')
    return Image.frombytes('L',(frame.width,frame.height),frame.pixels)


def frame_png(frame):
    buffer=io.BytesIO();frame_image(frame).save(buffer,format='PNG',compress_level=1)
    return buffer.getvalue()


def frame_jpeg(frame):
    buffer=io.BytesIO();frame_image(frame).convert('RGB').save(buffer,format='JPEG',quality=88,subsampling=0)
    return buffer.getvalue()


def publish(frame, directory, csv_path, peer):
    # Compatibility snapshots/CSV are saved at most once per second by monitor;
    # the high-rate MJPEG path uses only the newest frame held in memory.
    from PIL import Image
    image=frame_image(frame);native=frame_png(frame)
    atomic_write(directory / 'latest_camera_native.png',native)
    preview=directory/'latest_camera_preview.png';buffer=io.BytesIO()
    image.resize((640,360),Image.Resampling.BILINEAR).save(buffer,format='PNG',compress_level=1)
    atomic_write(preview,buffer.getvalue())
    row=dict(zip(FIELDS,[datetime.now(timezone.utc).isoformat(),peer[0],peer[1],
             'CAMERA_THUMB',frame.frame,frame.ms,frame.width,frame.height,'rgb565' if frame.format==2 else 'gray8',str(preview)]))
    new=not csv_path.exists();buffer=io.StringIO(newline='')
    writer=csv.DictWriter(buffer,fieldnames=FIELDS,quoting=csv.QUOTE_ALL)
    if new:writer.writeheader()
    writer.writerow(row)
    with csv_path.open('a',encoding='utf8',newline='') as file:file.write(buffer.getvalue())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='192.168.0.3')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--source-ip', default='192.168.0.2')
    parser.add_argument('--source-port', type=int, default=8080)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'web')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    csv_path = args.output / datetime.now().strftime('camera_%Y%m%d_%H%M%S.csv')
    assembler = Reassembler()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
        listener.bind((args.bind, args.port))
        listener.settimeout(.5)
        print(f'Listening on {args.bind}:{args.port}; TCAM1601 / 160x90 gray8 / 15 chunks per frame.', flush=True)
        print(f'Preview: {args.output / "latest_camera_preview.png"}\nCSV: {csv_path}', flush=True)
        try:
            while True:
                try:
                    data, peer = listener.recvfrom(65535)
                except socket.timeout:
                    assembler.expire(time.monotonic())
                    continue
                if peer != (args.source_ip, args.source_port):
                    continue
                try:
                    frame = assembler.add(data)
                except ValueError as error:
                    print(f'Ignored packet: {error}', flush=True)
                    continue
                if frame is not None:
                    publish(frame, args.output, csv_path, peer)
                    print(f'[CAMERA] frame={frame.frame} time_ms={frame.ms} thumbnail=160x90 saved; '
                          f'expired={assembler.expired} rejected={assembler.rejected}', flush=True)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
