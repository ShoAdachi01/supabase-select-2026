"""Evidence-grounded film direction, beat-grid compilation, and bounded visual revision."""

from __future__ import annotations

import base64
import io
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Literal

import imageio_ffmpeg
from PIL import Image, ImageDraw

from server.video_camera import (
    click_point,
    clicks,
    drifted,
    effective_scale,
    project,
    resolve_focus,
    visible_window,
    zoom_cap,
)
from server.video_composition import preview_frame_list
from server.video_direction_models import (
    AXES,
    FilmDirection,
    FilmReview,
    FilmTreatment,
)
from server.video_models import TimelineClip
from server.video_prompts import PROMPT_VERSION, TREATMENT, enriched_prompt
from server.video_providers import ProviderError, reason, setting

# Distilled motion grammar, not reusable shot sequences or customer-facing presets.
REFERENCES = {
    "tactile": {
        "source": "https://whatships.com/videos/mtioon/",
        "grammar": "Recurring product objects; spring settling; asymmetric compositions; alternate dense graphic passages with quiet product proof. Carry object identities through spatial match cuts. Give a useful control the starring role, not an invented mascot.",
    },
    "editorial": {
        "source": "https://whatships.com/videos/motion-opus-5-5/",
        "grammar": "Restrained palette; purposeful changes between command, execution and result; readable closeups; type used as a rhythmic event; contrast hard cuts with continuous camera movement. Hold on actual proof.",
    },
    "precision": {
        "source": "https://www.remotion.dev/docs/spring",
        "grammar": "Stable full-screen product proof; tight detail isolation; precise masks and short type entrances; continuity of position and scale. Motion explains a relationship. Avoid gratuitous bounce.",
    },
}

RULES = """You are the director, motion designer, and sound designer of a product launch film.
Produce a film-specific concept and state list, not a presentation or a fixed sequence of templates.
Reference grammar informs decisions; never copy reference content, logos, characters, or claims.
Do not always start with text or end with a logo. Do not repeat title-above-floating-screen scenes.
Choose a visual motif grounded in the supplied product. Each shot must prove or express something specific.
Alternate visual density and pacing. Use purposeful cuts, spatial matches, masks, kinetic type, and springs as appropriate; do not force every technique into every film.
A persistent layer ID represents one object: for entry=match its first geometry MUST exactly equal that ID's last state in the preceding shot. A match cut may swap the captured pixels; do not claim it is a pixel-identical continuous take.
Use one-container morphing locally where useful, not as a rule for the entire film.
Render contract: 1920x1080, 30fps, deterministic frame-based motion, one shared BPM (100/120/150/180), local beat coordinates. No CSS, JS, URLs, arbitrary assets, fabricated UI, or placeholder copy. Avoid decorative linear gradients.
Only real captured product pixels may depict the UI. Text INSIDE a product is not a capability OF that product. The user's feature brief supplies product facts and intended audience; you may express those facts even when this capture shows only part of the workflow. Distinguish supplied facts from observed actions. Never pretend an uncaptured interaction was filmed. Do not infer capabilities from sample project names. No invented metrics, outcomes, testimonials, pricing, or brand assets.
Keep product interactions unobstructed. One live footage layer per shot; it must stay readable and keep each recorded click in frame. Do not overlay headline text on the clicked control. Every supplied feature capture must appear as footage at least once, in capture order; you may interleave or bookend still/details/type shots.
Typography: one short thought per shot, at most eight words total. Place type deliberately, with enough width and height; keep it inside the canvas, visible for at least a second. No tiny captions.
Do not overlay plain text directly on captured pixels. Put it in negative space or over a purpose-designed opaque shape with contrasting ink. Product UI is usually light: white headlines on white screenshots are unreadable. You may use an entire shot for kinetic typography. Do not give every shot a caption.
Sound: at most a few purposeful whooshes for morphs, ticks for graphic punctuation, thumps for a key landing. Do not synthesize fake UI clicks: those already come from actual recorded events.
Plan a distinct composition for each purpose; avoid three consecutive shots with the same composition. Do not fill time just to hit the target. Leave breathing room after an action.
Aim for a motion designer's showreel of THIS product. A row of full-screen captures with labels is an unacceptable final design. Invent a recurring visual device from real details: a control isolated and enlarged, a captured card that expands, typography that occupies negative space, or a colored shape that carries the eye into the next product view. These are ingredients, not a mandatory sequence. Use at least two meaningful geometric state changes across the film. Readable proof holds typically need 3–4 seconds; graphical punctuation can be 1–2 seconds. Do not hold each screen for 8 seconds.
VOCABULARY. A camera frames part of a footage/product/detail source: cam_x, cam_y (focal point 0-1),
cam_zoom (1 = whole source, capped per capture). Set focus:"click-N" to frame a recorded click; Cutroom
fills in its coordinates. Shot drift {x,y,zoom} keeps a hold alive at a constant rate; layer depth 0-1
scales it for parallax. elevation 0-1 lifts a layer with a soft shadow. backdrop: flat, or radial light
(x,y,color2), optional grain 0-0.15. Shapes: rect, line (stroke), segments (count, gap) for rails or
sprockets, ring (stroke) with target_layer + target:"click-N" to circle a real control. Text font:
sans, display (serif, weight 400) or mono. A static hold is fine while it is being read; it is
rejected only when it outlasts its reading time.
"""


