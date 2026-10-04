"""Cutroom web application and Streamable HTTP MCP endpoint."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.background import BackgroundTask

from server.store import LOCAL_DEMO, SUPABASE_KEY, SUPABASE_URL, Store, authenticate
from server.video_generation import generation_capabilities
from server.video_models import GenerateClipInput, RenderInput, VideoId, VideoInput
from server.video_providers import capabilities, clone_voice, reason, setting, speech
from server.video_service import (
    VIDEO_DIR,
    create_video,
    directory,
    event,
    film,
    generate_animation,
    get_video,
    prepare_animation,
    prepare_render,
    rerender,
    resolve_voice,
    voices,
)
from server.video_timeline import launch_clips

ROOT = Path(__file__).resolve().parent.parent
SIGNING_KEY = setting("CUTROOM_SIGNING_KEY", secrets.token_hex(32)).encode()
app = FastAPI(title="Cutroom", description="Your agent's product video studio.", version="0.1.0")
bearer = HTTPBearer()


def workspace(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> Store:
    return authenticate(credentials.credentials)


@app.get("/api/config")
def config():
    return {
        "supabase_url": os.getenv("SUPABASE_PUBLIC_URL", SUPABASE_URL),
        "supabase_key": SUPABASE_KEY,
        "mode": "local-demo" if LOCAL_DEMO else "supabase",
        "configured": LOCAL_DEMO or bool(SUPABASE_URL and SUPABASE_KEY),
        "providers": {},
        "video": {**capabilities(), "video_generation": generation_capabilities()},
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "cutroom", "providers": capabilities()}


@app.get("/api/videos")
def list_videos(store: Store = Depends(workspace)):
    return [get_video(store, j["id"]) for j in store.list("video_jobs")]


@app.post("/api/videos")
def make_video(body: VideoInput, tasks: BackgroundTasks, store: Store = Depends(workspace)):
    job = create_video(store, body)
    tasks.add_task(film, store, job, body)
    return job


@app.get("/api/videos/{video_id}")
def video(video_id: uuid.UUID, store: Store = Depends(workspace)):
    return get_video(store, str(video_id))


@app.post("/api/videos/{video_id}/cancel")
def cancel(video_id: uuid.UUID, store: Store = Depends(workspace)):
    job = get_video(store, str(video_id))
    if job["status"] not in ("complete", "failed", "cancelled"):
        event(
            store, job, "cancelled", "This take was cancelled.", job["payload"].get("progress", 0)
        )
    return job


@app.post("/api/videos/render")
def edit(body: RenderInput, tasks: BackgroundTasks, store: Store = Depends(workspace)):
    job = prepare_render(store, body)
    tasks.add_task(rerender, store, job)
    return job


def media_url(store: Store, video_id: str, filename: str) -> str:
    expires = int(time.time()) + 1800
    subject = f"{store.user_id}:{video_id}:{filename}:{expires}"
    signature = hmac.new(SIGNING_KEY, subject.encode(), hashlib.sha256).hexdigest()
    return f"/media/{video_id}/{filename}?workspace={store.user_id}&expires={expires}&signature={signature}"


def playback_info(store: Store, job: dict) -> dict:
    folder = directory(store, job["id"])
    if job["status"] != "complete":
        raise HTTPException(409, "Wait for the film to finish rendering.")
    if (folder / "film.mp4").exists():
        url = media_url(store, job["id"], "film.mp4")
    elif job["payload"].get("storage_path") and not LOCAL_DEMO:
        result = store.request(
            "POST",
            f"/storage/v1/object/sign/videos/{job['payload']['storage_path']}",
            json={"expiresIn": 1800},
        ).json()
        url = SUPABASE_URL + "/storage/v1" + result["signedURL"]
    else:
        raise HTTPException(404, "The video artifact is unavailable. Start another take.")
    return {
        "url": url,
        "poster_url": media_url(store, job["id"], "poster.jpg")
        if (folder / "poster.jpg").exists()
        else None,
        "expires_in": 1800,
        "scenes": [
            {**s, "thumbnail_url": media_url(store, job["id"], s["thumbnail"])}
            for s in job["payload"].get("rendered_scenes", job["payload"]["scenes"])
        ],
        "assets": [
            {
                **a,
                "thumbnail_url": media_url(store, job["id"], f"asset-{a['id']}.jpg"),
                "url": media_url(store, job["id"], a["filename"]),
            }
            for a in job["payload"].get("assets", [])
            if a["status"] == "complete"
        ],
    }


@app.get("/api/videos/{video_id}/playback")
def playback(video_id: uuid.UUID, store: Store = Depends(workspace)):
    return playback_info(store, get_video(store, str(video_id)))


@app.get("/media/{video_id}/{filename}")
def media(video_id: uuid.UUID, filename: str, workspace: uuid.UUID, expires: int, signature: str):
    if filename not in ("film.mp4", "poster.jpg") and not re.fullmatch(
        r"(?:scene|edit)-\d{1,2}\.jpg|asset-[0-9a-f-]{36}\.(?:mp4|jpg)", filename
    ):
        raise HTTPException(404, "File not found.")
    subject = f"{workspace}:{video_id}:{filename}:{expires}"
    expected = hmac.new(SIGNING_KEY, subject.encode(), hashlib.sha256).hexdigest()
    if (
        expires < time.time()
        or expires > time.time() + 1900
        or not hmac.compare_digest(expected, signature)
    ):
        raise HTTPException(403, "This preview link has expired. Reopen the video.")
    path = VIDEO_DIR / str(workspace) / str(video_id) / filename
    if not path.exists():
        raise HTTPException(404, "File not found.")
    return FileResponse(
        path,
        media_type="video/mp4" if filename.endswith("mp4") else "image/jpeg",
        headers={"Cache-Control": "private, max-age=60"},
    )


@app.get("/api/voices")
def list_voices(store: Store = Depends(workspace)):
    return voices(store)


class VoicePreview(BaseModel):
    voice: str = "marin"
    text: str = Field(
        default="Meet your next product demo. Clear, confident, and ready to share.",
        min_length=1,
        max_length=1000,
    )


@app.post("/api/voices/preview")
def preview_voice(body: VoicePreview, store: Store = Depends(workspace)):
    custom = resolve_voice(store, body.voice)
    folder = VIDEO_DIR / str(uuid.UUID(store.user_id)) / "previews"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4()}.mp3"
    try:
        speech(
            body.text,
            body.voice,
            path,
            custom,
        )
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None
    return FileResponse(
        path, media_type="audio/mpeg", background=BackgroundTask(path.unlink, missing_ok=True)
    )


@app.post("/api/voices/upload")
async def upload_voice(
    name: str = Form(..., min_length=1, max_length=80),
    consent: bool = Form(...),
    file: UploadFile = File(...),
    store: Store = Depends(workspace),
):
    if not consent:
        raise HTTPException(
            400,
            "Confirm that this is your voice and that you consent to creating its synthetic version.",
        )
    data = await file.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024 or len(data) < 1000:
        raise HTTPException(400, "Upload a clear audio sample between 1 KB and 20 MB.")
    try:
        provider, external_id = clone_voice(name, data, Path(file.filename or "sample.wav").name)
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from None
    row = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": datetime.now(UTC).isoformat(),
        "payload": {"provider": provider, "external_id": external_id, "consent": True},
    }
    store.save("video_voices", row)
    return {
        "id": row["id"],
        "name": name,
        "provider": provider,
        "kind": "custom",
        "description": "Your cloned voice",
    }


@app.post("/api/videos/{video_id}/narration")
async def upload_narration(
    video_id: uuid.UUID, file: UploadFile = File(...), store: Store = Depends(workspace)
):
    job = get_video(store, str(video_id))
    if job["status"] != "complete":
        raise HTTPException(409, "Finish the first take before uploading your narration.")
    data = await file.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024 or len(data) < 1000:
        raise HTTPException(400, "Upload an audio recording between 1 KB and 30 MB.")
    folder = directory(store, job["id"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "narration-upload").write_bytes(data)
    job["payload"]["uploaded_narration"] = True
    store.save("video_jobs", job)
    return job


class Empty(BaseModel):
    pass


class GenerateAnimationInput(GenerateClipInput, VideoId):
    pass


@app.post("/api/videos/{video_id}/animations")
def animation(
    video_id: uuid.UUID,
    body: GenerateClipInput,
    tasks: BackgroundTasks,
    store: Store = Depends(workspace),
):
    job, asset_id = prepare_animation(store, str(video_id), body)
    tasks.add_task(generate_animation, store, job, body, asset_id)
    return job


@app.post("/api/videos/{video_id}/launch-plan")
def launch_plan(video_id: uuid.UUID, store: Store = Depends(workspace)):
    job = get_video(store, str(video_id))
    scenes = job["payload"]["scenes"]
    if not scenes:
        raise HTTPException(409, "Capture the product before planning launch scenes.")
    plan = None
    if capabilities()["reasoning"]:
        try:
            plan = reason(
                f"Create opening hook, one benefit card, and closing invitation for a launch film. Product: {job['title']}. Brief: {job['payload']['brief']}. Verified captured scenes: {json.dumps(scenes)}. Return JSON keys hook, benefit, outro; each has headline (2–7 words), subtitle (one short sentence), narration (6–10 words). Only claim benefits visible in the captured scenes. No invented stats, prices or testimonials."
            )
        except (ValueError, httpx.HTTPError):
            raise HTTPException(
                503, "Launch copy could not be planned. Add an animated title manually."
            ) from None
    return {"clips": launch_clips(scenes, job["title"], plan)}


TOOLS = [
    (
        "create_product_video",
        "Create a product film from a deployed URL, feature brief, optional demo credentials, voice, and style. Credentials are transient. Returns a video ID; poll get_video. Use a demo account. demo=true films our sample app only.",
        VideoInput,
    ),
    (
        "get_video",
        "Read recording progress, captured scenes, editable narration, and export metadata.",
        VideoId,
    ),
    ("list_videos", "List videos in this authenticated workspace.", Empty),
    ("list_voices", "List stock voices and this workspace's custom voices.", Empty),
    (
        "render_video",
        "Edit the source-referenced timeline: exact narration, titles, cuts/restores, ordering, trims, generated assets, and transitions. Supply clips from payload.timeline, or a legacy narration string per original captured scene. Select generated or uploaded audio. Poll get_video.",
        RenderInput,
    ),
    (
        "export_video",
        "Return a private MP4 preview/download URL valid for 30 minutes. Do not publish it without the user's instruction.",
        VideoId,
    ),
    ("cancel_video", "Stop a video job at its next stage boundary.", VideoId),
    (
        "plan_launch_video",
        "Plan editable animated hook, benefit and closing scenes grounded in the captured product. Returns a timeline draft; submit it to render_video.",
        VideoId,
    ),
    (
        "generate_animation",
        "Generate a short original abstract animation with Veo or Sora. Uses provider credits, preserves the existing film, and returns the job; poll get_video for assets. Add a finished asset with kind=generated in render_video.",
        GenerateAnimationInput,
    ),
]


@app.post("/mcp")
def mcp(body: dict, tasks: BackgroundTasks, request: Request, store: Store = Depends(workspace)):
    rpc_id, method = body.get("id"), body.get("method")

    def error(code: int, message: str):
        return JSONResponse(
            {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}
        )

    if body.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return error(-32600, "Invalid JSON-RPC request.")
    if method.startswith("notifications/"):
        return Response(status_code=202)
    if method == "initialize":
        result = {
            "protocolVersion": "2025-03-26",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "cutroom", "version": "0.1.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {"name": name, "description": desc, "inputSchema": model.model_json_schema()}
                for name, desc, model in TOOLS
            ]
        }
    elif method == "tools/call":
        params = body.get("params", {})
        if not isinstance(params, dict):
            return error(-32602, "Tool parameters must be an object.")
        tool = next((t for t in TOOLS if t[0] == params.get("name")), None)
        if not tool:
            return error(-32602, "Unknown tool.")
        try:
            args = tool[2].model_validate(params.get("arguments", {}))
            name = tool[0]
            if name == "create_product_video":
                output = create_video(store, args)
                tasks.add_task(film, store, output, args)
            elif name == "render_video":
                output = prepare_render(store, args)
                tasks.add_task(rerender, store, output)
            elif name == "list_videos":
                output = list_videos(store)
            elif name == "list_voices":
                output = voices(store)
            elif name == "export_video":
                output = playback_info(store, get_video(store, str(args.video_id)))
                origin = setting("CUTROOM_PUBLIC_ORIGIN", str(request.base_url).rstrip("/"))
                for key in ("url", "poster_url"):
                    if output.get(key, "") and output[key].startswith("/"):
                        output[key] = origin + output[key]
                for item in [*output.get("scenes", []), *output.get("assets", [])]:
                    for key in ("url", "thumbnail_url"):
                        if item.get(key, "").startswith("/"):
                            item[key] = origin + item[key]
            elif name == "plan_launch_video":
                output = launch_plan(args.video_id, store)
            elif name == "generate_animation":
                output, asset_id = prepare_animation(store, str(args.video_id), args)
                tasks.add_task(generate_animation, store, output, args, asset_id)
            elif name == "cancel_video":
                output = cancel(args.video_id, store)
            else:
                output = get_video(store, str(args.video_id))
            result = {"content": [{"type": "text", "text": json.dumps(output)}], "isError": False}
        except ValidationError:
            result = {
                "content": [
                    {"type": "text", "text": "Invalid arguments. Follow the tool's input schema."}
                ],
                "isError": True,
            }
        except HTTPException as exc:
            result = {"content": [{"type": "text", "text": str(exc.detail)}], "isError": True}
    else:
        return error(-32601, "Method not found.")
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


@app.get("/mcp")
def stream():
    return Response(status_code=405, headers={"Allow": "POST"})


app.mount("/sample", StaticFiles(directory=ROOT / "public/sample", html=True), name="sample")
DIST = ROOT / "dist"
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith(("api/", "mcp", "media/")) or not DIST.exists():
        raise HTTPException(404, "Not found.")
    if path == "favicon.svg":
        return FileResponse(DIST / "favicon.svg")
    return FileResponse(DIST / "index.html")
