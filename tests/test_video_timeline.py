"""Edits preserve original captures and exported timing matches actual transitions."""

import uuid
from copy import deepcopy

import httpx
import pytest
from fastapi import HTTPException

from server import video_generation
from server.video_models import TimelineClip
from server.video_timeline import browser_clips, compile_timeline, launch_clips


def job():
    return {
        "title": "Meridian",
        "payload": {
            "scenes": [
                {
                    "start": 1,
                    "end": 5,
                    "label": "Projects",
                    "narration": "Open a project.",
                    "thumbnail": "scene-0.jpg",
                },
                {
                    "start": 8,
                    "end": 12,
                    "label": "Board",
                    "narration": "See its board.",
                    "thumbnail": "scene-1.jpg",
                },
            ]
        },
    }


def test_cut_reorder_trim_and_narration_preserve_original_capture():
    source = job()
    before = deepcopy(source)
    clips = [TimelineClip.model_validate(c) for c in browser_clips(source["payload"]["scenes"])]
    clips[0].enabled = False
    clips[1].trim_start, clips[1].trim_end, clips[1].narration = 0.5, 3, "New wording."
    result = compile_timeline(source, clips[::-1])
    assert len(result) == 1
    assert result[0]["start"] == 8.5
    assert result[0]["end"] == 11
    assert result[0]["narration"] == "New wording."
    assert source == before


@pytest.mark.parametrize(
    "change", [{"trim_end": 10}, {"trim_start": 3.9}, {"scene_id": "foreign-scene"}]
)
def test_invalid_source_or_trim_is_rejected(change):
    source = job()
    clip = TimelineClip.model_validate({**browser_clips(source["payload"]["scenes"])[0], **change})
    with pytest.raises(HTTPException) as exc:
        compile_timeline(source, [clip])
    assert exc.value.status_code == 400


def test_all_cut_and_duplicate_ids_are_rejected():
    source = job()
    clip = TimelineClip.model_validate(browser_clips(source["payload"]["scenes"])[0])
    with pytest.raises(HTTPException):
        compile_timeline(source, [clip, clip])
    clip.enabled = False
    with pytest.raises(HTTPException):
        compile_timeline(source, [clip])


def test_asset_is_scoped_to_this_video_and_filename_cannot_escape():
    source = job()
    asset_id = uuid.uuid4()
    clip = TimelineClip(id="generated", kind="generated", asset_id=asset_id)
    with pytest.raises(HTTPException):
        compile_timeline(source, [clip])
    source["payload"]["assets"] = [
        {"id": str(asset_id), "status": "complete", "duration": 4, "filename": "../../private.mp4"}
    ]
    result = compile_timeline(source, [clip])
    assert result[0]["source_file"] == f"asset-{asset_id}.mp4"


def test_launch_plan_contains_real_captures_between_three_editable_cards():
    source = job()
    draft = launch_clips(
        source["payload"]["scenes"], "Meridian", {"hook": {"headline": "Your custom headline"}}
    )
    assert [c["kind"] for c in draft] == ["title", "browser", "browser", "title", "title"]
    assert draft[0]["headline"] == "Your custom headline"
    assert len(compile_timeline(source, [TimelineClip.model_validate(c) for c in draft])) == 5


def test_veo_uses_bounded_duration_and_actionable_quota_error(monkeypatch):
    monkeypatch.setattr(
        video_generation,
        "setting",
        lambda name, default="": "test-key" if name == "GEMINI_API_KEY" else default,
    )
    requests = []

    def post(url, **kwargs):
        requests.append(kwargs["json"])
        return httpx.Response(429, json={"error": {"message": "quota exhausted"}})

    monkeypatch.setattr(video_generation.httpx, "post", post)
    with pytest.raises(ValueError, match="billing"):
        video_generation.start_generation("veo", "Abstract geometric animation.", 4)
    assert requests[0]["parameters"]["durationSeconds"] == 4
    assert "no software UI" in requests[0]["instances"][0]["prompt"]


def test_animation_to_footage_dissolve_exports_actual_motion_and_timing(tmp_path):
    from server.video_render import ffmpeg, render

    raw = tmp_path / "capture.webm"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=green:s=320x180:r=30", "-t", "1", "-c:v", "libvpx", str(raw)
    )
    scenes = [
        {
            "kind": "title",
            "headline": "A better launch.",
            "subtitle": "Your exact words.",
            "layout": "hook",
            "label": "Opening",
            "narration": "",
            "duration": 2,
            "transition": "dissolve",
        },
        {
            "kind": "browser",
            "start": 0,
            "end": 1,
            "label": "Real product",
            "narration": "",
            "transition": "cut",
        },
    ]
    result = render(tmp_path, raw, scenes, "Meridian", "paper", "none", [None, None])
    assert result["duration_seconds"] == pytest.approx(5.7, abs=0.04)
    assert scenes[1]["timeline_start"] == pytest.approx(1.7)
    assert (tmp_path / "edit-0.jpg").exists()
    assert (tmp_path / "film.mp4").stat().st_size > 10000
    ffmpeg("-i", str(tmp_path / "film.mp4"), "-f", "null", "-")