def contact_sheet(
    folder: Path,
    items: list[tuple[str, str]],
    output: str,
    *,
    tile: tuple[int, int] = (480, 270),
    columns: int = 3,
) -> str:
    """Local allowlisted assets only; labels survive into the vision evidence."""
    cell_w, cell_h = tile[0], tile[1] + 30
    canvas = Image.new(
        "RGB", (columns * cell_w, math.ceil(len(items) / columns) * cell_h), "#eeeeee"
    )
    draw = ImageDraw.Draw(canvas)
    for i, (name, label) in enumerate(items):
        if not re.fullmatch(
            r"(?:(?:scene-\d{1,2}|preview-\d{1,2}-\d+|source-\d{1,2}-(?:start|end)|click-\d{1,2}-\d{1,2})\.jpg|detail-\d{1,2}-\d\.png|review-[\w-]+\.jpg)",
            name,
        ):
            raise ValueError("Invalid director evidence asset.")
        with Image.open(folder / name) as source:
            image = source.convert("RGB")
            image.thumbnail(tile)
        x, y = i % columns * cell_w, i // columns * cell_h
        canvas.paste(image, (x, y + 30))
        draw.text((x + 8, y + 8), label[:75], fill="black")
    canvas.save(folder / output, quality=88)
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def chunked_sheets(
    folder: Path, items: list[tuple[str, str]], stem: str, size: int, **sheet
) -> list[str]:
    return [
        contact_sheet(folder, items[i : i + size], f"{stem}-{k}.jpg", **sheet)
        for k, i in enumerate(range(0, len(items), size))
    ]


def source_frames(folder: Path, scenes: list[dict]) -> list[tuple[str, str]]:
    """Show native UI changes so the director/critic doesn't mistake them for camera motion."""
    raw = folder / "raw.webm"
    if not raw.exists():
        return []
    result = []
    for index, scene in enumerate(scenes[:8]):
        start, end = float(scene["start"]), float(scene["end"])
        for label, time in (("start", start + 1 / 30), ("end", max(start, end - 1 / 30))):
            name = f"source-{index}-{label}.jpg"
            target = folder / name
            stamp = folder / f"source-{index}-{label}.json"
            identity = {
                "time": time,
                "raw_bytes": raw.stat().st_size,
                "raw_mtime": raw.stat().st_mtime_ns,
            }
            if (
                not target.exists()
                or not stamp.exists()
                or json.loads(stamp.read_text()) != identity
            ):
                target.unlink(missing_ok=True)
                completed = subprocess.run(
                    [
                        imageio_ffmpeg.get_ffmpeg_exe(),
                        "-v",
                        "error",
                        "-y",
                        "-ss",
                        str(time),
                        "-i",
                        str(raw),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=960:540:force_original_aspect_ratio=decrease",
                        str(target),
                    ],
                    capture_output=True,
                    timeout=20,
                )
                if completed.returncode or not target.exists():
                    raise ValueError("Could not inspect the recorded source frames.")
                stamp.write_text(json.dumps(identity))
            result.append((name, f"RAW {scene['thumbnail']} {label.upper()} (native UI)"))
    return result


MAX_CLICK_CROPS = 4


def click_crops(folder: Path, scenes: list[dict]) -> list[tuple[str, str]]:
    """Native-resolution crops around each recorded click, so the director sees real control size."""
    raw = folder / "raw.webm"
    if not raw.exists():
        return []
    result = []
    for index, scene in enumerate(scenes[:8]):
        scale = float(scene.get("source_scale") or 1)
        width, height = round(960 * scale), round(540 * scale)
        for n, event in enumerate(clicks(scene)[:MAX_CLICK_CROPS]):
            if event.get("x") is None or event.get("y") is None:
                continue
            name = f"click-{index}-{n}.jpg"
            target = folder / name
            stamp = folder / f"click-{index}-{n}.json"
            identity = {
                "time": event["time"],
                "x": event["x"],
                "y": event["y"],
                "scale": scale,
                "raw_bytes": raw.stat().st_size,
                "raw_mtime": raw.stat().st_mtime_ns,
            }
            if (
                not target.exists()
                or not stamp.exists()
                or json.loads(stamp.read_text()) != identity
            ):
                target.unlink(missing_ok=True)
                cx, cy = event["x"] * scale, event["y"] * scale
                crop = (
                    f"crop=w=min({width}\\,iw):h=min({height}\\,ih)"
                    f":x=min(max({cx:.2f}-out_w/2\\,0)\\,iw-out_w)"
                    f":y=min(max({cy:.2f}-out_h/2\\,0)\\,ih-out_h)"
                )
                # Crops are advisory evidence: a click past the recording's end or a
                # decoder failure drops that crop rather than aborting the take.
                try:
                    completed = subprocess.run(
                        [
                            imageio_ffmpeg.get_ffmpeg_exe(),
                            "-v",
                            "error",
                            "-y",
                            "-ss",
                            str(float(event["time"])),
                            "-i",
                            str(raw),
                            "-frames:v",
                            "1",
                            "-vf",
                            crop,
                            str(target),
                        ],
                        capture_output=True,
                        timeout=20,
                    )
                except (ValueError, subprocess.TimeoutExpired, OSError):
                    continue
                if completed.returncode or not target.exists():
                    target.unlink(missing_ok=True)
                    continue
                stamp.write_text(json.dumps(identity))
            result.append((name, f"{scene['thumbnail']} / click-{n} ({event.get('label', '')})"))
    return result


def capture_summary(scene: dict) -> dict:
    keys = ("thumbnail", "label", "start", "end", "details", "interactions", "viewport", "focus")
    return {
        **{k: scene[k] for k in keys if k in scene},
        "clicks": [
            {
                "name": f"click-{n}",
                "label": e.get("label", ""),
                "time": e["time"],
                "x": e.get("x"),
                "y": e.get("y"),
            }
            for n, e in enumerate(clicks(scene))
        ],
        "zoom_cap": {
            "footage": zoom_cap("footage", scene),
            "product": zoom_cap("product", scene),
        },
    }


