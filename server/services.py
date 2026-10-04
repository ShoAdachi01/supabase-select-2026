from __future__ import annotations

import hashlib
import io
import json
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import HTTPException

from server.discovery import (
    canonical_url,
    domain,
    google_search,
    inspect_url,
    public_search,
    semantic_compare,
    serpapi_search,
)
from server.matching import compare, digest, image_from_bytes, png_bytes, thumbnail
from server.models import LicenseDecision, LicenseInput, ReviewInput, ScanInput
from server.network import fetch_public
from server.store import Store

ROOT = Path(__file__).resolve().parent.parent
SCAN_SLOTS = threading.BoundedSemaphore(2)
ACTIVE_SCANS: set[str] = set()


def now() -> str:
    return datetime.now(UTC).isoformat()


def record(table: str, store: Store, **fields) -> dict:
    return store.save(table, {"id": str(uuid.uuid4()), "created_at": now(), **fields})


def all_records(store: Store, table: str, filters: dict | None = None) -> list[dict]:
    records = []
    for offset in range(0, 10000, 100):
        page = store.list(table, filters, offset)
        records.extend(page)
        if len(page) < 100:
            break
    return records


def create_asset(
    store: Store,
    name: str,
    description: str,
    aliases: list[str],
    images: list[tuple[bytes, str]],
    demo: bool = False,
) -> dict:
    if not images or len(images) > 5:
        raise HTTPException(400, "Provide between one and five reference images.")
    asset_id = str(uuid.uuid4())
    references = []
    try:
        normalized = [(png_bytes(image_from_bytes(data)), url) for data, url in images]
    except Exception:
        raise HTTPException(
            400,
            "Unable to decode an image. Use a PNG, JPEG, WebP, or GIF under 5 MB and 20 megapixels.",
        ) from None
    for index, (data, url) in enumerate(normalized):
        path = f"references/{asset_id}/{index}.png"
        store.upload(path, data, "image/png")
        # Offline mode retains the same bytes; Supabase mode always reads from private Storage.
        if store_module_demo():
            local_path(store, path).write_bytes(data)
        references.append(
            {"path": path, "thumbnail": thumbnail(data), "public_url": url, "sha256": digest(data)}
        )
    return store.save(
        "trace_assets",
        {
            "id": asset_id,
            "name": name,
            "payload": {
                "description": description,
                "aliases": aliases,
                "references": references,
                "demo": demo,
            },
            "created_at": now(),
        },
    )


def store_module_demo() -> bool:
    from server.store import LOCAL_DEMO

    return LOCAL_DEMO


def local_path(store: Store, path: str) -> Path:
    from server.store import DATA_DIR

    target = DATA_DIR / store.user_id / path
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_bytes(store: Store, path: str) -> bytes:
    return local_path(store, path).read_bytes() if store_module_demo() else store.download(path)


def write_bytes(store: Store, path: str, data: bytes, mime: str):
    store.upload(path, data, mime)
    if store_module_demo():
        local_path(store, path).write_bytes(data)


def permission_context(finding: dict, grants: list[dict], at: date | None = None) -> dict:
    at = at or date.today()
    relevant = [
        g
        for g in grants
        if g["asset_id"] == finding["asset_id"]
        and g["payload"]["domain"] == finding["payload"].get("domain")
    ]
    for grant in relevant:
        scope = grant["payload"]
        if (
            finding["payload"].get("category", "unknown").casefold() != "unknown"
            and finding["payload"].get("territory", "unknown").casefold() != "unknown"
            and scope["category"].casefold()
            == finding["payload"].get("category", "unknown").casefold()
            and scope["territory"].casefold()
            == finding["payload"].get("territory", "unknown").casefold()
            and date.fromisoformat(scope["starts_on"]) <= at <= date.fromisoformat(scope["ends_on"])
        ):
            return {
                "status": "recorded_permission",
                "reason": "An approved record matches this domain, category, territory, and current date.",
                "grant_id": grant["id"],
            }
    if relevant:
        return {
            "status": "scope_requires_review",
            "reason": "A permission record exists for this domain; scope or dates are unknown or do not match.",
        }
    return {
        "status": "unknown",
        "reason": "No matching permission is recorded in this workspace. This does not prove unauthorized use.",
    }


