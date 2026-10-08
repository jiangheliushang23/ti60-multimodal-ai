"""Send a draft-v1 example to the desktop receiver; no board interaction."""
import argparse
import json
import socket

from protocol import packet

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=9001)
args = parser.parse_args()
messages = [
    packet("telemetry", 1, {"temperature_c": 24.6, "humidity_pct": 62.1,
                           "sht_valid": True, "camera_fps": 30},
           device="sample-generator", boot="sample", timestamp_ms=1000),
    packet("inference", 1, {"frame_id": 30, "valid": True, "person_score": .88, "inference_ms": 195},
           device="sample-generator", boot="sample", timestamp_ms=1000),
    packet("event", 1, {"event_id": "sample-event", "event_type": "示例报警",
                       "confidence": .88, "frame_id": 30},
           device="sample-generator", boot="sample", timestamp_ms=1000),
]
with socket.create_connection((args.host, args.port), timeout=3) as connection:
    for message in messages:
        connection.sendall((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
print("已发送三条明确标记为 sample-generator 的示例消息；没有连接开发板。")
