"""Original music and tactile interaction sounds, scheduled from the actual edit."""

import math
import wave
from pathlib import Path

import numpy as np

RATE = 24000


def write_audio(path: Path, samples):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes((np.clip(samples, -0.94, 0.94) * 32767).astype("<i2").tobytes())


def place(track, sound, seconds, pan=0):
    start = round(seconds * RATE)
    if start < 0 or start >= len(track):
        return
    count = min(len(sound), len(track) - start)
    gains = np.sqrt([(1 - pan) / 2, (1 + pan) / 2])
    track[start : start + count] += sound[:count, None] * gains


def interaction_schedule(scenes):
    scheduled = []
    for scene in scenes:
        if scene.get("kind", "browser") != "browser":
            continue
        direction = scene.get("direction")
        if direction and not any(layer["kind"] == "footage" for layer in direction["layers"]):
            continue
        start, end = scene.get("start", 0), scene.get("end", 0)
        speed = max(1, max(0.4, end - start) / scene["duration"])
        viewport = scene.get("viewport", {"width": 1920})
        for event in scene.get("interactions", []):
            if event.get("kind") not in ("click", "key") or not start <= event["time"] < end:
                continue
            local = (event["time"] - start) / speed
            if local >= scene["duration"]:
                continue
            scheduled.append(
                {
                    "kind": event["kind"],
                    "time": scene.get("timeline_start", 0) + local,
                    "pan": float(np.clip(event.get("x", 960) / viewport["width"] - 0.5, -0.5, 0.5)),
                }
            )
    return scheduled


def interaction_audio(path: Path, duration: float, scenes):
    track = np.zeros((math.ceil(duration * RATE), 2))
    schedule = interaction_schedule(scenes)
    for i, event in enumerate(schedule):
        click = event["kind"] == "click"
        t = np.arange(round(RATE * (0.065 if click else 0.036))) / RATE
        noise = np.random.default_rng(300 + i).standard_normal(len(t))
        body = np.sin(2 * np.pi * (780 if click else 1250 + i % 4 * 130) * t)
        sound = (0.12 * body + 0.035 * noise) * np.exp(-t * (100 if click else 170))
        sound *= np.minimum(t * 2200, 1)
        sound *= 3 if click else 2
        place(track, sound, event["time"], event["pan"])
    # Graphic accents share the animation clock; recorded clicks are never snapped to a beat.
    for i, event in enumerate(motion_schedule(scenes)):
        t = np.arange(round(RATE * (0.22 if event["kind"] == "whoosh" else 0.12))) / RATE
        if event["kind"] == "whoosh":
            noise = np.random.default_rng(900 + i).standard_normal(len(t))
            sound = (
                np.convolve(noise, np.ones(9) / 9, mode="same")
                * np.sin(np.pi * t / 0.22) ** 2
                * 0.11
            )
        else:
            frequency = 70 if event["kind"] == "thump" else 1600
            sound = (
                0.14 * np.sin(2 * np.pi * frequency * t) * np.exp(-t * 40) * np.minimum(t * 1200, 1)
            )
        place(track, sound, event["time"])
        schedule.append(event)
    write_audio(path, track)
    return schedule


def launch_music(path: Path, duration: float, bpm: int = 150, *, ambient: bool = False):
    """A deterministic stereo pluck/bass score on the film's beat clock."""
    track = np.zeros((math.ceil(duration * RATE), 2))
    chords = [(57, 60, 64, 67), (53, 57, 60, 64), (60, 64, 67, 71), (55, 59, 62, 67)]

    def hz(note):
        return 440 * 2 ** ((note - 69) / 12)

    beat = 60 / bpm
    for step in range(math.ceil(duration / beat)):
        at = step * beat
        chord = chords[(step // 8) % 4]
        # Leave room for clicks and typing: the melody breathes rather than playing every beat.
        if step % 8 in (0, 2, 3, 6):
            t = np.arange(round(RATE * 1.15)) / RATE
            frequency = hz(chord[(step // 2) % 4] + 12)
            bell = sum(
                np.sin(2 * np.pi * frequency * harmonic * t) * np.exp(-t * decay) * gain
                for harmonic, decay, gain in ((1, 5, 0.10), (2, 9, 0.025), (3, 16, 0.012))
            )
            bell *= np.minimum(t * 400, 1)
            pan = -0.35 if step % 4 < 2 else 0.35
            place(track, bell, at, pan)
            place(track, bell * 0.18, at + beat * 0.75, -pan)
        if step % 4 == 0:
            t = np.arange(round(RATE * 0.7)) / RATE
            bass = (
                0.13
                * np.sin(2 * np.pi * hz(chord[0] - 12) * t)
                * np.exp(-t * 5)
                * np.minimum(t * 100, 1)
            )
            place(track, bass, at)
        if not ambient and at >= beat * 6 and at < duration - beat * 4:
            t = np.arange(round(RATE * 0.16)) / RATE
            noise = np.random.default_rng(step + 400).standard_normal(len(t))
            if step % 2 == 0:
                kick = (
                    0.14
                    * np.sin(2 * np.pi * (48 * t + 2 * (1 - np.exp(-t * 40))))
                    * np.exp(-t * 28)
                )
                place(track, kick, at)
            hat = (noise - np.roll(noise, 1)) * 0.009 * np.exp(-t * 105)
            place(track, hat, at + (0.025 if step % 2 else 0), 0.3)
            if step % 4 == 2:
                clap = np.convolve(noise, np.ones(3) / 3, mode="same") * 0.06 * np.exp(-t * 55)
                place(track, clap, at, -0.1)
    t = np.arange(len(track)) / RATE
    fade = np.minimum(t / 0.04, 1) * np.clip((duration - t) / 0.7, 0, 1)
    track *= fade[:, None]
    write_audio(path, track)


def motion_schedule(scenes):
    return [
        {
            "kind": hit["kind"],
            "time": scene.get("timeline_start", 0) + hit["beat"] * 60 / direction["bpm"],
            "pan": 0,
        }
        for scene in scenes
        if (direction := scene.get("direction"))
        for hit in direction["hits"]
    ]


def beat_map(scenes, duration):
    bpm = next((s["direction"]["bpm"] for s in scenes if s.get("direction")), 150)
    beats = [round(i * 60 / bpm, 6) for i in range(math.ceil(duration * bpm / 60))]
    return {
        "bpm": bpm,
        "fps": 30,
        "beats": beats,
        "downbeats": beats[::4],
        "hits": motion_schedule(scenes),
        "interactions": interaction_schedule(scenes),
    }