def decorate(finding: dict, grants: list[dict]) -> dict:
    finding = {**finding, "payload": {**finding["payload"]}}
    payload = finding["payload"]
    permission = permission_context(finding, grants)
    payload["permission"] = permission
    decision = payload.get("review", {}).get("decision", "unreviewed")
    if (
        decision in ("authorized", "not_a_match")
        or payload.get("match", {}).get("kind") == "owner_rejected"
        or permission["status"] == "recorded_permission"
    ):
        priority, reason = (
            "low",
            "An owner decision or scoped permission record reduces review urgency.",
        )
    elif decision == "investigate" or (
        payload.get("commercial_signal")
        and payload.get("match", {}).get("kind") in ("same_image", "likely_copy", "owner_confirmed")
    ):
        priority, reason = (
            "high",
            "A close visual match and a commercial signal warrant owner review; permission remains unresolved.",
        )
    else:
        priority, reason = (
            "normal",
            "Review the visual match and usage context before deciding on action.",
        )
    payload["priority"] = priority
    payload["priority_reason"] = reason
    return finding


def list_findings(store: Store, asset_id: str | None = None) -> list[dict]:
    rows = all_records(store, "trace_findings", {"asset_id": asset_id} if asset_id else None)
    grants = all_records(store, "trace_grants")
    return [decorate(row, grants) for row in rows]


def demo_candidates() -> list[dict]:
    return [
        {
            "title": "Orbit Space Cat — official character print",
            "url": "https://orbit-studio.example/prints/orbit",
            "file": "reference.png",
            "category": "prints",
            "territory": "US",
        },
        {
            "title": "Space cat graphic T-shirt · $24",
            "url": "https://moon-market.example/products/space-cat-shirt",
            "file": "shirt.png",
            "category": "apparel",
            "territory": "US",
            "commercial_signal": True,
        },
        {
            "title": "Orbit sticker pack · $8",
            "url": "https://sticker-club.example/products/orbit-pack",
            "file": "sticker.png",
            "category": "stickers",
            "territory": "US",
            "commercial_signal": True,
        },
        {
            "title": "Orbit wallpaper — community post",
            "url": "https://fan-gallery.example/art/orbit",
            "file": "wallpaper.png",
            "category": "art",
            "territory": "unknown",
        },
        {
            "title": "Blue bunny plush · $18",
            "url": "https://moon-market.example/products/blue-bunny",
            "file": "different.png",
            "category": "toys",
            "territory": "US",
            "commercial_signal": True,
        },
        {
            "title": "Space cat graphic T-shirt — second listing",
            "url": "https://moon-market.example/products/space-cat-shirt-v2",
            "file": "shirt.png",
            "category": "apparel",
            "territory": "US",
            "commercial_signal": True,
        },
    ]


def create_demo(store: Store) -> dict:
    existing = [a for a in all_records(store, "trace_assets") if a["payload"].get("demo")]
    if existing:
        return existing[0]
    asset = create_asset(
        store,
        "Orbit",
        "An original space-cat mascot with a cream face, dark ears, a teal spacesuit, and a golden orbital ring. All demo listings are fictional.",
        ["Orbit Space Cat", "space cat"],
        [((ROOT / "public/demo/reference.png").read_bytes(), "")],
        True,
    )
    record(
        "trace_grants",
        store,
        asset_id=asset["id"],
        payload={
            "applicant": "Orbit Studio",
            "domain": "orbit-studio.example",
            "category": "prints",
            "territory": "US",
            "starts_on": "2026-01-01",
            "ends_on": "2099-12-31",
            "note": "Fictional permission record for the demo.",
        },
    )
    return asset


def recover_interrupted_scans(store: Store, scans: list[dict]) -> list[dict]:
    for scan in scans:
        if scan["status"] in ("queued", "searching") and scan["id"] not in ACTIVE_SCANS:
            scan["status"] = "failed"
            scan["payload"]["error"] = (
                "This search was interrupted by a worker restart. Start a new discovery run."
            )
            store.save("trace_scans", scan)
    return scans


