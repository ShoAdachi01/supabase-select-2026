"""Capture resolution is measured from decoded frames, never assumed from the request."""

import json
import subprocess

import pytest
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


def long_manifest(folder, seconds):
    (folder / "capture-frames").mkdir()
    Image.new("RGB", (64, 36), "white").save(folder / "capture-frames/000001.jpg")
    manifest = [{"name": "capture-frames/000001.jpg", "duration": 1.0}] * seconds
    (folder / "capture.json").write_text(json.dumps(manifest))


def test_capture_encode_timeout_scales_with_recording_length(tmp_path, monkeypatch):
    from server import video_render

    timeouts = []

    def run(command, **kwargs):
        timeouts.append(kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(video_render.subprocess, "run", run)
    long_manifest(tmp_path, 40)
    encode_directed_capture(tmp_path)
    assert timeouts == [800]
    timeouts.clear()
    (tmp_path / "capture.json").write_text(
        json.dumps([{"name": "capture-frames/000001.jpg", "duration": 1.0}] * 5)
    )
    encode_directed_capture(tmp_path)
    assert timeouts == [300]


def test_capture_encode_timeout_is_a_readable_error(tmp_path, monkeypatch):
    from server import video_render

    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(video_render.subprocess, "run", run)
    long_manifest(tmp_path, 3)
    with pytest.raises(ValueError, match="Encoding the recording took too long."):
        encode_directed_capture(tmp_path)


def test_ffmpeg_default_timeout_is_unchanged(monkeypatch):
    from server import video_render

    seen = []
    monkeypatch.setattr(
        video_render.subprocess,
        "run",
        lambda command, **kw: seen.append(kw["timeout"]) or subprocess.CompletedProcess(command, 0),
    )
    video_render.ffmpeg("-version")
    assert seen == [300]
