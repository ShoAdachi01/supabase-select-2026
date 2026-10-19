"""Encode timestamped browser frames without including time spent waiting for the director."""

import json
import math
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image

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
    # A 4K VP9 encode runs well below realtime; budget it by recording length.
    try:
        ffmpeg(
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(manifest),
            "-an",
            "-vf",
            "fps=30,scale='min(3840,trunc(iw/2)*2)':-2:in_range=pc:out_range=tv,format=yuv420p",
            "-color_range",
            "tv",
            "-t",
            str(total),
            "-c:v",
            "libvpx-vp9",
            "-crf",
            "20",
            "-b:v",
            "0",
            "-row-mt",
            "1",
            "-deadline",
            "good",
            "-cpu-used",
            "4",
            str(folder / "raw.webm"),
            timeout=max(300, round(total * 20)),
        )
    except subprocess.TimeoutExpired:
        raise ValueError("Encoding the recording took too long.") from None


def probe(path: Path) -> tuple[int, int, float]:
    """Decoded dimensions and average frame rate of a local video."""
    output = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    ).stderr
    match = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})[ ,].*?([\d.]+) fps", output)
    if not match:
        raise ValueError("Could not measure the recorded video.")
    return int(match[1]), int(match[2]), float(match[3])


def measure_sources(folder: Path, scenes: list[dict]) -> dict:
    """Zoom limits follow what was actually captured, not what was requested."""
    width, height, fps = probe(folder / "raw.webm")
    frames_path = folder / "capture.json"
    if frames_path.exists():
        frames = json.loads(frames_path.read_text())
        total = sum(float(f["duration"]) for f in frames)
        fps = round(len(frames) / total, 2) if total else fps
    viewport_width = (scenes[0].get("viewport") or {"width": 1920})["width"] if scenes else 1920
    source_scale = round(width / viewport_width, 2)
    for scene in scenes:
        scene["source_scale"] = source_scale
        name = scene.get("thumbnail", "")
        still = 1.0
        if re.fullmatch(r"scene-\d{1,2}\.jpg", name) and (folder / name).exists():
            with Image.open(folder / name) as image:
                still = round(image.width / scene.get("viewport", {"width": 1920})["width"], 2)
        scene["still_scale"] = still
    metrics = {
        "width": width,
        "height": height,
        "fps": fps,
        "bytes": (folder / "raw.webm").stat().st_size,
        "source_scale": source_scale,
    }
    (folder / "capture-metrics.json").write_text(json.dumps(metrics))
    return metrics
