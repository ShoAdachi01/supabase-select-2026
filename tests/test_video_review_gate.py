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


def test_blocking_finding_nested_under_an_axis_fails_the_gate():
    data = review()
    data["typography"] = axis(
        8,
        [
            {
                "shot": 2,
                "time": 6.0,
                "problem": "Headline is cropped at the right edge.",
                "change": "Shorten the line so it fits.",
                "blocking": "clipped_text",
            }
        ],
    )
    assert director.gate(FilmReview.model_validate(data)) == "needs_review"


def test_critic_prompt_keeps_source_guards():
    for phrase in (
        "Never request UI that is absent from the source frame",
        "recoloring product pixels",
        "enlarging every native UI label",
        "short cursor lead-in before the destination; that is not a duplicated shot",
        "White or light added type on a light screenshot is a readability defect.",
    ):
        assert phrase in director.CRITIC


def test_regression_rejection_survives_a_later_invalid_revision(tmp_path, monkeypatch):
    fake_previews(monkeypatch)
    revised = film().model_dump()
    revised["concept"] = "A revised concept that follows the same product action."
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    worse = review(canvas=6, typography=7) | {
        "canvas": axis(6, FIX),
        "typography": axis(7, FIX),
    }
    answers = iter([first, revised, worse, revised, first])
    checks = iter([[], ["Shot 0 holds too long."]])
    monkeypatch.setattr(director, "validate_evidence", lambda *a: next(checks))
    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "2")
    prompts = []

    def reasoner(prompt, *a, **k):
        prompts.append(prompt)
        return next(answers)

    _, report = director.review_film(film(), sources(), tmp_path, "paper", 30, reasoner=reasoner)
    assert report["passes"][1]["rejected_revision"] == [
        "Regressed typography",
        "Shot 0 holds too long.",
    ]
    saved = json.loads((tmp_path / "director-review.json").read_text())
    assert saved["passes"][1]["rejected_revision"][0] == "Regressed typography"
    assert "Regressed typography" in prompts[3]


def test_final_points_at_first_review_when_revision_provider_fails(tmp_path, monkeypatch):
    fake_previews(monkeypatch)
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    answers = iter([first])

    def reasoner(prompt, *a, **k):
        try:
            return next(answers)
        except StopIteration:
            raise director.ProviderError("revision failed") from None

    _, report = director.review_film(film(), sources(), tmp_path, "paper", 30, reasoner=reasoner)
    assert report["final"]["attempt"] == 0
    assert report["final"]["scores"] == report["passes"][0]["scores"]
    assert report["final"]["review"]["canvas"]["score"] == 6
    assert report["passes"][0]["rejected_revision"] == ["revision failed"]


def test_final_stays_on_best_attempt_after_regression(tmp_path, monkeypatch):
    fake_previews(monkeypatch)
    revised = film().model_dump()
    revised["concept"] = "A revised concept that follows the same product action."
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    worse = review(canvas=6, typography=7) | {
        "canvas": axis(6, FIX),
        "typography": axis(7, FIX),
    }
    answers = iter([first, revised, worse, revised, worse])
    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "2")
    _, report = director.review_film(
        film(), sources(), tmp_path, "paper", 30, reasoner=lambda *a, **k: next(answers)
    )
    assert report["final"]["attempt"] == 0
    assert report["final"]["scores"] == report["passes"][0]["scores"]
    assert report["passes"][1]["rejected_revision"] == ["Regressed typography"]


def test_unavailable_review_has_no_final(tmp_path, monkeypatch):
    fake_previews(monkeypatch)
    _, report = director.review_film(
        film(), sources(), tmp_path, "paper", 30, reasoner=lambda *a, **k: {"bad": 1}
    )
    assert report["status"] == "unavailable"
    assert "final" not in report


@pytest.mark.parametrize(
    "value, expected", [("abc", 2), ("1.5", 2), ("", 2), ("-3", 0), ("0", 0), ("3", 3), ("9", 4)]
)
def test_review_passes_setting_is_clamped(monkeypatch, value, expected):
    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", value)
    assert director.review_passes() == expected


def test_non_integer_review_passes_does_not_abort_review(tmp_path, monkeypatch):
    fake_previews(monkeypatch)
    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "lots")
    _, report = director.review_film(
        film(), sources(), tmp_path, "paper", 30, reasoner=lambda *a, **k: review()
    )
    assert report["status"] == "passed"


def test_evidence_failure_makes_the_pass_unavailable_not_an_exception(tmp_path, monkeypatch):
    fake_previews(monkeypatch)

    def broken(*a, **k):
        raise ValueError("Could not inspect the recorded source frames.")

    monkeypatch.setattr(director, "review_evidence", broken)
    calls = []
    plan, report = director.review_film(
        film(), sources(), tmp_path, "paper", 30, reasoner=lambda *a, **k: calls.append(a)
    )
    assert calls == []
    assert report["status"] == "unavailable"
    assert report["passes"][0]["attempt"] == 0 and "evidence" in report["passes"][0]["error"]
    assert plan == film()


