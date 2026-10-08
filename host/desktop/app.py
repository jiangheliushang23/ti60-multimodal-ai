"""Windows desktop monitor. Demo/replay/TCP are explicit, separate data sources."""
import argparse
import base64
import csv
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QFontDatabase
from PySide6.QtNetwork import QHostAddress, QTcpServer
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QFileDialog)

from protocol import LineDecoder, PacketError, decode_line, packet
from uart import parse_uart

STALE_SECONDS = 5


def heat_color(ratio):
    stops = [(19, 32, 67), (26, 156, 193), (236, 199, 71), (231, 77, 67)]
    t = max(0, min(1, ratio)) * 3
    i = min(2, int(t))
    return QColor(*(round(stops[i][c] + (stops[i+1][c] - stops[i][c]) * (t-i)) for c in range(3)))


class ImagePanel(QWidget):
    def __init__(self, title, placeholder):
        super().__init__()
        self.title, self.placeholder = title, placeholder
        self.image = None
        self.last_arrival = 0
        self.caption = ""
        self.setMinimumSize(280, 250)

    def clear(self):
        self.image = None
        self.caption = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101d2d"))
        painter.setPen(QColor("#dae7f2"))
        painter.setFont(QFont("Microsoft YaHei", 11))
        painter.drawText(QRect(16, 8, self.width()-32, 32), Qt.AlignVCenter, self.title)
        target = QRect(16, 49, self.width()-32, self.height()-87)
        if self.image is None or time.monotonic()-self.last_arrival > STALE_SECONDS:
            painter.setPen(QColor("#8fa2b7"))
            text = "数据已过期，等待新数据" if self.image is not None else self.placeholder
            painter.drawText(target, Qt.AlignCenter | Qt.TextWordWrap, text)
        else:
            size = self.image.size().scaled(target.size(), Qt.KeepAspectRatio)
            area = QRect(0, 0, size.width(), size.height())
            area.moveCenter(target.center())
            painter.drawImage(area, self.image)
        painter.setPen(QColor("#8fa2b7"))
        painter.setFont(QFont("Microsoft YaHei", 9))
        painter.drawText(QRect(16, self.height()-33, self.width()-32, 25), Qt.AlignVCenter, self.caption)


class MonitorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Offscreen Qt does not discover Windows fonts; use the installed fonts.
        if "Microsoft YaHei" not in QFontDatabase.families():
            for name in ("msyh.ttc", "msyhbd.ttc"):
                font = Path("C:/Windows/Fonts") / name
                if font.exists():
                    QFontDatabase.addApplicationFont(str(font))
        self.setWindowTitle("Ti60 多模态终端 · 桌面监控")
        self.resize(1380, 860)
        self.mode = "未连接"
        self.identity = None
        self.sequences = {}
        self.values = {}
        self.events = []
        self.received = self.rejected = self.duplicates = 0
        self.client = None
        self.replay_file = None
        self.replay_seq = 0
        self.demo_count = 0
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self.accept_client)
        self.demo_timer = QTimer(self)
        self.demo_timer.setInterval(200)
        self.demo_timer.timeout.connect(self.demo_tick)
        self.replay_timer = QTimer(self)
        self.replay_timer.setInterval(100)
        self.replay_timer.timeout.connect(self.replay_tick)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.refresh)
        self.build_ui()
        self.refresh_timer.start()
        self.refresh()

    def build_ui(self):
        self.setStyleSheet("""
            QWidget { background: #0b1422; color: #dbe7f2; font-family: 'Microsoft YaHei'; font-size: 13px; }
            QLabel { background: transparent; }
            QFrame#card { background: #142235; border: 1px solid #24364c; border-radius: 8px; }
            QPushButton { background: #1b334b; border: 1px solid #35546e; border-radius: 5px; padding: 8px 13px; }
            QPushButton:hover { background: #254964; }
            QLineEdit, QSpinBox { background: #142235; border: 1px solid #35546e; border-radius: 4px; padding: 5px; }
            QTableWidget { background: #101d2d; alternate-background-color: #142235; gridline-color: #25364b; border: 0; }
            QHeaderView::section { background: #1a2b40; color: #a7bdd2; border: 0; padding: 8px; }
        """)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        title = QLabel("Ti60  /  多模态终端监控")
        title.setStyleSheet("font-size: 25px; font-weight: 600;")
        self.source_label = QLabel("未连接开发板")
        self.source_label.setStyleSheet("color: #ffc76a; font-size: 14px;")
        heading.addWidget(title)
        heading.addStretch()
        heading.addWidget(self.source_label)
        layout.addLayout(heading)
        controls = QHBoxLayout()
        demo = QPushButton("模拟演示")
        demo.clicked.connect(self.start_demo)
        replay = QPushButton("打开日志 / JSONL")
        replay.clicked.connect(self.choose_replay)
        controls.addWidget(demo)
        controls.addWidget(replay)
        controls.addStretch()
        controls.addWidget(QLabel("监听地址"))
        self.address = QLineEdit("127.0.0.1")
        self.address.setMaximumWidth(150)
        controls.addWidget(self.address)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(9001)
        controls.addWidget(self.port)
        self.listen_button = QPushButton("启动 TCP 接收")
        self.listen_button.clicked.connect(self.toggle_listening)
        controls.addWidget(self.listen_button)
        layout.addLayout(controls)
        self.note = QLabel("等待数据源。串口日志没有视频像素与完整热图；模拟演示均为合成数据。")
        self.note.setStyleSheet("color: #8fa2b7;")
        layout.addWidget(self.note)
        cards = QHBoxLayout()
        self.cards = {}
        for key, label in (("temperature_c", "环境温度"), ("humidity_pct", "相对湿度"),
                           ("ir_center_c", "红外中心温度"), ("camera_fps", "采集帧率 · 设备上报"),
                           ("person_score", "人员置信度"), ("inference_ms", "推理耗时")):
            frame = QFrame()
            frame.setObjectName("card")
            inner = QVBoxLayout(frame)
            inner.addWidget(QLabel(label))
            value = QLabel("—")
            value.setStyleSheet("font-size: 27px; font-weight: 600; color: #5ce0ce;")
            inner.addWidget(value)
            self.cards[key] = value
            cards.addWidget(frame)
        layout.addLayout(cards)
        images = QHBoxLayout()
        self.video = ImagePanel("摄像头预览", "尚未收到视频像素")
        self.thermal = ImagePanel("红外热图 · 32 × 24", "尚未收到完整温度矩阵")
        images.addWidget(self.video, 2)
        images.addWidget(self.thermal, 1)
        layout.addLayout(images, 1)
        actions = QHBoxLayout()
        actions.addWidget(QLabel("事件记录   /   仅由收到的事件消息生成"))
        actions.addStretch()
        ack = QPushButton("确认选中记录 · 仅本机")
        ack.clicked.connect(self.acknowledge)
        export = QPushButton("导出事件 CSV")
        export.clicked.connect(self.choose_export)
        actions.addWidget(ack)
        actions.addWidget(export)
        layout.addLayout(actions)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["PC 接收时间", "设备时间/ms", "事件", "置信度", "关联帧号", "数据来源", "本机确认"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(145)
        self.table.setMaximumHeight(205)
        layout.addWidget(self.table)
        self.footer = QLabel("")
        self.footer.setStyleSheet("color: #8fa2b7;")
        layout.addWidget(self.footer)
        self.setCentralWidget(root)

    def clear_measurements(self):
        self.values.clear()
        self.sequences.clear()
        self.identity = None
        self.video.clear()
        self.thermal.clear()

    def stop_source(self):
        self.demo_timer.stop()
        self.replay_timer.stop()
        if self.replay_file:
            self.replay_file.close()
            self.replay_file = None
        self.server.close()
        if self.client:
            sock, self.client = self.client, None
            sock.abort()
            sock.deleteLater()
        self.listen_button.setText("启动 TCP 接收")
        self.clear_measurements()

    def start_demo(self):
        self.stop_source()
        self.mode = "模拟"
        self.demo_count = 0
        self.source_label.setText("模拟演示 · 未连接开发板")
        self.note.setText("视频、温度、AI 分数和事件均为合成数据，用于验证桌面界面与接口。")
        self.demo_tick()
        self.demo_timer.start()

    def toggle_listening(self):
        if self.server.isListening():
            self.stop_source()
            self.mode = "未连接"
            self.source_label.setText("监听已停止")
            self.refresh()
            return
        address = QHostAddress(self.address.text().strip())
        if address.isNull():
            self.note.setText("请输入有效的本机 IPv4/IPv6 地址。")
            return
        self.stop_source()
        if not self.server.listen(address, self.port.value()):
            self.note.setText("监听失败：" + self.server.errorString())
            return
        self.mode = "TCP"
        self.listen_button.setText("停止 TCP 接收")
        self.source_label.setText(f"TCP {self.address.text()}:{self.server.serverPort()} · 等待设备")
        self.note.setText("通信草案 v1：JSONL 接收；同一时刻显示一台设备。真实网络链路仍待队友联调。")

    def accept_client(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            if self.client is not None:
                sock.abort()
                sock.deleteLater()
                continue
            self.client = sock
            self.decoder = LineDecoder()
            sock.setReadBufferSize(2 * 1024 * 1024)
            sock.readyRead.connect(self.receive_bytes)
            sock.disconnected.connect(lambda s=sock: self.disconnected(s))
            self.clear_measurements()
            self.source_label.setText("TCP 已连接 · 等待有效数据")

    def disconnected(self, sock):
        if sock is self.client:
            self.client = None
            self.source_label.setText("TCP 已断开 · 等待重连")
            # The last values remain visible until stale; no zero is substituted.
        sock.deleteLater()

    def receive_bytes(self):
        if not self.client:
            return
        try:
            for msg in self.decoder.feed(bytes(self.client.readAll())):
                self.apply_packet(msg)
        except PacketError as exc:
            self.rejected += 1
            self.note.setText("消息被拒绝：" + str(exc))
            self.client.abort()

    def apply_packet(self, msg):
        identity = (msg["device_id"], msg["boot_id"])
        if identity != self.identity:
            self.clear_measurements()
            self.identity = identity
        kind, data = msg["type"], msg["data"]
        if msg["seq"] <= self.sequences.get(kind, -1):
            self.duplicates += 1
            return
        self.sequences[kind] = msg["seq"]
        self.received += 1
        now = time.monotonic()
        if kind == "telemetry":
            for key, value in data.items():
                self.values[key] = (value, now)
            if data.get("sht_valid") is False:
                for key in ("temperature_c", "humidity_pct"):
                    self.values[key] = (None, now)
            if data.get("ir_valid") is False:
                for key in ("ir_min_c", "ir_max_c", "ir_center_c"):
                    self.values[key] = (None, now)
        elif kind == "inference":
            for key in ("person_score", "inference_ms"):
                self.values[key] = (data.get(key) if data["valid"] else None, now)
            self.values["inference_frame_id"] = (data["frame_id"], now)
        elif kind == "thermal":
            pixels = data["pixels_centi"]
            valid = [x / 100 for x in pixels if x is not None]
            low, high = (min(valid), max(valid)) if valid else (0, 1)
            image = QImage(32, 24, QImage.Format_RGB32)
            for y in range(24):
                for x in range(32):
                    value = pixels[y*32+x]
                    color = QColor("#546477") if value is None else heat_color((value/100-low) / max(.01, high-low))
                    image.setPixelColor(x, y, color)
            self.thermal.image, self.thermal.last_arrival = image, now
            self.thermal.caption = f"有效像素 {len(valid)}/768  |  {low:.2f} ~ {high:.2f} °C" if valid else "无有效温度像素"
        elif kind == "video":
            image = QImage.fromData(base64.b64decode(data["jpeg_base64"]), "JPEG")
            if image.isNull() or image.width() > 4096 or image.height() > 4096:
                raise PacketError("JPEG 无法解码或尺寸超过 4096")
            self.video.image, self.video.last_arrival = image, now
            self.video.caption = f"帧 {data['frame_id']}  |  {image.width()} × {image.height()}  |  {self.mode}"
        elif kind == "event":
            event_key = (identity, data["event_id"])
            if any(row["_key"] == event_key for row in self.events):
                self.duplicates += 1
                return
            row = dict(_key=event_key, received_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                       timestamp_ms=msg["timestamp_ms"], event_type=data["event_type"],
                       confidence=data.get("confidence"), frame_id=data.get("frame_id"),
                       source=self.mode, device_id=identity[0], boot_id=identity[1],
                       event_id=data["event_id"], acknowledged=False)
            self.events.insert(0, row)
            del self.events[500:]
            self.render_events()
        if self.mode != "模拟":
            self.source_label.setText(f"{self.mode} · {identity[0]} · boot {identity[1]}")
        self.refresh()

    def refresh(self):
        formats = {"temperature_c": ("{:.2f}", " °C"), "humidity_pct": ("{:.2f}", " %"),
                   "ir_center_c": ("{:.2f}", " °C"), "camera_fps": ("{:.2f}", " fps"),
                   "person_score": ("{:.0%}", ""), "inference_ms": ("{:.1f}", " ms")}
        now = time.monotonic()
        for key, widget in self.cards.items():
            value, stamp = self.values.get(key, (None, 0))
            stale = now-stamp > STALE_SECONDS
            if value is None or stale:
                widget.setText("—")
                widget.setStyleSheet("font-size: 27px; color: #718499;")
            else:
                fmt, unit = formats[key]
                widget.setText(fmt.format(value) + unit)
                widget.setStyleSheet("font-size: 27px; font-weight: 600; color: #5ce0ce;")
        self.video.update()
        self.thermal.update()
        self.footer.setText(f"接收 {self.received} 条  ·  拒绝 {self.rejected} 条  ·  去重 {self.duplicates} 条  ·  数据有效期 5 s  ·  事件最多保留 500 条，可导出")

    def render_events(self):
        self.table.setRowCount(len(self.events))
        for index, row in enumerate(self.events):
            score = "—" if row["confidence"] is None else f"{row['confidence']:.0%}"
            display_time = datetime.fromisoformat(row["received_at"]).strftime("%m-%d %H:%M:%S")
            values = [display_time, row["timestamp_ms"], row["event_type"], score,
                      "—" if row["frame_id"] is None else row["frame_id"], row["source"],
                      "已确认" if row["acknowledged"] else "待确认"]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setToolTip(row["received_at"])
                self.table.setItem(index, col, item)

    def acknowledge(self):
        index = self.table.currentRow()
        if 0 <= index < len(self.events):
            self.events[index]["acknowledged"] = True
            self.render_events()
            self.note.setText("该记录已在本机确认；此操作不控制开发板报警。")

    def export_events(self, path):
        fields = ["received_at", "timestamp_ms", "device_id", "boot_id", "event_id",
                  "event_type", "confidence", "frame_id", "source", "acknowledged"]
        with open(path, "w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(reversed(self.events))

    def choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出事件", "ti60_events.csv", "CSV (*.csv)")
        if path:
            try:
                self.export_events(path)
                self.note.setText("事件已导出：" + path)
            except OSError as exc:
                self.note.setText("导出失败：" + str(exc))

    def choose_replay(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开历史数据", "", "日志 (*.log *.txt *.jsonl);;所有文件 (*)")
        if path:
            self.load_replay(path)

    def load_replay(self, path):
        try:
            stream = open(path, encoding="utf-8", errors="replace")
        except OSError as exc:
            self.note.setText("打开失败：" + str(exc))
            return
        self.stop_source()
        self.replay_file = stream
        self.replay_seq = 0
        self.mode = "历史回放"
        self.source_label.setText("历史日志回放 · 未连接开发板")
        self.note.setText("文件：" + Path(path).name + "；按记录加速回放，不代表当前硬件状态或原始播放速度。")
        self.replay_timer.start()

    def replay_tick(self):
        for _ in range(10):
            line = self.replay_file.readline()
            if not line:
                self.replay_file.close()
                self.replay_file = None
                self.replay_timer.stop()
                self.source_label.setText("回放完成 · 历史数据")
                return
            self.replay_seq += 1
            try:
                msg = decode_line(line.encode()) if line.lstrip().startswith("{") else parse_uart(line, self.replay_seq)
                if msg:
                    self.apply_packet(msg)
            except PacketError:
                self.rejected += 1

    def demo_tick(self):
        self.demo_count += 1
        n = self.demo_count
        stamp = n * 200
        self.apply_packet(packet("telemetry", n, dict(temperature_c=24.6 + math.sin(n/12)*.3,
            humidity_pct=62.1 + math.sin(n/15), ir_center_c=32.5, camera_fps=30,
            sht_valid=True, ir_valid=True), timestamp_ms=stamp))
        self.apply_packet(packet("inference", n, dict(frame_id=n, valid=True,
            person_score=.87 + .02*math.sin(n/10), inference_ms=196.5), timestamp_ms=stamp))
        pixels = [round(2450 + 900*math.exp(-((x-16-math.sin(n/8)*4)**2/20 + (y-12)**2/32)))
                  for y in range(24) for x in range(32)]
        self.apply_packet(packet("thermal", n, dict(width=32, height=24, pixels_centi=pixels), timestamp_ms=stamp))
        image = QImage(640, 360, QImage.Format_RGB32)
        painter = QPainter(image)
        for i, color in enumerate(["#406ca1", "#49a294", "#c9b960", "#a97c6e", "#725a90", "#354f75", "#193344", "#102232"]):
            painter.fillRect(i*80, 0, 80, 360, QColor(color))
        painter.fillRect(40+n*7 % 420, 125, 145, 115, QColor("#26364d"))
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Microsoft YaHei", 17))
        painter.drawText(25, 44, "SIMULATED VIDEO")
        painter.drawText(25, 330, f"DEMO  /  FRAME {n}")
        painter.end()
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "JPEG", 85)
        self.apply_packet(packet("video", n, dict(frame_id=n,
            jpeg_base64=base64.b64encode(bytes(buffer.data())).decode()), timestamp_ms=stamp))
        if n == 1 or n % 40 == 0:
            self.apply_packet(packet("event", n, dict(event_id=f"demo-{n}", event_type="演示：人员出现",
                confidence=.89, frame_id=n), timestamp_ms=stamp))

    def closeEvent(self, event):
        self.stop_source()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--snapshot", type=Path, help="save a desktop UI preview for review")
    args = parser.parse_args()
    if args.snapshot:
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication(sys.argv[:1])
    window = MonitorWindow()
    window.show()
    if args.demo:
        window.start_demo()
    if args.snapshot:
        def capture():
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.snapshot)):
                raise RuntimeError("Could not save UI preview")
            app.quit()
        QTimer.singleShot(700, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