def prepare_scan(store: Store, body: ScanInput) -> dict:
    asset = store.get("trace_assets", str(body.asset_id))
    if body.source == "demo" and not asset["payload"].get("demo"):
        raise HTTPException(400, "Demo scans are available only for the fictional Orbit example.")
    if body.source == "urls" and not body.urls:
        raise HTTPException(400, "Add at least one public URL to inspect.")
    scans = recover_interrupted_scans(
        store, all_records(store, "trace_scans", {"asset_id": str(body.asset_id)})
    )
    if any(s["status"] in ("queued", "searching") for s in scans):
        raise HTTPException(409, "A scan is already running for this character.")
    if not SCAN_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Two searches are already running. Try again shortly.")
    scan_id = str(uuid.uuid4())
    ACTIVE_SCANS.add(scan_id)
    try:
        return store.save(
            "trace_scans",
            {
                "id": scan_id,
                "created_at": now(),
                "asset_id": asset["id"],
                "status": "queued",
                "payload": {
                    "request": body.model_dump(mode="json"),
                    "coverage": [],
                    "events": [{"at": now(), "message": "Search queued"}],
                    "finding_count": 0,
                },
            },
        )
    except Exception:
        ACTIVE_SCANS.discard(scan_id)
        SCAN_SLOTS.release()
        raise


