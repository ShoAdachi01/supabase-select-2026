# Cutroom Motion Vocabulary and Scored Critic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the film director a camera, continuous motion, depth and richer shapes/type, record live footage at measured 2x, and replace the defect-only critic with a scored, evidence-backed rubric gate.

**Architecture:** The director keeps returning declarative JSON validated by pydantic (`server/video_direction_models.py`). New optional fields extend the contract. Shared camera math lives in one Python module (`server/video_camera.py`) used by the validator and composition, and is mirrored exactly in one TS module (`src/video/camera.ts`) used by the Remotion renderer. A render-based verification script proves the two agree. The critic returns a typed `FilmReview`, and a pure `gate()` function decides `passed` / `needs_review` / `unavailable`.

**Tech Stack:** Python 3.12, pydantic v2, Pillow, imageio-ffmpeg (ffmpeg with libvpx-vp9), pytest; Node 20, Playwright CDP screencast, Remotion 4.0.532, React/TypeScript, `@fontsource`.

**Spec:** `docs/superpowers/specs/2026-10-07-cutroom-motion-vocabulary-critic-design.md`

## Global Constraints

- The director never supplies executable code, URLs or arbitrary assets. Every new field is a bounded literal or number.
- All new schema fields are optional with neutral defaults. Existing plans must validate and render identically.
- Layout, readability and click coordinates are **logical CSS pixels** of `scene.viewport` (1920×1080). Physical resolution affects only zoom caps.
- Zoom cap per layer kind: footage `max(1.2, scene["source_scale"])`; product/detail `max(1.2, scene["still_scale"])`. Missing scale fields default to 1.
- Readability threshold: effective logical scale ≥ 0.65 while live footage is visible.
- Hold budget: `max(1.2, 0.3 × newly revealed words + 0.6, 2.0 if a proof layer just landed)` seconds.
- Drift bounds: `x`/`y` |v| ≤ 0.05 canvas units/s; `zoom` |v| ≤ 0.04 per second. Grain 0–0.15.
- Layers per shot ≤ 9. Fonts: `sans` = Inter Variable, `display` = Instrument Serif (`@fontsource/instrument-serif` 5.3.0, weight 400 only), `mono` = JetBrains Mono (`@fontsource-variable/jetbrains-mono` 5.3.0).
- 2x capture acceptance: decoded width 3840, achieved fps ≥ 20, interaction timing unchanged (`npm run test:interactions`), raw size within the 1.2 GB worker budget, uploaded `film.mp4` under the 50 MiB bucket limit. Otherwise fall back to 1x and report it.
- Critic: 7 axes (`readability`, `canvas`, `motion`, `pacing`, `typography`, `continuity`, `specificity`), scores 1–10, ≥ 1 observation per axis, actionable finding(s) for any axis < 8. Pass = all axes ≥ 8 and no blocking findings. Revision budget `CUTROOM_REVIEW_PASSES` (default 2). A revision is rejected if any axis drops by ≥ 2.
- Below-bar films still export (`needs_review`). `reviewed` is renamed `passed`.
- Commands: `.venv/bin/pytest -q`, `npm run lint`, `npm run build`, `npm test`. Format Python with `.venv/bin/ruff format`.
- Commit messages are concise and imperative, with no AI attribution or co-author trailers (see INSTRUCTIONS.md).

## File Structure

| File | Responsibility |
|---|---|
| `scripts/video_capture.mjs` | 4K screencast request, byte budget |
| `server/video_capture.py` | VP9 4K encode; `measure_sources()` records measured `source_scale`, `still_scale`, fps |
| `server/video_service.py` | Calls `measure_sources` after both capture paths |
| `server/video_composition.py` | Keeps native still resolution; footage sized to its zoom; passes aspect/scale/drift to jobs; explicit preview frame list |
| `server/video_direction_models.py` | Contract fields (camera, drift, depth, elevation, backdrop, shapes, fonts) and `FilmReview` |
| `server/video_camera.py` (new) | Pure camera math: zoom cap, focus resolution, visible window, projection, effective scale, drift |
| `src/video/camera.ts` (new) | Exact TS mirror of the render-side math in `video_camera.py` |
| `src/video/DirectedShot.tsx` | Renders camera, drift, elevation, backdrop, shapes, fonts |
| `server/video_direction.py` | Validator rules, evidence (click crops), critic prompt, gate loop |
| `server/video_prompts.py` | `motion-brief-v8` prose |
| `server/video_providers.py` | `reason()` accepts multiple images |
| `scripts/render_motion.mjs` | Renders preview frames listed by Python at scale 1 |
| `src/studio/FilmReview.tsx` (new) | Read-only per-axis scores and open findings |
| `scripts/verify_motion_vocabulary.py` (new) | Renders fixture jobs and checks pixels against `video_camera.py` predictions |
| `scripts/verify_capture_quality.py` (new) | 2x capture acceptance checks |
| `scripts/score_films.py` (new) | Critic discrimination and variance test |

---

## Phase 0

### Task 0: Commit the harness fixes already in the working tree

**Files:** `server/video_providers.py`, `tests/test_video_prompts.py` (already modified, already tested)

- [ ] **Step 1: Verify**

Run: `.venv/bin/pytest -q && npm run lint`
Expected: `120 passed`, `All checks passed!`, Prettier clean.

- [ ] **Step 2: Commit**

```bash
git add server/video_providers.py tests/test_video_prompts.py
git commit -m "Retry truncated Claude plans and surface provider error messages"
```

---

## Phase 1: Measured 2x capture

### Task 1: Request 4K screencast frames and encode them at native size with VP9

**Files:**
- Modify: `scripts/video_capture.mjs` (the `bytes > 350 * 1024 * 1024` check and the `startScreencast` options)
- Modify: `server/video_capture.py` (`encode_directed_capture`; add `measure_sources`)
- Test: `tests/test_video_capture.py` (new)

**Interfaces:**
- Produces: `measure_sources(folder: Path, scenes: list[dict]) -> dict`. It mutates each scene, adding `source_scale: float` and `still_scale: float`, and returns `{"width": int, "height": int, "fps": float, "bytes": int, "source_scale": float}`. It also writes `capture-metrics.json`.

- [ ] **Step 1: Write the failing tests**

```python
"""Capture resolution is measured from decoded frames, never assumed from the request."""

import json

from PIL import Image

from server.video_capture import encode_directed_capture, measure_sources


def frames(folder, size, count=6):
    (folder / "capture-frames").mkdir()
    manifest = []
    for i in range(count):
        name = f"capture-frames/{i + 1:06d}.jpg"
        Image.new("RGB", size, (i * 30, 40, 90)).save(folder / name, quality=85)
        manifest.append({"name": name, "duration": 1 / 25})
    (folder / "capture.json").write_text(json.dumps(manifest))


def scene(folder, still_size):
    Image.new("RGB", still_size, "white").save(folder / "scene-0.jpg")
    return [{"thumbnail": "scene-0.jpg", "viewport": {"width": 1920, "height": 1080}}]


def test_4k_frames_encode_natively_and_measure_as_2x(tmp_path):
    frames(tmp_path, (3840, 2160))
    encode_directed_capture(tmp_path)
    scenes = scene(tmp_path, (3840, 2160))
    metrics = measure_sources(tmp_path, scenes)
    assert (metrics["width"], metrics["height"]) == (3840, 2160)
    assert metrics["source_scale"] == 2
    assert scenes[0]["source_scale"] == 2 and scenes[0]["still_scale"] == 2
    assert metrics["fps"] > 0
    assert json.loads((tmp_path / "capture-metrics.json").read_text()) == metrics


def test_1x_frames_measure_as_1x_even_if_4k_was_requested(tmp_path):
    frames(tmp_path, (1920, 1080))
    encode_directed_capture(tmp_path)
    scenes = scene(tmp_path, (3840, 2160))
    metrics = measure_sources(tmp_path, scenes)
    assert metrics["width"] == 1920
    assert scenes[0]["source_scale"] == 1
    assert scenes[0]["still_scale"] == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_video_capture.py -v`
Expected: FAIL with `ImportError: cannot import name 'measure_sources'`.

- [ ] **Step 3: Implement**

In `scripts/video_capture.mjs`, change the budget and the screencast request:

```js
    if (++count > 12000 || bytes > 1200 * 1024 * 1024) {
```
```js
      await session.send('Page.startScreencast', {
        format: 'jpeg',
        quality: 85,
        maxWidth: 3840,
        maxHeight: 2160,
        everyNthFrame: 1,
      });
```

In `server/video_capture.py`, encode at the frames' native size. Scale only to make the dimensions even, and cap at 3840:

```python
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
```

Append the measurement helper (add `import subprocess`, `import imageio_ffmpeg`, `from PIL import Image` to the imports):

```python
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
```

Achieved fps comes from the screencast manifest (frames per wall-second), because the encode resamples to 30 fps.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_video_capture.py tests/test_video_sound.py -v`
Expected: PASS (the existing unsafe-capture tests still pass).

- [ ] **Step 5: Commit**

```bash
git add scripts/video_capture.mjs server/video_capture.py tests/test_video_capture.py
git commit -m "Capture directed takes at native 2x and measure the result"
```

### Task 2: Record measured scales for every capture path and keep native resolution in compositions

**Files:**
- Modify: `server/video_service.py:330-338` (after `encode_directed_capture(folder)` and after `align_result_shots(...)`)
- Modify: `scripts/compare_video_prompts.py` (`copy_capture`)
- Modify: `server/video_composition.py` (product resize, footage scale, job fields)
- Test: `tests/test_video_composition.py`

**Interfaces:**
- Consumes: `measure_sources` (Task 1).
- Produces: each motion job gains `"viewport": {"width","height"}`, `"source_scale": float`, `"still_scale": float`, `"detail_sizes": [[w,h], ...]`. Footage is encoded at width `footage_width(scene, direction)`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_video_composition.py`)