def numbered_evidence(monkeypatch):
    renders = []

    def evidence(folder, plan, jobs, scenes):
        renders.append(plan.concept)
        return [f"render-{len(renders) - 1}"]

    monkeypatch.setattr(director, "review_evidence", evidence)
    return renders


def test_revision_after_a_regression_sees_the_best_films_frames(tmp_path, monkeypatch):
    fake_previews(monkeypatch)
    numbered_evidence(monkeypatch)
    revised = film().model_dump()
    revised["concept"] = "A revised concept that follows the same product action."
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    worse = review(canvas=6, typography=7) | {
        "canvas": axis(6, FIX),
        "typography": axis(7, FIX),
    }
    answers = iter([first, revised, worse, revised, worse])
    revisions = []

    def reasoner(prompt, images, **k):
        if not prompt.startswith("Score these"):
            revisions.append((prompt, images))
        return next(answers)

    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "2")
    director.review_film(film(), sources(), tmp_path, "paper", 30, reasoner=reasoner)
    assert [images for _, images in revisions] == [["render-0"], ["render-0"]]
    assert "Prior revision rejections: []" in revisions[0][0]
    assert 'Prior revision rejections: [["Regressed typography"]]' in revisions[1][0]


def test_validator_rejected_revision_retries_without_rerendering(tmp_path, monkeypatch):
    calls = fake_previews(monkeypatch)
    renders = numbered_evidence(monkeypatch)
    revised = film().model_dump()
    revised["concept"] = "A revised concept that follows the same product action."
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    answers = iter([first, revised, revised, review()])
    checks = iter([["Shot 0 holds too long."], []])
    monkeypatch.setattr(director, "validate_evidence", lambda *a: next(checks))
    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "2")
    prompts = []

    def reasoner(prompt, *a, **k):
        prompts.append(prompt)
        return next(answers)

    plan, report = director.review_film(
        film(), sources(), tmp_path, "paper", 30, reasoner=reasoner
    )
    assert len(calls) == 2 and len(renders) == 2  # the unchanged best plan is not re-rendered
    assert "Shot 0 holds too long." in prompts[2]
    assert report["passes"][0]["rejected_revision"] == ["Shot 0 holds too long."]
    assert report["revision_count"] == 1 and report["status"] == "passed"
    assert plan.concept == revised["concept"]


def test_rejected_revisions_count_against_the_pass_budget(tmp_path, monkeypatch):
    calls = fake_previews(monkeypatch)
    revised = film().model_dump()
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    answers = iter([first, revised, revised, revised])
    monkeypatch.setattr(director, "validate_evidence", lambda *a: ["Shot 0 holds too long."])
    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "2")
    _, report = director.review_film(
        film(), sources(), tmp_path, "paper", 30, reasoner=lambda *a, **k: next(answers)
    )
    assert len(calls) == 1
    assert report["passes"][0]["rejected_revision"] == ["Shot 0 holds too long."] * 2
    assert report["status"] == "needs_review"


def test_critic_and_revision_usage_is_recorded_on_each_pass(tmp_path, monkeypatch):
    fake_previews(monkeypatch)
    revised = film().model_dump()
    first = review(canvas=6) | {"canvas": axis(6, FIX)}
    answers = iter([first, revised, review()])
    budgets = []

    def reasoner(prompt, images, *, telemetry=None, **k):
        critic = prompt.startswith("Score these")
        if critic:
            budgets.append(k["max_tokens"])
        telemetry.update(
            provider="claude",
            model="claude-opus-5-5",
            effort="high",
            seconds=1.5,
            usage={"output_tokens": 900 if critic else 4000},
            usage_attempts=[{"output_tokens": 900 if critic else 4000}],
            prompt="secret prompt text",
        )
        return next(answers)

    monkeypatch.setenv("CUTROOM_REVIEW_PASSES", "2")
    _, report = director.review_film(film(), sources(), tmp_path, "paper", 30, reasoner=reasoner)
    assert budgets == [12000, 12000]
    keys = {"provider", "model", "seconds", "usage", "usage_attempts"}
    for entry in report["passes"]:
        assert set(entry["usage"]) == keys
        assert entry["usage"]["usage"] == {"output_tokens": 900}
    (revision,) = report["passes"][0]["revision_usage"]
    assert set(revision) == keys and revision["usage"] == {"output_tokens": 4000}
    assert "revision_usage" not in report["passes"][1]
    assert "secret prompt text" not in (tmp_path / "director-review.json").read_text()