def evidence_scenes(scenes: list[dict]) -> list[dict]:
    return [s for s in scenes if s.get("action") != "overview"][:8]


def constrain_geometry(plan: FilmDirection, scenes: list[dict] | None = None) -> FilmDirection:
    """Resolve click focus and clamp the camera, preserving the director's composition.

    Footage keeps the size the director chose; readability is measured by validate_evidence.
    """
    plan = plan.model_copy(deep=True)
    # Reusing a capture as an animated background must not replay the same interaction.
    # Keep the clearest proof take live; other appearances use its settled still.
    for source in {shot.source for shot in plan.shots}:
        candidates = [
            shot
            for shot in plan.shots
            if shot.source == source and any(layer.kind == "footage" for layer in shot.layers)
        ]
        if len(candidates) > 1:
            proof = max(
                candidates,
                key=lambda shot: (
                    shot.composition == "product",
                    -len(shot.layers),
                    shot.beats * 60 / shot.bpm,
                ),
            )
            for shot in candidates:
                if shot is not proof:
                    for layer in shot.layers:
                        if layer.kind == "footage":
                            layer.kind = "product"
    if scenes is not None:
        plan = resolve_focus(plan, {s["thumbnail"]: s for s in evidence_scenes(scenes)})
    for shot in plan.shots:
        for layer in shot.layers:
            if layer.kind == "footage":
                for state in layer.states:
                    state.rotation = 0
    return plan


def click_seconds(shot, source: dict) -> list[tuple[str, float]]:
    """Shot-local seconds of each recorded click, using the composition's speed rule."""
    duration = shot.beats * 60 / shot.bpm
    speed = max(1, max(0.4, source["end"] - source["start"]) / duration)
    return [
        (f"click-{i}", (e["time"] - source["start"]) / speed)
        for i, e in enumerate(clicks(source))
        if source["start"] <= e["time"] < source["end"]
    ]


GEOMETRY = ("x", "y", "w", "h", "radius", "rotation", "opacity", "cam_x", "cam_y", "cam_zoom")


def moving_spans(shot) -> list[tuple[float, float, str]]:
    """Beat intervals where a layer changes, tagged with the layer kind."""
    spans = []
    for layer in shot.layers:
        for a, b in zip(layer.states, layer.states[1:], strict=False):
            if b.ease != "hold" and any(getattr(a, k) != getattr(b, k) for k in GEOMETRY):
                spans.append((a.beat, b.beat, layer.kind))
        if layer.kind == "text" and layer.entrance != "none":
            first = next((s.beat for s in layer.states if s.opacity > 0.5), None)
            if first is not None:
                spans.append((first, first + 0.8 * shot.bpm / 60, "text"))
    return sorted(spans)


def static_spans(shot) -> list[tuple[float, float]]:
    drift = shot.drift
    if any(layer.kind == "footage" for layer in shot.layers) or any((drift.x, drift.y, drift.zoom)):
        return []
    gaps, cursor = [], 0.0
    for start, end, _ in moving_spans(shot):
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < shot.beats:
        gaps.append((cursor, shot.beats))
    return gaps


def hold_budget(shot, start_beat: float) -> float:
    words = sum(
        len(layer.text.split())
        for layer in shot.layers
        if layer.kind == "text"
        and (first := next((s.beat for s in layer.states if s.opacity > 0.5), None)) is not None
        and first <= start_beat
    )
    landed = any(
        end == start_beat and kind not in ("text", "shape") for _, end, kind in moving_spans(shot)
    )
    return max(1.2, 0.3 * words + 0.6, 2.0 if landed else 0)


def layout_at(layer, beat: float) -> dict:
    """Sample planned rectangles for layout checks; rendering owns exact spring physics."""
    for before, after in zip(layer.states, layer.states[1:], strict=False):
        if before.beat <= beat < after.beat:
            t = (beat - before.beat) / (after.beat - before.beat)
            if after.ease == "hold":
                t = 0
            elif after.ease == "smooth":
                t = t * t * (3 - 2 * t)
            return {
                key: getattr(before, key) + t * (getattr(after, key) - getattr(before, key))
                for key in GEOMETRY
            }
    return layer.states[-1].model_dump()


def rects_overlap(a: dict, b: dict) -> bool:
    return (
        a["x"] < b["x"] + b["w"]
        and a["x"] + a["w"] > b["x"]
        and a["y"] < b["y"] + b["h"]
        and a["y"] + a["h"] > b["y"]
    )


def covers(backing: dict, text: dict) -> bool:
    return (
        backing["opacity"] >= 0.95
        and backing["x"] <= text["x"]
        and backing["y"] <= text["y"]
        and backing["x"] + backing["w"] + 1e-6 >= text["x"] + text["w"]
        and backing["y"] + backing["h"] + 1e-6 >= text["y"] + text["h"]
    )


def placed_at(shot, layer, beat: float, state: dict | None = None) -> dict:
    """The rectangle the renderer actually draws at a beat: planned geometry plus shot drift."""
    return drifted(
        state if state is not None else layout_at(layer, beat),
        shot.drift.model_dump(),
        layer.depth,
        beat * 60 / shot.bpm,
    )


def drift_samples(shot, layer) -> list[tuple[float, dict]]:
    """Each keyframe and the shot end, where drift has carried a layer furthest."""
    samples = [(state.beat, state.model_dump()) for state in layer.states]
    samples.append((float(shot.beats), layout_at(layer, shot.beats)))
    return [(beat, placed_at(shot, layer, beat, state)) for beat, state in samples]