def run_scan(store: Store, scan: dict):
    try:
        body = ScanInput.model_validate(scan["payload"]["request"])
        asset = store.get("trace_assets", scan["asset_id"])
        references = [read_bytes(store, ref["path"]) for ref in asset["payload"]["references"]]
        scan["status"] = "searching"
        scan["payload"]["events"].append({"at": now(), "message": "Discovering candidate pages"})
        store.save("trace_scans", scan)
        query = body.query.strip() or " ".join([asset["name"], *asset["payload"]["aliases"][:1]])
        if body.source == "demo":
            candidates = demo_candidates()
            coverage = [
                {
                    "source": "Fictional demo fixtures",
                    "status": "searched",
                    "query": "Orbit example",
                    "detail": "Six local fictional listings. No live search was performed.",
                }
            ]
        elif body.source == "public":
            candidates, coverage = public_search(query, body.limit)
        elif body.source == "google":
            candidates, coverage = google_search(references[0], body.limit)
        elif body.source == "serpapi":
            candidates, coverage = serpapi_search(
                asset["payload"]["references"][0].get("public_url", ""), query, body.limit
            )
        else:
            candidates, coverage = [], []
            for url in body.urls:
                try:
                    candidate, data = inspect_url(url)
                    if data:
                        candidate["bytes"] = data
                    candidates.append(candidate)
                    coverage.append(
                        {
                            "source": url,
                            "status": "searched",
                            "query": "Submitted URL",
                            "detail": "Inspected this page or image only.",
                        }
                    )
                except Exception:
                    coverage.append(
                        {
                            "source": url,
                            "status": "failed",
                            "query": "Submitted URL",
                            "detail": "Could not safely fetch this public URL.",
                        }
                    )
        unique = {}
        for candidate in candidates:
            if candidate.get("url"):
                unique.setdefault(canonical_url(candidate["url"]), candidate)
        candidates = list(unique.values())[: body.limit]
        scan["payload"]["coverage"] = coverage
        scan["payload"]["candidate_count"] = len(candidates)
        scan["payload"]["events"].append(
            {
                "at": now(),
                "message": f"Comparing {len(candidates)} candidates against {len(references)} reference image(s)",
            }
        )
        store.save("trace_scans", scan)
        previous = all_records(store, "trace_reviews", {"asset_id": asset["id"]})
        corrections = {}
        for review in reversed(previous):
            if review["payload"].get("image_sha256"):
                corrections[review["payload"]["image_sha256"]] = review["payload"]

        def verify(candidate: dict) -> dict:
            payload = {k: v for k, v in candidate.items() if k not in ("bytes", "snapshot", "file")}
            payload.update(
                {
                    "domain": domain(candidate["url"]),
                    "category": candidate.get("category", "unknown"),
                    "territory": candidate.get("territory", "unknown"),
                    "review": {"decision": "unreviewed", "note": ""},
                    "captured_at": now(),
                    "demo": body.source == "demo",
                }
            )
            finding_id = str(uuid.uuid4())
            try:
                if candidate.get("file"):
                    data = (ROOT / "public/demo" / candidate["file"]).read_bytes()
                elif candidate.get("bytes"):
                    data = candidate["bytes"]
                elif candidate.get("image_url"):
                    data, _, _ = fetch_public(candidate["image_url"])
                else:
                    raise ValueError("No image was returned for this candidate.")
                normalized = png_bytes(image_from_bytes(data))
                results = [compare(ref, normalized) for ref in references]
                selected = min(range(len(results)), key=lambda i: results[i]["distance"])
                payload["match"] = {
                    **results[selected],
                    "reference_index": selected,
                    "method": "pixel digest + perceptual fingerprint",
                }
                payload["thumbnail"] = thumbnail(normalized)
                payload["image_sha256"] = digest(normalized)
                payload["capture_sha256"] = hashlib.sha256(normalized).hexdigest()
                payload["evidence_path"] = f"evidence/{finding_id}/image.png"
                write_bytes(store, payload["evidence_path"], normalized, "image/png")
                if candidate.get("snapshot"):
                    payload["page_path"] = f"evidence/{finding_id}/page.html"
                    write_bytes(store, payload["page_path"], candidate["snapshot"], "text/html")
                correction = corrections.get(payload["image_sha256"])
                if correction and correction["decision"] in (
                    "not_a_match",
                    "confirmed_match",
                    "authorized",
                ):
                    # Identity feedback transfers only to identical pixels for this asset.
                    # Authorization does not transfer between pages or sellers.
                    payload["match"] = {
                        "kind": "owner_rejected"
                        if correction["decision"] == "not_a_match"
                        else "owner_confirmed",
                        "reason": "The owner previously reviewed identical image pixels for this character. Permission still requires separate review.",
                        "method": "verified image correction",
                        "reference_index": selected,
                    }
                    payload["reused_correction"] = True
                if body.semantic_review:
                    try:
                        payload["semantic_review"] = semantic_compare(
                            references[selected], normalized, asset["payload"]["description"]
                        )
                    except Exception:
                        payload["semantic_review_error"] = (
                            "The optional visual model could not complete its review; copy evidence is retained."
                        )
            except HTTPException:
                raise
            except Exception:
                payload["match"] = {
                    "kind": "unverified",
                    "reason": "The candidate image could not be fetched or decoded. Inspect the source manually.",
                    "method": "source metadata only",
                }
            if "commercial_signal" not in payload:
                payload["commercial_signal"] = any(
                    term in payload.get("title", "").lower()
                    for term in (
                        "buy ",
                        "shop ",
                        "for sale",
                        "t-shirt",
                        "sticker pack",
                        "price",
                        "$",
                    )
                )
            return store.save(
                "trace_findings",
                {
                    "id": finding_id,
                    "asset_id": asset["id"],
                    "scan_id": scan["id"],
                    "payload": payload,
                    "created_at": now(),
                },
            )

        with ThreadPoolExecutor(max_workers=4) as executor:
            findings = list(executor.map(verify, candidates))
        scan["payload"]["finding_count"] = len(findings)
        scan["payload"]["reused_corrections"] = sum(
            bool(f["payload"].get("reused_correction")) for f in findings
        )
        scan["status"] = (
            "complete" if any(c["status"] == "searched" for c in coverage) else "failed"
        )
        if scan["status"] == "failed":
            scan["payload"]["error"] = (
                "No sources could be searched. This is not evidence of no online usage."
            )
        scan["payload"]["events"].append(
            {"at": now(), "message": f"Review queue ready: {len(findings)} candidate appearances"}
        )
    except Exception as error:
        scan["status"] = "failed"
        scan["payload"]["error"] = (
            str(error)
            if isinstance(error, ValueError)
            else "Search failed. Check provider configuration and try again."
        )
    finally:
        try:
            store.save("trace_scans", scan)
        finally:
            ACTIVE_SCANS.discard(scan["id"])
            SCAN_SLOTS.release()


