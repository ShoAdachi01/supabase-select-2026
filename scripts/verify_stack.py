"""Check the real Supabase-backed workflow and cross-workspace boundaries."""

import io
import os
import time
import zipfile

import httpx

BASE = os.getenv("TRACE_URL", "http://127.0.0.1:8000")
config = httpx.get(BASE + "/api/config").json()
assert config["mode"] == "supabase"


def sign_in():
    response = httpx.post(
        config["supabase_url"] + "/auth/v1/signup",
        headers={"apikey": config["supabase_key"]},
        json={},
    )
    response.raise_for_status()
    return response.json()


owner, stranger = sign_in(), sign_in()
headers = {"Authorization": "Bearer " + owner["access_token"]}
other = {"Authorization": "Bearer " + stranger["access_token"]}


def request(path, body=None):
    response = httpx.request(
        "POST" if body is not None else "GET", BASE + path, headers=headers, json=body, timeout=30
    )
    response.raise_for_status()
    return response.json()


asset = request("/api/examples/demo", {})
scan = request("/api/scans", {"asset_id": asset["id"], "source": "demo"})
for _ in range(60):
    scan = request("/api/scans/" + scan["id"])
    if scan["status"] not in ("queued", "searching"):
        break
    time.sleep(0.3)
assert scan["status"] == "complete", scan["payload"]
workspace = request("/api/workspace")
assert len(workspace["findings"]) == 6
finding = next(f for f in workspace["findings"] if "shirt" in f["payload"]["url"])
inquiry = request(
    "/api/licenses",
    {
        "asset_id": asset["id"],
        "applicant": "Moon Market",
        "domain": "moon-market.example",
        "category": "apparel",
        "territory": "US",
        "starts_on": "2026-01-01",
        "ends_on": "2099-12-31",
    },
)
assert inquiry["status"] == "pending"
assert (
    next(f for f in request("/api/workspace")["findings"] if f["id"] == finding["id"])["payload"][
        "permission"
    ]["status"]
    == "unknown"
)
request(
    "/api/licenses/" + inquiry["id"] + "/decision",
    {"decision": "approved", "note": "Owner-provided decision."},
)
assert (
    next(f for f in request("/api/workspace")["findings"] if f["id"] == finding["id"])["payload"][
        "permission"
    ]["status"]
    == "recorded_permission"
)
request(
    "/api/findings/" + finding["id"] + "/review",
    {"decision": "confirmed_match", "note": "Reviewed reference and listing."},
)
bundle = httpx.get(BASE + "/api/findings/" + finding["id"] + "/export", headers=headers)
bundle.raise_for_status()
with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
    assert "candidate.png" in archive.namelist()
    assert b"Reviewed reference and listing." in archive.read("case.json")
assert (
    httpx.get(BASE + "/api/findings/" + finding["id"] + "/export", headers=other).status_code == 404
)
assert httpx.get(BASE + "/api/scans/" + scan["id"], headers=other).status_code == 404
supabase_headers = {**other, "apikey": config["supabase_key"]}
rows = httpx.get(
    config["supabase_url"] + "/rest/v1/trace_assets",
    headers=supabase_headers,
    params={"id": "eq." + asset["id"]},
)
assert rows.json() == []
spoof = httpx.post(
    config["supabase_url"] + "/rest/v1/trace_scans",
    headers=supabase_headers,
    json={
        "id": "11111111-1111-1111-1111-111111111111",
        "user_id": stranger["user"]["id"],
        "asset_id": asset["id"],
        "status": "queued",
        "payload": {},
    },
)
assert spoof.status_code >= 400, "Cross-owner relationship must be rejected."
storage_url = (
    config["supabase_url"]
    + "/storage/v1/object/trace/"
    + owner["user"]["id"]
    + "/"
    + asset["payload"]["references"][0]["path"]
)
assert httpx.get(storage_url, headers={**headers, "apikey": config["supabase_key"]}).is_success
assert httpx.get(storage_url, headers=supabase_headers).status_code >= 400
print(
    "PASS: Supabase Auth, private Storage, discovery, scoped licensing approval, evidence export, RLS isolation, and cross-owner relationship rejection."
)
