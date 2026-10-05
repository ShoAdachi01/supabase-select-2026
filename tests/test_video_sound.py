import json
import wave

import numpy as np
import pytest
from PIL import Image

from server.video_capture import encode_directed_capture
from server.video_render import ffmpeg, render
from server.video_sound import interaction_audio, interaction_schedule, launch_music
from server.video_timeline import launch_clips, music_launch_plan


def test_interactions_follow_trim_speed_and_timeline_offset(tmp_path):
    scenes = [
        {
            "kind": "browser",
            "start": 2,
            "end": 10,
            "duration": 4,
            "timeline_start": 3,
            "interactions": [
                {"kind": "click", "time": 1},
                {"kind": "click", "time": 4},
                {"kind": "key", "time": 8},
                {"kind": "key", "time": 10},
            ],
        }
    ]
    assert [e["time"] for e in interaction_schedule(scenes)] == [4, 6]
    path = tmp_path / "sound.wav"
    interaction_audio(path, 8, scenes)
    with wave.open(str(path)) as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").reshape(-1, 2)
        rate = source.getframerate()
    assert not samples[: 4 * rate].any()
    assert samples[4 * rate : 4 * rate + 100].any()
    assert not samples[5 * rate : 6 * rate].any()
    assert samples[6 * rate : 6 * rate + 100].any()


def test_music_is_repeatable_stereo_and_has_headroom(tmp_path):
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    launch_music(first, 6)
    launch_music(second, 6)
    assert first.read_bytes() == second.read_bytes()
    with wave.open(str(first)) as source:
        assert source.getnchannels() == 2
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").reshape(-1, 2)
    assert np.max(np.abs(samples.astype(int))) < 31000
    assert np.any(samples[:, 0] != samples[:, 1])


@pytest.mark.parametrize(
    "frame",
    [
        {"name": "../secret.jpg", "duration": 1},
        {"name": "capture-frames/000001.jpg", "duration": -1},
        {"name": "capture-frames/000001.jpg", "duration": float("nan")},
    ],
)
def test_capture_rejects_unsafe_assets_and_timing(tmp_path, frame):
    (tmp_path / "capture.json").write_text(json.dumps([frame]))
    with pytest.raises(ValueError, match="Invalid directed capture"):
        encode_directed_capture(tmp_path)


def test_music_led_plan_preserves_typing_and_uses_beat_lengths():
    scene = {
        "start": 0,
        "end": 6,
        "label": "Make it yours",
        "shot": "action",
        "action": "fill",
        "interactions": [{"kind": "key", "time": 5.1}],
        "narration": "Old narration",
    }
    clips = launch_clips([scene], "Product", music_led=True)
    assert all(not c["narration"] for c in clips)
    action = next(c for c in clips if c["kind"] == "browser")
    assert action["duration"] >= 5.7
    assert action["duration"] % 0.8 == pytest.approx(0, abs=1e-6)
    assert action["motion"] == "detail"


def test_music_led_plan_uses_generated_labels_and_ignores_invalid_label_shape():
    scenes = [{"start": 0, "end": 3, "label": "Open Projects"}]
    for plan, expected in [
        ({"labels": ["Every project, together."]}, "Every project, together."),
        ({"labels": None}, "Open Projects"),
    ]:
        clips = launch_clips(scenes, "Product", plan, music_led=True)
        clip = next(c for c in clips if c["kind"] == "browser")
        assert clip["headline"] == expected
        assert not clip["narration"]


def test_copy_director_receives_real_screens_and_rejects_unsafe_paths(tmp_path, monkeypatch):
    from server import video_providers

    calls = []
    monkeypatch.setattr(
        video_providers,
        "reason",
        lambda *args: calls.append(args) or {"labels": {"scene-1.jpg": "Owners. Dates. Progress."}},
    )
    Image.new("RGB", (320, 180), "blue").save(tmp_path / "scene-1.jpg")
    scenes = [{"label": "Website refresh", "action": "click", "thumbnail": "scene-1.jpg"}]
    plan = music_launch_plan("Product", "Show project tracking", scenes, tmp_path)
    assert plan["labels"] == ["Owners. Dates. Progress."]
    assert "content INSIDE" in calls[0][0]
    assert calls[0][1].startswith("/9j/")  # Actual JPEG evidence accompanies the brief.
    scenes[0]["thumbnail"] = "../private.jpg"
    with pytest.raises(ValueError, match="Invalid screen evidence"):
        music_launch_plan("Product", "Show project tracking", scenes, tmp_path)
    assert len(calls) == 1


def test_narrated_export_keeps_voice_audible_over_music(tmp_path):
    raw, speech = tmp_path / "raw.webm", tmp_path / "speech.wav"
    ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=1", "-c:v", "libvpx", str(raw))
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=1000:duration=0.7:sample_rate=24000", str(speech))
    render(
        tmp_path,
        raw,
        [{"start": 0, "end": 1, "duration": 1, "narration": "Voice remains."}],
        "Product",
        "paper",
        "momentum",
        [speech],
    )
    decoded = tmp_path / "check.wav"
    ffmpeg("-i", str(tmp_path / "film.mp4"), "-ac", "1", "-ar", "24000", str(decoded))
    with wave.open(str(decoded)) as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    spectrum = np.abs(np.fft.rfft(samples[2400:12000]))
    frequency = np.fft.rfftfreq(9600, 1 / 24000)[np.argmax(spectrum)]
    assert frequency == pytest.approx(1000, abs=5)
