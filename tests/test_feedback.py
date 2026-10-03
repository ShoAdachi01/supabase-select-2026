import asyncio
import uuid

import httpx

import server.store as persistence
from server.app import app, workspace


def test_feedback_export_reads_all_pages_and_excludes_other_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(persistence, "LOCAL_DEMO", True)
    monkeypatch.setattr(persistence, "DATA_DIR", tmp_path)
    store = persistence.Store("local-demo", "workspace-one")
    run_id = str(uuid.uuid4())
    store.save("runs", {"id": run_id})
    for i in range(105):
        store.save("predictions", {"id": str(uuid.uuid4()), "run_id": run_id, "actual": i})
    # Newer predictions in another run must not hide the requested run's feedback.
    for _ in range(100):
        store.save("predictions", {"id": str(uuid.uuid4()), "run_id": "other-run", "actual": 999})
    app.dependency_overrides[workspace] = lambda: store

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(f"/api/runs/{run_id}/feedback")

    try:
        response = asyncio.run(request())
        assert response.status_code == 200
        result = response.json()
        assert result["count"] == 105
        assert {row["actual"] for row in result["records"]} == set(range(105))
        assert all(row["run_id"] == run_id for row in result["records"])
    finally:
        app.dependency_overrides.clear()
