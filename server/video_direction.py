"""Evidence-grounded film direction, beat-grid compilation, and bounded visual revision."""

from __future__ import annotations

import base64
import io
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw

from server.video_direction_models import FilmDirection, FilmTreatment
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
Render contract: 1920x1080, 30fps, deterministic frame-based motion, one shared BPM (100/120/150/180), local beat coordinates. No CSS, JS, URLs, arbitrary assets, gradients, fabricated UI, or placeholder copy.
Only real captured product pixels may depict the UI. Text INSIDE a product is not a capability OF that product. The user's feature brief supplies product facts and intended audience; you may express those facts even when this capture shows only part of the workflow. Distinguish supplied facts from observed actions. Never pretend an uncaptured interaction was filmed. Do not infer capabilities from sample project names. No invented metrics, outcomes, testimonials, pricing, or brand assets.
Keep product interactions unobstructed. Footage layers must remain visible throughout, one per shot. Do not overlay headline text on the clicked control. Every supplied feature capture must appear as footage at least once, in capture order; you may interleave or bookend still/details/type shots.
Typography: one short thought per shot, at most eight words total. Place type deliberately, with enough width and height; keep it inside the canvas, visible for at least a second. No tiny captions.
Do not overlay plain text directly on captured pixels. Put it in negative space or over a purpose-designed opaque shape with contrasting ink. Product UI is usually light: white headlines on white screenshots are unreadable. You may use an entire shot for kinetic typography. Do not give every shot a caption.
Sound: at most a few purposeful whooshes for morphs, ticks for graphic punctuation, thumps for a key landing. Do not synthesize fake UI clicks: those already come from actual recorded events.
Plan a distinct composition for each purpose; avoid three consecutive shots with the same composition. Do not fill time just to hit the target. Leave breathing room after an action.
Aim for a motion designer's showreel of THIS product. A row of full-screen captures with labels is an unacceptable final design. Invent a recurring visual device from real details: a control isolated and enlarged, a captured card that expands, typography that occupies negative space, or a colored shape that carries the eye into the next product view. These are ingredients, not a mandatory sequence. Use at least two meaningful geometric state changes across the film. Readable proof holds typically need 3–4 seconds; graphical punctuation can be 1–2 seconds. Do not hold each screen for 8 seconds.
"""


def contact_sheet(folder: Path, items: list[tuple[str, str]], output: str) -> str:
    """Local allowlisted assets only; labels survive into the vision evidence."""
    canvas = Image.new("RGB", (1440, math.ceil(len(items) / 3) * 300), "#eeeeee")
    draw = ImageDraw.Draw(canvas)
    for i, (name, label) in enumerate(items):
        if not re.fullmatch(
            r"(?:(?:scene-\d{1,2}|preview-\d{1,2}-\d+)\.jpg|detail-\d{1,2}-\d\.png)", name
        ):
            raise ValueError("Invalid director evidence asset.")
        with Image.open(folder / name) as source:
            tile = source.convert("RGB")
            tile.thumbnail((480, 270))
        x, y = i % 3 * 480, i // 3 * 300
        canvas.paste(tile, (x, y + 30))
        draw.text((x + 8, y + 8), label[:75], fill="black")
    canvas.save(folder / output, quality=88)
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def evidence_scenes(scenes: list[dict]) -> list[dict]:
    return [s for s in scenes if s.get("action") != "overview"][:8]


def constrain_geometry(plan: FilmDirection) -> FilmDirection:
    """Project live takes into a readable safe viewport, preserving the chosen composition.

    Layout constraints belong in the renderer contract rather than consuming model retries
    for a screen that is a few pixels too small. Stills retain expressive off-screen motion.
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
    for shot in plan.shots:
        for layer in shot.layers:
            if layer.kind != "footage":
                continue
            for state in layer.states:
                state.w = min(1, max(0.65, state.w))
                state.h = min(1, max(0.65, state.h))
                state.x = min(1 - state.w, max(0, state.x))
                state.y = min(1 - state.h, max(0, state.y))
                state.opacity = 1
                state.rotation = 0
    return plan


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
                for key in ("x", "y", "w", "h", "opacity")
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
            if any(
                s.opacity < 0.98
                or s.w < 0.65
                or s.h < 0.65
                or s.x < 0
                or s.y < 0
                or s.x + s.w > 1.01
                or s.y + s.h > 1.01
                for s in footage[0].states
            ):
                issues.append(
                    f"{prefix}: keep live footage large, inside the canvas and fully opaque; use stills for expressive entrances."
                )
        words = sum(len(layer.text.split()) for layer in shot.layers if layer.kind == "text")
        if words > 8:
            issues.append(f"{prefix}: at most 8 on-screen words.")
        for layer in shot.layers:
            if layer.kind.startswith("detail-") and int(layer.kind[-1]) >= len(
                source.get("details", [])
            ):
                issues.append(f"{prefix}: {layer.kind} was not captured.")
            if layer.kind == "text":
                visible = [s for s in layer.states if s.opacity > 0.5]
                if not visible or any(
                    s.x < 0.025 or s.y < 0.025 or s.x + s.w > 0.975 or s.y + s.h > 0.975
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
    image = contact_sheet(folder, assets, "director-evidence.jpg")
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
        + f"Captures: {json.dumps([{k: s[k] for k in ('thumbnail', 'label', 'start', 'end', 'details', 'interactions', 'viewport', 'focus') if k in s} for s in sources])}\nVisible evidence: {json.dumps(evidence or [])[:12000]}\n"
        "Return the full film as JSON matching this schema. Keep concept to one sentence and grammar to three short sentences. Layer states use normalized x/y/w/h, pixel radius, local beat. "
        "The easing on a destination state controls movement toward that state. Omitted geometry inherits the preceding state. To hold, repeat geometry at a later beat before the next movement. Order layers back-to-front. "
        "Text uses size in pixels. Product is the settled screenshot; footage is the actual interaction. "
        "Do not cover footage with an opaque product screenshot.\n" + schema
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
                image,
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
                image,
                max_tokens=10000,
                motion=True,
                effort=geometry_effort or setting("CUTROOM_GEOMETRY_EFFORT", "medium"),
            )
            previous = json.dumps(proposed)
            (folder / f"director-proposal-{attempt}.json").write_text(previous)
            plan = constrain_geometry(FilmDirection.model_validate(proposed))
            errors = validate_evidence(plan, scenes, target)
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
    """Inspect rendered state sequences, with at most two targeted revision attempts.

    A self-assigned numeric grade is deliberately not used as a quality guarantee.
    The report records unresolved findings and review availability honestly.
    """
    from server.video_composition import prepare_compositions
    from server.video_timeline import compile_timeline

    reasoner = reasoner or reason
    creative_context = ""
    if (folder / "director-treatment.json").exists():
        creative_context = (
            "\nPreserve the selected treatment: " + (folder / "director-treatment.json").read_text()
        )
    report = {"status": "needs_review", "passes": [], "revision_count": 0}
    for attempt in range(3):
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
        items, offset = [], 0
        for job in jobs:
            # JS rounds halves upward. At 30fps selected durations have even frame counts.
            frames = sorted(
                {
                    0,
                    *[math.floor((job["frames"] - 1) * t + 0.5) for t in (0.2, 0.5, 0.8)],
                    job["frames"] - 1,
                }
            )
            for frame in frames:
                items.append(
                    (
                        f"preview-{job['index']}-{frame}.jpg",
                        f"Shot {job['index']} / {offset + frame / 30:.2f}s / frame {frame}",
                    )
                )
            offset += job["frames"] / 30
        image = contact_sheet(folder, items, f"director-review-{attempt}.jpg")
        prompt = (
            "Critique these actual rendered frames in chronological order, including shot boundaries. "
            'Return JSON {"findings":[{"shot":0,"time":0.5,"problem":"specific visible defect"}]}. '
            "Focus on OUR composited text, graphics and camera choices, NOT the customer's original UI styling. "
            "Never ask to recolor product pixels or enlarge every native UI label. Inspect added text especially: white on white is a defect. "
            "Typing and masks intentionally reveal partial words during entrances. Report clipping only if settled text remains cropped; a brief graphic anticipation is not automatically an empty hold. "
            "Live footage includes the cursor action before the destination appears; do not call a short action lead-in a duplicated shot. "
            "Check clipping, type readability and contrast, obscured interactions, repeated compositions, "
            "awkward spatial jumps, empty pauses, and whether real product evidence is clear. "
            "Also assess art direction against the supplied concept: flag tiny full-app insets, redundant copies of the same screen, graphic shots that finish moving early then hold without a readable reason, or typography too timid to establish hierarchy. "
            "Describe concrete visible evidence for each design weakness and the intended improvement, not generic requests to make it more premium. "
            "Do not give numeric quality scores, invent defects, or request new product assets. "
            "An empty findings list means you found no defects in these sampled frames, not a guarantee about audio or every frame. "
            f"Film plan: {plan.model_dump_json()}"
        )
        try:
            result = reasoner(prompt + creative_context, image, max_tokens=1600, motion=True)
            findings = result.get("findings")
            if not isinstance(findings, list) or any(
                not isinstance(f, dict) or not isinstance(f.get("problem"), str) for f in findings
            ):
                raise ValueError("Invalid visual review response.")
        except (ValueError, TypeError):
            report["status"] = "unavailable"
            report["passes"].append(
                {
                    "attempt": attempt,
                    "findings": [],
                    "error": "Visual review did not return a usable report.",
                }
            )
            break
        report["passes"].append({"attempt": attempt, "findings": findings[:12]})
        (folder / f"director-plan-{attempt}.json").write_text(plan.model_dump_json(indent=2))
        if not findings:
            report["status"] = "reviewed"
            break
        if attempt == 2:
            break
        if checkpoint:
            checkpoint()
        try:
            revised = FilmDirection.model_validate(
                reasoner(
                    enriched_prompt(RULES, "detailed")
                    + creative_context
                    + "\nRepair the specific rendered defects below. Keep the concept and unaffected shots. "
                    "Return the complete revised film, using exactly the same JSON schema and only existing assets.\n"
                    f"Maximum duration: {target}s. Prior revision rejections: {json.dumps([p.get('rejected_revision') for p in report['passes']])}\nFindings: {json.dumps(findings[:12])}\nExisting film: {plan.model_dump_json()}\nSchema: {json.dumps(FilmDirection.model_json_schema())}",
                    image,
                    max_tokens=10000,
                    motion=True,
                    effort=geometry_effort or setting("CUTROOM_GEOMETRY_EFFORT", "medium"),
                )
            )
            revised = constrain_geometry(revised)
            issues = validate_evidence(revised, scenes, target)
            if issues:
                report["passes"][-1]["rejected_revision"] = issues
                continue
            plan = revised
            report["revision_count"] += 1
        except ProviderError as exc:
            report["passes"][-1]["rejected_revision"] = [str(exc)]
            break
        except (ValueError, TypeError) as exc:
            report["passes"][-1]["rejected_revision"] = [str(exc)[:2000]]
    save_direction(folder, plan)
    (folder / "director-review.json").write_text(json.dumps(report, indent=2))
    return plan, report
