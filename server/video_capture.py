"""Encode timestamped browser frames without including time spent waiting for the director."""

import json
import math
import re
from pathlib import Path

from server.video_render import ffmpeg


def encode_directed_capture(folder: Path):
    frames = json.loads((folder / "capture.json").read_text())
    if not frames or len(frames) > 12000:
        raise ValueError("Invalid directed capture length.")
    lines, total = [], 0.0
    for frame in frames:
        name, duration = frame["name"], float(frame["duration"])
        if not re.fullmatch(r"capture-frames/\d{6}\.jpg", name):
            raise ValueError("Invalid directed capture asset.")
        if not math.isfinite(duration) or not 0 < duration <= 60:
            raise ValueError("Invalid directed capture timing.")
        total += duration
        lines.extend([f"file '{name}'", f"duration {duration:.6f}"])
    if total > 600:
        raise ValueError("The directed recording is too long.")
    lines.append(f"file '{frames[-1]['name']}'")
    manifest = folder / "capture.ffconcat"
    manifest.write_text("\n".join(lines))
    ffmpeg(
        "-f",
        "concat",
        "-safe",
        "1",
        "-i",
        str(manifest),
        "-an",
        "-vf",
        "fps=30,scale=1920:1080:in_range=pc:out_range=tv,format=yuv420p",
        "-color_range",
        "tv",
        "-t",
        str(total),
        "-c:v",
        "libvpx",
        "-deadline",
        "realtime",
        "-cpu-used",
        "8",
        "-b:v",
        "6M",
        str(folder / "raw.webm"),
    )
