"""Motion plans preserve real pixels, trimmed sources, speech, and private asset boundaries."""

import json
import wave

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from server import video_composition
from server.video_alignment import align_result_shots
from server.video_models import TimelineClip
from server.video_render import ffmpeg, original_music, transition_cues


@pytest.fixture
def capture(tmp_path):
    path = tmp_path / "raw.webm"
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=320x180:r=30:d=1",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=320x180:r=30:d=1",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v]",
        "-map",
        "[v]",
        "-c:v",
        "libvpx",
        str(path),
    )
    return path


def test_motion_uses_trimmed_frame_and_preserves_narration(tmp_path, capture, monkeypatch):
    monkeypatch.setattr(video_composition, "run_compositor", lambda *args: None)
    speech = tmp_path / "voice.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=400:sample_rate=48000", "-t", "2.7", str(speech))
    scenes = [
        {"kind": "title", "motion": "reveal", "duration": 1, "headline": "Real product"},
        {
            "kind": "browser",
            "motion": "detail",
            "start": 1.2,
            "end": 2,
            "duration": 1,
            "viewport": {"width": 1920, "height": 1080},
            "focus": {"x": 1440, "y": 810},
        },
    ]
    video_composition.prepare_compositions(tmp_path, capture, scenes, "paper", [None, speech])
    jobs = json.loads((tmp_path / "motion-jobs.json").read_text())["jobs"]
    assert jobs[1]["frames"] == 86
    assert jobs[1]["focus"] == {"x": 0.75, "y": 0.75}
    image = np.array(Image.open(tmp_path / jobs[0]["product"]))
    assert image[500, 900, 2] > 240  # The trimmed BLUE shot, not the capture's red first frame.
    assert image[500, 900, 0] < 10


def test_captured_details_cannot_escape_job_directory(tmp_path, capture, monkeypatch):
    monkeypatch.setattr(
        video_composition,
        "run_compositor",
        lambda *args: pytest.fail("Do not render unsafe assets"),
    )
    scenes = [
        {
            "kind": "browser",
            "motion": "panels",
            "start": 0,
            "end": 1,
            "duration": 1,
            "details": ["../../secret.png"],
        }
    ]
    with pytest.raises(ValueError, match="Invalid captured detail"):
        video_composition.prepare_compositions(tmp_path, capture, scenes, "paper", [None])


def test_only_reviewed_motion_presets_are_accepted():
    with pytest.raises(ValidationError):
        TimelineClip(id="x", motion="execute-javascript")
    assert TimelineClip(id="x").motion == "none"  # Old projects retain their original rendering.


def test_result_alignment_finds_screen_despite_wrong_browser_clock(tmp_path, capture):
    Image.new("RGB", (320, 180), "blue").save(tmp_path / "scene-0.jpg")
    scenes = [{"shot": "result", "thumbnail": "scene-0.jpg", "start": 0, "end": 0.8}]
    align_result_shots(capture, tmp_path, scenes)
    assert scenes[0]["start"] >= 1
    assert scenes[0]["end"] <= 2
    assert scenes[0]["capture_start"] == 0


def test_result_alignment_rejects_screen_absent_from_recording(tmp_path, capture):
    Image.new("RGB", (320, 180), "white").save(tmp_path / "scene-0.jpg")
    with pytest.raises(ValueError, match="could not be verified"):
        align_result_shots(
            capture,
            tmp_path,
            [{"shot": "result", "thumbnail": "scene-0.jpg", "start": 0, "end": 1}],
        )


def test_panel_treatment_without_regions_uses_complete_screen(tmp_path, capture, monkeypatch):
    monkeypatch.setattr(video_composition, "run_compositor", lambda *args: None)
    video_composition.prepare_compositions(
        tmp_path,
        capture,
        [{"motion": "panels", "start": 0, "end": 1, "duration": 1}],
        "paper",
        [None],
    )
    job = json.loads((tmp_path / "motion-jobs.json").read_text())["jobs"][0]
    assert job["preset"] == "reveal"
    assert job["details"] == []


def test_sound_cues_are_repeatable_and_do_not_clip(tmp_path):
    first, second = tmp_path / "a.wav", tmp_path / "b.wav"
    original_music(first, 2, "momentum")
    original_music(second, 2, "momentum")
    before = first.read_bytes()
    scenes = [{"motion": "panels", "timeline_start": 1}]
    transition_cues(first, scenes)
    transition_cues(second, scenes)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes() != before
    with wave.open(str(first)) as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    assert max(abs(samples.astype(int))) <= 31130