def validate_evidence(plan: FilmDirection, scenes: list[dict], target: int) -> list[str]:
    """Concrete quality gates supplement the schema and the visual critic."""
    issues = []
    sources = {s.get("thumbnail"): s for s in evidence_scenes(scenes)}
    bpms = {s.bpm for s in plan.shots}
    if len(bpms) != 1:
        issues.append("Use one BPM for the whole film.")
    total = sum(s.beats * 60 / s.bpm for s in plan.shots)
    if total > target + 0.05:
        issues.append(f"Film is {total:.1f}s; maximum target is {target}s.")
    filmed = []
    for index, shot in enumerate(plan.shots):
        prefix = f"Shot {index}"
        source = sources.get(shot.source)
        if source is None:
            issues.append(f"{prefix}: unknown capture {shot.source}.")
            continue
        duration = shot.beats * 60 / shot.bpm
        if (
            max(abs(shot.drift.x), abs(shot.drift.y)) * duration > 0.12 + 1e-9
            or abs(shot.drift.zoom) * duration > 0.15 + 1e-9
        ):
            issues.append(
                f"{prefix}: drift travels too far over {duration:.2f}s (at most 0.12 canvas "
                "units on x/y and 0.15 zoom per shot); reduce drift."
            )
        footage = [layer for layer in shot.layers if layer.kind == "footage"]
        if len(footage) > 1:
            issues.append(f"{prefix}: use at most one live footage layer.")
        if footage:
            filmed.append(shot.source)
            needed = max(
                (e["time"] - source["start"] + 0.5 for e in source.get("interactions", [])),
                default=1,
            )
            # A long clone of the capture's last frame is dead time, not product proof.
            maximum_proof = max(min(needed, 12), source["end"] - source["start"]) + 1.2
            if shot.beats * 60 / shot.bpm > maximum_proof:
                issues.append(
                    f"{prefix}: live proof exceeds its {maximum_proof:.2f}s useful window and would freeze the last frame. Shorten this shot; use a separate still/detail composition for a further visual idea."
                )
            if shot.beats * 60 / shot.bpm < min(needed, 12):
                issues.append(
                    f"{prefix}: hold at least {min(needed, 12):.2f}s to show the interaction."
                )
            view = source.get("viewport", {"width": 1920, "height": 1080})
            seconds = shot.beats * 60 / shot.bpm
            beats_per_second = shot.bpm / 60
            for beat, state in drift_samples(shot, footage[0]):
                if state["opacity"] > 0.5 and effective_scale(state, view) < 0.65:
                    issues.append(
                        f"{prefix}: live footage is not readable at beat {beat:g} "
                        f"(scale {effective_scale(state, view):.2f} < 0.65). Enlarge it or push the camera in."
                    )
                    break
                edge = min(beat, shot.beats - beat) / beats_per_second
                if state["opacity"] < 0.98 and edge > 0.3:
                    issues.append(f"{prefix}: footage may only fade within 0.3s of a shot edge.")
                    break
            recorded = clicks(source)
            for name, at in click_seconds(shot, source):
                if not 0 <= at < seconds or "x" not in recorded[int(name[6:])]:
                    continue
                state = placed_at(shot, footage[0], at * beats_per_second)
                aspect = (view["width"], view["height"])
                left, top, width, height = visible_window(state, aspect)
                px, py = click_point(source, name)
                cx, cy = project(state, aspect, px, py)
                margin = 0.04
                if not (
                    left + margin * width <= px <= left + width * (1 - margin)
                    and top + margin * height <= py <= top + height * (1 - margin)
                    and 0.025 <= cx <= 0.975
                    and 0.025 <= cy <= 0.975
                ):
                    issues.append(
                        f"{prefix}: {name} happens outside the camera frame at {at:.2f}s. Keep the action in view."
                    )
                if state["opacity"] < 0.98:
                    issues.append(f"{prefix}: footage must be opaque while {name} happens.")
        words = sum(len(layer.text.split()) for layer in shot.layers if layer.kind == "text")
        if words > 8:
            issues.append(f"{prefix}: at most 8 on-screen words.")
        for start, end in static_spans(shot):
            seconds_static = (end - start) * 60 / shot.bpm
            budget = hold_budget(shot, start)
            if seconds_static > budget + 1e-6:
                issues.append(
                    f"{prefix}: frame holds static for {seconds_static:.2f}s from beat {start:g}; "
                    f"its reading budget is {budget:.2f}s. Shorten the hold, add a purposeful move, or cut."
                )
        ids = {layer.id for layer in shot.layers}
        for layer in shot.layers:
            if layer.target_layer is not None and (
                layer.kind != "shape" or layer.target_layer not in ids - {layer.id}
            ):
                issues.append(
                    f"{prefix}: {layer.id} target_layer {layer.target_layer} must be a shape pointing at another layer in this shot."
                )
            if layer.target is not None and layer.target_layer is None:
                issues.append(f"{prefix}: {layer.id} target needs a target_layer.")
        for layer in shot.layers:
            if layer.kind.startswith("detail-") and int(layer.kind[-1]) >= len(
                source.get("details", [])
            ):
                issues.append(f"{prefix}: {layer.kind} was not captured.")
            if layer.kind == "text":
                visible = [s for _, s in drift_samples(shot, layer) if s["opacity"] > 0.5]
                if not visible or any(
                    s["x"] < 0.025
                    or s["y"] < 0.025
                    or s["x"] + s["w"] > 0.975
                    or s["y"] + s["h"] > 0.975
                    for s in visible
                ):
                    issues.append(f"{prefix}: keep readable text inside 2.5% safe margins.")
                if shot.beats * 60 / shot.bpm < 1:
                    issues.append(f"{prefix}: give text at least one second.")
                # Compare simultaneous states, not all positions across the entire shot.
                # Otherwise an opening fullscreen UI incorrectly forbids later type in
                # the space it has already vacated. The rendered critic checks in-between frames.
                media = [
                    candidate
                    for candidate in shot.layers[: shot.layers.index(layer)]
                    if candidate.kind not in ("shape", "text")
                ]
                times = sorted(
                    {state.beat for candidate in shot.layers for state in candidate.states}
                )
                times = sorted(
                    set(times + [(a + b) / 2 for a, b in zip(times, times[1:], strict=False)])
                )
                for beat in times:
                    state = layout_at(layer, beat)
                    if state["opacity"] <= 0.5:
                        continue
                    overlaps = any(
                        rects_overlap(state, layout_at(other, beat))
                        and layout_at(other, beat)["opacity"] > 0.5
                        for other in media
                    )
                    backing = any(
                        other.kind == "shape" and covers(layout_at(other, beat), state)
                        for other in shot.layers[: shot.layers.index(layer)]
                    )
                    if overlaps and not backing:
                        issues.append(
                            f"{prefix}: text {layer.id} overlaps product pixels without an opaque backing at beat {beat:g}. Move type to negative space or a dedicated graphic shot."
                        )
                        break
        if index >= 2 and all(
            s.composition == shot.composition for s in plan.shots[index - 2 : index]
        ):
            issues.append(
                f"{prefix}: three consecutive {shot.composition} compositions; vary the visual treatment."
            )
        if shot.entry == "match":
            previous = {layer.id: layer for layer in plan.shots[index - 1].layers} if index else {}
            shared = [layer for layer in shot.layers if layer.id in previous]
            if not shared:
                issues.append(
                    f"{prefix}: a match cut needs a persistent object from the previous shot."
                )
            for layer in shared:
                before = previous[layer.id].states[-1].model_dump(exclude={"beat", "ease"})
                after = layer.states[0].model_dump(exclude={"beat", "ease"})
                if before != after:
                    issues.append(
                        f"{prefix}: match-cut geometry for {layer.id} must equal the previous final state."
                    )
    if filmed != list(sources):
        issues.append(
            "Show each supplied capture exactly once as live footage, in capture order; use stills for other shots."
        )
    moving = sum(
        any(
            any(
                getattr(state, key) != getattr(layer.states[0], key)
                for key in ("x", "y", "w", "h", "radius", "rotation")
            )
            for state in layer.states[1:]
        )
        for shot in plan.shots
        for layer in shot.layers
        if layer.kind != "text"
    )
    if moving < 2:
        issues.append(
            "The film needs at least two purposeful object/camera/mask motions; static screenshots with labels are not sufficient."
        )
    return issues


