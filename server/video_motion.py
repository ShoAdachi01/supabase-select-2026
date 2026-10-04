"""Original launch motion design; exact text and real product imagery, frame by frame."""

from __future__ import annotations

import math
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from server.video_render import FFMPEG, font


def ease(value: float) -> float:
    return 1 - (1 - min(1, max(0, value))) ** 3


def motion_source(
    folder: Path, index: int, scene: dict, theme: str, duration: float, product: Path | None
) -> Path:
    """Stream frames to FFmpeg, without keeping an entire animation in memory."""
    dark = theme == "midnight"
    bg = "#111521" if dark else "#f3f0e8"
    fg = "#f9f7ee" if dark else "#242922"
    muted = "#a4b0a4" if dark else "#677160"
    accent = "#f57558"
    base = Image.new("RGB", (1920, 1080), bg)
    grid = ImageDraw.Draw(base)
    for x in range(0, 1920, 96):
        for y in range(0, 1080, 96):
            grid.ellipse((x, y, x + 2, y + 2), fill="#272e38" if dark else "#d9ddd1")
    screenshot = None
    if product and product.exists():
        screenshot = Image.open(product).convert("RGB").resize((770, 433))
    output = folder / f"motion-{index}.mp4"
    command = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        "1920x1080",
        "-r",
        "30",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-threads",
        "2",
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        for number in range(round(duration * 30)):
            t = number / 30
            canvas = base.copy()
            draw = ImageDraw.Draw(canvas)
            reveal = ease(t / 0.8)
            drift = math.sin(t * 1.3) * 22
            layout = scene.get("layout", "hook")
            draw.ellipse((1270 + drift, 60, 1930 + drift, 720), outline=accent, width=3)
            draw.ellipse((1390 + drift, 180, 1810 + drift, 600), outline="#8caa86", width=2)
            draw.rounded_rectangle((130, 134, 370, 184), 25, fill=accent)
            draw.text(
                (250, 159),
                {
                    "hook": "MEET YOUR PRODUCT",
                    "benefit": "IN THE SPOTLIGHT",
                    "outro": "YOUR NEXT STEP",
                }[layout],
                fill="#17211a",
                font=font(17),
                anchor="mm",
            )
            line_width = 23 if layout == "hook" and screenshot else 32
            lines = textwrap.wrap(scene.get("headline", ""), width=line_width)[:4]
            for line_index, line in enumerate(lines):
                progress = ease((t - line_index * 0.12) / 0.65)
                if progress <= 0:
                    continue
                layer = Image.new("RGBA", canvas.size)
                ink = ImageDraw.Draw(layer)
                ink.text(
                    (130, 263 + line_index * 114 + int((1 - progress) * 64)),
                    line,
                    fill=fg,
                    font=font(96),
                )
                layer.putalpha(layer.getchannel("A").point(lambda a, p=progress: int(a * p)))
                canvas = Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")
            draw = ImageDraw.Draw(canvas)
            subtitle_y = min(780, 300 + len(lines) * 114)
            for line_index, line in enumerate(
                textwrap.wrap(scene.get("subtitle", ""), width=65)[:2]
            ):
                draw.text((134, subtitle_y + line_index * 43), line, fill=muted, font=font(29))
            if screenshot and layout == "hook":
                x = round(1030 + 180 * (1 - reveal))
                y = round(357 + drift)
                draw.rounded_rectangle(
                    (x - 14, y - 53, x + 784, y + 448),
                    23,
                    fill="#ffffff" if not dark else "#2b3440",
                    outline="#8caa86",
                    width=2,
                )
                for dot, color in enumerate((accent, "#edcb78", "#8caa86")):
                    draw.ellipse((x + 9 + dot * 24, y - 32, x + 19 + dot * 24, y - 22), fill=color)
                canvas.paste(screenshot, (x, y))
            elif layout == "benefit":
                for i, word in enumerate(("FOCUS", "FLOW", "FORWARD")):
                    x = 140 + i * 410
                    y = 805 + round(math.sin(t * 2 + i) * 12)
                    draw.rounded_rectangle(
                        (x, y, x + 360, y + 105), 26, outline=accent if i == 1 else muted, width=2
                    )
                    draw.text((x + 180, y + 52), word, font=font(29), fill=fg, anchor="mm")
            elif layout == "outro":
                x = 140
                y = 770 + round(50 * (1 - reveal))
                draw.rounded_rectangle((x, y, x + 470, y + 98), 49, fill=accent)
                draw.text(
                    (x + 235, y + 49),
                    "TAKE A CLOSER LOOK  →",
                    font=font(27),
                    fill="#19221b",
                    anchor="mm",
                )
            draw.text((140, 1000), "PRODUCT / LAUNCH", font=font(19), fill=muted)
            draw.rounded_rectangle((1530, 1003, 1790, 1008), 3, fill=muted)
            draw.rounded_rectangle(
                (1530, 1003, 1530 + max(1, int(260 * t / duration)), 1008), 3, fill=accent
            )
            if number == min(30, round(duration * 30) - 1):
                canvas.save(folder / f"edit-{index}.jpg", quality=90)
            process.stdin.write(canvas.tobytes())
        process.stdin.close()
        stderr = process.stderr.read()
        if process.wait(timeout=30):
            raise ValueError("Motion rendering failed. " + stderr.decode(errors="replace")[-300:])
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
    return output
