import csv
import json
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app import MonitorWindow, STALE_SECONDS
from protocol import packet

APP = QApplication.instance() or QApplication([])


def spin(until, seconds=2):
    end = time.monotonic() + seconds
    while not until() and time.monotonic() < end:
        APP.processEvents()
        time.sleep(.005)
    if not until():
        raise AssertionError("Qt operation did not finish")


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.window = MonitorWindow()

    def tearDown(self):
        self.window.close()
        APP.processEvents()

    def test_real_tcp_fragmentation_disconnect_and_reconnect(self):
        self.window.port.setValue(18091)
        self.window.toggle_listening()
        self.assertTrue(self.window.server.isListening(), self.window.server.errorString())
        port = self.window.server.serverPort()
        msg = (json.dumps(packet("telemetry", 1, {"temperature_c": 24.5, "sht_valid": True},
                                  device="test", boot="one")) + "\n").encode()
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            spin(lambda: self.window.client is not None)
            client.sendall(msg[:8])
            APP.processEvents()
            self.assertEqual(self.window.received, 0)
            client.sendall(msg[8:])
            spin(lambda: self.window.received == 1)
            self.assertEqual(self.window.cards["temperature_c"].text(), "24.50 °C")
        spin(lambda: self.window.client is None)
        with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
            client.sendall(msg)
            spin(lambda: self.window.received == 2)

    def test_stale_fields_not_refreshed_by_unrelated_camera_packet(self):
        self.window.apply_packet(packet("telemetry", 1, {"temperature_c": 25}))
        self.window.values["temperature_c"] = (25, time.monotonic()-STALE_SECONDS-1)
        self.window.apply_packet(packet("telemetry", 2, {"camera_fps": 30}))
        self.assertEqual(self.window.cards["temperature_c"].text(), "—")
        self.assertEqual(self.window.cards["camera_fps"].text(), "30.00 fps")
        self.window.apply_packet(packet("telemetry", 3, {"temperature_c": 25, "sht_valid": False}))
        self.assertEqual(self.window.cards["temperature_c"].text(), "—")

    def test_duplicate_sequence_and_new_boot(self):
        first = packet("telemetry", 1, {"humidity_pct": 55})
        self.window.apply_packet(first)
        self.window.apply_packet(first)
        self.assertEqual(self.window.received, 1)
        self.assertEqual(self.window.duplicates, 1)
        self.window.apply_packet(packet("telemetry", 1, {"camera_fps": 30}, boot="new-boot"))
        self.assertNotIn("humidity_pct", self.window.values)

    def test_event_dedup_ack_and_csv_preserve_source(self):
        self.window.mode = "模拟"
        event = {"event_id": "e1", "event_type": "演示报警", "confidence": .8, "frame_id": 42}
        self.window.apply_packet(packet("event", 1, event))
        self.window.apply_packet(packet("event", 2, event))
        self.assertEqual(len(self.window.events), 1)
        self.window.table.selectRow(0)
        self.window.acknowledge()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"events.csv"
            self.window.export_events(path)
            with path.open(encoding="utf-8-sig", newline="") as f:
                records = list(csv.DictReader(f))
            self.assertEqual(records[0]["source"], "模拟")
            self.assertEqual(records[0]["acknowledged"], "True")
            self.assertEqual(records[0]["frame_id"], "42")

    def test_demo_contains_explicit_source_and_actual_display_pixels(self):
        self.window.start_demo()
        self.assertIn("模拟", self.window.source_label.text())
        self.assertFalse(self.window.video.image.isNull())
        self.assertEqual(self.window.thermal.image.size().width(), 32)
        self.assertEqual(self.window.events[0]["source"], "模拟")

    def test_uart_replay_does_not_create_video_or_thermal_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"input.log"
            path.write_text("IR seq=1 min_centi=2400 max_centi=3200 center_centi=2800 publish_ms=100\n",
                            encoding="utf-8")
            self.window.load_replay(path)
            self.window.replay_tick()
            self.assertEqual(self.window.mode, "历史回放")
            self.assertIsNone(self.window.video.image)
            self.assertIsNone(self.window.thermal.image)
            self.assertEqual(self.window.cards["ir_center_c"].text(), "28.00 °C")


if __name__ == "__main__":
    unittest.main()
