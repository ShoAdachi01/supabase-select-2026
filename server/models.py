from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class AssetInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1500)
    aliases: list[str] = Field(default_factory=list, max_length=8)
    reference_urls: list[str] = Field(default_factory=list, max_length=5)


class ScanInput(BaseModel):
    asset_id: uuid.UUID
    source: Literal["public", "google", "serpapi", "urls", "demo"] = "public"
    query: str = Field(default="", max_length=250)
    urls: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=12, ge=1, le=24)
    semantic_review: bool = False


class ReviewInput(BaseModel):
    decision: Literal["confirmed_match", "authorized", "not_a_match", "investigate", "unreviewed"]
    note: str = Field(default="", max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    territory: str | None = Field(default=None, max_length=80)


class LicenseInput(BaseModel):
    asset_id: uuid.UUID
    applicant: str = Field(min_length=1, max_length=120)
    email: str = Field(default="", max_length=200)
    domain: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=80)
    territory: str = Field(min_length=1, max_length=80)
    starts_on: str
    ends_on: str
    description: str = Field(default="", max_length=2000)


class LicenseDecision(BaseModel):
    decision: Literal["approved", "needs_information", "declined"]
    note: str = Field(default="", max_length=2000)
