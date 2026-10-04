"""Jobs shared by REST and MCP. Browser credentials are never persisted."""

from __future__ import annotations

import json
import os
import select
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from server.network import public_target
from server.store import LOCAL_DEMO, Store
from server.video_alignment import align_result_shots
from server.video_models import (
    STOCK_VOICES,
    GenerateClipInput,
    RenderInput,
    TimelineClip,
    VideoInput,
)
from server.video_providers import capabilities, reason, setting, speech
from server.video_render import ffmpeg, render
from server.video_timeline import browser_clips, compile_timeline, launch_clips, launch_prompt

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = Path(os.getenv("CUTROOM_DATA_DIR", ".cutroom")).resolve()
ACTIVE: set[str] = set()
LOCK = threading.Lock()
SLOTS = threading.BoundedSemaphore(2)


def now() -> str:
    return datetime.now(UTC).isoformat()


def directory(store: Store, video_id: str) -> Path:
    # Both IDs are server-generated UUIDs or authenticated identifiers.
    return VIDEO_DIR / str(uuid.UUID(store.user_id)) / str(uuid.UUID(video_id))


def event(store: Store, job: dict, status: str, message: str, progress: int):
    job["status"] = status
    job["payload"]["progress"] = progress
    job["payload"]["updated_at"] = now()
    job["payload"].setdefault("events", []).append(
        {"at": now(), "stage": status, "message": message}
    )
    job["payload"]["events"] = job["payload"]["events"][-30:]
    store.save("video_jobs", job)


def voices(store: Store) -> list[dict]:
    return [
        *[{**v, "provider": "openai", "kind": "stock"} for v in STOCK_VOICES],
        *[
            {
                "id": v["id"],
                "name": v["name"],
                "description": "Your voice · custom narrator",
                "provider": v["payload"]["provider"],
                "kind": "custom",
            }
            for v in store.list("video_voices")
        ],
    ]


def resolve_voice(store: Store, voice: str) -> dict | None:
    if voice in {v["id"] for v in STOCK_VOICES}:
        return None
    try:
        return store.get("video_voices", str(uuid.UUID(voice)))
    except ValueError:
        raise HTTPException(400, "Choose a voice from your workspace.") from None


def validate_target(body: VideoInput):
    if body.demo:
        # Only this server-owned sample app can bypass public network checks.
        return
    try:
        public_target(body.url)
        if body.credentials and body.credentials.login_url:
            public_target(body.credentials.login_url)
    except (ValueError, OSError):
        raise HTTPException(
            400, "Use a publicly deployed HTTP(S) app URL. Private network URLs are blocked."
        ) from None


def create_video(store: Store, body: VideoInput) -> dict:
    validate_target(body)
    resolve_voice(store, body.voice)
    if not body.demo:
        features = capabilities()
        if not features["reasoning"]:
            raise HTTPException(
                503, "Configure OPENAI_API_KEY or ANTHROPIC_API_KEY to direct your app."
            )
        if not features["narration"] and body.voice in {v["id"] for v in STOCK_VOICES}:
            raise HTTPException(503, "Configure OPENAI_API_KEY to generate the selected voiceover.")
    pending = [
        j
        for j in store.list("video_jobs")
        if j["status"] not in ("complete", "failed", "cancelled")
    ]
    if len(pending) >= 3:
        raise HTTPException(429, "Finish an existing video before starting another.")
    data = body.model_dump(exclude={"credentials"})
    if body.demo:
        data["url"] = setting("CUTROOM_SAMPLE_ORIGIN", "http://127.0.0.1:8000") + "/sample/"
    job = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "status": "queued",
        "created_at": now(),
        "payload": {
            **data,
            "progress": 0,
            "scenes": [],
            "events": [],
            "revision": 1,
            "has_credentials": bool(body.credentials and body.credentials.username),
            "host": urlsplit(data["url"]).hostname,
            "demo": body.demo,
        },
    }
    event(store, job, "queued", "Brief received. Preparing your recording studio.", 3)
    return job


