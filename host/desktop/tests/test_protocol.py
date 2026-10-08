import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import MAX_LINE_BYTES, LineDecoder, PacketError, decode_line, packet


class ProtocolTests(unittest.TestCase):
    def line(self):
        return (json.dumps(packet("telemetry", 1, {"temperature_c": 24.5})) + "\n").encode()

    def test_fragmented_and_coalesced_tcp(self):
        stream = LineDecoder()
        line = self.line()
        self.assertEqual(stream.feed(line[:12]), [])
        self.assertEqual(len(stream.feed(line[12:] + line)), 2)
        self.assertEqual(stream.buffer, b"")

    def test_bad_json_and_nonfinite(self):
        for raw in (b"{x}", b"\xff", b'{"data":NaN}', b'{"data":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(PacketError):
                decode_line(raw)

    def test_partial_thermal_frame_rejected(self):
        with self.assertRaises(PacketError):
            packet("thermal", 1, dict(width=32, height=24, pixels_centi=[2400] * 767))

    def test_bad_pixels_and_nullable_pixels(self):
        data = dict(width=32, height=24, pixels_centi=[None] * 768)
        self.assertEqual(packet("thermal", 1, data)["data"]["pixels_centi"][0], None)
        for value in (True, float("nan"), 40000):
            with self.subTest(value=value), self.assertRaises(PacketError):
                packet("thermal", 2, dict(data, pixels_centi=[value] * 768))

    def test_ranges_and_bool_as_number(self):
        for data in ({"humidity_pct": 101}, {"camera_fps": True}, {"temperature_c": float("inf")}):
            with self.subTest(data=data), self.assertRaises(PacketError):
                packet("telemetry", 1, data)
        self.assertIsNone(packet("telemetry", 2, {"temperature_c": None})["data"]["temperature_c"])

    def test_invalid_inference_does_not_require_scores(self):
        packet("inference", 1, {"frame_id": 10, "valid": False})
        with self.assertRaises(PacketError):
            packet("inference", 2, {"frame_id": 10, "valid": True, "person_score": 1.5, "inference_ms": 100})

    def test_oversized_tcp_line(self):
        with self.assertRaises(PacketError):
            LineDecoder().feed(b"x" * (MAX_LINE_BYTES + 1))

    def test_rejects_fake_jpeg(self):
        with self.assertRaises(PacketError):
            packet("video", 1, dict(frame_id=1, jpeg_base64=base64.b64encode(b"PNG").decode()))

    def test_unknown_version_and_bool_seq(self):
        msg = packet("telemetry", 1, {})
        for key, value in (("version", 2), ("seq", True), ("timestamp_ms", -1)):
            with self.subTest(key=key), self.assertRaises(PacketError):
                decode_line(json.dumps(dict(msg, **{key: value})).encode())


if __name__ == "__main__":
    unittest.main()
