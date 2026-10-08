"""Draft v1 packets shared by the desktop and the future board transport."""
import base64
import json
import math

MAX_LINE_BYTES = 1024 * 1024


class PacketError(ValueError):
    pass


def integer(value, name, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PacketError(f"{name} 必须是 {minimum}..{maximum} 内的整数")
    return value


def number(value, name, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise PacketError(f"{name} 超出范围")
    return value


def string(value, name, maximum=128):
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise PacketError(f"{name} 必须是非空字符串")
    return value


def validate(packet):
    if not isinstance(packet, dict):
        raise PacketError("消息必须是 JSON 对象")
    if type(packet.get("version")) is not int or packet["version"] != 1:
        raise PacketError("只接受 version=1")
    for field in ("device_id", "boot_id"):
        string(packet.get(field), field)
    integer(packet.get("seq"), "seq")
    integer(packet.get("timestamp_ms"), "timestamp_ms", maximum=2**32 - 1)
    kind = packet.get("type")
    data = packet.get("data")
    if not isinstance(data, dict):
        raise PacketError("data 必须是对象")
    if kind == "telemetry":
        ranges = {
            "temperature_c": (-40, 125), "humidity_pct": (0, 100),
            "camera_fps": (0, 240), "ir_min_c": (-40, 300),
            "ir_max_c": (-40, 300), "ir_center_c": (-40, 300),
        }
        for field, limits in ranges.items():
            if data.get(field) is not None:
                number(data[field], field, *limits)
        for field in ("sht_valid", "ir_valid"):
            if field in data and type(data[field]) is not bool:
                raise PacketError(f"{field} 必须是布尔值")
        for field in ("camera_errors", "camera_frame_id"):
            if field in data:
                integer(data[field], field)
    elif kind == "inference":
        integer(data.get("frame_id"), "frame_id")
        if type(data.get("valid")) is not bool:
            raise PacketError("valid 必须是布尔值")
        if data["valid"]:
            number(data.get("person_score"), "person_score", 0, 1)
            number(data.get("inference_ms"), "inference_ms", 0, 1_000_000)
    elif kind == "thermal":
        if type(data.get("width")) is not int or type(data.get("height")) is not int or (data["width"], data["height"]) != (32, 24):
            raise PacketError("热图尺寸必须是 32×24")
        pixels = data.get("pixels_centi")
        if not isinstance(pixels, list) or len(pixels) != 768:
            raise PacketError("热图必须包含 768 个按行排列的温度")
        for value in pixels:
            if value is not None:
                integer(value, "pixels_centi", -4000, 30000)
    elif kind == "video":
        integer(data.get("frame_id"), "frame_id")
        encoded = string(data.get("jpeg_base64"), "jpeg_base64", MAX_LINE_BYTES)
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise PacketError("jpeg_base64 编码错误") from exc
        if not raw.startswith(b"\xff\xd8"):
            raise PacketError("预览只接受 JPEG")
    elif kind == "event":
        string(data.get("event_id"), "event_id")
        string(data.get("event_type"), "event_type", 64)
        if data.get("confidence") is not None:
            number(data["confidence"], "confidence", 0, 1)
        if data.get("frame_id") is not None:
            integer(data["frame_id"], "frame_id")
    else:
        raise PacketError(f"未知消息类型：{kind}")
    return packet


def reject_constant(name):
    raise PacketError("不接受 NaN/Infinity")


def decode_line(line):
    if len(line) > MAX_LINE_BYTES:
        raise PacketError("单条消息超过 1 MiB")
    try:
        packet = json.loads(line.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PacketError("无效 UTF-8/JSON 消息") from exc
    return validate(packet)


class LineDecoder:
    """TCP byte stream: packet boundaries are newlines, not recv() calls."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk):
        self.buffer.extend(chunk)
        result = []
        while b"\n" in self.buffer:
            end = self.buffer.index(b"\n")
            if end > MAX_LINE_BYTES:
                self.buffer.clear()
                raise PacketError("单条消息超过 1 MiB")
            line = bytes(self.buffer[:end]).rstrip(b"\r")
            del self.buffer[:end + 1]
            if line:
                result.append(decode_line(line))
        if len(self.buffer) > MAX_LINE_BYTES:
            self.buffer.clear()
            raise PacketError("未结束的消息超过 1 MiB")
        return result


def packet(kind, seq, data, *, device="demo-ti60", boot="demo", timestamp_ms=0):
    return validate(dict(version=1, type=kind, device_id=device, boot_id=boot,
                         seq=seq, timestamp_ms=timestamp_ms, data=data))