def claim(job_id: str) -> bool:
    with LOCK:
        if job_id in ACTIVE:
            return False
        ACTIVE.add(job_id)
        return True


def release(job_id: str):
    with LOCK:
        ACTIVE.discard(job_id)


def get_video(store: Store, video_id: str) -> dict:
    job = store.get("video_jobs", video_id)
    # A stopped worker must not leave an endless spinner after a restart.
    updated = datetime.fromisoformat(job["payload"].get("updated_at", job["created_at"]))
    with LOCK:
        active = job["id"] in ACTIVE
    if (
        job["status"] not in ("complete", "failed", "cancelled")
        and not active
        and (datetime.now(UTC) - updated).total_seconds() > 60
    ):
        event(
            store,
            job,
            "failed",
            "The worker stopped before finishing. Start a new take.",
            job["payload"].get("progress", 0),
        )
    return job


def cancelled(store: Store, job: dict):
    if store.get("video_jobs", job["id"])["status"] == "cancelled":
        raise InterruptedError("Recording cancelled.")


def choose_action(observation: dict, body: VideoInput, history: list[dict]) -> dict:
    if body.demo and not capabilities()["reasoning"]:
        script = [
            {"type": "click", "match": "Projects", "label": "One home for every project"},
            {"type": "click", "match": "Website refresh", "label": "Bring the work into focus"},
            {"type": "click", "match": "Board", "label": "A clear view of what is next"},
            {"type": "click", "match": "Analytics", "label": "See the whole team's momentum"},
        ]
        if len(history) >= len(script):
            return {"type": "done"}
        action = dict(script[len(history)])
        match = action.pop("match")
        element = next((e for e in observation["elements"] if match in e["label"]), None)
        if not element:
            raise ValueError("The sample app did not expose the expected feature.")
        return {**action, "id": element["id"]}
    view = {k: v for k, v in observation.items() if k not in ("screenshot", "type")}
    prompt = (
        f"Feature brief: {body.brief}\nTarget length: {body.duration}s. "
        f"Completed actions: {json.dumps(history)}\nVisible app: {json.dumps(view)}\n"
        "Choose ONE next action to demonstrate the feature. Aim for 3–5 meaningful scenes, "
        "avoid repeated clicks. Use only visible element IDs. JSON shape: "
        '{"type":"click|fill|select|scroll|press|hold|done","id":0,"value":"",'
        '"amount":400,"key":"Enter","label":"Short scene title","shot":"action|result"}. '
        "Use shot=result for navigating between pages/tabs: the destination is filmed after navigation. "
        "Use shot=action when the actual interaction proves the feature (typing, selecting, changing a view). "
        "done means the requested feature has been visibly demonstrated. "
        'If the feature cannot be found, return {"type":"done","unavailable":true,"reason":"explanation"}.'
    )
    return reason(prompt, observation["screenshot"])