```python
def test_directed_jobs_keep_native_stills_and_size_footage_to_zoom(tmp_path, capture, monkeypatch):
    monkeypatch.setattr(video_composition, "run_compositor", lambda *args: None)
    calls = []
    real = video_composition.ffmpeg
    monkeypatch.setattr(
        video_composition, "ffmpeg", lambda *args: (calls.append(args), real(*args))[1]
    )
    Image.new("RGB", (3840, 2160), "white").save(tmp_path / "scene-0.jpg")
    direction = {
        "bpm": 120,
        "beats": 4,
        "hits": [],
        "layers": [
            {"id": "f", "kind": "footage", "states": [{"beat": 0, "cam_zoom": 1}, {"beat": 2, "cam_zoom": 1.6}]}
        ],
    }
    scenes = [
        {
            "kind": "browser",
            "motion": "directed",
            "direction": direction,
            "thumbnail": "scene-0.jpg",
            "start": 0,
            "end": 2,
            "duration": 2,
            "viewport": {"width": 1920, "height": 1080},
            "source_scale": 2,
            "still_scale": 2,
        }
    ]
    video_composition.prepare_compositions(tmp_path, capture, scenes, "paper", [None])
    job = json.loads((tmp_path / "motion-jobs.json").read_text())["jobs"][0]
    assert Image.open(tmp_path / job["product"]).size == (3840, 2160)
    assert job["viewport"] == {"width": 1920, "height": 1080}
    assert job["source_scale"] == 2 and job["still_scale"] == 2
    footage_call = next(c for c in calls if str(c[-1]).endswith("motion-footage-0.mp4"))
    assert "scale=3072:-2" in " ".join(footage_call)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_video_composition.py -k native -v`
Expected: FAIL (product is 1920×1080, `viewport` key missing).

- [ ] **Step 3: Implement**

In `server/video_composition.py`, add above `prepare_compositions`:

```python
def footage_width(scene: dict, direction: dict | None) -> int:
    """Decode only the resolution the deepest push-in can show."""
    zooms = [
        state.get("cam_zoom", 1)
        for layer in (direction or {}).get("layers", [])
        if layer["kind"] == "footage"
        for state in layer["states"]
    ] or [1]
    scale = min(float(scene.get("source_scale", 1)), max(1.0, max(zooms)))
    return max(1920, int(1920 * scale) // 2 * 2)
```

Replace the directed product resize:

```python
            with Image.open(folder / name) as image:
                image.convert("RGB").save(product)
```

Replace the footage filter's `scale=1920:1080` with `scale={footage_width(source, direction)}:-2`. In the `jobs.append({...})` dict add:

```python
                "viewport": viewport,
                "source_scale": float(source.get("source_scale", 1)),
                "still_scale": float(source.get("still_scale", 1)),
                "detail_sizes": [list(Image.open(folder / d).size) for d in details],
```

Use `viewport = source.get("viewport", {"width": 1920, "height": 1080})`. Keep the existing focus default of 1280×720 only for the legacy `focus` computation.

In `server/video_service.py`, after `encode_directed_capture(folder)` and also after `align_result_shots(folder / "raw.webm", folder, scenes)`, add:

```python
            measure_sources(folder, scenes)
```

Import it with `from server.video_capture import encode_directed_capture, measure_sources`.

In `scripts/compare_video_prompts.py` `copy_capture`, before writing `source-scenes.json`:

```python
    measure_sources(output, scenes)
```

Import it with `from server.video_capture import measure_sources`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/video_composition.py server/video_service.py scripts/compare_video_prompts.py tests/test_video_composition.py
git commit -m "Keep native capture resolution through motion compositions"
```

---

## Phase 2: Contract and renderer vocabulary

### Task 3: Extend the motion contract

**Files:**
- Modify: `server/video_direction_models.py`
- Test: `tests/test_video_motion_contract.py` (new)

**Interfaces:**
- Produces (pydantic):
  - `MotionState` adds `cam_x: float = 0.5 (0..1)`, `cam_y: float = 0.5 (0..1)`, `cam_zoom: float = 1 (1..2)`, `focus: str | None (pattern ^click-\d{1,2}$)`, `elevation: float = 0 (0..1)`.
  - `MotionLayer` adds `depth: float = 1 (0..1)`, `shape: Literal["rect","line","segments","ring"] = "rect"`, `stroke: int = 4 (1..40)`, `count: int = 8 (2..40)`, `gap: float = 0.4 (0..0.9)`, `target_layer: str | None`, `target: str | None (^click-\d{1,2}$)`, `target_x: float | None (0..1)`, `target_y: float | None (0..1)`, `font: Literal["sans","display","mono"] = "sans"`.
  - New `Drift(x=0, y=0, zoom=0)` with bounds ±0.05, ±0.05, ±0.04.
  - New `Backdrop(kind: Literal["flat","radial"]="flat", x=0.5, y=0.4, color2: hex | None = None, grain: float = 0 (0..0.15))`.
  - `ShotDirection` adds `drift: Drift = Drift()`, `backdrop: Backdrop = Backdrop()`; `layers` max_length 9.

**Carry-forward rule for `focus`:** `focus` carries forward like geometry. A state that sets `cam_x` or `cam_y` explicitly clears an inherited `focus`. A state that sets `focus` explicitly drops inherited `cam_x`/`cam_y`. `target_x`/`target_y` are server-set only: the model must not supply them (validated in Task 6).

- [ ] **Step 1: Write the failing tests**

```python
"""New motion vocabulary is optional, bounded, and inherits like geometry."""

import pytest
from pydantic import ValidationError

from server.video_direction_models import MotionLayer, ShotDirection
from tests.test_video_direction import film


def test_existing_plans_validate_unchanged():
    plan = film()
    assert plan.shots[0].drift.zoom == 0
    assert plan.shots[0].backdrop.kind == "flat"
    state = plan.shots[0].layers[0].states[1]
    assert (state.cam_x, state.cam_y, state.cam_zoom, state.focus, state.elevation) == (0.5, 0.5, 1, None, 0)


def test_camera_and_focus_carry_forward_and_explicit_camera_clears_focus():
    layer = MotionLayer.model_validate(
        dict(
            id="proof",
            kind="footage",
            states=[
                dict(beat=0, focus="click-1", cam_zoom=1.8),
                dict(beat=2),
                dict(beat=3, cam_x=0.2),
            ],
        )
    )
    assert layer.states[1].focus == "click-1" and layer.states[1].cam_zoom == 1.8
    assert layer.states[2].focus is None and layer.states[2].cam_x == 0.2


@pytest.mark.parametrize(
    "patch",
    [
        {"drift": {"zoom": 0.2}},
        {"backdrop": {"kind": "linear"}},
        {"backdrop": {"grain": 0.5}},
        {"layers": [dict(id=f"l{i}", kind="shape", states=[dict(beat=0)]) for i in range(10)]},
    ],
)
def test_out_of_contract_vocabulary_is_rejected(patch):
    shot = film().shots[0].model_dump(exclude={"source", "label"})
    with pytest.raises(ValidationError):
        ShotDirection.model_validate({**shot, **patch})


def test_focus_must_name_a_click_and_zoom_is_bounded():
    with pytest.raises(ValidationError):
        MotionLayer.model_validate(dict(id="a", kind="product", states=[dict(beat=0, focus="https://x")]))
    with pytest.raises(ValidationError):
        MotionLayer.model_validate(dict(id="a", kind="product", states=[dict(beat=0, cam_zoom=3)]))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_video_motion_contract.py -v`
Expected: FAIL (`AttributeError: 'ShotDirection' object has no attribute 'drift'`).

- [ ] **Step 3: Implement** in `server/video_direction_models.py`

```python
CLICK = r"^click-\d{1,2}$"
HEX = r"^#[0-9a-fA-F]{6}$"


class MotionState(Contract):
    beat: float = Field(ge=0, le=24)
    x: float = Field(default=0, ge=-1, le=1.5)
    y: float = Field(default=0, ge=-1, le=1.5)
    w: float = Field(default=1, ge=0.001, le=2)
    h: float = Field(default=1, ge=0.001, le=2)
    radius: float = Field(default=0, ge=0, le=540)
    rotation: float = Field(default=0, ge=-30, le=30)
    opacity: float = Field(default=1, ge=0, le=1)
    cam_x: float = Field(default=0.5, ge=0, le=1)
    cam_y: float = Field(default=0.5, ge=0, le=1)
    cam_zoom: float = Field(default=1, ge=1, le=2)
    focus: str | None = Field(default=None, pattern=CLICK)
    elevation: float = Field(default=0, ge=0, le=1)
    ease: Literal["spring", "smooth", "linear", "hold"] = "smooth"
```

In `MotionLayer`, add the fields listed under Interfaces. Replace the carry-forward loop in `inherit_geometry` with:

```python
        previous, states = {}, []
        for state in value["states"]:
            if not isinstance(state, dict):
                return value
            inherited = dict(previous)
            if "cam_x" in state or "cam_y" in state:
                inherited.pop("focus", None)
            if "focus" in state:
                inherited.pop("cam_x", None)
                inherited.pop("cam_y", None)
            current = {**inherited, **state}
            states.append(current)
            previous = {k: v for k, v in current.items() if k not in ("beat", "ease")}
