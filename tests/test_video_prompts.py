"""References, staged treatments, and explicit model routing for repeatable film experiments."""

import io
import json
from copy import deepcopy

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from server import video_direction as director
from server import video_providers as providers
from server import video_reference as references
from server.video_models import VideoInput
from tests.test_video_direction import film, sources


def treatment():
    return {
        "audience": "Project owners",
        "promise": "See the assigned work",
        "evidence": [
            {
                "source": "scene-0.jpg",
                "proves": "Opening a project",
                "visual_anchor": "Project card",
            }
        ],
        "concepts": [
            {
                "name": name,
                "device": "Expand the captured project card",
                "why": "Connect the action to the visible result",
            }
            for name in ("Card", "Path", "Focus")
        ],
        "chosen_concept": "Card",
        "palette": ["#111111", "#ffffff"],
        "typography": "Short left-aligned copy",
        "rhythm": "120 BPM, alternate detail with proof",
        "shots": [
            {"source": "scene-0.jpg", "purpose": "Show card"},
            {"source": "scene-1.jpg", "purpose": "Show result"},
        ],
        "avoid": ["Covering the click"],
        "reference_translation": "No external reference supplied",
    }


def test_staged_treatment_survives_geometry_repair(tmp_path, monkeypatch):
    for scene in sources():
        Image.new("RGB", (320, 180), "blue").save(tmp_path / scene["thumbnail"])
    invalid = film().model_dump()
    invalid["shots"][0]["source"] = "scene-9.jpg"
    answers = iter([treatment(), invalid, film().model_dump()])
    calls = []

    def request(prompt, image, **kwargs):
        calls.append(prompt)
        return next(answers)

    result = director.direct_film(
        "Product",
        "Show both features",
        sources(),
        tmp_path,
        strategy="storyboard",
        reasoner=request,
        reference_analysis={"motion": "a control grows into a panel"},
    )
    assert result == film()
    assert "three genuinely different concepts" in calls[0]
    assert "Implement this chosen treatment" in calls[1]
    assert "Implement this chosen treatment" in calls[2]
    assert "a control grows into a panel" in calls[2]
    assert "unknown capture" in calls[2]
    assert (
        json.loads((tmp_path / "director-treatment.json").read_text())["chosen_concept"] == "Card"
    )


def test_explicit_provider_cannot_be_overridden_by_workspace(monkeypatch):
    settings = {
        "OPENAI_API_KEY": "test-openai",
        "ANTHROPIC_API_KEY": "test-claude",
        "ANTHROPIC_WORKSPACE_ID": "workspace-test",
    }
    monkeypatch.setattr(providers, "setting", lambda name, default="": settings.get(name, default))
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "{}"}],
                "output": [{"content": [{"type": "output_text", "text": "{}"}]}],
                "usage": {"input_tokens": 20},
            },
        )

    monkeypatch.setattr(providers.httpx, "post", post)
    telemetry = {}
    providers.reason(
        "Plan",
        motion=True,
        provider="openai",
        model="gpt-6.1-sol",
        effort="high",
        telemetry=telemetry,
    )
    providers.reason("Plan", motion=True, provider="claude", model="claude-opus-5-5", effort="high")
    assert "openai.com" in calls[0][0]
    assert calls[0][1]["json"]["reasoning"] == {"effort": "high"}
    assert calls[1][1]["json"]["model"] == "claude-opus-5-5"
    assert calls[1][1]["json"]["output_config"] == {"effort": "high"}
    assert calls[1][1]["headers"]["anthropic-workspace-id"] == "workspace-test"
    assert telemetry["model"] == "gpt-6.1-sol"
    assert "test-openai" not in json.dumps(telemetry)


def test_reference_page_uses_guarded_embedded_media_fetch(monkeypatch):
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return b'<video src="/film.mp4"></video>', "text/html", "https://example.com/page"
        return b"video", "video/mp4", url

    monkeypatch.setattr(references, "fetch_public", fetch)
    assert references.fetch_media("https://example.com/page") == (b"video", "video/mp4")
    assert calls == ["https://example.com/page", "https://example.com/film.mp4"]


def test_unavailable_reference_does_not_claim_to_have_watched_it(tmp_path, monkeypatch):
    monkeypatch.setattr(
        references,
        "fetch_public",
        lambda *a, **kw: (_ for _ in ()).throw(ValueError("private URL with secret")),
    )
    result = references.analyze_references(
        ["http://127.0.0.1/private"],
        tmp_path,
        lambda *a, **kw: pytest.fail("Should not call model"),
    )
    assert result["references"][0]["status"] == "unavailable"
    assert "secret" not in json.dumps(result)
    assert "127.0.0.1" not in json.dumps(result)