def film(store: Store, job: dict, body: VideoInput):
    if not claim(job["id"]):
        return
    process = None
    folder = directory(store, job["id"])
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with SLOTS:
            cancelled(store, job)
            event(
                store,
                job,
                "exploring",
                "Opening an isolated browser and signing in before filming.",
                10,
            )
            credentials = None
            if body.credentials and not body.demo:
                credentials = {
                    "username": body.credentials.username,
                    "password": body.credentials.password.get_secret_value(),
                    "login_url": body.credentials.login_url,
                }
            process = subprocess.Popen(
                ["node", str(ROOT / "scripts/video_browser.mjs")],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=ROOT,
            )

            def send(data):
                process.stdin.write(json.dumps(data) + "\n")
                process.stdin.flush()

            send(
                {
                    "url": job["payload"]["url"],
                    "credentials": credentials,
                    "demo": body.demo,
                    "directory": str(folder),
                }
            )
            credentials = None
            history, views, completed = [], [], None
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                cancelled(store, job)
                ready, _, _ = select.select([process.stdout], [], [], 45)
                if not ready:
                    raise ValueError(
                        "The browser stopped responding. Check the app and try another take."
                    )
                line = process.stdout.readline()
                if not line:
                    raise ValueError("The browser closed before the recording was complete.")
                observation = json.loads(line)
                if observation["type"] == "error":
                    raise ValueError(observation["message"])
                if observation["type"] == "complete":
                    completed = observation
                    break
                views.append(observation["text"][:3000])
                if len(history) >= 8:
                    send({"type": "done"})
                    continue
                action = choose_action(observation, body, history)
                cancelled(store, job)
                if action.get("unavailable"):
                    raise ValueError(
                        str(action.get("reason", "The requested feature was not found."))[:300]
                    )
                history.append({k: v for k, v in action.items() if k != "value"})
                event(
                    store,
                    job,
                    "recording",
                    action.get("label") or "Capturing the requested feature.",
                    min(55, 18 + len(history) * 5),
                )
                send(action)
            if not completed:
                raise ValueError("Recording exceeded its time limit. Try a shorter feature brief.")
            scenes = completed["scenes"]
            raw = Path(completed["video"]).resolve()
            if raw.parent != folder:
                raise ValueError("Invalid browser artifact.")
            (folder / "raw.webm").write_bytes(raw.read_bytes())
            align_result_shots(folder / "raw.webm", folder, scenes)
            job["payload"]["scenes"] = [{**scene, "narration": ""} for scene in scenes]
            event(
                store,
                job,
                "scripting",
                "Writing a voiceover from the screens the agent actually demonstrated.",
                60,
            )
            result = {}
            if body.demo and not capabilities()["reasoning"]:
                scripts = [
                    "Meet Meridian. Bring your team's work together.",
                    "Every project. One clear view.",
                    "Tasks, deadlines, and ownership. All together.",
                    "See what is next. Keep work moving.",
                    "Your team's progress, in focus.",
                ]
            elif body.format == "launch":
                result = reason(
                    launch_prompt(body.title, body.brief, scenes)
                    + f" Screen evidence: {json.dumps(views)}"
                )
                scripts = result.get("narration", [])
            else:
                result = reason(
                    f"Write a concise feature demo voiceover for {body.title}. Brief: {body.brief}. "
                    f"Target duration: {body.duration}s. Actual captured scenes: {json.dumps(scenes)}. "
                    f"Verified screen text after each action: {json.dumps(views)}. "
                    'Return {"narration":["one sentence or two per scene"], "launch":{"hook":{"headline":"short opening hook","subtitle":"","narration":"opening line, 8 words"},"benefit":{"headline":"one verified benefit","subtitle":"","narration":"8 words"},"outro":{"headline":"closing invitation","subtitle":"","narration":"8 words"}}}. '
                    f"Exactly {len(scenes)} entries. Budget about {int(body.duration * 2.1 / len(scenes))} words per entry. "
                    "Explain benefits supported by the screen. No invented metrics, no pricing claims, no credentials."
                )
                scripts = result.get("narration", [])
            if len(scripts) != len(scenes) or any(
                not isinstance(t, str) or not 1 <= len(t) <= 1000 for t in scripts
            ):
                raise ValueError(
                    "The script did not match the captured scenes. Start another take."
                )
            for scene, script in zip(scenes, scripts, strict=True):
                scene["narration"] = script
            job["payload"]["scenes"] = scenes
            job["payload"]["timeline"] = (
                launch_clips(scenes, body.title, result, body.duration)
                if body.format == "launch"
                else browser_clips(scenes)
            )
            event(store, job, "narrating", "Generating the voiceover and aligning each scene.", 66)
            finish_render(store, job, folder)
    except InterruptedError:
        pass
    except Exception as exc:
        # Browser credentials and provider request bodies never appear in this message.
        message = (
            str(exc)
            if isinstance(exc, (ValueError, HTTPException))
            else "The video worker encountered an error. Try a new take."
        )
        event(store, job, "failed", message[:700], job["payload"].get("progress", 0))
    finally:
        if process:
            if process.poll() is None:
                process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        release(job["id"])


