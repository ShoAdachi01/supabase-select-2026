import asyncio
import io
import socket
import zipfile
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from server.app import app
from server.discovery import canonical_url
from server.matching import compare
from server.models import LicenseDecision, LicenseInput, ReviewInput, ScanInput
from server.network import fetch_public, public_target
from server.services import (
    create_demo,
    create_license,
    decide_license,
    evidence_bundle,
    list_findings,
    permission_context,
    prepare_scan,
    review_finding,
    run_scan,
)
from server.store import Store

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr("server.store.LOCAL_DEMO", True)
    monkeypatch.setattr("server.store.DATA_DIR", tmp_path)
    return Store("local-demo", "00000000-0000-0000-0000-000000000001")


def scanned_demo(store):
    asset = create_demo(store)
    scan = prepare_scan(store, ScanInput(asset_id=asset["id"], source="demo"))
    run_scan(store, scan)
    return asset, scan, list_findings(store, asset["id"])


def test_copy_detection_distinguishes_transforms_from_other_character():
    reference = (ROOT / "public/demo/reference.png").read_bytes()
    assert compare(reference, reference)["kind"] == "same_image"
    assert (
        compare(reference, (ROOT / "public/demo/wallpaper.png").read_bytes())["kind"]
        == "likely_copy"
    )
    assert (
        compare(reference, (ROOT / "public/demo/shirt.png").read_bytes())["kind"] == "likely_copy"
    )
    assert (
        compare(reference, (ROOT / "public/demo/different.png").read_bytes())["kind"]
        == "unverified"
    )


def test_permission_requires_asset_domain_scope_and_dates():
    finding = {
        "asset_id": "a",
        "payload": {"domain": "shop.example", "category": "apparel", "territory": "US"},
    }
    grant = {
        "id": "g",
        "asset_id": "a",
        "payload": {
            "domain": "shop.example",
            "category": "apparel",
            "territory": "US",
            "starts_on": "2026-01-01",
            "ends_on": "2026-12-31",
        },
    }
    assert (
        permission_context(finding, [grant], date(2026, 10, 3))["status"] == "recorded_permission"
    )
    assert (
        permission_context(finding, [grant], date(2027, 1, 1))["status"] == "scope_requires_review"
    )
    assert permission_context(finding, [{**grant, "asset_id": "b"}])["status"] == "unknown"
    finding["payload"]["territory"] = "JP"
    assert permission_context(finding, [grant])["status"] == "scope_requires_review"
    finding["payload"].update(category="unknown", territory="unknown")
    grant["payload"].update(category="unknown", territory="unknown")
    assert permission_context(finding, [grant])["status"] != "recorded_permission"
    finding["payload"]["domain"] = "sub.shop.example"
    assert permission_context(finding, [grant])["status"] == "unknown"


def test_pending_request_does_not_grant_permission_and_approval_checks_scope(store):
    asset, _, findings = scanned_demo(store)
    finding = next(f for f in findings if "shirt" in f["payload"]["url"])
    body = LicenseInput(
        asset_id=asset["id"],
        applicant="Moon Market",
        domain="moon-market.example",
        category="apparel",
        territory="US",
        starts_on="2026-01-01",
        ends_on="2099-12-31",
    )
    inquiry = create_license(store, body)
    assert inquiry["status"] == "pending"
    assert permission_context(finding, store.list("trace_grants"))["status"] == "unknown"
    decide_license(
        store, inquiry["id"], LicenseDecision(decision="approved", note="Owner supplied approval.")
    )
    updated = next(f for f in list_findings(store) if f["id"] == finding["id"])
    assert updated["payload"]["permission"]["status"] == "recorded_permission"
    assert updated["payload"]["priority"] == "low"
    with pytest.raises(HTTPException):
        decide_license(store, inquiry["id"], LicenseDecision(decision="approved"))


def test_feedback_improves_next_scan_without_transferring_authorization(store):
    asset, _, findings = scanned_demo(store)
    rejected = next(f for f in findings if "Blue bunny" in f["payload"]["title"])
    shirt = next(f for f in findings if "shirt" in f["payload"]["url"])
    review_finding(
        store,
        rejected["id"],
        ReviewInput(decision="not_a_match", note="This is a different character."),
    )
    review_finding(
        store, shirt["id"], ReviewInput(decision="authorized", category="apparel", territory="US")
    )
    scan = prepare_scan(store, ScanInput(asset_id=asset["id"], source="demo"))
    run_scan(store, scan)
    fresh = [f for f in list_findings(store) if f["scan_id"] == scan["id"]]
    bunny = next(f for f in fresh if "Blue bunny" in f["payload"]["title"])
    assert bunny["payload"]["match"]["kind"] == "owner_rejected"
    assert bunny["payload"]["reused_correction"]
    shirts = [f for f in fresh if "shirt" in f["payload"]["url"]]
    assert all(f["payload"]["match"]["kind"] == "owner_confirmed" for f in shirts)
    assert all(f["payload"]["review"]["decision"] == "unreviewed" for f in shirts)
    assert all(f["payload"]["permission"]["status"] == "unknown" for f in shirts)
    assert scan["payload"]["reused_corrections"] == 3


