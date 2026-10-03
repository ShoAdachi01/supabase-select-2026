"""Exercise real auth, storage, training, inference, MCP and tenant isolation."""

import os
import time
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()
base = os.getenv("FORGE_URL", "http://127.0.0.1:8000")
url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_ANON_KEY"]


def session():
    response = httpx.post(f"{url}/auth/v1/signup", headers={"apikey": key}, json={}, timeout=20)
    response.raise_for_status()
    data = response.json()
    return data["access_token"], data["user"]["id"]


token, user = session()
other_token, other_user = session()
with httpx.Client(
    base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=30
) as client:

    def call(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    data = call("POST", "/api/datasets/sample", json={"kind": "shipments"})
    columns = data["profile"]["columns"]
    features = [c["name"] for c in columns if not c["excluded"] and c["name"] != "delayed"]
    bad = client.post(
        "/api/runs",
        json={
            "dataset_id": data["id"],
            "target": "delayed",
            "features": features + ["actual_delivery_days"],
            "task": "classification",
            "name": "Bad leakage test",
        },
    )
    assert bad.status_code == 400
    run = call(
        "POST",
        "/api/runs",
        json={
            "dataset_id": data["id"],
            "target": "delayed",
            "features": features,
            "task": "classification",
            "name": "Verified shipment skill",
        },
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        run = call("GET", f"/api/runs/{run['id']}")
        if run["status"] in ("ready", "failed"):
            break
        time.sleep(0.5)
    assert run["status"] == "ready", run["payload"].get("error", "Timed out")
    result = run["payload"]["result"]
    prediction = call(
        "POST", f"/api/runs/{run['id']}/predict", json={"records": [result["example_input"]]}
    )
    feedback = call(
        "POST",
        f"/api/predictions/{prediction['prediction_id']}/feedback",
        json={"actual": prediction["predictions"][0]["value"]},
    )
    assert feedback["saved"]
    saved = call("GET", f"/api/runs/{run['id']}/feedback")
    assert saved["count"] == 1
    tools = call("POST", "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})[
        "result"
    ]["tools"]
    tool = next(t for t in tools if run["id"].replace("-", "")[:12] in t["name"])
    mcp = call(
        "POST",
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool["name"], "arguments": {"records": [result["example_input"]]}},
        },
    )
    assert mcp["result"]["isError"] is False
    for path in (f"/api/runs/{run['id']}", f"/api/datasets/{data['id']}/download"):
        response = httpx.get(base + path, headers={"Authorization": f"Bearer {other_token}"})
        assert response.status_code == 404, "Cross-workspace record was exposed"
    # Verify storage is independently protected by Supabase RLS.
    storage = httpx.get(
        f"{url}/storage/v1/object/forge/{user}/datasets/{data['id']}.csv",
        headers={"apikey": key, "Authorization": f"Bearer {other_token}"},
    )
    assert storage.status_code != 200, "Cross-workspace storage was exposed"
    # Verify a caller cannot associate their own run with another user's dataset.
    spoof = httpx.post(
        f"{url}/rest/v1/runs",
        headers={"apikey": key, "Authorization": f"Bearer {other_token}"},
        json={
            "id": str(uuid.uuid4()),
            "user_id": other_user,
            "dataset_id": data["id"],
            "name": "Spoof",
            "status": "queued",
            "payload": {},
        },
    )
    assert spoof.status_code >= 400, "Cross-workspace relationship was accepted"
    print(
        "PASS: Supabase Auth, private Storage, Postgres, leakage rejection, ML training, inference, feedback, MCP, and cross-user isolation."
    )
    print(
        f"Test balanced accuracy: {result['test_score']:.3f}; baseline: {result['baseline_score']:.3f}."
    )
