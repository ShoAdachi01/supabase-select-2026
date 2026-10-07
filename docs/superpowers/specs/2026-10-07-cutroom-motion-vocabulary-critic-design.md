# Cutroom motion vocabulary and scored critic — design

Status: approved design, revised after engineering review; pending implementation plan
Date: 2026-10-07
Branch: `feat/cutroom-music-led-launch`

## Problem

Directed launch films are flat even with a strong model. A controlled A/B on the same capture, brief,
art direction and reference analysis showed Opus 5.5 produces a clearer concept and a far more
honest critique than gpt-6.1-sol, but both films share the same ceiling:

- The renderer can only express rectangles of screenshots, Inter text and flat shapes on a flat
  field. Content always contain-fits its rectangle, so there is no camera: no push-in on the clicked
  control, no crop into a detail, no continuous motion during holds.
- `constrain_geometry` forces live footage to ≥ 65% of the frame, fully contained and opaque. This
  guarantees full-app insets with ~8px UI text.
- Live footage is recorded at 1x (1920×1080 VP8, realtime) even though screenshots are 2x.
- The critic only reports defects. An empty findings list means `reviewed`, so a flat but
  defect-free film passes (the gpt baseline passed with zero findings). Its evidence is 5 frames per
  shot at 480px, which missed the clipped "Still your" narration crop in the Opus take.
- Opus's critic repeated the same findings across passes (drift during holds, sprocket rhythm,
  tiny strip, dead holds) because the vocabulary cannot express the fixes.

Evidence: `.cutroom/verification/prompt-final-latest/openai-studies-8773328a/` and
`.cutroom/verification/opus55-ab/claude-studies-a7b445c6/`.

## Goals

1. Give the director a camera, continuous motion, depth and richer shapes/type, so its plans can
   express what the critic asks for.
2. Record live footage at 2x so the camera can push into real interactions crisply.
3. Replace the defect-only critic with a scored, evidence-backed rubric gate.

## Non-goals

- Music-led timing (beats derived from a composed track) and a binding reference style spec. These are
  separate later sub-projects. This spec improves composition and camera; much of the missing
  excitement is audiovisual rhythm, so music-led timing is the intended next sub-project, not an
  optional extra.
- Director-authored code. The director continues to return declarative JSON only. Its input includes
  untrusted web content, so the contract is the security boundary.
- Blocking export on quality. Below-bar films still export, flagged.

## §1 2x live capture

- `scripts/video_capture.mjs`: `Page.startScreencast` with `maxWidth: 3840, maxHeight: 2160`.
  The page is already at `deviceScaleFactor: 2`. JPEG quality goes from 90 to 85.
- Capture byte budget goes from 350 MB to 1.2 GB (sized for 60s at 4K). The 12,000-frame cap is unchanged.
- `server/video_capture.py` `encode_directed_capture`: encode at 3840×2160 with `libvpx-vp9`,
  CRF 20, `-b:v 0`, `-row-mt 1`. The output filename stays `raw.webm`.
- 4K is requested, not assumed. After encoding, the capture measures the actual decoded frame size
  and records `source_scale = frame_width / viewport_width` (logical CSS viewport, e.g. 1920), plus
  the achieved fps and bytes. The legacy `recordVideo` path measures the same way (→ 1). The zoom
  cap (§2) follows the measured value, so a capture that delivers only 1920-wide frames degrades to
  1x zoom limits instead of producing soft push-ins.
- The renderer requests footage at a size matched to the visible crop, so unzoomed shots do not
  decode 4K needlessly.
- Frame timing is unchanged: per-frame durations come from screencast timestamps, so interaction
  times and video frames share one clock.

Acceptance (e2e, measured on a real capture before 2x is relied on): decoded frames are 3840 wide;
achieved fps ≥ 20; recorded click times still land on the visible interaction (same check as
`scripts/verify_directed_capture.py` against the 1x path); capture size fits the private storage upload
limit. If any check fails, the screencast stays at 1x settings and this is reported, not hidden.
Render time increase is measured and recorded.

## §2 Schema and renderer vocabulary

All new fields are optional with neutral defaults. Existing plans validate and render identically.
`server/video_direction_models.py` and `src/video/DirectedShot.tsx` change in lockstep.

