"""Director contracts, evidence fidelity, continuity, and bounded rendered review."""

import json
from copy import deepcopy

import pytest
from PIL import Image
from pydantic import ValidationError

from server import video_composition
from server import video_direction as director
from server.video_direction_models import FilmDirection
from server.video_models import TimelineClip
from server.video_sound import beat_map, interaction_schedule, motion_schedule
from server.video_timeline import compile_timeline


def sources():
    return [
        dict(
            thumbnail=f"scene-{i}.jpg",
            start=i * 3,
            end=i * 3 + 3,
            label=f"Feature {i}",
            narration="",
            details=[],
            interactions=[dict(kind="click", time=i * 3 + 1)],
        )
        for i in range(2)
    ]


def film():
    return FilmDirection.model_validate(
        dict(
            concept="Follow a real product action through its visible result.",
            grammar="Precise product proof, one spatial match, and a deliberate closing cut.",
            reference="precision",
            shots=[
                dict(
                    source=f"scene-{i}.jpg",
                    label=f"Feature {i}",
                    purpose="Demonstrate the captured feature interaction.",
                    composition="product",
                    entry="cut" if i == 0 else "match",
                    bpm=120,
                    beats=6,
                    layers=[
                        dict(
                            id="product",
                            kind="footage",
                            states=[
                                dict(beat=0),
                                dict(beat=2, x=0.05, y=0.05, w=0.9, h=0.9),
                                dict(beat=6, x=0, y=0, w=1, h=1),
                            ],
                        )
                    ],
                    hits=[dict(beat=1, kind="thump")],
                )
                for i in range(2)
            ],
        )
    )


def test_capture_evidence_compiles_without_mutating_sources_or_losing_events():
    source = sources()
    before = deepcopy(source)
    plan = film()
    assert director.validate_evidence(plan, source, 30) == []
    clips = [TimelineClip.model_validate(c) for c in director.compile_direction(plan, source)]
    rendered = compile_timeline({"payload": {"scenes": source}}, clips)
    assert [s["start"] for s in rendered] == [0, 3]
    assert rendered[1]["direction"]["entry"] == "match"
    assert rendered[1]["interactions"] == source[1]["interactions"]
    assert source == before


def test_director_can_choose_structure_without_inserting_opening_or_closing_cards():
    plan = film()
    still = plan.shots[0].model_copy(deep=True)
    still.composition = "type"
    still.layers[0].kind = "product"
    still.entry = "cut"
    # A still can appear before or after the proof; there is no compulsory hook or outro.
    for shots in [[still, *plan.shots], [*plan.shots, still]]:
        variant = plan.model_copy(update={"shots": shots})
        assert director.validate_evidence(variant, sources(), 30) == []
        assert len(director.compile_direction(variant, sources())) == 3


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (lambda p: setattr(p.shots[0], "source", "scene-9.jpg"), "unknown capture"),
        (lambda p: setattr(p.shots[0], "beats", 2), "hold at least"),
        (lambda p: setattr(p.shots[1].layers[0].states[0], "x", 0.1), "match-cut geometry"),
        (lambda p: setattr(p.shots[1].layers[0], "kind", "detail-0"), "was not captured"),
        (lambda p: setattr(p.shots[1], "bpm", 150), "one BPM"),
        (lambda p: setattr(p.shots[0].layers[0].states[0], "opacity", 0), "fully opaque"),
    ],
)
def test_invalid_evidence_and_continuity_are_rejected(mutation, expected):
    plan = film()
    mutation(plan)
    assert any(expected in issue for issue in director.validate_evidence(plan, sources(), 30))


@pytest.mark.parametrize(
    "bad",
    [
        {"source": "../../private.jpg"},
        {"layers": [{"id": "secret", "kind": "https://private/image", "states": [{"beat": 0}]}]},
        {"layers": [{"id": "x", "kind": "shape", "states": [{"beat": 0, "x": float("nan")}]}]},
        {"layers": [{"id": "x", "kind": "shape", "states": [{"beat": 0}, {"beat": 0}]}]},
        {"background": "url(https://private/secret)"},
        {"execute": "alert(1)"},
    ],
)
def test_model_cannot_supply_code_remote_assets_or_invalid_numbers(bad):
    data = film().model_dump()
    data["shots"][0].update(bad)
    with pytest.raises(ValidationError):
        FilmDirection.model_validate(data)


def test_directed_clip_requires_matching_duration_and_scene_contract():
    with pytest.raises(ValidationError):
        TimelineClip(id="missing", motion="directed")
    clip = director.compile_direction(film(), sources())[0]
    clip["duration"] = 9
    with pytest.raises(ValidationError, match="beat grid"):
        TimelineClip.model_validate(clip)


