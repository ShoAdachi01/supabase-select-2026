"""Contracts shared by the studio and its agent connector."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class DemoCredentials(BaseModel):
    username: str = Field(default="", max_length=300)
    password: SecretStr = Field(default=SecretStr(""))
    login_url: str = Field(default="", max_length=2000)


class VideoInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="Product walkthrough", min_length=1, max_length=100)
    brief: str = Field(min_length=8, max_length=3000)
    credentials: DemoCredentials | None = None
    voice: str = Field(default="marin", max_length=100)
    music: Literal["ambient", "momentum", "none"] = "ambient"
    theme: Literal["midnight", "paper"] = "midnight"
    duration: Literal[30, 60, 90] = 60
    demo: bool = False


class VideoId(BaseModel):
    video_id: uuid.UUID


class RenderInput(VideoId):
    narration: list[str] = Field(min_length=1, max_length=12)
    voice: str = Field(default="marin", max_length=100)
    music: Literal["ambient", "momentum", "none"] = "ambient"
    theme: Literal["midnight", "paper"] = "midnight"


STOCK_VOICES = [
    {"id": "marin", "name": "Marin", "description": "Warm · clear · conversational"},
    {"id": "cedar", "name": "Cedar", "description": "Confident · measured · grounded"},
    {"id": "coral", "name": "Coral", "description": "Bright · friendly · expressive"},
    {"id": "ash", "name": "Ash", "description": "Calm · direct · understated"},
    {"id": "sage", "name": "Sage", "description": "Smooth · thoughtful · composed"},
    {"id": "nova", "name": "Nova", "description": "Energetic · crisp · inviting"},
]
