"""Controlled paid prompt experiments from one capture. Private artifacts, no automatic quality winner."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import time
from pathlib import Path

from server.video_direction import compile_direction, direct_film, review_film
from server.video_direction_models import FilmTreatment
from server.video_models import TimelineClip
from server.video_prompts import PROMPT_VERSION, STRATEGIES
from server.video_providers import reason
from server.video_reference import analyze_media
from server.video_render import render
from server.video_timeline import compile_timeline


def copy_capture(source: Path, output: Path) -> list[dict]:
    scenes = json.loads((source / "source-scenes.json").read_text())
    output.mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        scene["narration"] = ""
    for name in [
        "raw.webm",
        *[s["thumbnail"] for s in scenes],
        *[n for s in scenes for n in s.get("details", [])],
    ]:
        if not re.fullmatch(r"raw\.webm|scene-\d{1,2}\.jpg|detail-\d{1,2}-\d\.png", name):
            raise ValueError("Invalid capture asset")
        shutil.copyfile(source / name, output / name)
    (output / "source-scenes.json").write_text(json.dumps(scenes, indent=2))
    return scenes


def gallery(output: Path, rows: list[dict]):
    cards = []
    for index, row in enumerate(rows):
        name = row["name"]
        status = html.escape(row["status"])
        video = (
            f'<video controls preload="metadata" src="{name}/film.mp4"></video>'
            if row["status"] == "rendered"
            else f"<p>{status}</p>"
        )
        cards.append(
            f"<article><h2>Take {index + 1}</h2>{video}<details><summary>Reveal method</summary><pre>{html.escape(json.dumps(row, indent=2))}</pre></details></article>"
        )
    (output / "index.html").write_text(
        """<!doctype html><meta charset="utf-8"><title>Cutroom motion experiments</title>
