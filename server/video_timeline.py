"""Non-destructive edits: original captures remain immutable and addressable."""

from __future__ import annotations

import re
import uuid
from copy import deepcopy

from fastapi import HTTPException

from server.video_models import TimelineClip


def capture_id(scene: dict, index: int) -> str:
    return scene.get("id") or scene.get("thumbnail") or f"capture-{index}"


def browser_clips(scenes: list[dict]) -> list[dict]:
    return [
        TimelineClip(
            id=f"take-{i}",
            scene_id=capture_id(scene, i),
            label=scene["label"],
            narration=scene.get("narration", ""),
        ).model_dump(mode="json")
        for i, scene in enumerate(scenes)
    ]


def launch_prompt(title: str, brief: str, scenes: list[dict]) -> str:
    import json

    return (
        f"Direct a punchy 20–30 second launch film for {title}. Brief: {brief}. "
        f"Verified captured scenes: {json.dumps(scenes)}. "
        'Return {"narration":["6–9 spoken words per captured scene"], '
        '"hook":{"headline":"2–5 words","subtitle":""},'
        '"benefit":{"headline":"2–5 words","subtitle":""},'
        '"outro":{"headline":"2–5 words","subtitle":""}}. '
        f"Exactly {len(scenes)} narration entries in capture order, maximum 9 words each. "
        "Each line expresses one visible benefit. No step-by-step navigation instructions. "
        "The typography cards are silent, so do not add narration to hook, benefit or outro. "
        "Only claim benefits visible in the captured scenes; no invented stats, prices or testimonials."
    )


def launch_clips(
    scenes: list[dict], title: str, plan: dict | None = None, target_duration: int = 30
) -> list[dict]:
    plan = plan if isinstance(plan, dict) else {}
    originals = browser_clips(scenes)
    # Keep source clips recoverable, but do not repeat an establishing screen before the feature.
    for clip, source in zip(originals, scenes, strict=True):
        clip["enabled"] = not (len(scenes) > 1 and source.get("action") == "overview")
        clip["camera"] = "push" if source.get("shot") == "result" else "wide"
    scripts = plan.get("narration", [])
    if isinstance(scripts, list) and len(scripts) == len(originals):
        for clip, script in zip(originals, scripts, strict=True):
            if isinstance(script, str):
                clip["narration"] = script[:1000]
    shot_duration = (
        round(
            min(
                4,
                max(2.4, (target_duration - 6.8) / max(1, sum(c["enabled"] for c in originals))),
            )
            / 0.4
        )
        * 0.4
    )
    for clip in originals:
        clip["duration"] = round(shot_duration, 1)
    cards = []
    for layout, headline, narration in (
        ("hook", title, ""),
        ("benefit", scenes[min(1, len(scenes) - 1)]["label"], ""),
        ("outro", "See it in action.", ""),
    ):
        copy = plan.get(layout, {})
        if not isinstance(copy, dict):
            copy = {}
        cards.append(
            TimelineClip(
                id=str(uuid.uuid4()),
                kind="title",
                layout=layout,
                label={
                    "hook": "Opening hook",
                    "benefit": "Feature spotlight",
                    "outro": "Closing invitation",
                }[layout],
                headline=str(copy.get("headline") or headline)[:180],
                subtitle=str(copy.get("subtitle") or "")[:240],
                narration=str(copy.get("narration") or narration)[:1000],
                duration={"hook": 2.4, "benefit": 2, "outro": 2.4}[layout],
            ).model_dump(mode="json")
        )
    visible = [i for i, clip in enumerate(originals) if clip["enabled"]]
    midpoint = visible[min(1, len(visible) - 1)] + 1 if visible else len(originals)
    return [cards[0], *originals[:midpoint], cards[1], *originals[midpoint:], cards[2]]


def compile_timeline(job: dict, clips: list[TimelineClip]) -> list[dict]:
    payload = job["payload"]
    sources = {capture_id(s, i): s for i, s in enumerate(payload["scenes"])}
    assets = {a["id"]: a for a in payload.get("assets", []) if a["status"] == "complete"}
    if len({c.id for c in clips}) != len(clips):
        raise HTTPException(400, "Each timeline clip needs a unique ID.")
    rendered = []
    for clip in clips:
        if not clip.enabled:
            continue
        scene = clip.model_dump(mode="json")
        if clip.kind == "browser":
            source = sources.get(clip.scene_id)
            if not source:
                raise HTTPException(400, "Choose a captured scene from this video.")
            if source.get("thumbnail") and not re.fullmatch(
                r"scene-\d{1,2}\.jpg", source["thumbnail"]
            ):
                raise HTTPException(400, "Invalid captured thumbnail.")
            available = source["end"] - source["start"]
            end = clip.trim_end if clip.trim_end is not None else available
            if not 0 <= clip.trim_start < end <= available + 0.02 or end - clip.trim_start < 0.25:
                raise HTTPException(400, "Keep at least 0.25 seconds inside the original capture.")
            scene.update(
                start=source["start"] + clip.trim_start,
                end=source["start"] + end,
                focus=deepcopy(source.get("focus", {"x": 640, "y": 360})),
                thumbnail=source.get("thumbnail"),
            )
        elif clip.kind == "generated":
            asset = assets.get(str(clip.asset_id))
            if not asset:
                raise HTTPException(400, "Choose a finished animation from this video's assets.")
            if clip.duration > asset["duration"] + 0.05:
                raise HTTPException(400, "The animation duration exceeds its source clip.")
            scene.update(start=0, end=asset["duration"], source_file=f"asset-{clip.asset_id}.mp4")
        elif not clip.headline.strip():
            raise HTTPException(400, "Animated title scenes need a headline.")
        rendered.append(scene)
    if not rendered:
        raise HTTPException(400, "Keep at least one enabled scene in your film.")
    return rendered
