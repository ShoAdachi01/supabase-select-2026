"""Find verified result screens on the recording's clock, not the browser's wall clock."""

import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from server.video_render import FFMPEG


def align_result_shots(raw: Path, folder: Path, scenes: list[dict]) -> None:
    targets = []
    for scene in scenes:
        if scene.get("shot") != "result":
            continue
        name = scene.get("thumbnail", "")
        if not re.fullmatch(r"scene-\d{1,2}\.jpg", name):
            raise ValueError("Invalid screen evidence for recording alignment.")
        with Image.open(folder / name) as image:
            target = np.asarray(image.convert("L").resize((160, 90)), dtype=float)
        targets.append((scene, target, []))
    if not targets:
        return
    # Streaming keeps memory bounded even for long browser sessions.
    with subprocess.Popen(
        [
            FFMPEG,
            "-v",
            "error",
            "-i",
            str(raw),
            "-vf",
            "fps=5,scale=160:90",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        while data := process.stdout.read(160 * 90):
            if len(data) != 160 * 90:
                raise ValueError("Incomplete frame while aligning recording.")
            frame = np.frombuffer(data, dtype=np.uint8).reshape(90, 160).astype(float)
            for _, target, scores in targets:
                scores.append(float(np.mean(np.abs(frame - target))))
        if process.wait():
            raise ValueError("Could not align the captured product screens.")
    previous_end = 0
    for scene, _, values in targets:
        scores = np.array(values)
        times = np.arange(len(scores)) / 5
        allowed = (times >= previous_end) & (abs(times - scene["start"]) <= 15)
        if not allowed.any():
            raise ValueError("No recorded frames match the requested shot order.")
        best = float(np.min(scores[allowed]))
        if best > 2.5:
            raise ValueError(
                "A result screen could not be verified in the recording. Try another take."
            )
        matches = np.flatnonzero(allowed & (scores <= best + 0.25))
        runs = np.split(matches, np.where(np.diff(matches) > 1)[0] + 1)
        runs = [run for run in runs if len(run) >= 4]
        if not runs:
            raise ValueError("The result screen did not stay visible long enough to film.")
        run = min(runs, key=lambda r: abs(r[0] / 5 - scene["start"]))
        # Leave a frame margin on each edge; the renderer holds the last real frame if needed.
        start, end = float(run[0] / 5 + 0.1), float(run[-1] / 5 - 0.1)
        scene["capture_start"], scene["capture_end"] = scene["start"], scene["end"]
        scene["start"], scene["end"] = start, end
        scene["alignment_error"] = round(best, 3)
        previous_end = end
