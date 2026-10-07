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