def finish_render(store: Store, job: dict, folder: Path):
    payload = job["payload"]
    scenes = (
        compile_timeline(job, [TimelineClip.model_validate(c) for c in payload["timeline"]])
        if payload.get("timeline")
        else payload["scenes"]
    )
    custom = resolve_voice(store, payload["voice"])
    audio_paths = []
    uploaded = payload.get("uploaded_narration") and payload.get("use_uploaded_narration", True)
    if uploaded:
        payload["narration_source"] = "Uploaded recording"
        full_wav = folder / "uploaded.wav"
        ffmpeg("-i", str(folder / "narration-upload"), "-ac", "2", "-ar", "48000", str(full_wav))
        from server.video_render import wav_duration

        total = wav_duration(full_wav)
        weights = [max(1, len(s.get("narration", "").split())) for s in scenes]
        start = 0
        for i, weight in enumerate(weights):
            part = folder / f"speech-{i}.wav"
            duration = total * weight / sum(weights)
            ffmpeg("-ss", str(start), "-i", str(full_wav), "-t", str(duration), str(part))
            start += duration
            audio_paths.append(part)
    else:
        for i, scene in enumerate(scenes):
            cancelled(store, job)
            audio = folder / f"speech-{i}.mp3"
            if not scene.get("narration", "").strip():
                audio = None
            elif payload.get("demo") and not setting("OPENAI_API_KEY") and not custom:
                if os.name == "posix" and Path("/usr/bin/say").exists():
                    aiff = folder / f"speech-{i}.aiff"
                    subprocess.run(
                        [
                            "/usr/bin/say",
                            "-v",
                            "Samantha",
                            "-r",
                            "160",
                            "-o",
                            str(aiff),
                            scene["narration"],
                        ],
                        check=True,
                        timeout=60,
                    )
                    ffmpeg("-i", str(aiff), str(audio))
                    payload["narration_source"] = "Local system voice (sample only)"
                else:
                    audio = None
                    payload["narration_source"] = (
                        "Silent sample; configure OPENAI_API_KEY for speech"
                    )
            else:
                speech(scene["narration"], payload["voice"], audio, custom)
                payload["narration_source"] = "Custom voice" if custom else "OpenAI generated voice"
            audio_paths.append(audio)

    last_motion_update = 0.0

    def progress(index, count):
        nonlocal last_motion_update
        cancelled(store, job)
        if not index:
            if time.monotonic() - last_motion_update < 10:
                return
            last_motion_update = time.monotonic()
        event(
            store,
            job,
            "rendering",
            f"Composing scene {index} of {count}: framing, zooms, captions, and audio."
            if index
            else "Animating product details, typography, and camera movement.",
            72 + int(index / count * 20),
        )

    meta = render(
        folder,
        folder / "raw.webm",
        scenes,
        job["title"],
        payload["theme"],
        payload["music"],
        audio_paths,
        progress,
    )
    cancelled(store, job)
    if not LOCAL_DEMO:
        event(
            store, job, "rendering", "Saving your finished film to private workspace storage.", 97
        )
        for filename, content_type in (
            ("film.mp4", "video/mp4"),
            ("storyboard.json", "application/json"),
        ):
            store.request(
                "POST",
                f"/storage/v1/object/videos/{store.user_id}/{job['id']}/{filename}",
                content=(folder / filename).read_bytes(),
                headers={"Content-Type": content_type, "x-upsert": "true"},
            )
        payload["storage_path"] = f"{store.user_id}/{job['id']}/film.mp4"
    payload["export"] = meta
    payload["rendered_scenes"] = scenes
    cancelled(store, job)
    event(store, job, "complete", "Your film is ready. Review the script or download the MP4.", 100)