def test_export_preserves_capture_and_owner_history(store):
    _, _, findings = scanned_demo(store)
    finding = findings[0]
    review_finding(
        store,
        finding["id"],
        ReviewInput(decision="investigate", note="Verify permission with the owner."),
    )
    with zipfile.ZipFile(io.BytesIO(evidence_bundle(store, finding["id"]))) as bundle:
        assert {"case.json", "candidate.png", "reference-1.png", "REVIEW.md"} <= set(
            bundle.namelist()
        )
        assert b"Verify permission with the owner." in bundle.read("case.json")
        assert b"not establish infringement" in bundle.read("REVIEW.md")
        assert bundle.read("candidate.png").startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "https://[::1]/",
        "http://169.254.169.254/",
        "file:///etc/passwd",
        "http://user:secret@example.com/",
        "http://example.com:8000/",
        "http://10.0.0.1/",
    ],
)
def test_public_fetch_rejects_local_and_non_web_targets(url):
    with pytest.raises((ValueError, socket.gaierror)):
        public_target(url)


def test_redirect_to_private_address_is_rejected(monkeypatch):
    original_client = httpx.Client
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.url.host == "93.184.216.34"
        assert request.headers["Host"] == "example.com"
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    monkeypatch.setattr(
        "server.network.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    original_resolver = socket.getaddrinfo
    monkeypatch.setattr(
        "server.network.socket.getaddrinfo",
        lambda host, port, **kwargs: (
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
            if host == "example.com"
            else original_resolver(host, port, **kwargs)
        ),
    )
    with pytest.raises(ValueError, match="Private"):
        fetch_public("https://example.com/image")
    assert len(calls) == 1


def test_canonical_url_keeps_identity_query_parameters():
    assert (
        canonical_url("https://shop.example/product?id=2&utm_source=x#top")
        == "https://shop.example/product?id=2"
    )
    assert canonical_url("https://shop.example/product?id=3") != canonical_url(
        "https://shop.example/product?id=2"
    )


def test_workspace_isolation_and_invalid_mcp_arguments(store):
    asset = create_demo(store)
    other = Store("local-demo", "00000000-0000-0000-0000-000000000002")
    with pytest.raises(HTTPException) as error:
        other.get("trace_assets", asset["id"])
    assert error.value.status_code == 404

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/mcp",
                headers={"Authorization": "Bearer local-demo"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "find_character_usage", "arguments": {"asset_id": "bad"}},
                },
            )
            assert response.json()["result"]["isError"] is True
            assert (await client.get("/api/workspace")).status_code == 401

    asyncio.run(check())


def test_source_failure_is_not_reported_as_no_usage(store, monkeypatch):
    asset = create_demo(store)
    monkeypatch.setattr(
        "server.services.public_search",
        lambda *args: (
            [],
            [{"source": "Source", "status": "failed", "query": "Orbit", "detail": "Unavailable"}],
        ),
    )
    scan = prepare_scan(store, ScanInput(asset_id=asset["id"], source="public"))
    run_scan(store, scan)
    assert scan["status"] == "failed"
    assert "not evidence" in scan["payload"]["error"]


def test_omitted_review_scope_preserves_previously_recorded_context(store):
    _, _, findings = scanned_demo(store)
    finding = next(f for f in findings if "shirt" in f["payload"]["url"])
    reviewed = review_finding(store, finding["id"], ReviewInput(decision="confirmed_match"))
    assert reviewed["payload"]["category"] == "apparel"
    assert reviewed["payload"]["territory"] == "US"


def test_interrupted_worker_scan_can_be_retried(store):
    from server.services import record, recover_interrupted_scans

    asset = create_demo(store)
    stale = record("trace_scans", store, asset_id=asset["id"], status="searching", payload={})
    recovered = recover_interrupted_scans(store, [stale])[0]
    assert recovered["status"] == "failed"
    assert "interrupted" in recovered["payload"]["error"]
    fresh = prepare_scan(store, ScanInput(asset_id=asset["id"], source="demo"))
    run_scan(store, fresh)
    assert fresh["status"] == "complete"
