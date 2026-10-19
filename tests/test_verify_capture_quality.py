"""Capture acceptance exits 0 only when 4K, fps and size budgets all hold."""

import json

import pytest

from scripts import verify_capture_quality as verify


def run(tmp_path, monkeypatch, metrics, film_bytes=None):
    (tmp_path / "capture-metrics.json").write_text(json.dumps(metrics))
    if film_bytes is not None:
        (tmp_path / "film.mp4").write_bytes(b"x")
        monkeypatch.setattr(verify, "file_size", lambda path: film_bytes)
    monkeypatch.setattr("sys.argv", ["verify_capture_quality", str(tmp_path)])
    with pytest.raises(SystemExit) as exit_info:
        verify.main()
    return exit_info.value.code


GOOD = {"width": 3840, "height": 2160, "fps": 24.5, "bytes": 10_000_000, "source_scale": 2.0}


def test_passes_good_capture(tmp_path, monkeypatch, capsys):
    assert run(tmp_path, monkeypatch, GOOD) == 0
    assert "PASS: decoded width 3840" in capsys.readouterr().out


@pytest.mark.parametrize(
    "override",
    [{"width": 1920}, {"fps": 12}, {"bytes": 1200 * 1024 * 1024 + 1}],
)
def test_fails_each_bad_metric(tmp_path, monkeypatch, override):
    assert run(tmp_path, monkeypatch, {**GOOD, **override}) == 1


def test_uploaded_film_over_bucket_limit_fails(tmp_path, monkeypatch, capsys):
    assert run(tmp_path, monkeypatch, GOOD, film_bytes=50 * 1024 * 1024 + 1) == 1
    assert "FAIL: uploaded film within 50 MiB bucket limit" in capsys.readouterr().out
    assert run(tmp_path, monkeypatch, GOOD, film_bytes=50 * 1024 * 1024) == 0
