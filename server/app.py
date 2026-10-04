from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from server.discovery import public_search
from server.models import AssetInput, LicenseDecision, LicenseInput, ReviewInput, ScanInput
from server.network import fetch_public
from server.services import (
    all_records,
    create_asset,
    create_demo,
    create_license,
    decide_license,
    evidence_bundle,
    list_findings,
    prepare_scan,
    read_bytes,
    recover_interrupted_scans,
    review_finding,
    run_scan,
)
from server.store import LOCAL_DEMO, SUPABASE_KEY, SUPABASE_URL, Store, authenticate

app = FastAPI(
    title="Trace",
    description="Find and review online appearances of character artwork.",
    version="0.2.0",
)
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
        "providers": {
            "public": True,
            "google": bool(os.getenv("GOOGLE_VISION_API_KEY")),
            "serpapi": bool(os.getenv("SERPAPI_API_KEY")),
            "gemini": bool(os.getenv("GEMINI_API_KEY")),
        },
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "product": "trace",
        "persistence": "local-demo" if LOCAL_DEMO else "supabase",
    }


@app.get("/api/workspace")
def overview(store: Store = Depends(workspace)):
    return {
        "assets": all_records(store, "trace_assets"),
        "scans": recover_interrupted_scans(store, all_records(store, "trace_scans")),
        "findings": list_findings(store),
        "licenses": all_records(store, "trace_licenses"),
        "grants": all_records(store, "trace_grants"),
        "reviews": all_records(store, "trace_reviews"),
    }


@app.post("/api/assets")
def asset(body: AssetInput, store: Store = Depends(workspace)):
    images = []
    for url in body.reference_urls:
        try:
            data, _, final_url = fetch_public(url)
            images.append((data, final_url))
        except Exception:
            raise HTTPException(
                400, "Unable to fetch the public reference image. Try uploading the file instead."
            ) from None
    return create_asset(store, body.name, body.description, body.aliases, images)


@app.post("/api/assets/upload")
async def upload_asset(
    name: str = Form(..., min_length=1, max_length=100),
    description: str = Form("", max_length=1500),
    aliases: str = Form("", max_length=500),
    files: list[UploadFile] = File(...),
    store: Store = Depends(workspace),
):
    if not 1 <= len(files) <= 5:
        raise HTTPException(400, "Upload one to five images.")
    images = []
    for file in files:
        data = await file.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(413, "Each reference image must be 5 MB or smaller.")
        images.append((data, ""))
    alias_list = [item.strip() for item in aliases.split(",") if item.strip()]
    if len(alias_list) > 8:
        raise HTTPException(400, "Use up to eight alternate names.")
    return create_asset(store, name.strip(), description, alias_list, images)


@app.post("/api/examples/demo")
def demo(store: Store = Depends(workspace)):
    return create_demo(store)


@app.post("/api/examples/public")
def public_example(store: Store = Depends(workspace)):
    candidates, _ = public_search("White Rabbit Tenniel", 2)
    for candidate in candidates:
        if candidate.get("provider") != "Wikimedia Commons":
            continue
        try:
            data, _, final = fetch_public(candidate["image_url"])
            return create_asset(
                store,
                "White Rabbit",
                "A public-domain illustration example for testing discovery, not a claim of exclusive rights. Reference source: "
                + candidate["url"],
                ["White Rabbit Tenniel"],
                [(data, final)],
            )
        except (ValueError, HTTPException):
            continue
    raise HTTPException(
        502,
        "The public example could not be loaded. Upload your own character artwork or use the Orbit demo.",
    )


@app.post("/api/scans")
def scan(body: ScanInput, tasks: BackgroundTasks, store: Store = Depends(workspace)):
    result = prepare_scan(store, body)
    tasks.add_task(run_scan, store, result)
    return result


@app.get("/api/scans/{scan_id}")
def scan_status(scan_id: uuid.UUID, store: Store = Depends(workspace)):
    return recover_interrupted_scans(store, [store.get("trace_scans", str(scan_id))])[0]


@app.get("/api/assets/{asset_id}/reference/{index}")
def reference_image(asset_id: uuid.UUID, index: int, store: Store = Depends(workspace)):
    asset = store.get("trace_assets", str(asset_id))
    references = asset["payload"]["references"]
    if index < 0 or index >= len(references):
        raise HTTPException(404, "Reference image not found.")
    return Response(read_bytes(store, references[index]["path"]), media_type="image/png")


@app.get("/api/findings/{finding_id}/image")
def captured_image(finding_id: uuid.UUID, store: Store = Depends(workspace)):
    finding = store.get("trace_findings", str(finding_id))
    path = finding["payload"].get("evidence_path")
    if not path:
        raise HTTPException(404, "No image was captured for this finding.")
    return Response(read_bytes(store, path), media_type="image/png")


