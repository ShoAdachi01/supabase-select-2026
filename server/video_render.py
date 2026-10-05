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


def font(size: int, bold: bool = False):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def caption(path: Path, text: str):
    canvas = Image.new("RGBA", (1920, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    lines = textwrap.wrap(text, width=72)[:2]
    if lines:
        face = font(32)
        width = min(1760, max(draw.textlength(line, font=face) for line in lines) + 64)
        height = 32 + len(lines) * 40
        draw.rounded_rectangle(
            ((1920 - width) / 2, 0, (1920 + width) / 2, height), 16, fill=(14, 17, 26, 222)
        )
        for index, line in enumerate(lines):
            draw.text((960, 16 + index * 40), line, font=face, fill="white", anchor="mt")
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
            notes = np.array(chords[i % len(chords)]) * 2
            melody = notes[(local / 0.4).astype(int) % 3]
            track[mask] += 0.042 * np.sin(2 * np.pi * melody * phase) * np.exp(-phase * 11)
            kick = local % 0.8
            track[mask] += (
                0.1
                * np.sin(2 * np.pi * (48 * kick + 4 * (1 - np.exp(-kick * 32))))
                * np.exp(-kick * 18)
            )
            noise = np.random.default_rng(i).standard_normal(len(local))
            hat = noise - np.roll(noise, 1)
            track[mask] += 0.007 * hat * np.exp(-phase * 85)
            backbeat = (local + 0.4) % 0.8
            track[mask] += 0.035 * noise * np.exp(-backbeat * 38)
            track[mask] += (
                0.045
                * np.sin(2 * np.pi * chords[i % len(chords)][0] / 2 * kick)
                * np.exp(-kick * 5)
            )
    fade = np.minimum(t / 1.2, 1) * np.minimum((duration - t) / 1.8, 1)
    pcm = np.clip(track * fade * 32767, -32767, 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm.tobytes())


def transition_cues(path: Path, scenes: list[dict]):
    """Original short noise sweeps and soft impacts placed on actual edit boundaries."""
    with wave.open(str(path)) as source:
        rate = source.getframerate()
        track = (
            np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float64)
            / 32768
        )
    for i, scene in enumerate(scenes):
        if not scene.get("motion") or scene.get("motion") == "none":
            continue
        cue = max(0, scene.get("timeline_start", 0))
        start = max(0, round((cue - 0.16) * rate))
        count = min(round(0.3 * rate), len(track) - start)
        if count <= 0:
            continue
        t = np.arange(count) / rate
        noise = np.random.default_rng(i + 704).standard_normal(count)
        smooth = np.convolve(noise, np.ones(11) / 11, mode="same")
        sweep = 0.06 * smooth * np.sin(np.pi * np.arange(count) / count) ** 2
        impact_time = np.maximum(0, t - 0.16)
        impact = (
            0.055 * np.sin(2 * np.pi * 130 * impact_time) * np.exp(-impact_time * 45) * (t >= 0.16)
        )
        track[start : start + count] += sweep + impact
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes((np.clip(track, -0.95, 0.95) * 32767).astype("<i2").tobytes())


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
    designed = {}
    if any(s.get("motion", "none") != "none" for s in scenes):
        from server.video_composition import prepare_compositions

        checkpoint = (lambda: progress(0, len(scenes))) if progress else None
        if checkpoint:
            checkpoint()
        designed = prepare_compositions(directory, raw, scenes, theme, audio_paths, checkpoint)
    for i, (scene, audio) in enumerate(zip(scenes, audio_paths, strict=True)):
        background, captions = directory / f"frame-{i}.png", directory / f"caption-{i}.png"
        Image.new("RGB", (1920, 1080), "black").save(background)
        caption(captions, scene.get("narration", ""))
        audio_wav = directory / f"audio-{i}.wav"
        duration = scene.get("duration", 4)
        if audio:
            ffmpeg("-i", str(audio), "-ac", "2", "-ar", "48000", str(audio_wav))
            # Preserve exact edited speech. Never clip a sentence to meet a shot budget.
            duration = max(duration, wav_duration(audio_wav) + 0.15)
        else:
            ffmpeg(
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=stereo",
                "-t",
                str(duration),
                str(audio_wav),
            )
        duration = math.ceil(duration * 30) / 30
        lengths.append(duration)
        start = max(0, scene.get("start", 0))
        recorded = max(0.4, scene.get("end", duration) - start)
        focus = scene.get("focus", {"x": 640, "y": 360})
        viewport = scene.get("viewport", {"width": 1280, "height": 720})
        fx, fy = (
            min(1, max(0, focus["x"] / viewport["width"])),
            min(1, max(0, focus["y"] / viewport["height"])),
        )
        # Compress long action recordings into the edit budget. Short takes retain real-time motion.
        speed = max(1, recorded / duration)
        zoom = (
            f"1+0.10*pow(min(on/{max(1, int(duration * 30) - 1)},1),2)*(3-2*min(on/{max(1, int(duration * 30) - 1)},1))"
            if scene.get("camera") == "push"
            else "1"
        )
        size = "3840:2160" if scene.get("camera") == "push" else "1920:1080"
        filters = (
            f"[1:v]setpts=(PTS-STARTPTS)/{speed},fps=30,"
            f"scale={size}:force_original_aspect_ratio=increase,crop={size},"
            f"tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},"
            f"zoompan=z='{zoom}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':d=1:s=1920x1080:fps=30[v];"
            "[v][2:v]overlay=0:936,format=yuv420p[out];"
            f"[3:a]apad,atrim=duration={duration},afade=t=in:d=0.05,afade=t=out:st={max(0, duration - 0.15)}:d=0.15[a]"
        )
        source = raw
        if i in designed:
            source = designed[i]
            start, recorded = 0, duration
            scene["thumbnail"] = f"edit-{i}.jpg"
        elif scene.get("kind") == "title":
            from server.video_motion import motion_source

            # Match the exact first frame of the next visible product shot, including its trim.
            following = scenes[i + 1] if i + 1 < len(scenes) else None
            product = None
            if following and following.get("kind", "browser") == "browser":
                product = directory / f"reveal-{i}.png"
                ffmpeg(
                    "-ss",
                    str(max(0, following.get("start", 0))),
                    "-i",
                    str(raw),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080",
                    str(product),
                )
            source = motion_source(directory, i, scene, theme, duration, product)
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
        if scene.get("kind") in ("title", "generated") or i in designed:
            filters = (
                f"[1:v]fps=30,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                f"tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},setpts=PTS-STARTPTS[v];"
                "[v][2:v]overlay=0:936,format=yuv420p[out];"
                f"[3:a]apad,atrim=duration={duration},afade=t=in:d=0.05,afade=t=out:st={max(0, duration - 0.15)}:d=0.15[a]"
            )
            if scene.get("kind") == "generated":
                filters = filters.replace(
                    "[v][2:v]overlay=0:936",
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
    from server.video_sound import beat_map, interaction_audio, launch_music

    effects = directory / "interactions.wav"
    cues = interaction_audio(effects, total + 0.1, scenes)
    (directory / "sound-cues.json").write_text(json.dumps(cues, indent=2))
    beats = beat_map(scenes, total)
    (directory / "beats.json").write_text(json.dumps(beats, indent=2))
    if music != "none" or cues:
        bed = directory / "music.wav"
        voiced = any(audio_paths)
        if music == "none":
            ffmpeg(
                "-f", "lavfi", "-i", "anullsrc=r=24000:cl=stereo", "-t", str(total + 0.1), str(bed)
            )
        elif any(s.get("motion") == "directed" for s in scenes) or (
            not voiced and music == "momentum"
        ):
            launch_music(bed, total + 0.1, beats["bpm"], ambient=music == "ambient")
        else:
            original_music(bed, total + 0.1, music)
            if designed:
                transition_cues(bed, scenes)
        if voiced:
            graph = (
                "[0:a]loudnorm=I=-16:TP=-1.5:LRA=9,asplit=2[voice][side];"
                "[1:a]loudnorm=I=-21:TP=-2:LRA=7[bed];"
                "[bed][side]sidechaincompress=threshold=.06:ratio=2:attack=15:release=250[duck];"
                "[voice][duck][2:a]amix=inputs=3:duration=first:normalize=0,alimiter=limit=.95:level=false[a]"
            )
        else:
            bed_filter = "anull" if music == "none" else "loudnorm=I=-16:TP=-2:LRA=7"
            graph = f"[1:a]{bed_filter}[bed];[bed][2:a]amix=inputs=2:normalize=0,alimiter=limit=.95:level=false[a]"
        ffmpeg(
            "-i",
            str(joined),
            "-i",
            str(bed),
            "-i",
            str(effects),
            "-filter_complex",
            graph,
            "-map",
            "0:v",
            "-map",
            "[a]",
            "-t",
            str(total),
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
