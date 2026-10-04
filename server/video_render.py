"""Render actual browser footage into a composed, narrated 1080p film."""

from __future__ import annotations

import json
import math
import subprocess
import textwrap
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def ffmpeg(*args: str, timeout: int = 300):
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise ValueError("Video rendering failed. " + result.stderr.decode(errors="replace")[-900:])


def font(size: int):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def frame(path: Path, title: str, label: str, theme: str, number: int):
    dark = theme == "midnight"
    color = (16, 19, 31) if dark else (238, 236, 229)
    canvas = Image.new("RGB", (1920, 1080), color)
    draw = ImageDraw.Draw(canvas)
    # A restrained radial tint; the product remains the subject.
    for radius in range(1400, 50, -10):
        amount = (1 - radius / 1400) * 0.16
        tint = tuple(
            int(c * (1 - amount) + t * amount) for c, t in zip(color, (96, 74, 150), strict=True)
        )
        draw.ellipse((1200 - radius, -200 - radius, 1200 + radius, -200 + radius), fill=tint)
    fg = "#f1f0f6" if dark else "#292a31"
    muted = "#9599b0" if dark else "#74747d"
    draw.text((160, 32), title[:70], font=font(27), fill=fg)
    draw.text((1760, 36), f"{number:02d}", font=font(23), fill=muted, anchor="ra")
    draw.rounded_rectangle((148, 83, 1772, 1020), 18, fill="#090b14" if dark else "#ffffff")
    draw.rounded_rectangle((160, 88, 1760, 122), 10, fill="#252734" if dark else "#e4e4e9")
    for i, c in enumerate(("#fd7474", "#edc363", "#78c899")):
        draw.ellipse((180 + i * 22, 98, 190 + i * 22, 108), fill=c)
    draw.text((260, 94), label[:85], font=font(17), fill=muted)
    draw.text((160, 1043), "CUTROOM  /  PRODUCT FILM", font=font(17), fill=muted)
    draw.text((1760, 1043), "1920 × 1080", font=font(17), fill=muted, anchor="ra")
    canvas.save(path)


