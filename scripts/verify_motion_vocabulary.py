"""Render fixture shots and check pixels where video_camera.py predicts them. Uses local Chromium only."""

import json
import tempfile
from pathlib import Path

from PIL import Image

from server.video_camera import project
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
    (folder / "motion-jobs.json").write_text(json.dumps({"jobs": [job], "preview": True}))
    return direction


def main():
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        direction = fixture(folder)
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


if __name__ == "__main__":
    main()
