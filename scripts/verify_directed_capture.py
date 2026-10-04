"""Check encoded pixels against a real browser click and its generated sound onset."""

import json
import wave
from pathlib import Path

import numpy as np
from PIL import Image

from server.video_capture import encode_directed_capture
from server.video_render import ffmpeg
from server.video_sound import interaction_audio


def main():
    folder = Path(".cutroom/verification/interaction-clock")
    scenes = json.loads((folder / "scenes.json").read_text())
    encode_directed_capture(folder)
    click = scenes[1]["interactions"][0]["time"]
    pixels = []
    for i, offset in enumerate((-0.15, 0.15)):
        still = folder / f"check-{i}.png"
        ffmpeg(
            "-ss", str(click + offset), "-i", str(folder / "raw.webm"), "-frames:v", "1", str(still)
        )
        with Image.open(still) as image:
            pixels.append(image.getpixel((1200, 800)))
    assert pixels[0][0] > pixels[0][1] + 8, "Before click: original red state."
    assert pixels[1][1] > pixels[1][0] + 8, "After click: actual green result."
    assert max(abs(a - b) for a, b in zip(pixels[0], (237, 221, 221), strict=True)) < 5, (
        "Capture preserves color range."
    )
    for scene in scenes:
        scene["duration"] = scene["end"] - scene["start"]
        scene["timeline_start"] = scene["start"]
    audio = folder / "effects.wav"
    interaction_audio(audio, scenes[-1]["end"], scenes)
    with wave.open(str(audio)) as source:
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").reshape(-1, 2)
        at = round(click * source.getframerate())
    assert not samples[at - 100 : at].any()
    assert samples[at : at + 100].any()
    print(
        "PASS: encoded click result within 150 ms, sound onset on the event clock, and correct source colors."
    )


if __name__ == "__main__":
    main()
