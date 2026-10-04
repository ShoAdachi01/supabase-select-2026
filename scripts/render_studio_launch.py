"""Compose an explicitly directed film of Cutroom's real UI; no simulated product screens."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server.video_providers import speech
from server.video_render import render

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--reuse-audio",
    action="store_true",
    help="Reuse this recording's existing speech when the narration has not changed.",
)
args = parser.parse_args()
folder = Path(".cutroom/verification/cutroom-launch")
scenes = json.loads((folder / "scenes.json").read_text())
opening = {
    "kind": "title",
    "layout": "hook",
    "headline": "Build. Launch. Repeat.",
    "subtitle": "Meet Cutroom.",
    "label": "Meet Cutroom",
    "duration": 1.6,
    "narration": "",
    "transition": "cut",
}
closing = {
    "kind": "title",
    "layout": "outro",
    "headline": "From shipped to shared.",
    "subtitle": "cutroom / Your agent’s video studio",
    "label": "Launch with Cutroom",
    "duration": 2,
    "narration": "Cutroom. From shipped to shared.",
    "transition": "cut",
}
timeline = [opening, *scenes, closing]


def narrate(item):
    index, scene = item
    if not scene.get("narration"):
        return None
    path = folder / f"voice-{index}.mp3"
    if not args.reuse_audio or not path.exists():
        speech(scene["narration"], "coral", path)
    return path


with ThreadPoolExecutor(max_workers=3) as pool:
    audio = list(pool.map(narrate, enumerate(timeline)))
meta = render(
    folder,
    folder / "raw.webm",
    timeline,
    "Cutroom",
    "midnight",
    "momentum",
    audio,
    lambda i, n: print(f"Rendering {i}/{n}", flush=True),
)
(folder / "export.json").write_text(json.dumps(meta, indent=2))
print(json.dumps(meta), flush=True)
