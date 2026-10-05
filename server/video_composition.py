"""Prepare private, verified product assets for reviewed Remotion compositions."""

from __future__ import annotations

import json
import math
import os
import re
import signal
import subprocess
import time
from pathlib import Path

from PIL import Image

from server.video_render import ffmpeg, wav_duration

ROOT = Path(__file__).resolve().parent.parent


def shot_duration(scene: dict, audio: Path | None) -> float:
    duration = scene.get("duration", 4)
    if audio:
        duration = max(duration, wav_duration(audio) + 0.15)
    return math.ceil(duration * 30) / 30


def run_compositor(folder: Path, manifest: Path, checkpoint=None):
    started = time.monotonic()
    with (
        (folder / "motion-error.log").open("wb") as errors,
        (folder / "motion-run.jsonl").open("wb") as output,
    ):
        process = subprocess.Popen(
            ["node", str(ROOT / "scripts/render_motion.mjs"), str(manifest.resolve())],
            cwd=ROOT,
            stdout=output,
            stderr=errors,
            start_new_session=True,
        )
        try:
            while process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if checkpoint:
                        checkpoint()
                    if time.monotonic() - started > 1200:
                        raise ValueError(
                            "Motion composition exceeded its render time limit."
                        ) from None
            if process.returncode:
                raise ValueError(
                    "Motion composition failed. Check the worker's local motion-error.log."
                )
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def prepare_compositions(
    folder: Path,
    raw: Path,
    scenes: list[dict],
    theme: str,
    audio: list,
    checkpoint=None,
    *,
    preview=False,
) -> dict:
    jobs, outputs = [], {}
    for i, (scene, speech) in enumerate(zip(scenes, audio, strict=True)):
        preset = scene.get("motion", "none")
        if preset == "none" or scene.get("kind") == "generated":
            continue
        speech_wav = None
        if speech:
            speech_wav = folder / f"motion-voice-{i}.wav"
            ffmpeg("-i", str(speech), "-ac", "2", "-ar", "48000", str(speech_wav))
        duration = shot_duration(scene, speech_wav)
        direction = scene.get("direction") if preset == "directed" else None
        if direction and duration > scene["duration"]:
            # Narration can extend a shot; keep motion and sound on the same beat clock.
            import math

            old_beats = direction["beats"]
            direction["beats"] = math.ceil(duration * direction["bpm"] / 60)
            for layer in direction["layers"]:
                for state in layer["states"]:
                    state["beat"] *= direction["beats"] / old_beats
            for hit in direction["hits"]:
                hit["beat"] *= direction["beats"] / old_beats
            duration = direction["beats"] * 60 / direction["bpm"]
        scene["duration"] = duration
        # Titles use the NEXT shot's trimmed first frame. Closing uses the preceding product.
        candidates = (
            scenes[i + 1 :] if scene.get("layout") != "outro" else list(reversed(scenes[:i]))
        )
        source = (
            scene
            if scene.get("kind", "browser") == "browser"
            else next((s for s in candidates if s.get("kind", "browser") == "browser"), None)
        )
        source_at_end = False
        if preset == "panels" and source and source.get("interactions"):
            preceding = next(
                (s for s in reversed(scenes[:i]) if s.get("kind", "browser") == "browser"), None
            )
            if preceding:
                source, source_at_end = preceding, True
        if not source:
            # Text-only edits still render; no fabricated product UI is substituted.
            source = {"start": 0, "end": 1}
        product = folder / f"motion-product-{i}.png"
        ffmpeg(
            "-ss",
            str(max(0, source.get("end", 0) - 1 / 30 if source_at_end else source.get("start", 0))),
            "-i",
            str(raw),
            "-frames:v",
            "1",
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
            str(product),
        )
        if direction:
            name = source.get("thumbnail", "")
            if not re.fullmatch(r"scene-\d{1,2}\.jpg", name):
                raise ValueError("Invalid directed product asset.")
            with Image.open(folder / name) as image:
                image.convert("RGB").resize((1920, 1080)).save(product)
        details = []
        for j, name in enumerate(source.get("details", [])[:3]):
            if not re.fullmatch(r"detail-\d{1,2}-\d\.png", name):
                raise ValueError("Invalid captured detail asset.")
            target = folder / f"motion-detail-{i}-{j}.png"
            with Image.open(folder / name) as im:
                im.convert("RGB").save(target)
            details.append(target.name)
        if preset == "panels" and len(details) < 2:
            # Unverified crops often magnify blank space. Reveal the complete real screen instead.
            preset = "reveal"
        footage = None
        if preset == "detail" or (
            direction and any(layer["kind"] == "footage" for layer in direction["layers"])
        ):
            footage = folder / f"motion-footage-{i}.mp4"
            recorded = max(0.25, source["end"] - source["start"])
            speed = max(1, recorded / duration)
            ffmpeg(
                "-ss",
                str(source["start"]),
                "-t",
                str(recorded),
                "-i",
                str(raw),
                "-an",
                "-vf",
                f"setpts=(PTS-STARTPTS)/{speed},fps=30,scale=1920:1080,tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                str(footage),
            )
        focus = source.get("focus", {"x": 640, "y": 360})
        viewport = source.get("viewport", {"width": 1280, "height": 720})
        jobs.append(
            {
                "index": i,
                "direction": direction,
                "preset": preset,
                "theme": theme,
                "headline": scene.get("headline") or scene.get("label", ""),
                "subtitle": scene.get("subtitle", ""),
                "frames": round(duration * 30),
                "interactive": bool(source.get("interactions")),
                "product": product.name,
                "details": details,
                "footage": footage.name if footage else None,
                "focus": {
                    "x": min(0.8, max(0.2, focus["x"] / viewport["width"])),
                    "y": min(0.8, max(0.2, focus["y"] / viewport["height"])),
                },
            }
        )
        outputs[i] = folder / f"motion-{i}.mp4"
    if jobs:
        manifest = folder / "motion-jobs.json"
        manifest.write_text(json.dumps({"jobs": jobs, "preview": preview}))
        run_compositor(folder, manifest, checkpoint)
    return outputs
