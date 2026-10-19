"""Camera geometry shared by validation and composition. Mirrored exactly in src/video/camera.ts.

Coordinates: canvas is normalized 1920x1080; sources are normalized 0..1 in their own pixels;
readability is measured in logical CSS pixels of the recorded viewport.
"""

from __future__ import annotations

from server.video_direction_models import FilmDirection

CANVAS = (1920, 1080)


def zoom_cap(kind: str, scene: dict) -> float:
    scale = scene.get("source_scale", 1) if kind == "footage" else scene.get("still_scale", 1)
    return round(max(1.2, min(2.0, float(scale))), 2)


def clicks(scene: dict) -> list[dict]:
    return [e for e in scene.get("interactions", []) if e.get("kind") == "click"]


def click_point(scene: dict, name: str) -> tuple[float, float]:
    index = int(name.split("-")[1])
    events = clicks(scene)
    if index >= len(events) or "x" not in events[index]:
        raise ValueError(f"{name} was not recorded in this capture.")
    view = scene.get("viewport", {"width": 1920, "height": 1080})
    return events[index]["x"] / view["width"], events[index]["y"] / view["height"]


def _get(state, key):
    return state[key] if isinstance(state, dict) else getattr(state, key)


def fitted_scale(state, aspect: tuple[float, float]) -> float:
    box_w, box_h = _get(state, "w") * CANVAS[0], _get(state, "h") * CANVAS[1]
    return min(box_w / aspect[0], box_h / aspect[1])


def effective_scale(state, viewport: dict) -> float:
    return fitted_scale(state, (viewport["width"], viewport["height"])) * _get(state, "cam_zoom")


def _axis(focus: float, box: float, content: float) -> tuple[float, float]:
    """Returns (visible start, visible length) in normalized source units on one axis."""
    if content <= box:
        return 0.0, 1.0
    length = box / content
    return min(1 - length, max(0.0, focus - length / 2)), length


def visible_window(state, aspect) -> tuple[float, float, float, float]:
    scale = fitted_scale(state, aspect) * _get(state, "cam_zoom")
    left, width = _axis(_get(state, "cam_x"), _get(state, "w") * CANVAS[0], aspect[0] * scale)
    top, height = _axis(_get(state, "cam_y"), _get(state, "h") * CANVAS[1], aspect[1] * scale)
    return left, top, width, height


def project(state, aspect, px: float, py: float) -> tuple[float, float]:
    scale = fitted_scale(state, aspect) * _get(state, "cam_zoom")
    box_w, box_h = _get(state, "w") * CANVAS[0], _get(state, "h") * CANVAS[1]
    content_w, content_h = aspect[0] * scale, aspect[1] * scale
    left, _, _, _ = visible_window(state, aspect)
    _, top, _, _ = visible_window(state, aspect)
    offset_x = (box_w - content_w) / 2 if content_w <= box_w else -left * content_w
    offset_y = (box_h - content_h) / 2 if content_h <= box_h else -top * content_h
    x = _get(state, "x") * CANVAS[0] + offset_x + px * content_w
    y = _get(state, "y") * CANVAS[1] + offset_y + py * content_h
    return x / CANVAS[0], y / CANVAS[1]


def drifted(rect: dict, drift: dict, depth: float, seconds: float) -> dict:
    scale = 1 + drift["zoom"] * seconds * depth
    shift_x, shift_y = drift["x"] * seconds * depth, drift["y"] * seconds * depth
    return {
        **rect,
        "x": 0.5 + (rect["x"] - 0.5) * scale + shift_x,
        "y": 0.5 + (rect["y"] - 0.5) * scale + shift_y,
        "w": rect["w"] * scale,
        "h": rect["h"] * scale,
    }


def resolve_focus(plan: FilmDirection, scenes_by_source: dict[str, dict]) -> FilmDirection:
    plan = plan.model_copy(deep=True)
    for shot in plan.shots:
        scene = scenes_by_source.get(shot.source, {})
        for layer in shot.layers:
            cap = zoom_cap(layer.kind, scene)
            for state in layer.states:
                if state.focus and layer.kind in ("footage", "product"):
                    state.cam_x, state.cam_y = click_point(scene, state.focus)
                state.cam_zoom = min(state.cam_zoom, cap)
            if layer.kind == "shape" and layer.target:
                layer.target_x, layer.target_y = click_point(scene, layer.target)
    return plan