def prepare_render(store: Store, body: RenderInput) -> dict:
    job = get_video(store, str(body.video_id))
    if job["status"] not in ("complete", "failed") or not job["payload"].get("scenes"):
        raise HTTPException(409, "Wait for the first take to finish before editing.")
    if not (directory(store, job["id"]) / "raw.webm").exists():
        raise HTTPException(
            409, "The original capture is unavailable on this worker. Start a new take."
        )
    resolve_voice(store, body.voice)
    if body.audio_source == "uploaded" and not job["payload"].get("uploaded_narration"):
        raise HTTPException(400, "Upload a finished narration before choosing that audio source.")
    if body.clips is not None:
        compile_timeline(job, body.clips)
        job["payload"]["timeline"] = [c.model_dump(mode="json") for c in body.clips]
    else:
        if len(body.narration) != len(job["payload"]["scenes"]):
            raise HTTPException(400, "Supply one narration entry per captured scene.")
        if any(not t.strip() or len(t) > 1000 for t in body.narration):
            raise HTTPException(400, "Each scene needs 1–1000 characters of narration.")
        for scene, text in zip(job["payload"]["scenes"], body.narration, strict=True):
            scene["narration"] = text.strip()
        job["payload"]["timeline"] = browser_clips(job["payload"]["scenes"])
    job["payload"].update(
        voice=body.voice,
        music=body.music,
        theme=body.theme,
        use_uploaded_narration=body.audio_source == "uploaded",
        revision=job["payload"].get("revision", 1) + 1,
    )
    event(store, job, "queued", "Your edits are saved. Rendering a new version.", 60)
    return job


def rerender(store: Store, job: dict):
    if not claim(job["id"]):
        return
    try:
        with SLOTS:
            finish_render(store, job, directory(store, job["id"]))
    except InterruptedError:
        pass
    except Exception:
        event(
            store,
            job,
            "failed",
            "The new version could not be rendered. Check voice access and retry.",
            60,
        )
    finally:
        release(job["id"])


def prepare_animation(store: Store, video_id: str, body: GenerateClipInput) -> tuple[dict, str]:
    from server.video_generation import generation_capabilities

    job = get_video(store, video_id)
    if job["status"] != "complete":
        raise HTTPException(409, "Finish this film before generating an animation.")
    if not generation_capabilities()[body.provider]:
        raise HTTPException(503, "Configure the selected video-generation provider first.")
    assets = job["payload"].setdefault("assets", [])
    if len(assets) >= 8:
        raise HTTPException(400, "This video already has eight generated assets.")
    asset_id = str(uuid.uuid4())
    assets.append(
        {
            "id": asset_id,
            "status": "queued",
            "provider": body.provider,
            "prompt": body.prompt,
            "duration": body.seconds,
            "filename": f"asset-{asset_id}.mp4",
        }
    )
    event(
        store,
        job,
        "generating",
        "Generating a short original launch animation. Your existing film is preserved.",
        70,
    )
    return job, asset_id


def generate_animation(store: Store, job: dict, body: GenerateClipInput, asset_id: str):
    from server.video_generation import generate_file

    if not claim(job["id"]):
        return
    asset = next(a for a in job["payload"]["assets"] if a["id"] == asset_id)
    folder = directory(store, job["id"])
    try:
        with SLOTS:
            cancelled(store, job)
            generate_file(
                body.provider,
                body.prompt,
                body.seconds,
                folder / asset["filename"],
                lambda: cancelled(store, job),
            )
            ffmpeg(
                "-ss",
                "1",
                "-i",
                str(folder / asset["filename"]),
                "-frames:v",
                "1",
                str(folder / f"asset-{asset_id}.jpg"),
            )
            asset["status"] = "complete"
            event(
                store,
                job,
                "complete",
                "Your animation is ready. Add it to the timeline and render your film.",
                100,
            )
    except InterruptedError:
        asset["status"] = "cancelled"
    except Exception as exc:
        asset["status"] = "failed"
        asset["error"] = (
            str(exc)[:250]
            if isinstance(exc, ValueError)
            else "Animation generation failed. Check provider access."
        )
        event(store, job, "complete", asset["error"] + " Your existing film is preserved.", 100)
    finally:
        release(job["id"])
