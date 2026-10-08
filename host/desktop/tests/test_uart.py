import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import PacketError
from uart import bcd, parse_uart

SHT = "SHT seq=337 status=1 raw=659ab560 t_bcd=00002446 h_bcd=00007085 sample_ms=344373 age_ms=4 seq_hex=00000151 seq_check=00000151"


class UartTests(unittest.TestCase):
    def test_environment_decode(self):
        d = parse_uart(SHT, 1)["data"]
        self.assertEqual(d, dict(sht_valid=True, temperature_c=24.46, humidity_pct=70.85))

    def test_bad_sequence_status_or_age_is_invalid(self):
        for line in (SHT.replace("seq=337", "seq=999"), SHT.replace("status=1", "status=9"),
                     SHT.replace("age_ms=4", "age_ms=-3")):
            with self.subTest(line=line):
                self.assertEqual(parse_uart(line, 2)["data"], {"sht_valid": False})

    def test_bad_bcd_rejected(self):
        with self.assertRaises(PacketError):
            parse_uart(SHT.replace("t_bcd=00002446", "t_bcd=00002a46"), 2)
        self.assertEqual(bcd("80000325", True), -3.25)

    def test_ir_summary_does_not_invent_heatmap(self):
        m = parse_uart("IR seq=1343 min_centi=2415 max_centi=2894 center_centi=2640 publish_ms=343616", 3)
        self.assertEqual(m["type"], "telemetry")
        self.assertNotIn("pixels_centi", m["data"])
        self.assertEqual(m["data"]["ir_max_c"], 28.94)

    def test_camera_fps_from_50mhz_counter(self):
        m = parse_uart("CAM ms=343697 seq=10293 period_ticks=1666663 bad=0 overflow=0 dropped=0 werr=0 rerr=0 underflow=0", 4)
        self.assertAlmostEqual(m["data"]["camera_fps"], 30, places=3)

    def test_service_lines_ignored(self):
        self.assertIsNone(parse_uart("IR_SERVICE steps=100", 5))


if __name__ == "__main__":
    unittest.main()