def compile_direction(plan: FilmDirection, scenes: list[dict]) -> list[dict]:
    sources = {s["thumbnail"]: s for s in evidence_scenes(scenes)}
    clips = []
    for index, shot in enumerate(plan.shots):
        live = any(layer.kind == "footage" for layer in shot.layers)
        source = sources[shot.source]
        clips.append(
            TimelineClip(
                id=f"directed-{index}",
                kind="browser",
                scene_id=source.get("id") or shot.source,
                label=shot.label,
                narration=source.get("narration", "") if live else "",
                duration=shot.beats * 60 / shot.bpm,
                motion="directed",
                direction=shot.model_dump(exclude={"source", "label"}),
            ).model_dump(mode="json")
        )
    return clips


def save_direction(folder: Path, plan: FilmDirection):
    run = (
        json.loads((folder / "director-run.json").read_text())
        if (folder / "director-run.json").exists()
        else {}
    )
    (folder / "director-plan.json").write_text(plan.model_dump_json(indent=2))
    (folder / "style-guide.json").write_text(
        json.dumps(
            {
                "concept": plan.concept,
                "grammar": plan.grammar,
                "reference": REFERENCES[plan.reference],
                "reference_observations": run.get("reference_analysis"),
                "prompt_version": run.get("prompt_version"),
                "strategy": run.get("strategy"),
                "render": {"width": 1920, "height": 1080, "fps": 30},
            },
            indent=2,
        )
    )
    cursor = 0
    rows = []
    for i, shot in enumerate(plan.shots):
        frames = round(shot.beats * 1800 / shot.bpm)
        rows.append(
            {
                "shot": i,
                "start_frame": cursor,
                "end_frame": cursor + frames,
                "source": shot.source,
                "purpose": shot.purpose,
                "entry": shot.entry,
                "layers": [layer.model_dump() for layer in shot.layers],
                "hits": [hit.model_dump() for hit in shot.hits],
            }
        )
        cursor += frames
    (folder / "beat-grid.json").write_text(json.dumps(rows, indent=2))