### Camera on sources (footage, product, detail layers)
Keyframed on `MotionState` and carried forward by the existing `inherit_geometry` validator:

| field | range | default | meaning |
|---|---|---|---|
| `cam_x`, `cam_y` | 0–1 | 0.5 | focal point inside the source |
| `cam_zoom` | 1–cap | 1 | 1 = whole source (today's behavior) |
| `focus` | `click-N` | none | server resolves to `cam_x/cam_y` from the recorded interaction |

The renderer draws the source at `zoom` × its fitted size, translated so the focal point sits at the
layer center. It is clamped so no empty edge ever shows, and interpolated with the same easing as geometry.
The cap is `max(1.2, measured source_scale)`, i.e. 2.0 for a verified 2x capture and 1.2 at 1x.

All layout, readability and click coordinates are **logical CSS pixels** of the recorded
`scene.viewport`. Physical resolution affects only the zoom cap. `focus: "click-N"` resolves from
the interaction's logical x/y.

### Continuous drift and parallax
- Shot-level `drift: {x, y, zoom}`: constant rates over the whole shot (default 0). `x`/`y` are
  normalized canvas units per second (|v| ≤ 0.05); `zoom` is a fractional scale change per second
  (|v| ≤ 0.04, e.g. 0.02 = +2%/s), applied around the canvas center.
- Layer-level `depth` 0–1 scales the drift per layer, giving parallax.

### Depth and surface
- Keyframed `elevation` 0–1 per layer adds a layered soft shadow.
- Shot-level `backdrop` from an allow-list: `flat` (default), `radial` (light position x/y plus a
  second palette color), `grain` (subtle deterministic per-frame noise; amount 0–0.15).
- The blanket gradient ban narrows to "no linear decorative gradients".

### Shapes and type
- Shape layers gain `shape`: `rect` (default), `line` (with `stroke`), `segments` (`count`, `gap`:
  sprockets, tick rails), `ring` (outlined highlight; may target `click-N` and track the camera).
- Text gains `font`: `sans` (Inter, default), `display` (Instrument Serif, `@fontsource/instrument-serif`),
  `mono` (JetBrains Mono, `@fontsource-variable/jetbrains-mono`). All are
  bundled through `@fontsource` and preloaded with the existing `delayRender` handle. No network fonts.
- Layers per shot: 7 → 9.

## §3 Director prompt and validator

### Validator (`server/video_direction.py`)
1. **Readability replaces the 65% rule.** Effective scale in logical pixels, accounting for the
   contain fit: `min(layer.w × 1920 / viewport.width, layer.h × 1080 / viewport.height) × cam_zoom`
   must be ≥ 0.65 whenever live footage is visible. A fullscreen 1920×1080 source scores 1.0
   regardless of capture resolution. `constrain_geometry` no longer clamps
   footage size; it resolves `focus` references and clamps the camera to valid bounds and the zoom cap.
2. **Click in frame.** At each recorded click time within a live shot, the click point lies inside
   the visible camera window, with a margin.
3. **References.** Each `click-N` must exist in the shot's source. `cam_zoom` must be ≤ the cap.
4. **Holds are budgeted by reading time, not banned.** A static span (no layer state change, zero
   drift, no live footage playing) may last up to its reading budget: 0.3s per newly revealed word
   plus 0.6s, or 2.0s after a proof frame lands, whichever is larger, and at least 1.2s. Only holds
   beyond the budget are rejected. Drift is never required to satisfy this rule; subtler pacing
   judgments belong to the critic's Pacing axis.
5. Footage opacity may fade over ≤ 0.3s at shot edges, but stays 1 during interactions.

### Director evidence
- Interactions are listed as `click-0…N` with element label, time and source coordinates, plus
  `source_scale` and the zoom cap.
- The contact sheet adds a 2x crop around each click, taken from the raw frame at that moment.

### Prompts (`server/video_prompts.py`, `PROMPT_VERSION = "motion-brief-v8"`)
- RULES drops constraints that are now enforced by the schema or validator (render contract, 65% rule,
  gradient ban) and adds a short vocabulary section (camera/focus, drift/depth, elevation,
  backdrops, shapes, fonts).
- MOTION_STUDIES is rewritten around the new verbs: a push from full proof into `click-N` with a
  ring landing on the control; a segments rail that carries the eye across a cut; a parallax hold
  with type and product at different depths. Still "not a template".
- TREATMENT shots gain `camera` and `depth` notes.

## §4 Scored critic gate

### Rubric (1–10 per axis, each with written 5 and 8 anchors in the prompt)
Proof readability · Canvas and scale · Motion intent · Pacing · Typography · Continuity · Specificity.

### Gate
- `passed`: every axis ≥ 8 and no open blocking findings (clipped settled text, a click hidden or
  cropped, unreadable added type).
- `needs_review`: below the bar after the revision budget. The film still exports.
- `unavailable`: no usable review, including any axis score without a supporting observation.

### Evidence rule
- Every axis score carries at least one observation: shot, time and what is visible. Observations
  may be positive. High scores need evidence as much as low ones.
- Every axis below 8 also carries at least one actionable finding (problem plus intended change).
- An axis at 8 or above needs no defect. The critic is not asked to invent criticism of strong work.
- `reviewed` is replaced by `passed`. The README keeps its honesty wording: "met the rubric on
  sampled frames", not certified quality.

### Revisions
- Budget 2 (`CUTROOM_REVIEW_PASSES`). A revision prompt leads with the lowest axes and the blocking findings.
- A revision is accepted only if it passes the validator and a re-score drops no axis by ≥ 2.

### Evidence
- `reason()` accepts multiple images.
- Per-shot sheets: frames every 0.5s plus shot boundaries, at 960×540.
- 1:1 crops of each text layer's settled rectangle; the click crops from §3.

### Studio
`src/components/ReviewDrawer.tsx` shows per-axis scores and open findings for `passed` and
`needs_review`, with "Another pass" wired to the existing revision action. No new endpoints.

## §5 Testing and verification

Deterministic tests (pytest, mocked providers, no credits), written before implementation:
- Schema: old plans unchanged; camera fields carried forward; `focus` resolution and unknown-click
  rejection; zoom cap follows `source_scale`.
- Validator: readability uses logical pixels (fullscreen 2x source scores 1.0; a non-16:9 source uses
  the contain-fit minimum); small pushed-in footage passes and small unpushed footage fails; a
  cropped-out click fails; a static hold within its reading budget passes without drift, and one
  beyond it fails.
- Critic gate: an axis score without an observation → `unavailable`; an axis below 8 without an
  actionable finding → `unavailable`; all axes ≥ 8 with only positive observations → `passed`; a
  blocking finding → `needs_review` even when all axes ≥ 8; a revision lowering an axis by ≥ 2 is
  rejected; multiple images reach the reasoner.
- Capture: synthetic 4K frames encode to 3840×2160 VP9; `source_scale` is measured from decoded frames
  (synthetic 1920-wide frames → 1, and the zoom cap falls to 1.2).
- Renderer: Remotion stills of fixture plans for camera crop, parallax drift and each shape kind,
  checked with region pixel assertions.

Integration (real credits, run by hand):
1. A fresh 2x capture of the Cutroom flow; run the §1 acceptance checks (frame size, fps,
   interaction timing, storage) and record render time against the 1x path.
2. `scripts/compare_video_prompts.py` with Opus 5.5 and `--review`, into a new folder next to the two
   existing takes.
3. Critic discrimination test. Scores are diagnostic evidence, not tuning targets:
   - Score an independently selected strong film that is not used as a director reference, alongside
     the gpt and Opus takes. Frame-based axes only for the external film (it has no capture
     metadata, so readability/click blocking checks do not apply).
   - Score each film 3 times to measure run-to-run variance.
   - The rubric is trusted only if the strong film ranks clearly above both takes on the visual
     axes by more than the observed variance. Anchors are not adjusted to make particular films
     fail; if the rubric does not discriminate, the anchors are rewritten and the test re-run on
     the same set.
4. Watch all three films side by side.

Then `npm test`, `npm run lint`, `npm run build`.

## Rollout order

§1 capture → §2 schema/renderer → §3 validator/prompts → §4 critic → integration and calibration.
§2 is backward compatible, so each step can merge independently.
