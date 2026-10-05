"""Observable contracts, access boundaries, and provider requests without live services."""

import json
import uuid

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server import studio, video_providers, video_service
from server.video_models import VideoInput


class MemoryStore:
    def __init__(self):
        self.user_id = str(uuid.uuid4())
        self.rows = {}

    def save(self, table, row):
        self.rows[(table, row["id"])] = json.loads(json.dumps({**row, "user_id": self.user_id}))
        return row

    def get(self, table, record_id):
        row = self.rows.get((table, record_id))
        if not row:
            raise HTTPException(404, "Record not found in your workspace.")
        return json.loads(json.dumps(row))

    def list(self, table):
        return [
            json.loads(json.dumps(row)) for (kind, _), row in self.rows.items() if kind == table
        ]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(video_service, "VIDEO_DIR", tmp_path)
    monkeypatch.setattr(studio, "VIDEO_DIR", tmp_path)
    return MemoryStore()


@pytest.fixture
def client(store):
    studio.app.dependency_overrides[studio.workspace] = lambda: store
    with TestClient(studio.app) as connection:
        yield connection
    studio.app.dependency_overrides.clear()


def test_credentials_are_never_saved_in_project(store, monkeypatch):
    monkeypatch.setattr(video_service, "public_target", lambda _: None)
    monkeypatch.setattr(
        video_service, "capabilities", lambda: {"reasoning": True, "narration": True}
    )
    secret = "this-is-a-private-test-password"
    body = VideoInput(
        url="https://app.example.com",
        brief="Show the project board.",
        credentials={"username": "private@example.com", "password": secret},
    )
    result = video_service.create_video(store, body)
    saved = json.dumps(list(store.rows.values()))
    assert secret not in str(result)
    assert "private@example.com" not in str(result)
    assert secret not in saved
    assert result["payload"]["has_credentials"] is True


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "file:///etc/passwd",
        "http://user:password@example.com/",
    ],
)
def test_private_or_credentialed_urls_are_rejected(store, url):
    with pytest.raises(HTTPException) as exc:
        video_service.create_video(store, VideoInput(url=url, brief="Show the project board."))
    assert exc.value.status_code == 400


def test_demo_flag_cannot_target_an_arbitrary_internal_app(store, monkeypatch):
    monkeypatch.setattr(video_service, "setting", lambda name, default="": default)
    result = video_service.create_video(
        store, VideoInput(url="http://169.254.169.254/", brief="Show this private app.", demo=True)
    )
    assert result["payload"]["url"] == "http://127.0.0.1:8000/sample/"


def test_private_preview_ticket_cannot_be_reused_for_another_file(store, client, tmp_path):
    video_id = str(uuid.uuid4())
    folder = tmp_path / store.user_id / video_id
    folder.mkdir(parents=True)
    (folder / "film.mp4").write_bytes(b"test video")
    link = studio.media_url(store, video_id, "film.mp4")
    assert client.get(link).status_code == 200
    assert client.get(link.replace("film.mp4", "scene-0.jpg")).status_code == 403
    assert client.get(link.replace(store.user_id, str(uuid.uuid4()))).status_code == 403


def test_scene_count_must_match_capture(store, tmp_path):
    from server.video_models import RenderInput

    result = video_service.create_video(
        store, VideoInput(url="https://example.com", brief="Show the project board.", demo=True)
    )
    result["status"] = "complete"
    result["payload"]["scenes"] = [{"narration": "one"}, {"narration": "two"}]
    store.save("video_jobs", result)
    folder = video_service.directory(store, result["id"])
    folder.mkdir(parents=True)
    (folder / "raw.webm").write_bytes(b"capture")
    with pytest.raises(HTTPException) as exc:
        video_service.prepare_render(store, RenderInput(video_id=result["id"], narration=["one"]))
    assert exc.value.status_code == 400


def test_mcp_unknown_video_is_a_tool_error(client):
    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_video", "arguments": {"video_id": str(uuid.uuid4())}},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is True


def test_stock_voice_speech_request_is_generated_and_saved(tmp_path, monkeypatch):
    requests = []
    monkeypatch.setattr(
        video_providers,
        "setting",
        lambda name, default="": "key" if name == "OPENAI_API_KEY" else default,
    )

    def post(url, **kwargs):
        requests.append((url, kwargs))
        return httpx.Response(200, content=b"generated audio")

    monkeypatch.setattr(video_providers.httpx, "post", post)
    output = tmp_path / "voice.mp3"
    video_providers.speech("A real feature demo.", "marin", output)
    assert output.read_bytes() == b"generated audio"
    assert requests[0][1]["json"]["voice"] == "marin"
    assert requests[0][1]["json"]["input"] == "A real feature demo."