<style>body{background:#111318;color:#eee;font:16px system-ui;margin:40px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(450px,1fr));gap:24px}article{background:#1c2027;padding:20px;border-radius:16px}video{width:100%}pre{white-space:pre-wrap}summary{cursor:pointer;margin-top:16px}</style>
<h1>Compare the films</h1><p>Same footage and brief. Assess specificity, readable proof, choreography, pacing, and audio fit. Methods are hidden until you reveal them. These are drafts, not quality-certified samples.</p><main>"""
        + "".join(cards)
        + "</main>"
    )
    (output / "comparison.json").write_text(json.dumps(rows, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument(
        "--providers", nargs="+", choices=["openai", "claude"], default=["openai", "claude"]
    )
    parser.add_argument("--openai-model", default="gpt-6.1-sol")
    parser.add_argument("--claude-model", default="claude-opus-5-5")
    parser.add_argument("--effort", choices=["low", "medium", "high"], default="high")
    parser.add_argument(
        "--reference",
        type=Path,
        help="Optional local reference MP4; analyzed once for every method's identical input",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Include up to two rendered-preview revisions per method",
    )
    parser.add_argument("--title", default="Cutroom")
    parser.add_argument(
        "--brief",
        default="Show how Cutroom turns a product feature brief into a film you can preview and export. Audience: developers preparing a launch. Prove only actions visible in this capture. This is a launch film, not a narrated tutorial.",
    )
    parser.add_argument(
        "--direction",
        default="Confident, playful precision. Make a real product detail the protagonist. Strong hierarchy, restrained palette drawn from the product, varied scale and pace, decisive motion with readable holds. No recurring title-over-screen layout. Music and real interaction sounds, no narration.",
    )
    parser.add_argument("--geometry-effort", choices=["low", "medium", "high"], default="medium")
    parser.add_argument(
        "--treatment",
        type=Path,
        help="Reuse an existing validated treatment for a controlled geometry/render follow-up",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    if (args.output / "comparison.json").exists():
        rows = json.loads((args.output / "comparison.json").read_text())
    reference = None
    if args.reference:
        reference_data = args.reference.read_bytes()
        reference_hash = hashlib.sha256(reference_data).hexdigest()
        cached = args.output / "shared-reference" / "analysis.json"
        origin = cached.parent / "source.json"
        if (
            cached.exists()
            and origin.exists()
            and json.loads(origin.read_text()).get("sha256") == reference_hash
        ):
            reference = json.loads(cached.read_text())
        else:
            reference = analyze_media(
                reference_data,
                "video/mp4",
                cached.parent,
                lambda *a, **kw: reason(
                    *a,
                    **kw,
                    provider=args.providers[0],
                    model=args.openai_model if args.providers[0] == "openai" else args.claude_model,
                    effort=args.effort,
                ),
            )
        origin.write_text(json.dumps({"sha256": reference_hash}))
    source_hash = hashlib.sha256()
    scenes_for_hash = json.loads((args.source / "source-scenes.json").read_text())
    for asset in [
        "source-scenes.json",
        "raw.webm",
        *[s["thumbnail"] for s in scenes_for_hash],
        *[n for s in scenes_for_hash for n in s.get("details", [])],
    ]:
        source_hash.update((args.source / asset).read_bytes())
    experiment = {
        "capture_sha256": source_hash.hexdigest(),
        "title": args.title,
        "brief": args.brief,
        "direction": args.direction,
        "reference": reference,
        "effort": args.effort,
        "geometry_effort": args.geometry_effort,
        "treatment_sha256": hashlib.sha256(args.treatment.read_bytes()).hexdigest()
        if args.treatment
        else None,
        "review": args.review,
        "prompt_version": PROMPT_VERSION,
    }
    (args.output / "experiment.json").write_text(json.dumps(experiment, indent=2))
    for provider in args.providers:
        model = args.openai_model if provider == "openai" else args.claude_model
        for strategy in args.strategies:
            signature = hashlib.sha256(
                json.dumps(
                    {**experiment, "model": model, "provider": provider, "strategy": strategy},
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            name = f"{provider}-{strategy}-{signature[:8]}"
            if any(row["name"] == name and row["status"] == "rendered" for row in rows):
                continue
            folder = args.output / name
            scenes = copy_capture(args.source, folder)
            (folder / "experiment.json").write_text(json.dumps(experiment, indent=2))
            calls = []

            def request(*a, provider=provider, model=model, calls=calls, folder=folder, **kw):
                telemetry = {}
                call_effort = kw.pop("effort", args.effort)
                try:
                    return reason(
                        *a,
                        **kw,
                        provider=provider,
                        model=model,
                        effort=call_effort,
                        telemetry=telemetry,
                    )
                finally:
                    calls.append(telemetry)
                    (folder / "usage.json").write_text(json.dumps(calls, indent=2))

            row = {
                "name": name,
                "signature": signature,
                "provider": provider,
                "model": model,
                "effort": args.effort,
                "geometry_effort": args.geometry_effort,
                "strategy": strategy,
                "reference": bool(reference),
                "review_enabled": args.review,
            }
            started = time.monotonic()
            print(f"Starting {name} / {model}", flush=True)
            try:
                plan = direct_film(
                    args.title,
                    args.brief,
                    scenes,
                    folder,
                    30,
                    args.direction,
                    strategy=strategy,
                    reasoner=request,
                    reference_analysis=reference,
                    geometry_effort=args.geometry_effort,
                    prepared_treatment=FilmTreatment.model_validate_json(args.treatment.read_text())
                    if args.treatment
                    else None,
                )
                if args.review:
                    plan, report = review_film(
                        plan,
                        scenes,
                        folder,
                        "midnight",
                        30,
                        reasoner=request,
                        geometry_effort=args.geometry_effort,
                    )
                    row["review"] = report
                compiled = compile_timeline(
                    {"payload": {"scenes": scenes}},
                    [TimelineClip.model_validate(c) for c in compile_direction(plan, scenes)],
                )
                result = render(
                    folder,
                    folder / "raw.webm",
                    compiled,
                    args.title,
                    "midnight",
                    "momentum",
                    [None] * len(compiled),
                    lambda i, n: None,
                )
                row.update(
                    status="rendered",
                    export=result,
                    concept=plan.concept,
                    compositions=[s.composition for s in plan.shots],
                    durations=[round(s.beats * 60 / s.bpm, 2) for s in plan.shots],
                )
            except Exception as exc:
                # ProviderError messages are redacted; all other failures get only their type.
                from server.video_providers import ProviderError

                row.update(
                    status="failed",
                    error=str(exc) if isinstance(exc, ProviderError) else type(exc).__name__,
                )
            row.update(seconds=round(time.monotonic() - started, 1), calls=len(calls))
            rows = [r for r in rows if r["name"] != name] + [row]
            gallery(args.output, rows)
            print(json.dumps(row), flush=True)
            if row.get("error", "").startswith("Claude returned 400"):
                print(
                    "Claude access rejected; skipping remaining Claude methods until workspace configuration is repaired.",
                    flush=True,
                )
                break


if __name__ == "__main__":
    main()