def direct_film(
    title: str,
    brief: str,
    scenes: list[dict],
    folder: Path,
    target: int = 30,
    creative_direction: str = "",
    evidence=None,
    *,
    strategy: str | None = None,
    reasoner=None,
    reference_urls: list[str] | None = None,
    reference_analysis: dict | None = None,
    geometry_effort: str | None = None,
    prepared_treatment: FilmTreatment | None = None,
) -> FilmDirection:
    reasoner = reasoner or reason
    strategy = strategy or setting("CUTROOM_PROMPT_STRATEGY", "storyboard")
    if reference_urls:
        from server.video_reference import analyze_references

        reference_analysis = analyze_references(reference_urls, folder, reasoner)
    sources = evidence_scenes(scenes)
    if not sources:
        raise ValueError("Capture a feature before directing its film.")
    assets = []
    for source in sources:
        assets.append((source["thumbnail"], source["thumbnail"]))
        assets.extend(
            (name, f"{source['thumbnail']} / detail-{i}")
            for i, name in enumerate(source.get("details", [])[:3])
        )
    assets.extend(source_frames(folder, sources))
    assets.extend(click_crops(folder, sources))
    # 15 tiles of 480x300 make a 1440x1500 sheet: within the size the model actually sees.
    images = chunked_sheets(folder, assets, "director-evidence", 15)
    schema = json.dumps(FilmDirection.model_json_schema())
    prompt = (
        RULES + f"\nProduct: {title}\nBrief: {brief}\nArt direction: {creative_direction}\n"
        f"Maximum duration: {target}s. Reference grammars: {json.dumps(REFERENCES)}\n"
        "Live proof windows (seconds; budget readable action, not frozen padding): "
        + json.dumps(
            [
                {
                    "source": s["thumbnail"],
                    "recorded_seconds": round(s["end"] - s["start"], 2),
                    "max_seconds": round(
                        max(
                            s["end"] - s["start"],
                            min(
                                max(
                                    (
                                        e["time"] - s["start"] + 0.5
                                        for e in s.get("interactions", [])
                                    ),
                                    default=1,
                                ),
                                12,
                            ),
                        )
                        + 1.2,
                        2,
                    ),
                }
                for s in sources
            ]
        )
        + "\n"
        + f"Captures: {json.dumps([capture_summary(s) for s in sources])}\nVisible evidence: {json.dumps(evidence or [])[:12000]}\n"
        "Return the full film as JSON matching this schema. Keep concept to one sentence and grammar to three short sentences. Layer states use normalized x/y/w/h, pixel radius, local beat. "
        "The easing on a destination state controls movement toward that state. Omitted geometry inherits the preceding state. To hold, repeat geometry at a later beat before the next movement. Order layers back-to-front. "
        "Text uses size in pixels. Product is the settled screenshot; footage is the actual interaction. "
        "Do not cover footage with an opaque product screenshot. RAW START/END frames show the native recording progression; they are evidence only, not additional render assets. Account for native full-screen previews or navigation when planning the story.\n"
        + schema
    )
    prompt = enriched_prompt(prompt, strategy, reference_analysis)
    treatment = prepared_treatment
    if strategy in ("storyboard", "studies"):
        treatment_prompt = (
            prompt.split("Return the full film as JSON")[0]
            + "\n"
            + enriched_prompt(TREATMENT, strategy, reference_analysis)
        )
        (folder / "treatment-prompt.txt").write_text(treatment_prompt)
        treatment_errors = []
        for _attempt in range(0 if treatment is not None else 2):
            proposed = reasoner(
                treatment_prompt + "\nValidation feedback: " + json.dumps(treatment_errors),
                images,
                max_tokens=4000,
                motion=True,
            )
            (folder / f"treatment-proposal-{_attempt}.json").write_text(
                json.dumps(proposed, indent=2)
            )
            try:
                treatment = FilmTreatment.model_validate(proposed)
                break
            except ValueError as exc:
                treatment_errors = [str(exc)[:2000]]
        if treatment is None:
            raise ValueError("The director could not produce a usable treatment.")
        (folder / "director-treatment.json").write_text(treatment.model_dump_json(indent=2))
        prompt += (
            "\nImplement this chosen treatment, adapting only where render constraints require it:\n"
            + treatment.model_dump_json()
        )
    (folder / "director-run.json").write_text(
        json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "strategy": strategy,
                "geometry_effort": geometry_effort or setting("CUTROOM_GEOMETRY_EFFORT", "medium"),
                "reference_analysis": reference_analysis,
            },
            indent=2,
        )
    )
    original_prompt = prompt
    errors = []
    previous = ""
    for attempt in range(3):
        try:
            request_prompt = prompt + "\nFix these validation findings: " + json.dumps(errors)
            (folder / f"director-prompt-{attempt}.txt").write_text(request_prompt)
            proposed = reasoner(
                request_prompt,
                images,
                max_tokens=10000,
                motion=True,
                effort=geometry_effort or setting("CUTROOM_GEOMETRY_EFFORT", "medium"),
            )
            previous = json.dumps(proposed)
            (folder / f"director-proposal-{attempt}.json").write_text(previous)
            plan = constrain_geometry(FilmDirection.model_validate(proposed), scenes)
            errors = validate_evidence(plan, scenes, target)
            if any(
                layer.get("target_x") is not None or layer.get("target_y") is not None
                for shot in proposed.get("shots", [])
                for layer in shot.get("layers", [])
            ):
                errors.append("target_x/target_y are set by Cutroom; use target")
            if not errors:
                save_direction(folder, plan)
                return plan
        except ProviderError:
            raise
        except (ValueError, TypeError) as exc:
            # Pydantic errors may include supplied content; keep them private to the revision call.
            errors = [str(exc)[:3000]]
        if previous:
            prompt = (
                original_prompt
                + "\nRepair this exact film and return the full JSON with the same schema. "
                + previous
            )
        (folder / "director-validation.json").write_text(
            json.dumps({"attempt": attempt + 1, "issues": errors}, indent=2)
        )
    raise ValueError(
        "The director could not produce a valid film within three attempts. Refine the feature or creative direction."
    )


MAX_EDGE = 1568
MAX_EVIDENCE_IMAGES = 60


