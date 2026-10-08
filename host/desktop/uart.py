"""Read existing UART text as historical telemetry; no serial writes."""
import re

from protocol import PacketError, packet


def bcd(text, signed=False):
    value = int(text, 16)
    if value & ~(0x800FFFFF if signed else 0xFFFFF):
        raise ValueError("BCD reserved bits")
    digits = [(value >> (4 * i)) & 15 for i in range(5)]
    if any(d > 9 for d in digits):
        raise ValueError("BCD digit")
    result = sum(d * 10**i for i, d in enumerate(digits)) / 100
    return -result if signed and value & 0x80000000 else result


def parse_uart(line, seq, boot="replay"):
    fields = dict(re.findall(r"(\w+)=(\S+)", line))
    try:
        if line.startswith("CAM "):
            ticks = int(fields["period_ticks"])
            if ticks <= 0:
                raise ValueError("bad frame period")
            data = {"camera_fps": 50_000_000 / ticks,
                    "camera_frame_id": int(fields["seq"]),
                    "camera_errors": sum(int(fields[k]) for k in
                                         ("bad", "overflow", "dropped", "werr", "rerr", "underflow"))}
            stamp = int(fields["ms"])
        elif line.startswith("SHT "):
            valid = (int(fields["status"]) == 1 and
                     int(fields["seq"]) == int(fields["seq_hex"], 16) == int(fields["seq_check"], 16) and
                     0 <= int(fields["age_ms"]) <= 3000 and
                     0 <= int(fields["sample_ms"]) < 2**32)
            data = {"sht_valid": False}
            if valid:
                data.update(sht_valid=True, temperature_c=bcd(fields["t_bcd"], True),
                            humidity_pct=bcd(fields["h_bcd"]))
            stamp = max(0, int(fields["sample_ms"])) % 2**32
        elif line.startswith("IR "):
            data = {"ir_valid": True, "ir_min_c": int(fields["min_centi"]) / 100,
                    "ir_max_c": int(fields["max_centi"]) / 100,
                    "ir_center_c": int(fields["center_centi"]) / 100}
            stamp = int(fields["publish_ms"])
        else:
            return None
        return packet("telemetry", seq, data, device="uart-log", boot=boot, timestamp_ms=stamp)
    except (ValueError, KeyError, PacketError) as exc:
        raise PacketError(f"串口记录无效：{exc}") from exc
