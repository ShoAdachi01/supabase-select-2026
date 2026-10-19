"""Render fixture shots and check pixels where video_camera.py predicts them. Uses local Chromium only."""

import json
import tempfile
from pathlib import Path

from PIL import Image

from server.video_camera import drifted, project
from server.video_composition import run_compositor
from server.video_direction_models import MotionState

VIEW = {"width": 1920, "height": 1080}


def fixture(folder: Path):
    # A 3840x2160 still: white field, a 40px red square centered at logical (1440, 270).
    image = Image.new("RGB", (3840, 2160), "white")
    image.paste((220, 20, 20), (2880 - 40, 540 - 40, 2880 + 40, 540 + 40))
    image.save(folder / "motion-product-0.png")
    direction = {
        "purpose": "Verify the camera and ring.",
        "composition": "product",
        "entry": "cut",
        "background": "#101218",
        "bpm": 120,
        "beats": 2,
        "hits": [],
        "drift": {"x": 0, "y": 0, "zoom": 0},
        "backdrop": {"kind": "flat", "x": 0.5, "y": 0.4, "color2": None, "grain": 0},
        "layers": [
            {
                "id": "proof",
                "kind": "product",
                "depth": 1,
                "text": "",
                "color": "#ffffff",
                "size": 100,
                "weight": 600,
                "align": "left",
                "entrance": "none",
                "shape": "rect",
                "stroke": 4,
                "count": 8,
                "gap": 0.4,
                "font": "sans",
                "target_layer": None,
                "target": None,
                "target_x": None,
                "target_y": None,
                "states": [
                    {
                        "beat": 0,
                        "x": 0,
                        "y": 0,
                        "w": 1,
                        "h": 1,
                        "radius": 0,
                        "rotation": 0,
                        "opacity": 1,
                        "cam_x": 0.75,
                        "cam_y": 0.25,
                        "cam_zoom": 2,
                        "focus": None,
                        "elevation": 0,
                        "ease": "hold",
                    }
                ],
            },
            {
                "id": "ring",
                "kind": "shape",
                "depth": 1,
                "text": "",
                "color": "#00ff00",
                "size": 100,
                "weight": 600,
                "align": "left",
                "entrance": "none",
                "shape": "ring",
                "stroke": 8,
                "count": 8,
                "gap": 0.4,
                "font": "sans",
                "target_layer": "proof",
                "target": "click-0",
                "target_x": 0.75,
                "target_y": 0.25,
                "states": [
                    {
                        "beat": 0,
                        "x": 0,
                        "y": 0,
                        "w": 0.1,
                        "h": 0.18,
                        "radius": 0,
                        "rotation": 0,
                        "opacity": 1,
                        "cam_x": 0.5,
                        "cam_y": 0.5,
                        "cam_zoom": 1,
                        "focus": None,
                        "elevation": 0,
                        "ease": "hold",
                    }
                ],
            },
        ],
    }
    job = {
        "index": 0,
        "direction": direction,
        "preset": "directed",
        "theme": "midnight",
        "headline": "",
        "subtitle": "",
        "frames": 30,
        "interactive": False,
        "product": "motion-product-0.png",
        "details": [],
        "footage": None,
        "focus": {"x": 0.5, "y": 0.5},
        "viewport": VIEW,
        "source_scale": 1,
        "still_scale": 2,
        "detail_sizes": [],
        "preview_frames": [0],
    }
    return direction, job


def layer(id, kind="shape", **fields):
    state = {
        "beat": 0,
        "x": 0,
        "y": 0,
        "w": 0.1,
        "h": 0.1,
        "radius": 0,
        "rotation": 0,
        "opacity": 1,
        "cam_x": 0.5,
        "cam_y": 0.5,
        "cam_zoom": 1,
        "focus": None,
        "elevation": 0,
        "ease": "hold",
    }
    base = {
        "id": id,
        "kind": kind,
        "depth": 1,
        "text": "",
        "color": "#ffffff",
        "size": 100,
        "weight": 600,
        "align": "left",
        "entrance": "none",
        "shape": "rect",
        "stroke": 4,
        "count": 8,
        "gap": 0.4,
        "font": "sans",
        "target_layer": None,
        "target": None,
        "target_x": None,
        "target_y": None,
    }
    geometry = {k: fields.pop(k) for k in ("x", "y", "w", "h") if k in fields}
    return {**base, **fields, "states": [{**state, **geometry}]}


def shape_job(index, layers, drift, preview_frames, frames=60):
    return {
        "index": index,
        "direction": {
            "purpose": "Verify drift and shape kinds.",
            "composition": "graphic",
            "entry": "cut",
            "background": "#101218",
            "bpm": 120,
            "beats": frames // 15,
            "hits": [],
            "drift": drift,
            "backdrop": {"kind": "flat", "x": 0.5, "y": 0.4, "color2": None, "grain": 0},
            "layers": layers,
        },
        "preset": "directed",
        "theme": "midnight",
        "headline": "",
        "subtitle": "",
        "frames": frames,
        "interactive": False,
        "product": "motion-product-0.png",
        "details": [],
        "footage": None,
        "focus": {"x": 0.5, "y": 0.5},
        "viewport": VIEW,
        "source_scale": 1,
        "still_scale": 2,
        "detail_sizes": [],
        "preview_frames": preview_frames,
    }


