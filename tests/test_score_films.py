"""Critic calibration samples frames within the image cap and aggregates runs honestly."""

import json
import statistics

import pytest
from PIL import Image

from scripts import score_films
from server.video_render import ffmpeg

AXES = ("readability", "canvas", "motion", "pacing", "typography", "continuity", "specificity")


@pytest.fixture
def film(tmp_path):
    path = tmp_path / "film.mp4"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=640x360:r=30:d=5",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    )
    return path


def review(score):
    observations = [{"shot": 0, "time": 1.0, "note": "a visible detail"}]
    findings = []
    if score and score < 8:
        findings = [{"shot": 0, "time": 1.0, "problem": "a visible problem", "change": "change it"}]
    axis = {"score": score, "observations": observations, "findings": findings}
    return {**{a: axis for a in AXES}, "blocking": []}


def test_sheets_respect_image_cap(film, tmp_path):
    sheets = score_films.film_sheets(film, 0, tmp_path / "work")
    assert len(sheets) == 3  # 5 s at 2 fps = 10 frames, 4 per sheet
    import base64
    import io

    counts = []
    for encoded in sheets:
        image = Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert max(image.size) <= 1568
        counts.append(image.width // 784 * (image.height // 471))
    assert max(counts) <= 4


def test_aggregation_skips_invalid_run(film, tmp_path, monkeypatch, capsys):
    scores = iter([6, None, 8])
    prompts = []

    def fake_reason(prompt, sheets, **kwargs):
        prompts.append(prompt)
        assert kwargs["motion"] is True and kwargs["provider"] == "claude"
        score = next(scores)
        kwargs["telemetry"].update(provider="claude", usage={"input_tokens": 5})
        return review(score) if score else {"nonsense": True}

    monkeypatch.setattr(score_films, "reason", fake_reason)
    out = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv", ["score_films", "--films", str(film), "--runs", "3", "--out", str(out)]
    )
    score_films.main()
    assert "No plan or capture metadata is available" in prompts[0]
    data = json.loads((out / "scores.json").read_text())
    runs = data[str(film)]["runs"]
    assert [bool(r["error"]) for r in runs] == [False, True, False]
    assert runs[0]["usage"]["usage"] == {"input_tokens": 5}
    assert data[str(film)]["summary"]["canvas"]["mean"] == 7
    assert data[str(film)]["summary"]["canvas"]["stdev"] == pytest.approx(statistics.stdev([6, 8]))
    assert data[str(film)]["valid_runs"] == 2
    assert "7.00 ± 1.41" in capsys.readouterr().out
