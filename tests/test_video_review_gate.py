"""The critic gate needs evidence for every score and never invents criticism of strong work."""

import json

import pytest
from PIL import Image
from pydantic import ValidationError

from server import video_composition
from server import video_direction as director
from server.video_direction_models import AXES, FilmReview
from tests.test_video_direction import film, sources


def axis(score, findings=None):
    return {
        "score": score,
        "observations": [
            {"shot": 0, "time": 0.5, "note": "The clicked board fills the frame legibly."}
        ],
        "findings": findings or [],
    }


def review(**scores):
    return {a: axis(scores.get(a, 9)) for a in AXES} | {"blocking": []}


FIX = [
    {
        "shot": 1,
        "time": 2.5,
        "problem": "Strip occupies a thin band.",
        "change": "Scale strip to fill the lower half.",
    }
]


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
    data["canvas"] = axis(6, FIX)
    assert director.gate(FilmReview.model_validate(data)) == "needs_review"


def test_blocking_finding_fails_even_when_every_axis_passes():
    data = review()
    data["blocking"] = [
        {
            "shot": 4,
            "time": 13.4,
            "problem": "Narration text is cropped at the right edge.",
            "change": "Reduce zoom so the full line fits.",
            "blocking": "clipped_text",
        }
    ]
    assert director.gate(FilmReview.model_validate(data)) == "needs_review"


def test_regression_detects_two_point_drops():
    before = FilmReview.model_validate(review(typography=9))
    after = FilmReview.model_validate(
        review(typography=7, canvas=10)
        | {
            "typography": axis(
                7,
                [
                    {
                        "shot": 0,
                        "time": 1,
                        "problem": "Orphaned word.",
                        "change": "Rebreak the line.",
                    }
                ],
            )
        }
    )
    assert director.regressed(before, after) == ["typography"]


def fake_previews(monkeypatch):
    calls = []

    def preview(folder, raw, scenes, theme, audio, checkpoint, **kwargs):
        calls.append(scenes)
        jobs = [{"index": i, "frames": 90} for i in range(2)]
        (folder / "motion-jobs.json").write_text(json.dumps({"jobs": jobs}))
        for job in jobs:
            for frame in director.preview_frame_list(90):
                Image.new("RGB", (960, 540), "blue").save(
                    folder / f"preview-{job['index']}-{frame}.jpg"
                )

    monkeypatch.setattr(video_composition, "prepare_compositions", preview)
    return calls


def test_first_review_passing_skips_revision(tmp_path, monkeypatch):
    calls = fake_previews(monkeypatch)
    prompts = []

    def reasoner(prompt, images, **kwargs):
        prompts.append(prompt)
        return review()

    _, report = director.review_film(film(), sources(), tmp_path, "paper", 30, reasoner=reasoner)
    assert len(calls) == 1 and len(prompts) == 1
    assert report["status"] == "passed"
    assert report["rubric"] == "film-rubric-v1"
    assert report["revision_count"] == 0
    assert report["passes"][0]["scores"] == {a: 9 for a in AXES}


def test_revision_that_regresses_an_axis_is_rejected(tmp_path, monkeypatch):
    calls = fake_previews(monkeypatch)
    original = film()
    revised = film().model_dump()
    revised["concept"] = "A revised concept that follows the same product action."
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    worse = review(canvas=6, typography=7) | {
        "canvas": axis(6, FIX),
        "typography": axis(7, FIX),
    }
    answers = iter([first, revised, worse, revised, worse])
    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "2")
    plan, report = director.review_film(
        original, sources(), tmp_path, "paper", 30, reasoner=lambda *a, **k: next(answers)
    )
    assert len(calls) == 3
    assert report["revision_count"] == 0
    assert report["passes"][1]["rejected_revision"] == ["Regressed typography"]
    assert report["status"] == "needs_review"
    assert plan.concept == original.concept
