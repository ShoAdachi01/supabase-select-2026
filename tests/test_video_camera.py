"""One definition of camera geometry for validator, composition and renderer checks."""

import pytest

from server import video_camera as cam
from server.video_direction_models import FilmDirection, MotionState
from tests.test_video_direction import film

VIEW = {"width": 1920, "height": 1080}


def state(**kw):
    return MotionState(beat=0, **kw)


def test_fullscreen_source_is_readable_regardless_of_capture_resolution():
    assert cam.effective_scale(state(), VIEW) == pytest.approx(1.0)


def test_contain_fit_uses_the_limiting_dimension():
    # A 0.5-wide by full-height box shows the 16:9 source width-limited.
    assert cam.effective_scale(state(w=0.5, h=1), VIEW) == pytest.approx(0.5)
    assert cam.effective_scale(state(w=0.5, h=1, cam_zoom=1.4), VIEW) == pytest.approx(0.7)


def test_window_clamps_inside_the_source_and_projects_points():
    s = state(cam_zoom=2, cam_x=0.95, cam_y=0.5)
    left, top, width, height = cam.visible_window(s, (1920, 1080))
    assert (width, height) == pytest.approx((0.5, 0.5))
    assert left == pytest.approx(0.5)  # clamped: no empty edge
    assert cam.project(s, (1920, 1080), 0.75, 0.5) == pytest.approx((0.5, 0.5))


def test_zoom_cap_follows_measured_scale_per_kind():
    scene = {"source_scale": 1, "still_scale": 2}
    assert cam.zoom_cap("footage", scene) == 1.2
    assert cam.zoom_cap("product", scene) == 2
    assert cam.zoom_cap("detail-0", {}) == 1.2


def test_focus_resolves_from_logical_click_and_unknown_click_fails():
    data = film().model_dump()
    data["shots"][0]["layers"][0]["states"][1].update(focus="click-0", cam_zoom=1.9)
    plan = FilmDirection.model_validate(data)
    scene = {
        "viewport": VIEW,
        "source_scale": 1,
        "interactions": [{"kind": "click", "time": 1, "x": 480, "y": 270}],
    }
    resolved = cam.resolve_focus(plan, {"scene-0.jpg": scene, "scene-1.jpg": scene})
    s = resolved.shots[0].layers[0].states[1]
    assert (s.cam_x, s.cam_y, s.cam_zoom) == (0.25, 0.25, 1.2)
    data["shots"][0]["layers"][0]["states"][1]["focus"] = "click-5"
    with pytest.raises(ValueError, match="click-5"):
        cam.resolve_focus(
            FilmDirection.model_validate(data), {"scene-0.jpg": scene, "scene-1.jpg": scene}
        )


def test_drift_scales_with_depth_around_canvas_center():
    moved = cam.drifted({"x": 0, "y": 0, "w": 1, "h": 1}, {"x": 0.01, "y": 0, "zoom": 0.02}, 0.5, 2)
    assert moved["w"] == pytest.approx(1.02)
    assert moved["x"] == pytest.approx(0.5 - 0.5 * 1.02 + 0.01)
