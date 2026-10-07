"""Declarative motion contracts. The director never supplies executable code or asset URLs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CLICK = r"^click-\d{1,2}$"
HEX = r"^#[0-9a-fA-F]{6}$"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MotionState(Contract):
    beat: float = Field(ge=0, le=24)
    x: float = Field(default=0, ge=-1, le=1.5)
    y: float = Field(default=0, ge=-1, le=1.5)
    w: float = Field(default=1, ge=0.001, le=2)
    h: float = Field(default=1, ge=0.001, le=2)
    radius: float = Field(default=0, ge=0, le=540)
    rotation: float = Field(default=0, ge=-30, le=30)
    opacity: float = Field(default=1, ge=0, le=1)
    cam_x: float = Field(default=0.5, ge=0, le=1)
    cam_y: float = Field(default=0.5, ge=0, le=1)
    cam_zoom: float = Field(default=1, ge=1, le=2)
    focus: str | None = Field(default=None, pattern=CLICK)
    elevation: float = Field(default=0, ge=0, le=1)
    ease: Literal["spring", "smooth", "linear", "hold"] = "smooth"


class MotionLayer(Contract):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[\w-]+$")
    kind: Literal["footage", "product", "detail-0", "detail-1", "detail-2", "text", "shape"]
    states: list[MotionState] = Field(min_length=1, max_length=8)
    text: str = Field(default="", max_length=90)
    color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    size: int = Field(default=100, ge=26, le=220)
    weight: Literal[400, 500, 600, 700, 800] = 600
    align: Literal["left", "center", "right"] = "left"
    entrance: Literal["none", "words", "mask", "type"] = "none"
    depth: float = Field(default=1, ge=0, le=1)
    shape: Literal["rect", "line", "segments", "ring"] = "rect"
    stroke: int = Field(default=4, ge=1, le=40)
    count: int = Field(default=8, ge=2, le=40)
    gap: float = Field(default=0.4, ge=0, le=0.9)
    target_layer: str | None = Field(default=None, max_length=40, pattern=r"^[\w-]+$")
    target: str | None = Field(default=None, pattern=CLICK)
    target_x: float | None = Field(default=None, ge=0, le=1)
    target_y: float | None = Field(default=None, ge=0, le=1)
    font: Literal["sans", "display", "mono"] = "sans"

    @model_validator(mode="before")
    @classmethod
    def inherit_geometry(cls, value):
        if not isinstance(value, dict) or not isinstance(value.get("states"), list):
            return value
        previous, states = {}, []
        for state in value["states"]:
            if not isinstance(state, dict):
                return value
            inherited = dict(previous)
            if "cam_x" in state or "cam_y" in state:
                inherited.pop("focus", None)
            if "focus" in state:
                inherited.pop("cam_x", None)
                inherited.pop("cam_y", None)
            current = {**inherited, **state}
            states.append(current)
            previous = {k: v for k, v in current.items() if k not in ("beat", "ease")}
        if states and isinstance(states[0].get("beat"), (int, float)) and states[0]["beat"] > 0:
            states.insert(0, {**states[0], "beat": 0, "opacity": 0})
        return {**value, "states": states}

    @model_validator(mode="after")
    def ordered(self):
        times = [s.beat for s in self.states]
        if times != sorted(set(times)) or times[0] != 0:
            raise ValueError("Layer states must start at beat 0 and increase strictly.")
        if self.kind == "text" and not self.text.strip():
            raise ValueError("Text layers need visible copy.")
        return self


class MotionHit(Contract):
    beat: float = Field(ge=0, le=24)
    kind: Literal["whoosh", "thump", "tick"]


class Drift(Contract):
    x: float = Field(default=0, ge=-0.05, le=0.05)
    y: float = Field(default=0, ge=-0.05, le=0.05)
    zoom: float = Field(default=0, ge=-0.04, le=0.04)


class Backdrop(Contract):
    kind: Literal["flat", "radial"] = "flat"
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.4, ge=0, le=1)
    color2: str | None = Field(default=None, pattern=HEX)
    grain: float = Field(default=0, ge=0, le=0.15)


class ShotDirection(Contract):
    purpose: str = Field(min_length=8, max_length=240)
    composition: Literal["product", "detail", "type", "graphic", "split"]
    entry: Literal["cut", "match"] = "cut"
    background: str = Field(default="#101218", pattern=r"^#[0-9a-fA-F]{6}$")
    bpm: Literal[100, 120, 150, 180] = 120
    beats: int = Field(ge=2, le=24)
    layers: list[MotionLayer] = Field(min_length=1, max_length=9)
    hits: list[MotionHit] = Field(default_factory=list, max_length=4)
    drift: Drift = Field(default_factory=Drift)
    backdrop: Backdrop = Field(default_factory=Backdrop)

    @model_validator(mode="after")
    def within_shot(self):
        if len({layer.id for layer in self.layers}) != len(self.layers):
            raise ValueError("Layer IDs must be unique inside a shot.")
        if any(s.beat > self.beats for layer in self.layers for s in layer.states):
            raise ValueError("A layer state extends beyond its shot.")
        if any(hit.beat >= self.beats for hit in self.hits):
            raise ValueError("Sound hits must occur inside the shot.")
        if self.beats * 60 / self.bpm > 15:
            raise ValueError("Shots must fit the 15 second render contract.")
        return self


class DirectedShot(ShotDirection):
    source: str = Field(pattern=r"^scene-\d{1,2}\.jpg$")
    label: str = Field(min_length=1, max_length=70)


class FilmDirection(Contract):
    concept: str = Field(min_length=12, max_length=1000)
    grammar: str = Field(min_length=12, max_length=2000)
    reference: Literal["editorial", "tactile", "precision"]
    shots: list[DirectedShot] = Field(min_length=2, max_length=10)


class FilmConcept(Contract):
    name: str = Field(min_length=1, max_length=100)
    device: str = Field(min_length=8, max_length=1000)
    why: str = Field(min_length=8, max_length=600)


class FilmTreatment(Contract):
    audience: str = Field(max_length=600)
    promise: str = Field(max_length=600)
    evidence: list[dict[str, str]] = Field(min_length=1, max_length=8)
    concepts: list[FilmConcept] = Field(min_length=3, max_length=3)
    chosen_concept: str = Field(max_length=100)
    palette: list[str] = Field(min_length=1, max_length=6)
    typography: str = Field(max_length=1200)
    rhythm: str = Field(max_length=1200)
    shots: list[dict] = Field(min_length=2, max_length=10)
    avoid: list[str] = Field(max_length=8)
    reference_translation: str = Field(max_length=1600)

    @model_validator(mode="after")
    def selected(self):
        if self.chosen_concept not in {c.name for c in self.concepts}:
            raise ValueError("Choose one of the three proposed concepts")
        return self