def caption(path: Path, text: str):
    canvas = Image.new("RGBA", (1600, 115), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    lines = textwrap.wrap(text, width=85)[:2]
    if lines:
        draw.rounded_rectangle((90, 5, 1510, 106), 18, fill=(14, 17, 26, 225))
        for index, line in enumerate(lines):
            draw.text((800, 27 + index * 34), line, font=font(25), fill="white", anchor="mt")
    canvas.save(path)


def animation_title(path: Path, headline: str, subtitle: str):
    canvas = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    lines = textwrap.wrap(headline, width=26)[:4]
    if lines:
        height = len(lines) * 104 + (100 if subtitle else 20)
        top = (1080 - height) // 2
        draw.rounded_rectangle((240, top - 55, 1680, top + height + 40), 35, fill=(18, 24, 25, 150))
        for i, line in enumerate(lines):
            draw.text((960, top + i * 104), line, font=font(86), fill="#fffdf6", anchor="mt")
        for i, line in enumerate(textwrap.wrap(subtitle, width=65)[:2]):
            draw.text(
                (960, top + len(lines) * 104 + 20 + i * 38),
                line,
                font=font(28),
                fill="#dbe7d5",
                anchor="mt",
            )
    canvas.save(path)


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as source:
        return source.getnframes() / source.getframerate()


def original_music(path: Path, duration: float, style: str):
    """Original synthesized instrumental bed; no sampled or third-party recordings."""
    rate = 24000
    t = np.arange(int(duration * rate), dtype=np.float64) / rate
    track = np.zeros_like(t)
    chords = [
        (130.81, 164.81, 196),
        (110, 130.81, 164.81),
        (87.31, 110, 130.81),
        (98, 123.47, 146.83),
    ]
    bar = 4.0 if style == "ambient" else 3.2
    for i in range(math.ceil(duration / bar)):
        mask = (t >= i * bar) & (t < (i + 1) * bar)
        local = t[mask] - i * bar
        envelope = np.sin(np.pi * np.minimum(local / 0.5, 1) / 2) * np.minimum(
            (bar - local) / 0.7, 1
        )
        for frequency in chords[i % len(chords)]:
            track[mask] += (
                envelope
                * (
                    np.sin(2 * np.pi * frequency * local)
                    + 0.18 * np.sin(4 * np.pi * frequency * local)
                )
                * 0.055
            )
        if style == "momentum":
            phase = local % 0.4
            track[mask] += (
                0.03 * np.sin(2 * np.pi * (800 + local * 100) * local) * np.exp(-phase * 28)
            )
    fade = np.minimum(t / 1.2, 1) * np.minimum((duration - t) / 1.8, 1)
    pcm = np.clip(track * fade * 32767, -32767, 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm.tobytes())


def render(
    directory: Path,
    raw: Path,
    scenes: list[dict],
    title: str,
    theme: str,
    music: str,
    audio_paths: list[Path | None],
    progress=None,
) -> dict:
    clips, lengths = [], []
    for i, (scene, audio) in enumerate(zip(scenes, audio_paths, strict=True)):
        background, captions = directory / f"frame-{i}.png", directory / f"caption-{i}.png"
        frame(background, title, scene["label"], theme, i + 1)
        caption(captions, scene.get("narration", ""))
        audio_wav = directory / f"audio-{i}.wav"
        if audio:
            ffmpeg("-i", str(audio), "-ac", "2", "-ar", "48000", str(audio_wav))
            duration = max(3.5, wav_duration(audio_wav) + 0.35)
        else:
            duration = max(4, min(9, len(scene.get("narration", "").split()) / 2.4))
            if scene.get("kind") in ("title", "generated"):
                duration = scene.get("duration", 4)
            ffmpeg(
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-t",
                str(duration),
                str(audio_wav),
            )
        if scene.get("kind") in ("title", "generated"):
            duration = max(duration, scene.get("duration", 4))
        duration = math.ceil(duration * 30) / 30
        lengths.append(duration)
        start = max(0, scene.get("start", 0))
        recorded = max(0.4, scene.get("end", duration) - start)
        focus = scene.get("focus", {"x": 640, "y": 360})
        fx, fy = min(1, max(0, focus["x"] / 1280)), min(1, max(0, focus["y"] / 720))
        # One output frame per input frame preserves the real click/typing footage.
        zoom = f"1+0.12*sin(PI*min(on/{int(duration * 30)},1))"
        filters = (
            f"[1:v]fps=30,tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},"
            f"setpts=PTS-STARTPTS,scale=2560:1440,"
            f"zoompan=z='{zoom}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d=1:s=1600x900:fps=30[v];"
            f"[0:v][v]overlay=160:112[composed];[composed][2:v]overlay=160:890,"
            "format=yuv420p[out];"
            f"[3:a]apad,atrim=duration={duration},afade=t=in:d=0.05,afade=t=out:st={max(0, duration - 0.15)}:d=0.15[a]"
        )
        source = raw
        if scene.get("kind") == "title":
            from server.video_motion import motion_source

            product = next(
                (s.get("thumbnail") for s in scenes if s.get("kind", "browser") == "browser"), None
            )
            source = motion_source(
                directory, i, scene, theme, duration, directory / product if product else None
            )
            start, recorded = 0, duration
            scene["thumbnail"] = f"edit-{i}.jpg"
        elif scene.get("kind") == "generated":
            source = directory / scene["source_file"]
            start, recorded = 0, scene["end"]
            ffmpeg(
                "-ss", "1", "-i", str(source), "-frames:v", "1", str(directory / f"edit-{i}.jpg")
            )
            scene["thumbnail"] = f"edit-{i}.jpg"
            animation_title(captions, scene.get("headline", ""), scene.get("subtitle", ""))
        if scene.get("kind") in ("title", "generated"):
            filters = (
                f"[1:v]fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                f"tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},setpts=PTS-STARTPTS[v];"
                "[v][2:v]overlay=160:940,format=yuv420p[out];"
                f"[3:a]apad,atrim=duration={duration},afade=t=in:d=0.05,afade=t=out:st={max(0, duration - 0.15)}:d=0.15[a]"
            )
            if scene.get("kind") == "generated":
                filters = filters.replace(
                    "[v][2:v]overlay=160:940",
                    "[2:v]format=rgba,fade=t=in:st=0:d=0.6:alpha=1[type];[v][type]overlay=x=0:y='40*(1-min(t/0.6,1))'",
                )
        if scene.get("transition") == "fade":
            filters = filters.replace(
                "format=yuv420p[out]",
                f"fade=t=in:d=0.15,fade=t=out:st={duration - 0.15}:d=0.15,format=yuv420p[out]",
            )
        clip = directory / f"clip-{i}.mp4"
        ffmpeg(
            "-loop",
            "1",
            "-i",
            str(background),
            "-ss",
            str(start),
            "-t",
            str(recorded),
            "-i",
            str(source),
            "-loop",
            "1",
            "-i",
            str(captions),
            "-i",
            str(audio_wav),
            "-filter_complex",
            filters,
            "-map",
            "[out]",
            "-map",
            "[a]",
            "-r",
            "30",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(clip),
        )
        clips.append(clip)
        scene["duration"] = round(duration, 2)
        if progress:
            progress(i + 1, len(scenes))
    manifest = directory / "concat.txt"
    manifest.write_text("\n".join(f"file '{clip.name}'" for clip in clips))
    joined = directory / "joined.mp4"
    total = lengths[0]
    scenes[0]["timeline_start"] = 0
    if any(s.get("transition") == "dissolve" for s in scenes[:-1]):
        inputs, graph = [], []
        for i, clip in enumerate(clips):
            inputs += ["-i", str(clip)]
            graph += [
                f"[{i}:v]setpts=PTS-STARTPTS,fps=30,settb=AVTB,format=yuv420p[v{i}]",
                f"[{i}:a]apad,atrim=duration={lengths[i]},asetpts=PTS-STARTPTS[a{i}]",
            ]
        current_v, current_a = "v0", "a0"
        for i in range(1, len(clips)):
            overlap = 0.3 if scenes[i - 1].get("transition") == "dissolve" else 0
            scenes[i]["timeline_start"] = round(total - overlap, 3)
            if overlap:
                graph += [
                    f"[{current_v}][v{i}]xfade=transition=fade:duration={overlap}:offset={total - overlap}[joinv{i}]",
                    f"[{current_a}][a{i}]acrossfade=d={overlap}:c1=tri:c2=tri[joina{i}]",
                ]
            else:
                graph += [
                    f"[{current_v}][v{i}]concat=n=2:v=1:a=0,fps=30,settb=AVTB[joinv{i}]",
                    f"[{current_a}][a{i}]concat=n=2:v=0:a=1[joina{i}]",
                ]
            current_v, current_a = f"joinv{i}", f"joina{i}"
            total += lengths[i] - overlap
        ffmpeg(
            "-filter_complex_threads",
            "1",
            *inputs,
            "-filter_complex",
            ";".join(graph),
            "-map",
            f"[{current_v}]",
            "-map",
            f"[{current_a}]",
            "-t",
            str(total),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "2",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(joined),
        )
    else:
        for i in range(1, len(scenes)):
            scenes[i]["timeline_start"] = round(total, 3)
            total += lengths[i]
        ffmpeg("-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(joined))
    output = directory / "film.mp4"
    if music != "none":
        bed = directory / "music.wav"
        original_music(bed, total + 0.5, music)
        ffmpeg(
            "-i",
            str(joined),
            "-i",
            str(bed),
            "-filter_complex",
            "[0:a]asplit=2[voice][side];[1:a]volume=.38[bed];[bed][side]sidechaincompress=threshold=.015:ratio=6:attack=20:release=500[duck];[voice][duck]amix=inputs=2:duration=first:normalize=0[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        )
    else:
        output.write_bytes(joined.read_bytes())
    (directory / "storyboard.json").write_text(json.dumps(scenes, indent=2))
    ffmpeg(
        "-ss",
        str(min(2.0, total / 2)),
        "-i",
        str(output),
        "-frames:v",
        "1",
        str(directory / "poster.jpg"),
    )
    return {
        "duration_seconds": round(total, 2),
        "bytes": output.stat().st_size,
        "resolution": "1920×1080",
        "format": "MP4",
        "fps": 30,
    }