def test_still_reference_has_explicit_motion_limits(tmp_path):
    output = io.BytesIO()
    Image.new("RGB", (160, 90), "red").save(output, "PNG")
    calls = []
    grammar = {
        key: "Observed composition"
        for key in (
            "palette",
            "typography",
            "composition",
            "pacing",
            "transitions",
            "motion",
            "limitations",
        )
    }
    grammar["transferable_devices"] = ["Asymmetric composition"]

    def request(prompt, image, **kwargs):
        calls.append(prompt)
        return deepcopy(grammar)

    result = references.analyze_media(output.getvalue(), "image/png", tmp_path, request)
    assert result["kind"] == "image"
    assert "motion, pacing and sound were not observed" in result["limitation"]
    assert "not observed" in calls[0]
    assert (tmp_path / "contact.jpg").exists()


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "https://user:password@example.com/a", "javascript:alert(1)"]
)
def test_reference_input_rejects_nonweb_and_credentials(url):
    with pytest.raises(ValidationError):
        VideoInput(url="https://example.com", brief="Show the feature", reference_urls=[url])


def test_structured_video_metadata_precedes_poster():
    parser = references.MediaLinks()
    parser.feed(
        '<meta property="og:image" content="poster.jpg"><script type="application/ld+json">{"@graph":[{"@type":"VideoObject","contentUrl":"film.mp4","thumbnailUrl":"poster.jpg"}]}</script>'
    )
    assert parser.videos == ["film.mp4"]


def test_video_reference_sampling_uses_local_bounded_decoder(tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        for index in range(1, 4):
            Image.new("RGB", (320, 180), "blue").save(tmp_path / f"frame-{index:03}.jpg")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(references.subprocess, "run", run)
    _, metadata = references.sample_media(b"local-video", "video/mp4", tmp_path)
    assert metadata["sample_times"] == [0, 0.5, 1]
    command, options = calls[0]
    assert command[command.index("-protocol_whitelist") + 1] == "file,pipe"
    assert command[command.index("-t") + 1] == "24"
    assert options["timeout"] == 45
    assert "http" not in " ".join(command)


def test_type_can_enter_space_after_product_has_moved_away():
    from server.video_direction_models import DirectedShot

    plan = film()
    setup = DirectedShot.model_validate(
        {
            "source": "scene-0.jpg",
            "label": "Introduce the project",
            "purpose": "Connect the card to its proof",
            "composition": "split",
            "bpm": 120,
            "beats": 6,
            "layers": [
                {
                    "id": "screen",
                    "kind": "product",
                    "states": [
                        {"beat": 0},
                        {"beat": 1, "x": 0.55, "y": 0.1, "w": 0.4, "h": 0.8},
                        {"beat": 6},
                    ],
                },
                {
                    "id": "copy",
                    "kind": "text",
                    "text": "Follow the work",
                    "states": [
                        {"beat": 0, "x": 0.05, "y": 0.2, "w": 0.4, "h": 0.2, "opacity": 0},
                        {"beat": 2, "opacity": 0},
                        {"beat": 3, "opacity": 1},
                        {"beat": 6},
                    ],
                },
            ],
        }
    )
    plan.shots.insert(0, setup)
    assert director.validate_evidence(plan, sources(), 30) == []
    setup.layers[1].states[0].opacity = 1
    assert any(
        "overlaps product pixels" in error
        for error in director.validate_evidence(plan, sources(), 30)
    )


def test_frozen_footage_padding_is_rejected_but_readable_hold_is_allowed():
    plan = film()
    assert director.validate_evidence(plan, sources(), 30) == []
    plan.shots[-1].beats = 16
    assert any(
        "freeze the last frame" in issue
        for issue in director.validate_evidence(plan, sources(), 30)
    )


def test_output_budget_exhaustion_is_retried_without_feeding_truncated_json(monkeypatch):
    config = {"OPENAI_API_KEY": "test-key"}
    monkeypatch.setattr(providers, "setting", lambda name, default="": config.get(name, default))
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "usage": {"output_tokens": 18000},
                    "output": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "usage": {"output_tokens": 5000},
                "output": [{"content": [{"type": "output_text", "text": '{"ready":true}'}]}],
            },
        )

    monkeypatch.setattr(providers.httpx, "post", post)
    telemetry = {}
    assert providers.reason(
        "Compose the film", motion=True, max_tokens=10000, telemetry=telemetry
    ) == {"ready": True}
    assert calls[0]["max_output_tokens"] == 18000
    assert calls[1]["max_output_tokens"] == 32000
    assert calls[0]["input"] == calls[1]["input"]
    assert len(telemetry["usage_attempts"]) == 2
