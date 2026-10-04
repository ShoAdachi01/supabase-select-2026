"""Render and review a new directed film from an existing private capture (uses model credits)."""

import argparse
import json
import re
import shutil
from pathlib import Path

from server.video_direction import (
    compile_direction,
    constrain_geometry,
    direct_film,
    review_film,
    validate_evidence,
)
from server.video_direction_models import FilmDirection
from server.video_models import TimelineClip
from server.video_render import render
from server.video_timeline import compile_timeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--plan",
        type=Path,
        help="Resume a saved model proposal through validation and rendered review",
    )
    parser.add_argument("--title", default="Meridian")
    parser.add_argument(
        "--brief",
        default="Show projects, owners, task details, board views, and progress. Create a confident launch film with character and varied compositions.",
    )
    parser.add_argument(
        "--direction",
        default="Use tactile product details, bold editorial type, and purposeful spatial continuity. No generic opening title over a floating screen.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # Exported storyboard retains original capture IDs even when thumbnail points to an edited frame.
    if (args.source / "source-scenes.json").exists():
        scenes = json.loads((args.source / "source-scenes.json").read_text())
    elif (args.source / "scenes.json").exists():
        scenes = json.loads((args.source / "scenes.json").read_text())
    else:
        scenes = []
        for item in json.loads((args.source / "storyboard.json").read_text()):
            if item.get("kind") == "browser":
                scene = dict(item)
                scene["thumbnail"] = scene["scene_id"]
                scene["narration"] = ""
                scenes.append(scene)
    for scene in scenes:
        scene["narration"] = ""
    for name in [
        "raw.webm",
        *[s["thumbnail"] for s in scenes],
        *[n for s in scenes for n in s.get("details", [])],
    ]:
        if not re.fullmatch(r"(raw\.webm|scene-\d{1,2}\.jpg|detail-\d{1,2}-\d\.png)", name):
            raise ValueError("Invalid capture asset")
        shutil.copyfile(args.source / name, args.output / name)
    (args.output / "source-scenes.json").write_text(json.dumps(scenes, indent=2))
    print("Directing from captured evidence...", flush=True)
    if args.plan:
        plan = constrain_geometry(FilmDirection.model_validate_json(args.plan.read_text()))
        issues = validate_evidence(plan, scenes, 30)
        if issues:
            raise ValueError(issues)
    else:
        plan = direct_film(args.title, args.brief, scenes, args.output, 30, args.direction)
    print("Reviewing rendered states...", flush=True)
    plan, report = review_film(plan, scenes, args.output, "midnight", 30)
    print(f"Review: {report['status']}; {report['revision_count']} revisions", flush=True)
    clips = compile_direction(plan, scenes)
    compiled = compile_timeline(
        {"payload": {"scenes": scenes}}, [TimelineClip.model_validate(c) for c in clips]
    )
    print("Rendering final film...", flush=True)
    result = render(
        args.output,
        args.output / "raw.webm",
        compiled,
        args.title,
        "midnight",
        "momentum",
        [None] * len(compiled),
        lambda i, n: print(f"Render {i}/{n}", flush=True) if i else None,
    )
    (args.output / "result.json").write_text(json.dumps(result, indent=2))
    print(result, flush=True)


if __name__ == "__main__":
    main()