def encode_sheet(canvas: Image.Image, folder: Path, name: str) -> str:
    canvas.save(folder / name, quality=88)
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def type_crops(folder: Path, plan: FilmDirection, jobs: list[dict]) -> list[str]:
    """Crop each text layer's settled, drifted rectangle 1:1 from the shot's last preview frame.

    Crops are shelf-packed into sheets of at most MAX_EDGE on each side; only a crop
    larger than a sheet is scaled down.
    """
    crops: list[Image.Image] = []
    for job in jobs:
        if job["index"] >= len(plan.shots):
            continue
        with Image.open(folder / f"preview-{job['index']}-{job['frames'] - 1}.jpg") as opened:
            frame = opened.convert("RGB")
        width, height = frame.size
        shot = plan.shots[job["index"]]
        for layer in shot.layers:
            if layer.kind != "text" or not layer.states:
                continue
            # The last preview frame is the shot end, where drift has moved the type furthest.
            last = placed_at(shot, layer, shot.beats, layer.states[-1].model_dump())
            left = max(0, int(last["x"] * width) - 24)
            top = max(0, int(last["y"] * height) - 24)
            right = min(width, math.ceil((last["x"] + last["w"]) * width) + 24)
            bottom = min(height, math.ceil((last["y"] + last["h"]) * height) + 24)
            if right > left and bottom > top:
                crop = frame.crop((left, top, right, bottom))
                if crop.width > MAX_EDGE or crop.height > MAX_EDGE:
                    crop.thumbnail((MAX_EDGE, MAX_EDGE))
                crops.append(crop)
    sheets: list[list[tuple[int, int, Image.Image]]] = []
    x = y = row_h = 0
    for crop in crops:
        if not sheets:
            sheets.append([])
        if x + crop.width > MAX_EDGE:
            x, y, row_h = 0, y + row_h, 0
        if y + crop.height > MAX_EDGE:
            sheets.append([])
            x = y = row_h = 0
        sheets[-1].append((x, y, crop))
        x += crop.width
        row_h = max(row_h, crop.height)
    images = []
    for k, placed in enumerate(sheets):
        canvas = Image.new(
            "RGB",
            (max(c.width + px for px, _, c in placed), max(c.height + py for _, py, c in placed)),
            "#eeeeee",
        )
        for px, py, crop in placed:
            canvas.paste(crop, (px, py))
        images.append(encode_sheet(canvas, folder, f"review-type-{k}.jpg"))
    return images


def review_evidence(
    folder: Path, plan: FilmDirection, jobs: list[dict], scenes: list[dict]
) -> list[str]:
    """Per-shot half-second sheets, settled type crops, click crops and RAW source frames.

    Every image stays within MAX_EDGE on its long edge, and at most 60 are returned.
    """
    images, offset = [], 0.0
    for job in jobs:
        items = [
            (
                f"preview-{job['index']}-{frame}.jpg",
                f"Shot {job['index']} / {offset + frame / 30:.2f}s / frame {frame}",
            )
            for frame in preview_frame_list(job["frames"])
        ]
        images += chunked_sheets(
            folder, items, f"review-shot-{job['index']}", 4, tile=(784, 441), columns=2
        )
        offset += job["frames"] / 30
    images += type_crops(folder, plan, jobs)
    used = evidence_scenes(scenes)
    images += chunked_sheets(folder, click_crops(folder, used), "review-clicks", 12)
    images += chunked_sheets(folder, source_frames(folder, used), "review-sources", 12)
    return images[:MAX_EVIDENCE_IMAGES]


def gate(review: FilmReview) -> Literal["passed", "needs_review"]:
    """Pass only when every axis is at least 8 and no finding, top-level or nested, is blocking."""
    nested = any(f.blocking for a in AXES for f in getattr(review, a).findings)
    if min(review.scores().values()) >= 8 and not review.blocking and not nested:
        return "passed"
    return "needs_review"


def regressed(before: FilmReview, after: FilmReview) -> list[str]:
    return [a for a in AXES if before.scores()[a] - after.scores()[a] >= 2]


CRITIC = """Score these actual rendered frames of a product launch film on seven axes, 1-10.
Anchors (5 = acceptable draft, 8 = launch-ready):
- readability: 5 = key UI legible only on pause; 8 = the clicked control and its result read at 1080p.
- canvas: 5 = large unused areas or thin bands; 8 = the dominant object fills its frame by intent.
- motion: 5 = moves happen but do not lead the eye; 8 = every move guides attention to a real detail.
- pacing: 5 = holds outlast their reading; 8 = contrast of density and speed, ending lands.
- typography: 5 = readable but timid or awkward breaks; 8 = clear hierarchy, no orphans or clipping.
- continuity: 5 = cuts register as jumps; 8 = matches and scale changes feel intentional.
- specificity: 5 = could be any SaaS; 8 = concept and copy belong to this product only.
For EVERY axis give 1-4 observations (shot, time, what is visible). Observations may be positive.
For any axis below 8 give actionable findings (problem plus the intended change).
List blocking defects separately: clipped_text (settled text cropped), hidden_click (recorded
action outside the frame or covered), unreadable_type (added text illegible). Do not invent
criticism of strong work; a score of 8-10 needs observations, not defects.
Focus on OUR composition, not the customer's UI styling. RAW frames show native UI changes.
Never request UI that is absent from the source frame, recoloring product pixels, or enlarging every native UI label. Live footage includes a short cursor lead-in before the destination; that is not a duplicated shot. White or light added type on a light screenshot is a readability defect.
Images: per-shot sheets, settled type crops, click crops, RAW source frames.
Return JSON matching this schema: """


def revision_brief(review: FilmReview) -> str:
    """Lead with the weakest axes and blocking defects so the revision targets them first."""
    scores = review.scores()
    weakest = sorted(AXES, key=lambda a: scores[a])
    findings = [f.model_dump() for a in weakest for f in getattr(review, a).findings]
    return (
        f"Axes, lowest first: {json.dumps({a: scores[a] for a in weakest})}\n"
        f"Blocking defects: {json.dumps([f.model_dump() for f in review.blocking])}\n"
        f"Findings: {json.dumps(findings)}"
    )


USAGE_KEYS = ("provider", "model", "seconds", "usage", "usage_attempts")


