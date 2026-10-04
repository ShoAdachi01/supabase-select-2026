"""Frame-accurate typography and real UI reveals, with an exact handoff to footage."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from server.video_render import FFMPEG, font


def ease(value: float) -> float:
    value = min(1, max(0, value))
    return value * value * (3 - 2 * value)


def text_lines(text: str, face, width: int) -> list[str]:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = [""]
    for word in text.split():
        candidate = f"{lines[-1]} {word}".strip()
        if draw.textlength(candidate, font=face) > width and lines[-1]:
            lines.append(word)
        else:
            lines[-1] = candidate
    return lines


def motion_frame(
    scene: dict, theme: str, t: float, duration: float, product: Image.Image | None
) -> Image.Image:
    dark = theme == "midnight"
    bg, fg = ("#0d1120", "#ffffff") if dark else ("#f7f9fc", "#131b30")
    muted, accent = ("#a6b4cf", "#b4c6ff") if dark else ("#59657c", "#4a61e8")
    layout = scene.get("layout", "hook")
    reveal = product is not None and layout != "outro"
    # Last frame equals the following full-screen shot, with no border or lingering title.
    handoff = ease((t - (duration - 0.8)) / (0.8 - 1 / 30)) if reveal else 0
    if handoff >= 1:
        return product.copy()
    canvas = Image.new("RGB", (1920, 1080), bg)
    ink = Image.new("RGBA", canvas.size)
    draw = ImageDraw.Draw(ink)
    entrance = ease(t / 0.42)
    offset = round(36 * (1 - entrance))
    left = 120
    top = 275 if layout == "hook" else 300
    width = 760 if layout == "hook" and reveal else 1600
    face = font(104 if layout == "hook" else 116)
    lines = text_lines(scene.get("headline", ""), face, width)
    # Long user copy fits instead of being silently truncated.
    if len(lines) > 4:
        face = font(72)
        lines = text_lines(scene.get("headline", ""), face, width)
    line_height = face.size + 12
    draw.rounded_rectangle((left, top - 74, left + round(72 * entrance), top - 68), 3, fill=accent)
    for i, line in enumerate(lines):
        draw.text((left, top + i * line_height + offset), line, font=face, fill=fg)
    subtitle_top = top + len(lines) * line_height + 34
    for i, line in enumerate(text_lines(scene.get("subtitle", ""), font(30), width)):
        draw.text((left + 4, subtitle_top + i * 40 + offset), line, font=font(30), fill=muted)
    opacity = entrance * (1 - ease(handoff * 2))
    ink.putalpha(ink.getchannel("A").point(lambda a: round(a * opacity)))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), ink).convert("RGB")
    if reveal:
        if layout == "hook":
            start_width, start_x, start_y = 900, 990, 370
        else:
            start_width, start_x, start_y = 1056, 760, 660
        w = round(start_width + (1920 - start_width) * handoff)
        h = round(w * 9 / 16)
        x = round(start_x * (1 - handoff))
        y = round((start_y + 42 * (1 - entrance)) * (1 - handoff))
        shot = product.resize((w, h), Image.Resampling.LANCZOS)
        mask = Image.new("L", (w, h))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), round(18 * (1 - handoff)), fill=255)
        shadow = ImageDraw.Draw(canvas)
        for spread in range(18, 0, -3):
            shade = "#090c16" if dark else "#e6eaf2"
            shadow.rounded_rectangle(
                (x - spread, y - spread + 14, x + w + spread, y + h + spread + 14), 24, fill=shade
            )
        canvas.paste(shot, (x, y), mask)
    elif layout == "outro":
        draw = ImageDraw.Draw(canvas)
        y = min(930, subtitle_top + 120)
        # A single underline resolves with the soundtrack instead of a fake button.
        draw.rounded_rectangle(
            (124, y, 124 + max(1, round(460 * ease(t / 0.9))), y + 5), 3, fill=accent
        )
    return canvas


def motion_source(
    folder: Path, index: int, scene: dict, theme: str, duration: float, product: Path | None
) -> Path:
    screenshot = None
    if product and product.exists():
        with Image.open(product) as source:
            screenshot = source.convert("RGB").resize((1920, 1080), Image.Resampling.LANCZOS)
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
            canvas = motion_frame(scene, theme, number / 30, duration, screenshot)
            if number == min(20, round(duration * 30) - 1):
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