PARALLAX_DRIFT = {"x": 0.04, "y": 0, "zoom": 0}
LATER = 45  # frame sampled after 1.5s of drift


def parallax_job():
    # Two squares under the same shot drift: depth 0 stays put, depth 1 travels drift.x * t.
    return shape_job(
        1,
        [
            layer("still", color="#ff0000", depth=0, x=0.1, y=0.2, w=0.1, h=0.1),
            layer("drifting", color="#00ff00", depth=1, x=0.1, y=0.6, w=0.1, h=0.1),
        ],
        PARALLAX_DRIFT,
        [0, LATER],
    )


def shapes_job():
    # A horizontal 8px line, and a rail of four segments that fill the middle half of each cell.
    return shape_job(
        2,
        [
            layer("line", shape="line", stroke=8, x=0.1, y=0.1, w=0.8, h=0.1),
            layer("rail", shape="segments", count=4, gap=0.5, x=0.1, y=0.5, w=0.8, h=0.1),
        ],
        {"x": 0, "y": 0, "zoom": 0},
        [0],
    )


def left_edge(frame, y, match) -> int:
    return next(x for x in range(frame.width) if match(frame.getpixel((x, y))))


def red(p):
    return p[0] > 180 and p[1] < 80 and p[2] < 80


def green(p):
    return p[1] > 180 and p[0] < 80 and p[2] < 80


def white(p):
    return min(p) > 200


def dark(p):
    return max(p) < 60


def check_parallax(folder: Path):
    first = Image.open(folder / "preview-1-0.jpg").convert("RGB")
    later = Image.open(folder / f"preview-1-{LATER}.jpg").convert("RGB")
    seconds = LATER / 30
    still_y, drift_y = round(0.25 * 1080), round(0.65 * 1080)
    moved = left_edge(later, drift_y, green) - left_edge(first, drift_y, green)
    expected = (
        drifted({"x": 0.1, "y": 0.6, "w": 0.1, "h": 0.1}, PARALLAX_DRIFT, 1, seconds)["x"] * 1920
        - 0.1 * 1920
    )
    assert abs(moved - expected) <= 3, f"depth-1 layer moved {moved}px, expected {expected:.1f}"
    stayed = left_edge(later, still_y, red) - left_edge(first, still_y, red)
    assert abs(stayed) <= 1, f"depth-0 layer moved {stayed}px under drift"


def check_shapes(folder: Path):
    frame = Image.open(folder / "preview-2-0.jpg").convert("RGB")
    line_y = round(0.15 * 1080)
    assert white(frame.getpixel((960, line_y))), "line stroke missing at its center"
    assert dark(frame.getpixel((960, line_y - 12))), "line is thicker than its stroke"
    assert dark(frame.getpixel((960, line_y + 12))), "line is thicker than its stroke"
    rail_y = round(0.55 * 1080)
    cell = 0.8 * 1920 / 4
    for i in range(4):
        start = 0.1 * 1920 + i * cell
        fill, gap = round(start + cell / 2), round(start + cell / 8)
        assert white(frame.getpixel((fill, rail_y))), f"segment {i} fill missing at x={fill}"
        assert dark(frame.getpixel((gap, rail_y))), f"segment {i} gap filled at x={gap}"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        direction, camera_job = fixture(folder)
        jobs = [camera_job, parallax_job(), shapes_job()]
        (folder / "motion-jobs.json").write_text(json.dumps({"jobs": jobs, "preview": True}))
        run_compositor(folder, folder / "motion-jobs.json")
        frame = Image.open(folder / "preview-0-0.jpg").convert("RGB")
        assert frame.size == (1920, 1080), frame.size
        state = MotionState.model_validate(direction["layers"][0]["states"][0])
        x, y = project(state, (1920, 1080), 0.75, 0.25)
        px, py = round(x * 1920), round(y * 1080)
        red = frame.getpixel((px, py))
        assert red[0] > 180 and red[1] < 80, f"camera: expected red at {(px, py)}, got {red}"
        # At 2x zoom the 40 logical-px square is 80 canvas px wide: edge 30px out is still red.
        assert frame.getpixel((px + 30, py))[0] > 180, "camera zoom not applied"
        ring = frame.getpixel((px + 96 - 4, py))
        assert ring[1] > 180 and ring[0] < 80, f"ring not centered on click: {ring}"
        print("PASS: camera crop, zoom and click-targeted ring match video_camera.py")
        check_parallax(folder)
        print("PASS: parallax drift moves depth-1 by drift.x * t and leaves depth-0 in place")
        check_shapes(folder)
        print("PASS: line stroke and segment fill/gap regions")


if __name__ == "__main__":
    main()