def usage_record(telemetry: dict) -> dict:
    """Provider accounting only: never prompts, images or credentials."""
    return {k: telemetry[k] for k in USAGE_KEYS if k in telemetry}


def review_passes() -> int:
    """CUTROOM_REVIEW_PASSES as a revision budget of 0-4; anything non-integer means 2."""
    try:
        return max(0, min(4, int(setting("CUTROOM_REVIEW_PASSES", "2"))))
    except ValueError:
        return 2


def review_film(
    plan: FilmDirection,
    scenes: list[dict],
    folder: Path,
    theme: str,
    target: int,
    checkpoint=None,
    *,
    reasoner=None,
    geometry_effort: str | None = None,
) -> tuple[FilmDirection, dict]:
    """Score rendered frames on a seven-axis rubric, with a bounded number of revisions.

    A revision is kept only if it passes the evidence validator and its re-score drops no
    axis by two or more. Every revision request, accepted or not, spends one pass of the
    budget. The report summarizes sampled visual evidence, not certified quality.
    """
    from server.video_composition import prepare_compositions
    from server.video_timeline import compile_timeline

    reasoner = reasoner or reason
    creative_context = ""
    if (folder / "director-treatment.json").exists():
        creative_context = (
            "\nPreserve the selected treatment: " + (folder / "director-treatment.json").read_text()
        )
    budget = review_passes()
    report = {
        "status": "unavailable",
        "rubric": "film-rubric-v1",
        "passes": [],
        "revision_count": 0,
    }
    # The best plan, its review and the frames that review saw always travel together, so
    # a revision never reads frames of a different (rejected) film.
    best_plan, best_review, best_images, candidate = plan, None, [], None
    attempt = 0
    while True:
        if checkpoint:
            checkpoint()
        clips = compile_direction(plan, scenes)
        compiled = compile_timeline(
            {"payload": {"scenes": scenes}}, [TimelineClip.model_validate(c) for c in clips]
        )
        prepare_compositions(
            folder,
            folder / "raw.webm",
            compiled,
            theme,
            [None] * len(compiled),
            checkpoint,
            preview=True,
        )
        jobs = json.loads((folder / "motion-jobs.json").read_text())["jobs"]
        try:
            images = review_evidence(folder, plan, jobs, scenes)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            report["passes"].append(
                {"attempt": attempt, "error": "Visual review evidence could not be built."}
            )
            break
        prompt = (
            CRITIC
            + json.dumps(FilmReview.model_json_schema())
            + f"\nFilm plan: {plan.model_dump_json()}"
        )
        telemetry: dict = {}
        try:
            review = FilmReview.model_validate(
                reasoner(
                    prompt + creative_context,
                    images,
                    max_tokens=12000,
                    motion=True,
                    telemetry=telemetry,
                )
            )
        except (ValueError, TypeError):
            report["passes"].append(
                {
                    "attempt": attempt,
                    "error": "Visual review did not return a usable report.",
                    "usage": usage_record(telemetry),
                }
            )
            break
        entry = {
            "attempt": attempt,
            "scores": review.scores(),
            "review": review.model_dump(),
            "usage": usage_record(telemetry),
        }
        report["passes"].append(entry)
        (folder / f"director-plan-{attempt}.json").write_text(plan.model_dump_json(indent=2))
        drops = regressed(best_review, review) if candidate is not None else []
        if drops:
            entry["rejected_revision"] = [f"Regressed {axis}" for axis in drops]
        else:
            if candidate is not None:
                report["revision_count"] += 1
            best_plan, best_review, best_images = plan, review, images
            report["final"] = {
                "attempt": attempt,
                "scores": review.scores(),
                "review": review.model_dump(),
            }
        candidate = None
        while budget > 0 and candidate is None and gate(best_review) != "passed":
            budget -= 1
            if checkpoint:
                checkpoint()
            rejections = [
                p["rejected_revision"] for p in report["passes"] if p.get("rejected_revision")
            ]
            revision_telemetry: dict = {}
            try:
                revised = FilmDirection.model_validate(
                    reasoner(
                        enriched_prompt(RULES, "detailed")
                        + creative_context
                        + "\nRevise the film to raise the lowest rubric axes and clear every blocking defect. "
                        "Keep the concept and unaffected shots. "
                        "Return the complete revised film, using exactly the same JSON schema and only existing assets.\n"
                        f"Maximum duration: {target}s. Prior revision rejections: {json.dumps(rejections)}\n"
                        f"{revision_brief(best_review)}\nExisting film: {best_plan.model_dump_json()}\nSchema: {json.dumps(FilmDirection.model_json_schema())}",
                        best_images,
                        max_tokens=10000,
                        motion=True,
                        effort=geometry_effort or setting("CUTROOM_GEOMETRY_EFFORT", "medium"),
                        telemetry=revision_telemetry,
                    )
                )
                revised = constrain_geometry(revised, scenes)
                issues = validate_evidence(revised, scenes, target)
                if issues:
                    # The best plan is unchanged; retry at once instead of re-scoring it.
                    entry.setdefault("rejected_revision", []).extend(issues)
                    continue
                candidate = revised
            except ProviderError as exc:
                entry.setdefault("rejected_revision", []).append(str(exc))
                budget = 0
            except (ValueError, TypeError) as exc:
                entry.setdefault("rejected_revision", []).append(str(exc)[:2000])
            finally:
                if revision_telemetry:
                    entry.setdefault("revision_usage", []).append(usage_record(revision_telemetry))
        if candidate is None:
            break
        plan = candidate
        attempt += 1
    if best_review is not None:
        report["status"] = gate(best_review)
    save_direction(folder, best_plan)
    (folder / "director-review.json").write_text(json.dumps(report, indent=2))
    return best_plan, report