def test_generated_background_keeps_editable_title_and_dissolves_into_capture(tmp_path):
    from server.video_render import ffmpeg, render

    raw = tmp_path / "capture.webm"
    asset_id = uuid.uuid4()
    asset = tmp_path / f"asset-{asset_id}.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30", "-t", "2", "-c:v", "libx264", str(asset))
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=green:s=320x180:r=30", "-t", "1", "-c:v", "libvpx", str(raw)
    )
    scenes = [
        {
            "kind": "generated",
            "source_file": asset.name,
            "end": 2,
            "duration": 2,
            "headline": "Exact editable words.",
            "subtitle": "Independent from the generated pixels.",
            "label": "Launch visual",
            "narration": "",
            "transition": "dissolve",
        },
        {
            "kind": "browser",
            "start": 0,
            "end": 1,
            "label": "Actual capture",
            "narration": "",
            "transition": "cut",
        },
    ]
    result = render(tmp_path, raw, scenes, "Product", "paper", "none", [None, None])
    assert result["duration_seconds"] == pytest.approx(5.7, abs=0.04)
    assert (tmp_path / "caption-0.png").exists()
    assert scenes[0]["thumbnail"] == "edit-0.jpg"
    ffmpeg("-i", str(tmp_path / "film.mp4"), "-f", "null", "-")


def test_veo_completed_operation_returns_download_uri_without_credentials(monkeypatch):
    monkeypatch.setattr(
        video_generation,
        "setting",
        lambda name, default="": "test-key" if name == "GEMINI_API_KEY" else default,
    )

    def get(url, **kwargs):
        assert kwargs["headers"] == {"x-goog-api-key": "test-key"}
        return httpx.Response(
            200,
            json={
                "done": True,
                "response": {
                    "generateVideoResponse": {
                        "generatedSamples": [
                            {
                                "video": {
                                    "uri": "https://generativelanguage.googleapis.com/v1beta/files/video:download?alt=media"
                                }
                            }
                        ]
                    }
                },
            },
        )

    monkeypatch.setattr(video_generation.httpx, "get", get)
    status, uri = video_generation.poll_generation(
        {"provider": "veo", "operation": "models/veo/operations/example"}
    )
    assert status == "complete"
    assert "test-key" not in uri


def test_untrusted_video_download_location_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="download location"):
        video_generation.download_generation(
            {"provider": "veo"}, "https://evil.example/private", tmp_path / "video.mp4"
        )


def test_launch_recuts_overview_and_copy_without_changing_capture():
    source = job()
    source["payload"]["scenes"][0]["action"] = "overview"
    before = deepcopy(source)
    clips = launch_clips(
        source["payload"]["scenes"], "Meridian", {"narration": ["One home.", "Keep work moving."]}
    )
    assert clips[1]["enabled"] is False
    assert clips[2]["narration"] == "Keep work moving."
    assert all(c["transition"] == "cut" for c in clips)
    assert all(not c["narration"] for c in clips if c["kind"] == "title")
    assert sum(c["duration"] for c in clips if c["enabled"]) < 30
    assert source == before


def test_reveal_lands_exactly_on_next_product_frame():
    import numpy as np
    from PIL import Image

    from server.video_motion import motion_frame

    pixels = np.random.default_rng(42).integers(0, 256, (1080, 1920, 3), dtype=np.uint8)
    product = Image.fromarray(pixels)
    for layout in ("hook", "benefit"):
        scene = {"layout": layout, "headline": "Launch with clarity."}
        opening = motion_frame(scene, "midnight", 0.5, 2.4, product)
        last = motion_frame(scene, "midnight", 2.4 - 1 / 30, 2.4, product)
        assert not np.array_equal(np.array(opening), pixels)
        assert np.array_equal(np.array(last), pixels)


def test_short_shot_is_full_screen_and_keeps_complete_speech(tmp_path):
    import numpy as np
    from PIL import Image

    from server.video_render import ffmpeg, render

    raw, audio = tmp_path / "raw.webm", tmp_path / "speech.wav"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=green:s=320x180:r=30", "-t", "1", "-c:v", "libvpx", str(raw)
    )
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2.7", str(audio))
    scenes = [
        {
            "kind": "browser",
            "start": 0,
            "end": 1,
            "duration": 1.6,
            "label": "Product",
            "narration": "",
            "transition": "cut",
        }
    ]
    result = render(tmp_path, raw, scenes, "Product", "paper", "none", [audio])
    assert 2.8 < result["duration_seconds"] < 3
    frame = tmp_path / "check.png"
    ffmpeg("-ss", "0.5", "-i", str(tmp_path / "film.mp4"), "-frames:v", "1", str(frame))
    pixels = np.array(Image.open(frame))
    for y, x in ((20, 20), (20, 1900), (1060, 20), (1060, 1900)):
        assert pixels[y, x, 1] > 100
        assert pixels[y, x, 0] < 10
        assert pixels[y, x, 2] < 10