def test_still_product_never_replays_captured_clicks_and_motion_has_exact_frame_times():
    clips = compile_timeline(
        {"payload": {"scenes": sources()}},
        [TimelineClip.model_validate(c) for c in director.compile_direction(film(), sources())],
    )
    clips[0]["timeline_start"] = 0
    clips[1]["timeline_start"] = 3
    clips[1]["direction"]["layers"][0]["kind"] = "product"
    assert [e["time"] for e in interaction_schedule(clips)] == [1]
    assert [e["time"] for e in motion_schedule(clips)] == [0.5, 3.5]
    beats = beat_map(clips, 6)
    assert beats["bpm"] == 120
    assert beats["downbeats"] == [0, 2, 4]
    assert all(time * 30 == round(time * 30) for time in beats["beats"])


def test_director_repairs_invalid_plan_and_receives_screens(tmp_path, monkeypatch):
    for scene in sources():
        Image.new("RGB", (320, 180), "blue").save(tmp_path / scene["thumbnail"])
    invalid = film().model_dump()
    invalid["shots"][0]["source"] = "scene-9.jpg"
    answers = iter([invalid, film().model_dump()])
    calls = []
    monkeypatch.setattr(
        director, "reason", lambda *args, **kwargs: calls.append(args) or next(answers)
    )
    result = director.direct_film("Product", "Show both features", sources(), tmp_path)
    assert result == film()
    assert calls[0][1].startswith("/9j/")
    assert "unknown capture" in calls[1][0]
    assert (tmp_path / "beat-grid.json").exists()
    assert json.loads((tmp_path / "beat-grid.json").read_text())[1]["start_frame"] == 90


def test_review_uses_rendered_frames_and_is_bounded(tmp_path, monkeypatch):
    calls = []

    def preview(folder, raw, scenes, theme, audio, checkpoint, **kwargs):
        assert kwargs["preview"] is True
        calls.append(scenes)
        jobs = [{"index": i, "frames": 90} for i in range(2)]
        (folder / "motion-jobs.json").write_text(json.dumps({"jobs": jobs}))
        for job in jobs:
            for frame in (0, 18, 45, 71, 89):
                Image.new("RGB", (960, 540), "blue").save(
                    folder / f"preview-{job['index']}-{frame}.jpg"
                )

    monkeypatch.setattr(video_composition, "prepare_compositions", preview)
    answers = iter(
        [
            {"findings": [{"shot": 0, "time": 1, "problem": "Title needs room"}]},
            film().model_dump(),
            {"findings": [{"shot": 0, "time": 1, "problem": "Title needs room"}]},
            film().model_dump(),
            {"findings": [{"shot": 0, "time": 1, "problem": "Title needs room"}]},
        ]
    )
    monkeypatch.setattr(director, "reason", lambda *args, **kwargs: next(answers))
    _, report = director.review_film(film(), sources(), tmp_path, "paper", 30)
    assert len(calls) == 3
    assert report["revision_count"] == 2
    assert (
        report["status"] == "needs_review"
    )  # Never claim that self-evaluation guarantees quality.
    assert (tmp_path / "director-review-2.jpg").exists()


def test_evidence_paths_do_not_escape_private_job(tmp_path):
    with pytest.raises(ValueError, match="evidence asset"):
        director.contact_sheet(tmp_path, [("../secret.jpg", "secret")], "contact.jpg")


def test_partial_state_keeps_geometry_instead_of_jumping_to_defaults():
    from server.video_direction_models import MotionLayer

    layer = MotionLayer.model_validate(
        dict(
            id="card",
            kind="product",
            states=[
                dict(beat=0, x=0.2, y=0.3, w=0.5, h=0.4, radius=24),
                dict(beat=2, opacity=0),
            ],
        )
    )
    assert layer.states[1].x == 0.2
    assert layer.states[1].radius == 24
    assert layer.states[1].opacity == 0


def test_motion_model_configuration_is_separate_from_browser_selection(monkeypatch):
    import httpx

    from server import video_providers

    config = {
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "gpt-4.1-mini",
        "CUTROOM_MOTION_MODEL": "gpt-5.4",
    }
    monkeypatch.setattr(
        video_providers, "setting", lambda name, default="": config.get(name, default)
    )
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        )

    monkeypatch.setattr(video_providers.httpx, "post", post)
    video_providers.reason("Select a button")
    video_providers.reason("Compose motion", motion=True, max_tokens=10000)
    assert calls[0]["model"] == "gpt-4.1-mini"
    assert "reasoning" not in calls[0]
    assert calls[1]["model"] == "gpt-5.4"
    assert calls[1]["reasoning"] == {"effort": "medium"}
    assert calls[1]["max_output_tokens"] == 18000
    assert calls[1]["store"] is False


def test_provider_access_error_is_not_retried_as_bad_art_direction(tmp_path, monkeypatch):
    from server.video_providers import ProviderError

    for scene in sources():
        Image.new("RGB", (320, 180), "blue").save(tmp_path / scene["thumbnail"])
    calls = []

    def fail(*args, **kwargs):
        calls.append(1)
        raise ProviderError("Unavailable provider")

    monkeypatch.setattr(director, "reason", fail)
    with pytest.raises(ProviderError):
        director.direct_film("Product", "Show features", sources(), tmp_path)
    assert len(calls) == 1