def test_json_mode_always_mentions_json_in_input_messages(monkeypatch):
    requests = []
    monkeypatch.setattr(
        video_providers,
        "setting",
        lambda name, default="": "key" if name == "OPENAI_API_KEY" else default,
    )

    def post(url, **kwargs):
        requests.append(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": '{"narration":["A clear story."]}'}
                        ]
                    }
                ]
            },
        )

    monkeypatch.setattr(video_providers.httpx, "post", post)
    result = video_providers.reason("Write the product narration.")
    assert result["narration"] == ["A clear story."]
    assert "json" in requests[0]["input"][0]["content"][0]["text"].lower()


def test_voice_clone_is_workspace_scoped_and_requires_consent(client, monkeypatch):
    called = []
    monkeypatch.setattr(
        studio, "clone_voice", lambda *args: called.append(args) or ("elevenlabs", "external-voice")
    )
    response = client.post(
        "/api/voices/upload",
        data={"name": "My voice", "consent": "false"},
        files={"file": ("voice.wav", b"0" * 2000)},
    )
    assert response.status_code == 400
    assert not called
    response = client.post(
        "/api/voices/upload",
        data={"name": "My voice", "consent": "true"},
        files={"file": ("voice.wav", b"0" * 2000)},
    )
    assert response.status_code == 200
    custom = client.get("/api/voices").json()[-1]
    assert custom["kind"] == "custom"
    assert custom["name"] == "My voice"
    assert custom["id"] == response.json()["id"]


def test_renderer_exports_real_1080p_mp4_with_music(tmp_path):
    from server.video_render import ffmpeg, render

    raw = tmp_path / "capture.webm"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30", "-t", "1", "-c:v", "libvpx", str(raw)
    )
    scenes = [
        {
            "start": 0,
            "end": 1,
            "label": "A captured scene",
            "narration": "A clear feature demo.",
            "focus": {"x": 640, "y": 360},
        }
    ]
    result = render(tmp_path, raw, scenes, "A product film", "paper", "ambient", [None])
    film = tmp_path / "film.mp4"
    assert film.exists()
    assert b"ftyp" in film.read_bytes()[:40]
    assert result["resolution"] == "1920×1080"
    assert result["fps"] == 30
    assert result["duration_seconds"] >= 4
    assert result["bytes"] > 1000
    assert (tmp_path / "music.wav").exists()
    assert scenes[0]["duration"] == result["duration_seconds"]


def test_failed_animation_generation_preserves_existing_film_and_export(store, monkeypatch):
    from server import video_generation
    from server.video_models import GenerateClipInput

    job = video_service.create_video(
        store, VideoInput(url="https://example.com", brief="Show the project board.", demo=True)
    )
    job["status"] = "complete"
    job["payload"]["export"] = {"bytes": 1234}
    store.save("video_jobs", job)
    folder = video_service.directory(store, job["id"])
    folder.mkdir(parents=True)
    (folder / "film.mp4").write_bytes(b"existing finished film")
    monkeypatch.setattr(video_generation, "generation_capabilities", lambda: {"veo": True})

    def quota_failure(*args):
        raise ValueError("Veo generation quota is unavailable.")

    monkeypatch.setattr(video_generation, "generate_file", quota_failure)
    body = GenerateClipInput(provider="veo", prompt="An original geometric launch animation.")
    pending, asset_id = video_service.prepare_animation(store, job["id"], body)
    video_service.generate_animation(store, pending, body, asset_id)
    after = store.get("video_jobs", job["id"])
    assert after["status"] == "complete"
    assert after["payload"]["export"] == {"bytes": 1234}
    assert after["payload"]["assets"][0]["status"] == "failed"
    assert (folder / "film.mp4").read_bytes() == b"existing finished film"


def test_reference_brief_is_saved_and_forwarded_to_replanning(store, client, monkeypatch):
    from server import video_direction
    from tests.test_video_direction import film, sources

    body = VideoInput(
        url="https://example.com",
        demo=True,
        brief="Show the project board.",
        creative_direction="Follow the project card",
        reference_urls=["https://example.com/reference.mp4"],
    )
    job = video_service.create_video(store, body)
    job["payload"]["scenes"] = sources()
    store.save("video_jobs", job)
    calls = []
    monkeypatch.setattr(studio, "capabilities", lambda: {"reasoning": True})
    monkeypatch.setattr(
        video_direction,
        "direct_film",
        lambda *args, **kwargs: calls.append((args, kwargs)) or film(),
    )
    response = client.post(f"/api/videos/{job['id']}/launch-plan")
    assert response.status_code == 200
    assert calls[0][0][5] == body.creative_direction
    assert calls[0][1]["reference_urls"] == body.reference_urls
    assert store.get("video_jobs", job["id"])["payload"]["reference_urls"] == body.reference_urls