def review_finding(store: Store, finding_id: str, body: ReviewInput) -> dict:
    finding = store.get("trace_findings", finding_id)
    review = {
        **body.model_dump(),
        "at": now(),
        "image_sha256": finding["payload"].get("image_sha256"),
    }
    record(
        "trace_reviews", store, asset_id=finding["asset_id"], finding_id=finding_id, payload=review
    )
    finding["payload"]["review"] = review
    if body.category is not None:
        finding["payload"]["category"] = body.category
    if body.territory is not None:
        finding["payload"]["territory"] = body.territory
    store.save("trace_findings", finding)
    return decorate(finding, all_records(store, "trace_grants"))


def create_license(store: Store, body: LicenseInput) -> dict:
    store.get("trace_assets", str(body.asset_id))
    try:
        start, end = date.fromisoformat(body.starts_on), date.fromisoformat(body.ends_on)
    except ValueError:
        raise HTTPException(400, "Use YYYY-MM-DD dates.") from None
    if end < start:
        raise HTTPException(400, "The end date must be on or after the start date.")
    value = body.domain.strip().lower()
    host = domain(value if "://" in value else "https://" + value)
    if not host or "." not in host or any(char.isspace() for char in host):
        raise HTTPException(400, "Enter a valid applicant website domain.")
    payload = {**body.model_dump(mode="json"), "domain": host}
    return record(
        "trace_licenses", store, asset_id=str(body.asset_id), status="pending", payload=payload
    )


def decide_license(store: Store, license_id: str, body: LicenseDecision) -> dict:
    request = store.get("trace_licenses", license_id)
    if request["status"] == "approved":
        raise HTTPException(409, "This request already has an approved permission record.")
    if body.decision == "approved":
        # Stable ID makes repeated approval attempts idempotent if a later write fails.
        store.save(
            "trace_grants",
            {
                "id": request["id"],
                "asset_id": request["asset_id"],
                "created_at": now(),
                "payload": {**request["payload"], "note": body.note, "approved_at": now()},
            },
        )
    request["status"] = body.decision
    request["payload"]["decision_note"] = body.note
    request["payload"]["decided_at"] = now()
    return store.save("trace_licenses", request)


def evidence_bundle(store: Store, finding_id: str) -> bytes:
    finding = decorate(store.get("trace_findings", finding_id), all_records(store, "trace_grants"))
    asset = store.get("trace_assets", finding["asset_id"])
    reviews = all_records(store, "trace_reviews", {"finding_id": finding_id})
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "case.json",
            json.dumps(
                {
                    "finding": finding,
                    "character": asset,
                    "reviews": reviews,
                    "exported_at": now(),
                    "limitations": "Candidate appearance, not a determination of infringement or financial loss. Captures are not notarized. Demo sources are fictional.",
                },
                indent=2,
            ),
        )
        payload = finding["payload"]
        for key, name in (("evidence_path", "candidate.png"), ("page_path", "source.html")):
            if payload.get(key):
                bundle.writestr(name, read_bytes(store, payload[key]))
        for index, reference in enumerate(asset["payload"]["references"]):
            bundle.writestr(f"reference-{index + 1}.png", read_bytes(store, reference["path"]))
        bundle.writestr(
            "REVIEW.md",
            f"# Usage review\n\nCharacter: {asset['name']}\nSource: {payload['url']}\nCaptured: {payload['captured_at']}\nVisual finding: {payload['match']['reason']}\nPermission: {payload['permission']['reason']}\n\n## Questions for the owner or counsel\n\n- Which rights and territories are relevant?\n- Is there permission outside this workspace?\n- Does context change the proposed action?\n- What additional evidence or source verification is needed?\n\nThis export contains recorded evidence and review history. It does not establish infringement, recoverable damages, or admissibility.\n",
        )
    return data.getvalue()
