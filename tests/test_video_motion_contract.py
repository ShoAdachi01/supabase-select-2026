"""New motion vocabulary is optional, bounded, and inherits like geometry."""

import pytest
from pydantic import ValidationError

from server.video_direction_models import MotionLayer, ShotDirection
from tests.test_video_direction import film


def test_existing_plans_validate_unchanged():
    plan = film()
    assert plan.shots[0].drift.zoom == 0
    assert plan.shots[0].backdrop.kind == "flat"
    state = plan.shots[0].layers[0].states[1]
    assert (state.cam_x, state.cam_y, state.cam_zoom, state.focus, state.elevation) == (
        0.5,
        0.5,
        1,
        None,
        0,
    )


def test_camera_and_focus_carry_forward_and_explicit_camera_clears_focus():
    layer = MotionLayer.model_validate(
        dict(
            id="proof",
            kind="footage",
            states=[
                dict(beat=0, focus="click-1", cam_zoom=1.8),
                dict(beat=2),
                dict(beat=3, cam_x=0.2),
            ],
        )
    )
    assert layer.states[1].focus == "click-1" and layer.states[1].cam_zoom == 1.8
    assert layer.states[2].focus is None and layer.states[2].cam_x == 0.2


@pytest.mark.parametrize(
    "patch",
    [
        {"drift": {"zoom": 0.2}},
        {"backdrop": {"kind": "linear"}},
        {"backdrop": {"grain": 0.5}},
        {"layers": [dict(id=f"l{i}", kind="shape", states=[dict(beat=0)]) for i in range(10)]},
    ],
)
def test_out_of_contract_vocabulary_is_rejected(patch):
    shot = film().shots[0].model_dump(exclude={"source", "label"})
    with pytest.raises(ValidationError):
        ShotDirection.model_validate({**shot, **patch})


def test_focus_must_name_a_click_and_zoom_is_bounded():
    with pytest.raises(ValidationError):
        MotionLayer.model_validate(
            dict(id="a", kind="product", states=[dict(beat=0, focus="https://x")])
        )
    with pytest.raises(ValidationError):
        MotionLayer.model_validate(dict(id="a", kind="product", states=[dict(beat=0, cam_zoom=3)]))
