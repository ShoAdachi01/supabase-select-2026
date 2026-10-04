"""Contracts shared by the studio and its agent connector."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator

from server.video_direction_models import ShotDirection


class DemoCredentials(BaseModel):
    username: str = Field(default="", max_length=300)
    password: SecretStr = Field(default=SecretStr(""))
    login_url: str = Field(default="", max_length=2000)


class VideoInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="Product walkthrough", min_length=1, max_length=100)
    brief: str = Field(min_length=8, max_length=3000)
    credentials: DemoCredentials | None = None
    voice: str = Field(
        default="none",
        max_length=100,
        description="Use none for a music-led launch film without narration.",
    )
    music: Literal["ambient", "momentum", "none"] = "momentum"
    theme: Literal["midnight", "paper"] = "midnight"
    duration: Literal[30, 60, 90] = 30
    demo: bool = False
    format: Literal["launch", "walkthrough"] = "launch"
    creative_direction: str = Field(
        default="",
        max_length=2000,
        description="Optional art direction or reference grammar: pacing, typography, motion, and sound. The director chooses a film-specific structure.",
    )


class VideoId(BaseModel):
    video_id: uuid.UUID


class TimelineClip(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["browser", "title", "generated"] = "browser"
    scene_id: str | None = None
    asset_id: uuid.UUID | None = None
    label: str = Field(default="Scene", min_length=1, max_length=100)
    narration: str = Field(default="", max_length=1000)
    headline: str = Field(default="", max_length=180)
    subtitle: str = Field(default="", max_length=240)
    layout: Literal["hook", "benefit", "outro"] = "hook"
    duration: float = Field(default=4, ge=1, le=15)
    camera: Literal["wide", "push"] = "wide"
    motion: Literal["none", "reveal", "panels", "detail", "resolve", "directed"] = "none"
    direction: ShotDirection | None = None
    trim_start: float = Field(default=0, ge=0)
    trim_end: float | None = Field(default=None, ge=0)
    enabled: bool = True
    transition: Literal["cut", "fade", "dissolve"] = "cut"

    @model_validator(mode="after")
    def directed_contract(self):
        if self.motion == "directed":
            if self.direction is None:
                raise ValueError("Directed clips need a validated scene specification.")
            if abs(self.duration - self.direction.beats * 60 / self.direction.bpm) > 0.001:
                raise ValueError("Directed duration must match its beat grid.")
        return self


class RenderInput(VideoId):
    narration: list[str] | None = Field(default=None, min_length=1, max_length=12)
    clips: list[TimelineClip] | None = Field(default=None, min_length=1, max_length=24)
    voice: str = Field(default="marin", max_length=100)
    music: Literal["ambient", "momentum", "none"] = "ambient"
    theme: Literal["midnight", "paper"] = "midnight"
    audio_source: Literal["generated", "uploaded"] = "generated"

    @model_validator(mode="after")
    def require_edit(self):
        if self.narration is None and self.clips is None:
            raise ValueError("Supply an edited timeline or narration.")
        return self


class GenerateClipInput(BaseModel):
    provider: Literal["sora", "veo"] = "sora"
    prompt: str = Field(min_length=12, max_length=2000)
    seconds: Literal[4, 8] = 4


STOCK_VOICES = [
    {"id": "marin", "name": "Marin", "description": "Warm · clear · conversational"},
    {"id": "cedar", "name": "Cedar", "description": "Confident · measured · grounded"},
    {"id": "coral", "name": "Coral", "description": "Bright · friendly · expressive"},
    {"id": "ash", "name": "Ash", "description": "Calm · direct · understated"},
    {"id": "sage", "name": "Sage", "description": "Smooth · thoughtful · composed"},
    {"id": "nova", "name": "Nova", "description": "Energetic · crisp · inviting"},
]