```

Add the `Drift` and `Backdrop` classes, then add to `ShotDirection`:

```python
class Drift(Contract):
    x: float = Field(default=0, ge=-0.05, le=0.05)
    y: float = Field(default=0, ge=-0.05, le=0.05)
    zoom: float = Field(default=0, ge=-0.04, le=0.04)


class Backdrop(Contract):
    kind: Literal["flat", "radial"] = "flat"
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.4, ge=0, le=1)
    color2: str | None = Field(default=None, pattern=HEX)
    grain: float = Field(default=0, ge=0, le=0.15)
```

```python
    layers: list[MotionLayer] = Field(min_length=1, max_length=9)
    drift: Drift = Field(default_factory=Drift)
    backdrop: Backdrop = Field(default_factory=Backdrop)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q`
Expected: all pass (existing direction tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add server/video_direction_models.py tests/test_video_motion_contract.py
git commit -m "Add camera, drift, depth, surface, shape and font fields to the motion contract"
```

### Task 4: Shared camera math in Python

**Files:**
- Create: `server/video_camera.py`
- Test: `tests/test_video_camera.py` (new)

**Interfaces:**
- Produces:
  - `zoom_cap(kind: str, scene: dict) -> float`
  - `clicks(scene: dict) -> list[dict]` (interactions with `kind == "click"`, in order; `click-N` indexes this list)
  - `resolve_focus(plan: FilmDirection, scenes_by_source: dict[str, dict]) -> FilmDirection` (copy; sets `cam_x/cam_y` from the click's logical `x/y ÷ viewport`; sets `target_x/target_y` on shape layers with `target`; clamps `cam_zoom` to the cap; raises `ValueError` on an unknown click)
  - `fitted_scale(state, aspect: tuple[float, float]) -> float` (logical px per source px at zoom 1, contain fit)
  - `effective_scale(state, viewport: dict) -> float` = `fitted_scale × cam_zoom` (canvas px per logical source px)
  - `visible_window(state, aspect) -> tuple[float, float, float, float]` (normalized source rect `left, top, width, height` shown by the camera)
  - `project(state, aspect, px: float, py: float) -> tuple[float, float]` (normalized source point → normalized canvas point)
  - `drifted(state, drift: dict, depth: float, seconds: float) -> dict` (x/y/w/h after drift)

The definitions below are normative; `src/video/camera.ts` (Task 5) must implement the identical formulas.

- [ ] **Step 1: Write the failing tests**

```python
"""One definition of camera geometry for validator, composition and renderer checks."""

import pytest

from server import video_camera as cam
from server.video_direction_models import FilmDirection, MotionState
from tests.test_video_direction import film

VIEW = {"width": 1920, "height": 1080}


def state(**kw):
    return MotionState(beat=0, **kw)


def test_fullscreen_source_is_readable_regardless_of_capture_resolution():
    assert cam.effective_scale(state(), VIEW) == pytest.approx(1.0)


def test_contain_fit_uses_the_limiting_dimension():
    # A 0.5-wide by full-height box shows the 16:9 source width-limited.
    assert cam.effective_scale(state(w=0.5, h=1), VIEW) == pytest.approx(0.5)
    assert cam.effective_scale(state(w=0.5, h=1, cam_zoom=1.4), VIEW) == pytest.approx(0.7)


def test_window_clamps_inside_the_source_and_projects_points():
    s = state(cam_zoom=2, cam_x=0.95, cam_y=0.5)
    left, top, width, height = cam.visible_window(s, (1920, 1080))
    assert (width, height) == pytest.approx((0.5, 0.5))
    assert left == pytest.approx(0.5)  # clamped: no empty edge
    assert cam.project(s, (1920, 1080), 0.75, 0.5) == pytest.approx((0.5, 0.5))


def test_zoom_cap_follows_measured_scale_per_kind():
    scene = {"source_scale": 1, "still_scale": 2}
    assert cam.zoom_cap("footage", scene) == 1.2
    assert cam.zoom_cap("product", scene) == 2
    assert cam.zoom_cap("detail-0", {}) == 1.2


def test_focus_resolves_from_logical_click_and_unknown_click_fails():
    data = film().model_dump()
    data["shots"][0]["layers"][0]["states"][1].update(focus="click-0", cam_zoom=1.9)
    plan = FilmDirection.model_validate(data)
    scene = {"viewport": VIEW, "source_scale": 1, "interactions": [{"kind": "click", "time": 1, "x": 480, "y": 270}]}
    resolved = cam.resolve_focus(plan, {"scene-0.jpg": scene, "scene-1.jpg": scene})
    s = resolved.shots[0].layers[0].states[1]
    assert (s.cam_x, s.cam_y, s.cam_zoom) == (0.25, 0.25, 1.2)
    data["shots"][0]["layers"][0]["states"][1]["focus"] = "click-5"
    with pytest.raises(ValueError, match="click-5"):
        cam.resolve_focus(FilmDirection.model_validate(data), {"scene-0.jpg": scene, "scene-1.jpg": scene})


def test_drift_scales_with_depth_around_canvas_center():
    moved = cam.drifted({"x": 0, "y": 0, "w": 1, "h": 1}, {"x": 0.01, "y": 0, "zoom": 0.02}, 0.5, 2)
    assert moved["w"] == pytest.approx(1.02)
    assert moved["x"] == pytest.approx(0.5 - 0.5 * 1.02 + 0.01)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_video_camera.py -v`
Expected: FAIL with `ModuleNotFoundError: server.video_camera`.

- [ ] **Step 3: Implement** `server/video_camera.py`

```python
"""Camera geometry shared by validation and composition. Mirrored exactly in src/video/camera.ts.

Coordinates: canvas is normalized 1920x1080; sources are normalized 0..1 in their own pixels;
readability is measured in logical CSS pixels of the recorded viewport.
"""

from __future__ import annotations

from server.video_direction_models import FilmDirection

CANVAS = (1920, 1080)


def zoom_cap(kind: str, scene: dict) -> float:
    scale = scene.get("source_scale", 1) if kind == "footage" else scene.get("still_scale", 1)
    return round(max(1.2, min(2.0, float(scale))), 2)


def clicks(scene: dict) -> list[dict]:
    return [e for e in scene.get("interactions", []) if e.get("kind") == "click"]


def click_point(scene: dict, name: str) -> tuple[float, float]:
    index = int(name.split("-")[1])
    events = clicks(scene)
    if index >= len(events) or "x" not in events[index]:
        raise ValueError(f"{name} was not recorded in this capture.")
    view = scene.get("viewport", {"width": 1920, "height": 1080})
    return events[index]["x"] / view["width"], events[index]["y"] / view["height"]


def _get(state, key):
    return state[key] if isinstance(state, dict) else getattr(state, key)


def fitted_scale(state, aspect: tuple[float, float]) -> float:
    box_w, box_h = _get(state, "w") * CANVAS[0], _get(state, "h") * CANVAS[1]
    return min(box_w / aspect[0], box_h / aspect[1])


def effective_scale(state, viewport: dict) -> float:
    return fitted_scale(state, (viewport["width"], viewport["height"])) * _get(state, "cam_zoom")


def _axis(focus: float, box: float, content: float) -> tuple[float, float]:
    """Returns (visible start, visible length) in normalized source units on one axis."""
    if content <= box:
        return 0.0, 1.0
    length = box / content
    return min(1 - length, max(0.0, focus - length / 2)), length


def visible_window(state, aspect) -> tuple[float, float, float, float]:
    scale = fitted_scale(state, aspect) * _get(state, "cam_zoom")
    left, width = _axis(_get(state, "cam_x"), _get(state, "w") * CANVAS[0], aspect[0] * scale)
    top, height = _axis(_get(state, "cam_y"), _get(state, "h") * CANVAS[1], aspect[1] * scale)
    return left, top, width, height


def project(state, aspect, px: float, py: float) -> tuple[float, float]:
    scale = fitted_scale(state, aspect) * _get(state, "cam_zoom")
    box_w, box_h = _get(state, "w") * CANVAS[0], _get(state, "h") * CANVAS[1]
    content_w, content_h = aspect[0] * scale, aspect[1] * scale
    left, _, _, _ = visible_window(state, aspect)
    _, top, _, _ = visible_window(state, aspect)
    offset_x = (box_w - content_w) / 2 if content_w <= box_w else -left * content_w
    offset_y = (box_h - content_h) / 2 if content_h <= box_h else -top * content_h
    x = _get(state, "x") * CANVAS[0] + offset_x + px * content_w
    y = _get(state, "y") * CANVAS[1] + offset_y + py * content_h
    return x / CANVAS[0], y / CANVAS[1]


def drifted(rect: dict, drift: dict, depth: float, seconds: float) -> dict:
    scale = 1 + drift["zoom"] * seconds * depth
    shift_x, shift_y = drift["x"] * seconds * depth, drift["y"] * seconds * depth
    return {
        **rect,
        "x": 0.5 + (rect["x"] - 0.5) * scale + shift_x,
        "y": 0.5 + (rect["y"] - 0.5) * scale + shift_y,
        "w": rect["w"] * scale,
        "h": rect["h"] * scale,
    }


def resolve_focus(plan: FilmDirection, scenes_by_source: dict[str, dict]) -> FilmDirection:
    plan = plan.model_copy(deep=True)
    for shot in plan.shots:
        scene = scenes_by_source.get(shot.source, {})
        for layer in shot.layers:
            cap = zoom_cap(layer.kind, scene)
            for state in layer.states:
                if state.focus and layer.kind in ("footage", "product"):
                    state.cam_x, state.cam_y = click_point(scene, state.focus)
                state.cam_zoom = min(state.cam_zoom, cap)
            if layer.kind == "shape" and layer.target:
                layer.target_x, layer.target_y = click_point(scene, layer.target)
    return plan
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_video_camera.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/video_camera.py tests/test_video_camera.py
git commit -m "Define shared camera geometry for validation and rendering"
```

### Task 5: Render the vocabulary in Remotion

**Files:**
- Create: `src/video/camera.ts`
- Modify: `src/video/DirectedShot.tsx`, `src/video/LaunchShot.tsx` (`ShotProps` gains `viewport`, `source_scale`, `still_scale`, `detail_sizes`)
- Modify: `package.json` (`@fontsource/instrument-serif` 5.3.0, `@fontsource-variable/jetbrains-mono` 5.3.0)
- Create: `scripts/verify_motion_vocabulary.py`
- Modify: `package.json` scripts: `"test:motion": ".venv/bin/python -m scripts.verify_motion_vocabulary"`

**Interfaces:**
- Consumes: job fields from Task 2; contract from Task 3; formulas from Task 4.
- Produces: `camera.ts` exports `fittedScale`, `visibleWindow`, `project`, `drifted` with the same semantics as `video_camera.py`.

- [ ] **Step 1: Install fonts**

Run: `npm install --save-exact @fontsource/instrument-serif@5.3.0 @fontsource-variable/jetbrains-mono@5.3.0`
Expected: `package.json` and `package-lock.json` updated.

- [ ] **Step 2: Write the failing render verification** `scripts/verify_motion_vocabulary.py`

```python
"""Render fixture shots and check pixels where video_camera.py predicts them. Uses local Chromium only."""

import json
import tempfile
from pathlib import Path

from PIL import Image

from server.video_camera import project
from server.video_composition import run_compositor
from server.video_direction_models import MotionState

VIEW = {"width": 1920, "height": 1080}


def fixture(folder: Path):
    # A 3840x2160 still: white field, a 40px red square centered at logical (1440, 270).
    image = Image.new("RGB", (3840, 2160), "white")
    image.paste((220, 20, 20), (2880 - 40, 540 - 40, 2880 + 40, 540 + 40))
    image.save(folder / "motion-product-0.png")
    direction = {
        "purpose": "Verify the camera and ring.",
        "composition": "product",
        "entry": "cut",
        "background": "#101218",
        "bpm": 120,
        "beats": 2,
        "hits": [],
        "drift": {"x": 0, "y": 0, "zoom": 0},
        "backdrop": {"kind": "flat", "x": 0.5, "y": 0.4, "color2": None, "grain": 0},
        "layers": [
            {
                "id": "proof", "kind": "product", "depth": 1, "text": "", "color": "#ffffff",
                "size": 100, "weight": 600, "align": "left", "entrance": "none", "shape": "rect",
                "stroke": 4, "count": 8, "gap": 0.4, "font": "sans", "target_layer": None,
                "target": None, "target_x": None, "target_y": None,
                "states": [
                    {"beat": 0, "x": 0, "y": 0, "w": 1, "h": 1, "radius": 0, "rotation": 0,
                     "opacity": 1, "cam_x": 0.75, "cam_y": 0.25, "cam_zoom": 2, "focus": None,
                     "elevation": 0, "ease": "hold"}
                ],
            },
            {
                "id": "ring", "kind": "shape", "depth": 1, "text": "", "color": "#00ff00",
                "size": 100, "weight": 600, "align": "left", "entrance": "none", "shape": "ring",
                "stroke": 8, "count": 8, "gap": 0.4, "font": "sans", "target_layer": "proof",
                "target": "click-0", "target_x": 0.75, "target_y": 0.25,
                "states": [
                    {"beat": 0, "x": 0, "y": 0, "w": 0.1, "h": 0.18, "radius": 0, "rotation": 0,
                     "opacity": 1, "cam_x": 0.5, "cam_y": 0.5, "cam_zoom": 1, "focus": None,
                     "elevation": 0, "ease": "hold"}
                ],
            },
        ],
    }
    job = {
        "index": 0, "direction": direction, "preset": "directed", "theme": "midnight",
        "headline": "", "subtitle": "", "frames": 30, "interactive": False,
        "product": "motion-product-0.png", "details": [], "footage": None,
        "focus": {"x": 0.5, "y": 0.5}, "viewport": VIEW, "source_scale": 1,
        "still_scale": 2, "detail_sizes": [], "preview_frames": [0],
    }
    (folder / "motion-jobs.json").write_text(json.dumps({"jobs": [job], "preview": True}))
    return direction


def main():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        direction = fixture(folder)
        run_compositor(folder, folder / "motion-jobs.json")
        frame = Image.open(folder / "preview-0-0.jpg").convert("RGB")
        assert frame.size == (1920, 1080), frame.size
        state = MotionState.model_validate(direction["layers"][0]["states"][0])
        x, y = project(state, (1920, 1080), 0.75, 0.25)
        px, py = round(x * 1920), round(y * 1080)
        red = frame.getpixel((px, py))
        assert red[0] > 180 and red[1] < 80, f"camera: expected red at {(px, py)}, got {red}"
        # At 2x zoom the 40 logical-px square is 80 canvas px wide: edge 30px out is still red.
        assert frame.getpixel((px + 30, py))[0] > 180, "camera zoom not applied"
        ring = frame.getpixel((px + 96 - 4, py))
        assert ring[1] > 180 and ring[0] < 80, f"ring not centered on click: {ring}"
        print("PASS: camera crop, zoom and click-targeted ring match video_camera.py")


if __name__ == "__main__":
    main()
```

The ring is 0.1 × 1920 = 192px wide, so its right edge stroke sits about 96 − 4 px right of the projected center.

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/bin/python -m scripts.verify_motion_vocabulary`
Expected: FAIL at the `camera` assertion (the current renderer contain-fits the whole still), or at frame size if previews are still at scale 0.5. Task 9 sets preview scale to 1. For now, edit the `renderStill` `scale: 0.5` in `scripts/render_motion.mjs` to `scale: 1` as part of this task, and render the frames listed in `job.preview_frames` when present:

```js
      const frames = job.preview_frames ?? [
        ...new Set([
          0,
          ...[0.2, 0.5, 0.8].map((t) => Math.round((job.frames - 1) * t)),
          job.frames - 1,
        ]),
      ];
```

- [ ] **Step 4: Implement** `src/video/camera.ts`

```ts
// Exact mirror of server/video_camera.py. Change both together; verify_motion_vocabulary checks agreement.
export const CANVAS = [1920, 1080] as const;
type Rect = { x: number; y: number; w: number; h: number };
type Cam = Rect & { cam_x: number; cam_y: number; cam_zoom: number };

export function fittedScale(s: Rect, aspect: readonly [number, number]) {
  return Math.min((s.w * CANVAS[0]) / aspect[0], (s.h * CANVAS[1]) / aspect[1]);
}

function axis(focus: number, box: number, content: number): [number, number] {
  if (content <= box) return [0, 1];
  const length = box / content;
  return [Math.min(1 - length, Math.max(0, focus - length / 2)), length];
}

export function visibleWindow(s: Cam, aspect: readonly [number, number]) {
  const scale = fittedScale(s, aspect) * s.cam_zoom;
  const [left, width] = axis(s.cam_x, s.w * CANVAS[0], aspect[0] * scale);
  const [top, height] = axis(s.cam_y, s.h * CANVAS[1], aspect[1] * scale);
  return { left, top, width, height, scale };
}

/** Pixel placement of the source inside its layer box (relative to the box's top-left). */
export function contentBox(s: Cam, aspect: readonly [number, number]) {
  const { left, top, scale } = visibleWindow(s, aspect);
  const boxW = s.w * CANVAS[0];
  const boxH = s.h * CANVAS[1];
  const width = aspect[0] * scale;
  const height = aspect[1] * scale;
  return {
    width,
    height,
    left: width <= boxW ? (boxW - width) / 2 : -left * width,
    top: height <= boxH ? (boxH - height) / 2 : -top * height,
  };
}

export function project(s: Cam, aspect: readonly [number, number], px: number, py: number) {
  const box = contentBox(s, aspect);
  return {
    x: (s.x * CANVAS[0] + box.left + px * box.width) / CANVAS[0],
    y: (s.y * CANVAS[1] + box.top + py * box.height) / CANVAS[1],
  };
}

export function drifted<T extends Rect>(
  rect: T,
  drift: { x: number; y: number; zoom: number },
  depth: number,
  seconds: number,
): T {
  const scale = 1 + drift.zoom * seconds * depth;
  return {
    ...rect,
    x: 0.5 + (rect.x - 0.5) * scale + drift.x * seconds * depth,
    y: 0.5 + (rect.y - 0.5) * scale + drift.y * seconds * depth,
    w: rect.w * scale,
    h: rect.h * scale,
  };
}
```

- [ ] **Step 5: Implement the renderer changes** in `src/video/DirectedShot.tsx`

1. Types: extend `MotionState` with `cam_x, cam_y, cam_zoom, elevation: number; focus: string | null`. Extend `MotionLayer` with `depth: number; shape: 'rect' | 'line' | 'segments' | 'ring'; stroke: number; count: number; gap: number; font: 'sans' | 'display' | 'mono'; target_layer: string | null; target_x: number | null; target_y: number | null`. Extend `ShotDirection` with `drift: { x: number; y: number; zoom: number }` and `backdrop: { kind: 'flat' | 'radial'; x: number; y: number; color2: string | null; grain: number }`. Mark every new field optional (`?`) and default it at the point of use, so older stored plans still type-check.
2. Interpolation: in `stateAt`, change the property list to `['x','y','w','h','radius','rotation','opacity','cam_x','cam_y','cam_zoom','elevation']` and default missing values (`cam_x`/`cam_y` 0.5, `cam_zoom` 1, `elevation` 0) when reading `from`/`to`.
3. Drift: after `const s = stateAt(...)`, apply `const d = drifted(s, direction.drift ?? {x:0,y:0,zoom:0}, layer.depth ?? 1, frame / fps)` and use `d` for `left/top/width/height`.
4. Fonts: import `@fontsource/instrument-serif/400.css` and `@fontsource-variable/jetbrains-mono`. Load all three in the effect with `Promise.all([document.fonts.load('600 100px "Inter Variable"'), document.fonts.load('400 100px "Instrument Serif"'), document.fonts.load('500 100px "JetBrains Mono Variable"')])`. Map `font` to a family: `sans → 'Inter Variable'` (letterSpacing `-.045em`), `display → 'Instrument Serif'` (weight 400, letterSpacing `-.02em`), `mono → 'JetBrains Mono Variable'` (letterSpacing `0`). Pass that family, weight and spacing into both `fitTextOnNLines` and the rendered style.
5. Camera: replace the `<Img>`/`<OffthreadVideo>` `objectFit: 'contain'` boxes with an absolutely positioned inner box from `contentBox(s, aspect)`. `aspect` is `[props.viewport.width, props.viewport.height]` for `footage`/`product`, and `props.detail_sizes[i]` for `detail-i`. The media fills that inner box (`width: '100%', height: '100%'`).
6. Elevation: when `s.elevation > 0`, set `boxShadow: \`0 ${s.elevation * 40}px ${s.elevation * 90}px rgba(0,0,0,${0.12 + s.elevation * 0.22}), 0 ${s.elevation * 6}px ${s.elevation * 14}px rgba(0,0,0,${0.08 + s.elevation * 0.1})\``.
7. Backdrop: set the root `background` to `direction.backdrop?.kind === 'radial' && direction.backdrop.color2 ? \`radial-gradient(circle at ${x*100}% ${y*100}%, ${color2} 0%, ${direction.background} 70%)\` : direction.background`. When `grain > 0`, render a last full-frame `<svg>` with `<filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed={frame} /></filter><rect width="100%" height="100%" filter="url(#g)" opacity={grain} />` and `mixBlendMode: 'overlay'`.
8. Shapes (`kind === 'shape'`):
   - `rect`: as today.
   - `line`: a centered bar along the longer axis with thickness `stroke`.
   - `segments`: a flex row (or column when h > w) of `count` blocks, each `(1 - gap)` of its slot.
   - `ring`: transparent fill, `border: ${stroke}px solid ${color}`, `borderRadius: s.radius`.
   - When `target_layer` and `target_x`/`target_y` are set, find that layer's interpolated state (with drift applied) and its aspect. Compute `project(...)` and center the ring's own w/h on that point every frame.

- [ ] **Step 6: Run the render verification and the build**

Run: `.venv/bin/python -m scripts.verify_motion_vocabulary && npm run build && npm run lint`
Expected: `PASS: camera crop, zoom and click-targeted ring match video_camera.py`; build and lint clean.

- [ ] **Step 7: Run the existing preview path for regressions**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add src/video package.json package-lock.json scripts/render_motion.mjs scripts/verify_motion_vocabulary.py
git commit -m "Render camera, drift, depth, backdrops, shapes and fonts"
```

---

## Phase 3: Validator, evidence and prompts

### Task 6: Replace the 65% clamp with measured readability, click framing, references and hold budgets

**Files:**
- Modify: `server/video_direction.py` (`constrain_geometry`, `validate_evidence`; new helpers `click_seconds`, `static_spans`, `hold_budget`)
- Modify: `tests/test_video_direction.py::test_live_geometry_is_constrained_without_replacing_the_composition`
- Test: `tests/test_video_direction.py` (append)

**Interfaces:**
- Consumes: `video_camera.resolve_focus`, `effective_scale`, `visible_window`, `clicks`, `zoom_cap`.
- Produces: `constrain_geometry(plan, scenes: list[dict] | None = None) -> FilmDirection` (resolves focus, clamps camera; no longer resizes footage). Update both call sites in `direct_film` and `review_film` to pass `scenes`.

- [ ] **Step 1: Update the outdated test and write the new failing tests**

Replace the body of `test_live_geometry_is_constrained_without_replacing_the_composition` with:

```python
def test_live_geometry_keeps_the_directors_size_and_clamps_only_the_camera():
    plan = film()
    plan.shots[0].layers[0].states[0].w = 0.5
    plan.shots[0].layers[0].states[0].cam_zoom = 2
    fitted = director.constrain_geometry(plan, sources())
    assert fitted.shots[0].layers[0].states[0].w == 0.5
    assert fitted.shots[0].layers[0].states[0].cam_zoom == 1.2  # 1x capture cap
    assert plan.shots[0].layers[0].states[0].cam_zoom == 2
    assert fitted.shots[0].composition == plan.shots[0].composition
```

Append:

```python
def with_footage_state(**state):
    data = film().model_dump()
    for shot in data["shots"]:
        shot["layers"][0]["states"] = [dict(beat=0, x=0, y=0, w=1, h=1, **state), dict(beat=6, **state)]
    return FilmDirection.model_validate(data)


def scaled(scale=2, x=480, y=270):
    out = sources()
    for s in out:
        s.update(viewport={"width": 1920, "height": 1080}, source_scale=scale, still_scale=2)
        s["interactions"][0].update(x=x, y=y)
    return out


def test_small_footage_fails_readability_unless_pushed_in():
    scenes = scaled()
    small = with_footage_state(x=0.25, y=0.25, w=0.5, h=0.5)
    issues = director.validate_evidence(director.constrain_geometry(small, scenes), scenes, 30)
    assert any("readable" in i for i in issues)
    pushed = with_footage_state(x=0.25, y=0.25, w=0.5, h=0.5, cam_zoom=1.5, focus="click-0")
    assert not any(
        "readable" in i
        for i in director.validate_evidence(director.constrain_geometry(pushed, scenes), scenes, 30)
    )


def test_push_in_that_crops_out_the_click_is_rejected():
    scenes = scaled(x=1800, y=1000)
    plan = with_footage_state(cam_zoom=2, cam_x=0.1, cam_y=0.1)
    issues = director.validate_evidence(director.constrain_geometry(plan, scenes), scenes, 30)
    assert any("click-0" in i and "frame" in i for i in issues)


def test_reading_hold_is_allowed_without_drift_but_dead_air_is_not():
    data = film().model_dump()
    graphic = dict(
        source="scene-0.jpg",
        label="Line",
        purpose="State the promise in type.",
        composition="type",
        bpm=120,
        beats=8,
        layers=[
            dict(id="t", kind="text", text="Edit every word", states=[dict(beat=0, x=0.1, y=0.3, w=0.8, h=0.3, opacity=0), dict(beat=0.5, opacity=1)]),
        ],
    )
    data["shots"].insert(1, {**graphic, "beats": 4})
    plan = FilmDirection.model_validate(data)
    (start, end), = director.static_spans(plan.shots[1])
    assert director.hold_budget(plan.shots[1], start) == pytest.approx(1.5)  # 3 words
    issues = director.validate_evidence(plan, sources(), 30)
    assert not any("holds static" in i for i in issues)  # 0.95s reading hold, no drift needed
    data["shots"][1]["beats"] = 8
    issues = director.validate_evidence(FilmDirection.model_validate(data), sources(), 30)
    assert any("holds static" in i for i in issues)  # 2.95s of the same line
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_video_direction.py -v -k "readab or crops_out or hold or camera"`
Expected: FAIL (`constrain_geometry() takes 1 positional argument`, missing `hold_budget`).

- [ ] **Step 3: Implement**

In `constrain_geometry(plan, scenes=None)`, keep the duplicate-live-take demotion loop. Delete the footage clamp loop (`state.w = min(1, max(0.65, ...))` through `state.rotation = 0`) and replace it with:

```python
    if scenes is not None:
        plan = resolve_focus(plan, {s["thumbnail"]: s for s in evidence_scenes(scenes)})
    for shot in plan.shots:
        for layer in shot.layers:
            if layer.kind == "footage":
                for state in layer.states:
                    state.rotation = 0
    return plan
```

Add the helpers:

```python
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
```

In `validate_evidence`:
- Replace the footage check (`s.opacity < 0.98 or s.w < 0.65 ...`) with the readability, fade and click-framing checks below.
- Add the static-span check for every shot.
- Add the reference check. Reject any layer that supplies `target_x`/`target_y` before resolution: the model may not set them. Detect this in `direct_film` by checking the raw proposal dict for those keys and adding the issue "target_x/target_y are set by Cutroom; use target".

```python
        if footage:
            view = source.get("viewport", {"width": 1920, "height": 1080})
            seconds = shot.beats * 60 / shot.bpm
            beats_per_second = shot.bpm / 60
            for state in footage[0].states:
                if state.opacity > 0.5 and effective_scale(state, view) < 0.65:
                    issues.append(
                        f"{prefix}: live footage is not readable at beat {state.beat:g} "
                        f"(scale {effective_scale(state, view):.2f} < 0.65). Enlarge it or push the camera in."
                    )
                    break
                edge = min(state.beat, shot.beats - state.beat) / beats_per_second
                if state.opacity < 0.98 and edge > 0.3:
                    issues.append(f"{prefix}: footage may only fade within 0.3s of a shot edge.")
                    break
            for name, at in click_seconds(shot, source):
                if not 0 <= at < seconds:
                    continue
                state = layout_state(footage[0], at * beats_per_second)
                left, top, width, height = visible_window(state, (view["width"], view["height"]))
                px, py = click_point(source, name)
                margin = 0.04
                if not (left + margin * width <= px <= left + width * (1 - margin)
                        and top + margin * height <= py <= top + height * (1 - margin)):
                    issues.append(f"{prefix}: {name} happens outside the camera frame at {at:.2f}s. Keep the action in view.")
                if state.opacity < 0.98:
                    issues.append(f"{prefix}: footage must be opaque while {name} happens.")
        for start, end in static_spans(shot):
            seconds_static = (end - start) * 60 / shot.bpm
            budget = hold_budget(shot, start)
            if seconds_static > budget + 1e-6:
                issues.append(
                    f"{prefix}: frame holds static for {seconds_static:.2f}s from beat {start:g}; "
                    f"its reading budget is {budget:.2f}s. Shorten the hold, add a purposeful move, or cut."
                )
```

`layout_state(layer, beat)` returns a `MotionState` interpolated like `layout_at`, including the camera fields. Implement it by extending `layout_at` to interpolate `GEOMETRY` keys and returning `MotionState.model_validate({**result, "beat": beat})`.

Imports: `from server.video_camera import click_point, clicks, effective_scale, resolve_focus, visible_window`.

Note on the test: at 120 bpm the text becomes visible at beat 0.5 and its entrance counts as moving for 0.8s (1.6 beats), so the static span starts at beat 2.1. A 3-word line has budget `max(1.2, 0.3 × 3 + 0.6) = 1.5s`. The 4-beat shot holds 0.95s (accepted); the 8-beat shot holds 2.95s (rejected). `hold_budget` counts every text layer visible by the span start, i.e. everything there is to read.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q`
Expected: all pass. Existing fixtures use full-screen footage (scale 1.0) and do not crop clicks.

- [ ] **Step 5: Commit**

```bash
git add server/video_direction.py tests/test_video_direction.py
git commit -m "Validate readability, click framing and hold budgets instead of fixed footage size"
```

### Task 7: Give the director click evidence and the v8 prompt

**Files:**
- Modify: `server/video_direction.py` (`contact_sheet` asset regex; new `click_crops`; `direct_film` prompt payload)
- Modify: `server/video_prompts.py` (`PROMPT_VERSION`, `MOTION_STUDIES`, `TREATMENT`) and `RULES` in `server/video_direction.py`
- Test: `tests/test_video_prompts.py` (append)

**Interfaces:**
- Produces: `click_crops(folder: Path, scenes: list[dict]) -> list[tuple[str, str]]` returning `(f"click-{i}-{n}.jpg", f"{thumbnail} / click-{n} ({label})")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_director_prompt_lists_named_clicks_and_zoom_caps(tmp_path, monkeypatch):
    for name in ("scene-0.jpg", "scene-1.jpg"):
        Image.new("RGB", (640, 360), "white").save(tmp_path / name)
    scenes = sources()
    for s in scenes:
        s.update(viewport={"width": 1920, "height": 1080}, source_scale=2, still_scale=2)
        s["interactions"][0].update(x=960, y=540, label="Board")
    monkeypatch.setattr(director, "click_crops", lambda folder, scenes: [])
    prompts = []

    def reasoner(prompt, image, **kwargs):
        prompts.append(prompt)
        return film().model_dump()

    director.direct_film("App", "Brief", scenes, tmp_path, strategy="baseline", reasoner=reasoner)
    assert '"click-0"' in prompts[-1]
    assert '"zoom_cap": {"footage": 2.0, "product": 2.0}' in prompts[-1]


def test_v8_prompt_teaches_vocabulary_and_drops_enforced_prohibitions():
    from server.video_prompts import MOTION_STUDIES, PROMPT_VERSION

    assert PROMPT_VERSION == "motion-brief-v8"
    assert "focus" in MOTION_STUDIES and "ring" in MOTION_STUDIES and "depth" in MOTION_STUDIES
    assert "arbitrary assets, gradients" not in director.RULES
    assert "Footage layers must remain visible throughout" not in director.RULES
    assert "VOCABULARY." in director.RULES
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_video_prompts.py -k "named_clicks or v8" -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

1. `contact_sheet` regex: add `|click-\d{1,2}-\d{1,2}\.jpg`.
2. `click_crops`: for each evidence scene `i` and each click `n`:
   - Extract one frame at the click time from `raw.webm`, the same way as `source_frames`. Cache it in `click-{i}-{n}.json` stamped with `raw_bytes`/`raw_mtime`.
   - Crop a box of `960×540 × source_scale` physical pixels centered on `(x × source_scale, y × source_scale)`, clamped inside the frame.
   - Save it as `click-{i}-{n}.jpg`.
3. In `direct_film`, after `assets.extend(source_frames(folder, sources))`, add `assets.extend(click_crops(folder, sources))`. Add to the prompt's captures JSON, for each source:

```python
"clicks": [
    {"name": f"click-{n}", "label": e.get("label", ""), "time": e["time"], "x": e.get("x"), "y": e.get("y")}
    for n, e in enumerate(clicks(s))
],
"zoom_cap": {"footage": zoom_cap("footage", s), "product": zoom_cap("product", s)},
```

   Write it with `json.dumps` so the keys appear exactly as `"zoom_cap": {"footage": 2.0, "product": 2.0}`.
4. `RULES`: delete the sentence `No CSS, JS, URLs, arbitrary assets, gradients, fabricated UI, or placeholder copy.` and replace it with `No CSS, JS, URLs, arbitrary assets, fabricated UI, or placeholder copy. Avoid decorative linear gradients.` Replace the footage sentence `Footage layers must remain visible throughout, one per shot.` with `One live footage layer per shot; it must stay readable and keep each recorded click in frame.` Append the vocabulary paragraph:

```text
VOCABULARY. A camera frames part of a footage/product/detail source: cam_x, cam_y (focal point 0-1),
cam_zoom (1 = whole source, capped per capture). Set focus:"click-N" to frame a recorded click; Cutroom
fills in its coordinates. Shot drift {x,y,zoom} keeps a hold alive at a constant rate; layer depth 0-1
scales it for parallax. elevation 0-1 lifts a layer with a soft shadow. backdrop: flat, or radial light
(x,y,color2), optional grain 0-0.15. Shapes: rect, line (stroke), segments (count, gap) for rails or
sprockets, ring (stroke) with target_layer + target:"click-N" to circle a real control. Text font:
sans, display (serif, weight 400) or mono. A static hold is fine while it is being read; it is
rejected only when it outlasts its reading time.
```

5. `server/video_prompts.py`: set `PROMPT_VERSION = "motion-brief-v8"`. Replace `MOTION_STUDIES` studies A–C with:

```text
A. Push into the proof. Footage starts full-frame (cam_zoom 1). From beat 1.5 to 2.3 it springs to
cam_zoom 1.8 with focus:"click-N" just before that click happens. A ring with target_layer set to the
footage and target:"click-N" fades in as the camera settles, then the camera eases back to 1.2 so
the result reads. The click never leaves the frame.

B. A rail carries the eye. A segments shape (count 10, gap .45) in the accent color sits on a
baseline. It extends laterally over .3 seconds as type lands. Its final geometry equals the first
state of a matching rail in the next shot (entry:"match"), so the cut feels continuous.

C. Parallax hold. A product still sits at depth .4 with elevation .6 over a radial backdrop; a 2-4
word line sits at depth 1. Shot drift {x:-0.01, zoom:0.015} moves the line more than the product
while it is read. Do not add drift to a shot that is already moving.
```

   Keep the surrounding framing text ("NOT a film sequence or templates…", "Translate seconds into the chosen BPM", "You can reject them all"). Remove the obsolete sentence "No small full-app inset alongside another full-app screenshot…" only if it contradicts readability; keep it otherwise.
6. `TREATMENT`: change the shots item to `{"source":"scene-N.jpg", "purpose":"…", "eye_path":"…", "camera":"framing per beat, e.g. full → push to click-1 at 1.8x → settle 1.2x", "depth":"what sits in front/behind", "transition":"…", "seconds":3}`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q`
Expected: all pass. Any test asserting `motion-brief-v7` is updated to `v8`.

- [ ] **Step 5: Commit**

```bash
git add server/video_direction.py server/video_prompts.py tests/test_video_prompts.py
git commit -m "Show the director named clicks and teach the v8 motion vocabulary"
```

---

## Phase 4: Scored critic gate

### Task 8: `reason()` accepts several images

**Files:**
- Modify: `server/video_providers.py` (`reason` signature and both content builders)
- Test: `tests/test_video_prompts.py` (append)

**Interfaces:**
- Produces: `reason(prompt, screenshot: str | list[str] | None = None, ...)`. A list is sent as multiple image blocks in order. A single string behaves exactly as today.

- [ ] **Step 1: Write the failing test**

```python
def test_reasoner_sends_every_image_in_order(monkeypatch):
    monkeypatch.setattr(providers, "setting", claude_settings)
    calls = []
    monkeypatch.setattr(
        providers.httpx,
        "post",
        lambda url, **kw: (calls.append(kw["json"]), httpx.Response(200, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": "{}"}]}))[1],
    )
    providers.reason("Review", ["AAA", "BBB"], motion=True)
    images = [b["source"]["data"] for b in calls[0]["messages"][0]["content"] if b["type"] == "image"]
    assert images == ["AAA", "BBB"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_video_prompts.py -k every_image -v`
Expected: FAIL (the list is embedded as a single `data` value).

- [ ] **Step 3: Implement.** At the top of `reason`, normalize: `images = [screenshot] if isinstance(screenshot, str) else list(screenshot or [])`. Build one Claude `image` block per item, and one OpenAI `input_image` item per item, in order.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add server/video_providers.py tests/test_video_prompts.py
git commit -m "Allow several evidence images per reasoning call"
```

### Task 9: Sharper review evidence

**Files:**
- Modify: `server/video_composition.py` (add `preview_frames` to jobs when `preview=True`)
- Modify: `server/video_direction.py` (`review_evidence(folder, plan, jobs, scenes) -> list[str]`)
- Test: `tests/test_video_direction.py` (append)

**Interfaces:**
- Consumes: `scripts/render_motion.mjs` renders `job["preview_frames"]` at scale 1 (Task 5).
- Produces:
  - `preview_frame_list(frames: int) -> list[int]`: every 15 frames (0.5s) plus `frames - 1`.
  - `review_evidence(...)`: base64 JPEGs in this order:
    1. One per-shot sheet (`review-shot-{i}.jpg`, tiles 960×540, labeled with seconds).
    2. One text-crop sheet (`review-type.jpg`): each text layer's settled rectangle cropped 1:1 from the last preview frame of its shot, padded 24px.
    3. The click-crop sheet (`review-clicks.jpg`).
    4. The RAW source frames sheet.

- [ ] **Step 1: Write the failing test**

```python
def test_review_evidence_samples_every_half_second_and_crops_settled_type(tmp_path):
    assert director.preview_frame_list(61) == [0, 15, 30, 45, 60]
    plan = film()
    plan.shots[0].layers.append(
        plan.shots[0].layers[0].model_copy(update={"id": "t", "kind": "text", "text": "Still yours"})
    )
    jobs = [{"index": 0, "frames": 61}, {"index": 1, "frames": 61}]
    for job in jobs:
        for f in director.preview_frame_list(job["frames"]):
            Image.new("RGB", (1920, 1080), "white").save(tmp_path / f"preview-{job['index']}-{f}.jpg")
    images = director.review_evidence(tmp_path, plan, jobs, sources())
    assert len(images) >= 3
    assert (tmp_path / "review-shot-0.jpg").exists()
    assert Image.open(tmp_path / "review-type.jpg").width >= 960
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_video_direction.py -k half_second -v`
Expected: FAIL (`preview_frame_list` missing).

- [ ] **Step 3: Implement**

```python
def preview_frame_list(frames: int) -> list[int]:
    return sorted({*range(0, frames, 15), frames - 1})
```

- In `prepare_compositions`, when `preview` is true, set `job["preview_frames"] = preview_frame_list(job["frames"])`. Import it lazily to avoid a cycle, or move `preview_frame_list` into `video_composition.py` and re-export it from `video_direction`.
- `review_evidence`:
  - Build per-shot sheets by reusing `contact_sheet` with a `tile=(960, 540)` keyword. Add `tile: tuple[int, int] = (480, 270)` and `columns: int = 3` parameters to `contact_sheet`, defaulting to today's values. Extend its name regex to `preview-\d{1,2}-\d+\.jpg|review-[\w-]+\.jpg`.
  - For text crops, take the last state of each text layer, convert it to pixels (`x × 1920` and so on), pad by 24px, and crop from `preview-{i}-{frames-1}.jpg`. Paste the crops into `review-type.jpg`, two columns, original scale. Skip it if there is no text.
  - Return the base64 of each sheet.
- In `review_film`, replace the single `image` with `images = review_evidence(folder, plan, jobs, scenes)`, and pass `images` to the reasoner.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest -q`
Expected: all pass. Update `test_review_uses_rendered_frames_and_is_bounded`: its fake `preview` must write `preview_frame_list(90)` frames, and its expected sheet file changes from `director-review-2.jpg` to `review-shot-0.jpg`.

- [ ] **Step 5: Commit**

```bash
git add server/video_composition.py server/video_direction.py tests/test_video_direction.py
git commit -m "Review films from half-second frames, settled type crops and click crops"
```

### Task 10: Rubric, gate and no-regression revisions

**Files:**
- Modify: `server/video_direction_models.py` (`Observation`, `ReviewFinding`, `AxisScore`, `FilmReview`, `AXES`)
- Modify: `server/video_direction.py` (`CRITIC` prompt constant, `gate`, `review_film` loop)
- Modify: `README.md` (review paragraph: `reviewed` → `passed`, rubric wording)
- Test: `tests/test_video_review_gate.py` (new); update `test_review_uses_rendered_frames_and_is_bounded`

**Interfaces:**
- Produces:
  - `AXES = ("readability", "canvas", "motion", "pacing", "typography", "continuity", "specificity")`
  - `FilmReview` with one `AxisScore` field per axis and `blocking: list[ReviewFinding]` (max 6).
  - `gate(review: FilmReview) -> Literal["passed", "needs_review"]`
  - `regressed(before: FilmReview, after: FilmReview) -> list[str]` (axes that dropped by ≥ 2)
  - Report: `{"status", "rubric": "film-rubric-v1", "passes": [{"attempt", "scores": {axis: int}, "review": dict, "rejected_revision"?: list[str]}], "revision_count"}`

- [ ] **Step 1: Write the failing tests** `tests/test_video_review_gate.py`

```python
"""The critic gate needs evidence for every score and never invents criticism of strong work."""

import pytest
from pydantic import ValidationError

from server import video_direction as director
from server.video_direction_models import AXES, FilmReview


def axis(score, findings=None):
    return {
        "score": score,
        "observations": [{"shot": 0, "time": 0.5, "note": "The clicked board fills the frame legibly."}],
        "findings": findings or [],
    }


def review(**scores):
    return {a: axis(scores.get(a, 9)) for a in AXES} | {"blocking": []}


def test_strong_work_passes_with_positive_observations_only():
    assert director.gate(FilmReview.model_validate(review())) == "passed"


def test_axis_without_observation_is_invalid():
    data = review()
    data["pacing"]["observations"] = []
    with pytest.raises(ValidationError):
        FilmReview.model_validate(data)


def test_failing_axis_requires_an_actionable_finding():
    data = review()
    data["canvas"] = axis(6)
    with pytest.raises(ValidationError):
        FilmReview.model_validate(data)
    data["canvas"] = axis(6, [{"shot": 1, "time": 2.5, "problem": "Strip occupies a thin band.", "change": "Scale strip to fill the lower half."}])
    assert director.gate(FilmReview.model_validate(data)) == "needs_review"


def test_blocking_finding_fails_even_when_every_axis_passes():
    data = review()
    data["blocking"] = [{"shot": 4, "time": 13.4, "problem": "Narration text is cropped at the right edge.", "change": "Reduce zoom so the full line fits.", "blocking": "clipped_text"}]
    assert director.gate(FilmReview.model_validate(data)) == "needs_review"


def test_regression_detects_two_point_drops():
    before = FilmReview.model_validate(review(typography=9))
    after = FilmReview.model_validate(review(typography=7, canvas=10) | {"typography": axis(7, [{"shot": 0, "time": 1, "problem": "Orphaned word.", "change": "Rebreak the line."}])})
    assert director.regressed(before, after) == ["typography"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_video_review_gate.py -v`
Expected: FAIL with `ImportError: cannot import name 'AXES'`.

- [ ] **Step 3: Implement the models** in `server/video_direction_models.py`

```python
AXES = ("readability", "canvas", "motion", "pacing", "typography", "continuity", "specificity")


class Observation(Contract):
    shot: int = Field(ge=0, le=20)
    time: float = Field(ge=0, le=120)
    note: str = Field(min_length=8, max_length=400)


class ReviewFinding(Contract):
    shot: int = Field(ge=0, le=20)
    time: float = Field(ge=0, le=120)
    problem: str = Field(min_length=8, max_length=600)
    change: str = Field(min_length=8, max_length=400)
    blocking: Literal["clipped_text", "hidden_click", "unreadable_type"] | None = None


class AxisScore(Contract):
    score: int = Field(ge=1, le=10)
    observations: list[Observation] = Field(min_length=1, max_length=4)
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def failing_needs_action(self):
        if self.score < 8 and not self.findings:
            raise ValueError("An axis below 8 needs an actionable finding.")
        return self


class FilmReview(Contract):
    readability: AxisScore
    canvas: AxisScore
    motion: AxisScore
    pacing: AxisScore
    typography: AxisScore
    continuity: AxisScore
    specificity: AxisScore
    blocking: list[ReviewFinding] = Field(default_factory=list, max_length=6)

    def scores(self) -> dict[str, int]:
        return {axis: getattr(self, axis).score for axis in AXES}
```

- [ ] **Step 4: Implement the gate and loop** in `server/video_direction.py`

```python
def gate(review: FilmReview) -> str:
    return "passed" if min(review.scores().values()) >= 8 and not review.blocking else "needs_review"


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
Images: per-shot sheets, settled type crops, click crops, RAW source frames.
Return JSON matching this schema: """
```

Rewrite `review_film`:
- `passes = int(setting("CUTROOM_REVIEW_PASSES", "2"))`.
- The loop runs `for attempt in range(passes + 1)`:
  1. Render previews and build `images` (Task 9).
  2. Call `reasoner(CRITIC + schema + plan + creative_context, images, max_tokens=4000, motion=True)`.
  3. `FilmReview.model_validate`. On `ValueError`/`TypeError`, set status `unavailable` and break, as today.
  4. If this is a revision (`candidate` is set) and `regressed(best_review, review)` is not empty, record `rejected_revision: [f"Regressed {axis}" ...]`, restore `plan = best_plan`, and keep `best_review`. Otherwise set `best_plan, best_review = plan, review` and increment `revision_count` if it was a revision.
  5. If `gate(best_review) == "passed"`, set status `passed` and break.
  6. If `attempt == passes`, break.
  7. Revise. The prompt leads with the axes sorted by score ascending, then the blocking findings, then all findings. On validation issues, record `rejected_revision` and continue with `candidate = None`.
- At the end, status is `passed` if `gate(best_review)` passes, `needs_review` if there was any valid review, else `unavailable`.
- Save `best_plan` and return `best_plan, report`.

Update `test_review_uses_rendered_frames_and_is_bounded`: its answers become two invalid-then-valid `FilmReview` dicts that never pass (e.g. canvas 6 with a finding), interleaved with `film().model_dump()`. It still asserts 3 renders, `revision_count == 2` and `status == "needs_review"`.

README: in the review paragraph, replace the sentence about statuses with:

> Reports distinguish `passed` (all seven rubric axes ≥ 8 with supporting observations and no blocking defects on the sampled frames), `needs_review` and `unavailable`. The rubric summarizes visible evidence; it is not a guarantee of quality.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest -q && npm run lint`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add server/video_direction_models.py server/video_direction.py tests/test_video_review_gate.py tests/test_video_direction.py README.md
git commit -m "Gate films on an evidence-backed seven-axis rubric"
```

### Task 11: Show the review in the studio

**Files:**
- Create: `src/studio/FilmReview.tsx`
- Modify: `src/studio/types.ts` (`Video.payload.direction?`), `src/studio/Studio.tsx` (render below the film player), `src/studio/studio.css`

**Interfaces:**
- Consumes: `job.payload.direction.review` (Task 10 report).

- [ ] **Step 1: Add the types** to `src/studio/types.ts`

```ts
export type ReviewNote = { shot: number; time: number; note?: string; problem?: string; change?: string; blocking?: string | null };
export type AxisReview = { score: number; observations: ReviewNote[]; findings: ReviewNote[] };
export const AXES = ['readability', 'canvas', 'motion', 'pacing', 'typography', 'continuity', 'specificity'] as const;
export type Axis = (typeof AXES)[number];
export type FilmReviewReport = {
  status: 'passed' | 'needs_review' | 'unavailable';
  passes: {
    attempt: number;
    scores?: Record<Axis, number>;
    review?: Partial<Record<Axis, AxisReview>> & { blocking?: ReviewNote[] };
  }[];
  revision_count: number;
};
```

In `Video.payload`, add `direction?: { concept: string; review?: FilmReviewReport };`.

- [ ] **Step 2: Create** `src/studio/FilmReview.tsx`

```tsx
import { AXES, type FilmReviewReport } from './types';

const LABELS: Record<(typeof AXES)[number], string> = {
  readability: 'Readability',
  canvas: 'Canvas',
  motion: 'Motion',
  pacing: 'Pacing',
  typography: 'Type',
  continuity: 'Continuity',
  specificity: 'Specificity',
};
const STATUS = {
  passed: 'Met the rubric on sampled frames',
  needs_review: 'Below the bar — review before publishing',
  unavailable: 'Visual review unavailable',
};

export function FilmReview({ report }: { report: FilmReviewReport }) {
  const last = [...report.passes].reverse().find((p) => p.review);
  const findings = last?.review
    ? [...(last.review.blocking ?? []), ...AXES.flatMap((axis) => last.review![axis]?.findings ?? [])]
    : [];
  return (
    <section className={`film-review ${report.status}`} aria-label="Film review">
      <header>
        <strong>{STATUS[report.status]}</strong>
        <small>{report.revision_count} revision{report.revision_count === 1 ? '' : 's'}</small>
      </header>
      {last?.scores && (
        <ul className="film-review-scores">
          {AXES.map((axis) => (
            <li key={axis} className={(last.scores![axis] ?? 0) >= 8 ? 'ok' : 'low'}>
              <span>{LABELS[axis]}</span>
              <meter min={1} max={10} low={7.9} optimum={10} value={last.scores![axis]} />
              <b>{last.scores![axis]}</b>
            </li>
          ))}
        </ul>
      )}
      {findings.length > 0 && (
        <ol className="film-review-findings">
          {findings.map((f, i) => (
            <li key={i}>
              <span>Shot {f.shot + 1} · {f.time.toFixed(1)}s</span> {f.problem} <em>{f.change}</em>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Render it.** In `Studio.tsx`, directly after the closing tag of the `film-player` div inside `film-panel`, add `{job.payload.direction?.review && <FilmReview report={job.payload.direction.review} />}`, and import the component. Add compact styles in `studio.css` for `.film-review`, `.film-review-scores` (a 7-row grid: label, meter, value), `.low` (coral meter), and `.film-review-findings` (small text, max 6 visible with overflow scroll). Use the existing studio CSS variables.

- [ ] **Step 4: Verify**

Run: `npm run build && npm run lint`
Expected: clean. Then run `npm run dev` with the API (`npm run server`), open a completed directed job, and confirm the panel shows status, seven scores and findings. Take a screenshot for the PR.

- [ ] **Step 5: Commit**

```bash
git add src/studio
git commit -m "Show rubric scores and open findings for directed films"
```

---

## Phase 5: Integration (uses API credits; run by hand)

### Task 12: Capture acceptance, a fresh take, and the critic discrimination test

**Files:**
- Create: `scripts/verify_capture_quality.py`, `scripts/score_films.py`

- [ ] **Step 1: Write** `scripts/verify_capture_quality.py`

```python
"""2x capture acceptance: measured frame size, fps, storage. Click timing uses verify_directed_capture."""

import argparse
import json
import sys
from pathlib import Path

# raw.webm stays on the worker (only film.mp4 and storyboard.json are uploaded, 50 MiB bucket limit).
MAX_BYTES = 1200 * 1024 * 1024  # worker-disk budget, matching the screencast byte cap


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    folder = parser.parse_args().folder
    metrics = json.loads((folder / "capture-metrics.json").read_text())
    checks = {
        "decoded width 3840": metrics["width"] == 3840,
        "fps >= 20": metrics["fps"] >= 20,
        "raw size within worker budget": metrics["bytes"] <= MAX_BYTES,
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name} ({metrics})")
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
```

Also confirm the uploaded `film.mp4` (still 1080p) stays under the 50 MiB `file_size_limit` in `supabase/config.toml`; 4K capture must not change its size materially.

- [ ] **Step 2: Capture and check.** Run a music-led capture of the Cutroom flow through the studio or `npm run test:video:e2e` (see README). Then:

Run: `.venv/bin/python -m scripts.verify_capture_quality .cutroom/<job-id>/<take>` and `npm run test:interactions` (live click/keystroke clock check through the same `createDirectedCapture`, now at 4K)
Expected: all PASS. If decoded width is 1920 or fps < 20, revert the `maxWidth`/`maxHeight` request to 1920/1080 in `scripts/video_capture.mjs`, record the measured values in the PR, and continue (zoom caps fall back to 1.2 automatically).

- [ ] **Step 3: Fresh take**

Run (brief and direction copied from `.cutroom/verification/prompt-final-latest/experiment.json`):
```bash
.venv/bin/python -m scripts.compare_video_prompts <new-capture-folder> .cutroom/verification/vocab-v8 \
  --providers claude --claude-model claude-opus-5-5 --strategies studies --review \
  --reference .cutroom/verification/references/lukas/mtioon.mp4 --title Cutroom \
  --brief "<baseline brief>" --direction "<baseline direction>"
```
Expected: `status: rendered` with a review status and scores in the row.

- [ ] **Step 4: Write** `scripts/score_films.py`. It takes `--films a.mp4 b.mp4 …` and `--runs 3`:
  - Samples one frame every 0.5s at 960×540 (ffmpeg `fps=2`).
  - Groups frames into sheets of 12, labeled with seconds.
  - Calls `reason(CRITIC_FRAMES_ONLY + schema, sheets, motion=True, provider="claude", model="claude-opus-5-5")`. `CRITIC_FRAMES_ONLY` is `CRITIC` with this addition: "No plan or capture metadata is available; judge only visible frames; leave blocking empty unless clearly visible."
  - Validates with `FilmReview`.
  - Writes `scores.json` and prints a table: film × axis, mean ± stdev over runs.
  - Exits 0. It is a measurement, not a test.

- [ ] **Step 5: Run the discrimination test**

Pick an independent strong film that is not one of the director references (`mtioon.mp4`, `linear-dashboards.mp4`); ask the user to supply one if none is on disk. Then run:

```bash
.venv/bin/python -m scripts.score_films --runs 3 --films <strong.mp4> \
  .cutroom/verification/prompt-final-latest/openai-studies-8773328a/film.mp4 \
  .cutroom/verification/opus55-ab/claude-studies-a7b445c6/film.mp4 \
  .cutroom/verification/vocab-v8/<take>/film.mp4
```

Expected: the strong film's mean exceeds both old takes on `canvas`, `motion`, `pacing` and `typography` by more than 2 × the largest stdev. If not, rewrite the anchors in `CRITIC` (not tuned to make particular films fail) and re-run on the same set. Record the table in the PR.

- [ ] **Step 6: Full verification and commit**

Run: `npm test && npm run lint && npm run build && npm run test:motion`
Expected: all pass.

```bash
git add scripts/verify_capture_quality.py scripts/score_films.py
git commit -m "Add capture acceptance and critic discrimination checks"
```

- [ ] **Step 7: Report.** Put the three films (baseline, Opus v7, v8 vocabulary) side by side, plus the score table, in the PR description, with screenshots of the studio review panel.
