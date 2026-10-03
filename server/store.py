"""User-scoped Supabase persistence. Never uses a service-role key."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
DATA_DIR = Path(os.getenv("FORGE_DATA_DIR", ".forge")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")
LOCAL_DEMO = os.getenv("LOCAL_DEMO_MODE", "false").lower() == "true"


class Store:
    def __init__(self, token: str, user_id: str):
        self.token = token
        self.user_id = user_id
        self.headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"}

    def request(self, method: str, path: str, **kwargs):
        try:
            response = httpx.request(
                method,
                SUPABASE_URL + path,
                headers={**self.headers, **kwargs.pop("headers", {})},
                timeout=30,
                **kwargs,
            )
        except httpx.HTTPError:
            raise HTTPException(
                503, "Supabase is unavailable. Check your local stack or hosted project settings."
            ) from None
        if response.status_code >= 400:
            raise HTTPException(
                502,
                f"Supabase rejected the operation ({response.status_code}). Check the migration, session, and access policies.",
            )
        return response

    def _connection(self):
        connection = sqlite3.connect(DATA_DIR / "offline.sqlite")
        connection.execute(
            "create table if not exists records (id text primary key, kind text, user_id text, body text)"
        )
        return connection

    def save(self, table: str, row: dict):
        row = {**row, "user_id": self.user_id}
        if LOCAL_DEMO:
            with self._connection() as con:
                con.execute(
                    "insert or replace into records values (?, ?, ?, ?)",
                    (row["id"], table, self.user_id, json.dumps(row)),
                )
            return row
        self.request(
            "POST",
            f"/rest/v1/{table}",
            json=row,
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        return row

    def get(self, table: str, record_id: str):
        if LOCAL_DEMO:
            with self._connection() as con:
                row = con.execute(
                    "select body from records where id=? and kind=? and user_id=?",
                    (record_id, table, self.user_id),
                ).fetchone()
            rows = [json.loads(row[0])] if row else []
        else:
            rows = self.request(
                "GET", f"/rest/v1/{table}", params={"id": f"eq.{record_id}", "select": "*"}
            ).json()
        if not rows:
            raise HTTPException(404, "Record not found in your workspace.")
        return rows[0]

    def list(self, table: str, filters: dict[str, str] | None = None, offset: int = 0):
        if LOCAL_DEMO:
            with self._connection() as con:
                rows = con.execute(
                    "select body from records where kind=? and user_id=? order by rowid desc",
                    (table, self.user_id),
                ).fetchall()
            records = [json.loads(row[0]) for row in rows]
            if filters:
                records = [r for r in records if all(r.get(k) == v for k, v in filters.items())]
            return records[offset : offset + 100]
        return self.request(
            "GET",
            f"/rest/v1/{table}",
            params={
                "select": "*",
                "order": "created_at.desc,id.desc",
                "limit": "100",
                "offset": str(offset),
                **{key: f"eq.{value}" for key, value in (filters or {}).items()},
            },
        ).json()

    def upload(self, path: str, data: bytes, content_type: str):
        if not LOCAL_DEMO:
            self.request(
                "POST",
                f"/storage/v1/object/forge/{self.user_id}/{path}",
                content=data,
                headers={"Content-Type": content_type, "x-upsert": "true"},
            )

    def download(self, path: str) -> bytes:
        if LOCAL_DEMO:
            raise HTTPException(404, "Local artifact is missing. Upload the dataset again.")
        return self.request("GET", f"/storage/v1/object/forge/{self.user_id}/{path}").content


def authenticate(token: str) -> Store:
    if LOCAL_DEMO:
        if token != "local-demo":
            raise HTTPException(401, "Use the local demo session.")
        return Store(token, "00000000-0000-0000-0000-000000000001")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(503, "Configure Supabase or explicitly enable LOCAL_DEMO_MODE.")
    try:
        response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Unable to reach Supabase Auth.") from None
    if response.status_code != 200:
        raise HTTPException(401, "Your session expired. Refresh to create a new session.")
    return Store(token, response.json()["id"])