@app.post("/api/findings/{finding_id}/review")
def review(finding_id: uuid.UUID, body: ReviewInput, store: Store = Depends(workspace)):
    return review_finding(store, str(finding_id), body)


@app.get("/api/findings/{finding_id}/export")
def export(finding_id: uuid.UUID, store: Store = Depends(workspace)):
    return Response(
        evidence_bundle(store, str(finding_id)),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="trace-evidence-{finding_id}.zip"'},
    )


@app.post("/api/licenses")
def license_request(body: LicenseInput, store: Store = Depends(workspace)):
    return create_license(store, body)


@app.post("/api/licenses/{license_id}/decision")
def license_decision(
    license_id: uuid.UUID, body: LicenseDecision, store: Store = Depends(workspace)
):
    return decide_license(store, str(license_id), body)


class AssetId(BaseModel):
    asset_id: uuid.UUID | None = None


class ScanId(BaseModel):
    scan_id: uuid.UUID


class FindingId(BaseModel):
    finding_id: uuid.UUID


class ReviewTool(ReviewInput):
    finding_id: uuid.UUID


TOOLS = [
    (
        "list_characters",
        "List the reference artwork and character context in this workspace.",
        AssetId,
    ),
    (
        "find_character_usage",
        "Start a bounded online search using reference artwork and text. Returns a scan ID; poll get_scan. Sources and limitations are explicit. demo searches fictional fixtures only.",
        ScanInput,
    ),
    ("get_scan", "Read search progress, source coverage, and candidate counts.", ScanId),
    (
        "list_usage_findings",
        "List candidate appearances with visual evidence, permission context, owner decisions, and review priority. These are not infringement determinations.",
        AssetId,
    ),
    (
        "submit_license_request",
        "Record a licensing inquiry for owner review. Pending requests never establish permission.",
        LicenseInput,
    ),
    (
        "record_usage_review",
        "Record an owner-directed review decision and scoped correction. Use only when the owner has supplied the decision.",
        ReviewTool,
    ),
    (
        "prepare_evidence",
        "Return evidence metadata and an authenticated ZIP-download path for owner or counsel review. Does not file notices or lawsuits.",
        FindingId,
    ),
]


def agent_metadata(value):
    """Keep images accessible on demand without inflating every tool response."""
    if isinstance(value, list):
        return [agent_metadata(item) for item in value]
    if not isinstance(value, dict):
        return value
    output = {key: agent_metadata(item) for key, item in value.items() if key != "thumbnail"}
    payload = output.get("payload", {})
    if payload.get("references"):
        for index, reference in enumerate(payload["references"]):
            reference["download_path"] = f"/api/assets/{value['id']}/reference/{index}"
    if payload.get("evidence_path"):
        payload["image_download_path"] = f"/api/findings/{value['id']}/image"
    return output


@app.post("/mcp")
def mcp(body: dict, tasks: BackgroundTasks, store: Store = Depends(workspace)):
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
            "serverInfo": {"name": "trace", "version": "0.2.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {"name": name, "description": description, "inputSchema": model.model_json_schema()}
                for name, description, model in TOOLS
            ]
        }
    elif method == "tools/call":
        params = body.get("params", {})
        if not isinstance(params, dict):
            return error(-32602, "Tool parameters must be an object.")
        tool = next((item for item in TOOLS if item[0] == params.get("name")), None)
        if not tool:
            return error(-32602, "Unknown tool.")
        try:
            args = tool[2].model_validate(params.get("arguments", {}))
            name = tool[0]
            if name == "list_characters":
                output = all_records(store, "trace_assets")
            elif name == "find_character_usage":
                output = prepare_scan(store, args)
                tasks.add_task(run_scan, store, output)
            elif name == "get_scan":
                output = recover_interrupted_scans(
                    store, [store.get("trace_scans", str(args.scan_id))]
                )[0]
            elif name == "list_usage_findings":
                output = list_findings(store, str(args.asset_id) if args.asset_id else None)
            elif name == "submit_license_request":
                output = create_license(store, args)
            elif name == "record_usage_review":
                output = review_finding(
                    store, str(args.finding_id), ReviewInput.model_validate(args.model_dump())
                )
            else:
                finding = store.get("trace_findings", str(args.finding_id))
                output = {
                    "finding_id": finding["id"],
                    "download_path": f"/api/findings/{finding['id']}/export",
                    "authentication": "Use this workspace's Bearer token to download.",
                    "limitations": "Evidence preparation only; owner or counsel decides on any action.",
                }
            result = {
                "content": [{"type": "text", "text": json.dumps(agent_metadata(output))}],
                "isError": False,
            }
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


DIST = Path(__file__).resolve().parent.parent / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
app.mount(
    "/demo",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "public/demo"),
    name="demo",
)


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith(("api/", "mcp")) or not DIST.exists():
        raise HTTPException(404, "Not found.")
    if path == "favicon.svg":
        return FileResponse(DIST / "favicon.svg")
    return FileResponse(DIST / "index.html")
