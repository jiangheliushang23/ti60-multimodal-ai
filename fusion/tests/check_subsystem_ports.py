"""Check that structural subsystem wrappers preserve their leaf interfaces."""
from pathlib import Path
import re

SRC = Path(__file__).resolve().parents[1] / "ti60_multimodal/src/fusion"
PAIRS = {
    "fusion_camera_subsys": "fusion_camera",
    "fusion_video_path": "video_ddr",
    "fusion_sensor_front": "fusion_sensor_hdmi",
}


def ports(path):
    text = re.sub(r"/\*.*?\*/|//[^\n]*", "", path.read_text(), flags=re.S)
    head = text[:text.index(");")]
    # A parameterized module has a separate #(...) before its port list.
    head = head[head.index("("):]
    if "#" in text[:text.index("(")]:
        head = head[head.index(")") + 1:]
    head = head[head.index("(") + 1:]
    result = {}
    direction, width = None, 1
    for item in head.split(","):
        match = re.fullmatch(
            r"\s*(?:(input|output|inout)\s+(?:(?:wire|reg)\s+)?"
            r"(?:\[(\d+):(\d+)\]\s*)?)?(\w+)\s*", item
        )
        if not match:
            raise ValueError(f"Unsupported port declaration in {path}: {item!r}")
        if match[1]:
            direction = match[1]
            width = abs(int(match[2]) - int(match[3])) + 1 if match[2] else 1
        if direction is None:
            raise ValueError(f"Missing direction in {path}: {item!r}")
        result[match[4]] = (direction, width)
    return result


def check():
    total = 0
    for wrapper, leaf in PAIRS.items():
        outer = ports(SRC / (wrapper + ".v"))
        inner = ports(SRC / (leaf + ".v"))
        if outer != inner:
            mismatches = {name: (outer.get(name), inner.get(name))
                          for name in sorted(outer.keys() | inner.keys())
                          if outer.get(name) != inner.get(name)}
            raise AssertionError(f"{wrapper} does not preserve {leaf}: {mismatches}")
        total += len(outer)
        print(f"PASS {wrapper}: {len(outer)} port directions and widths match {leaf}")
    print(f"PASS {total} subsystem ports")


if __name__ == "__main__":
    check()
