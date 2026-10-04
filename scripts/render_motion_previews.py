"""Render two comparable short treatments through the same engine used by UI and MCP jobs."""

import json
import shutil
from pathlib import Path

from server.video_render import render


def main():
    root = Path(".cutroom/verification/motion-v2")
    source = root / "source"
    captured = json.loads((source / "scenes.json").read_text())[0]
    voice = Path(".cutroom/verification/cutroom-launch/voice-6.mp3")
    if not voice.exists():
        from server.video_providers import speech

        voice = source / "voice.mp3"
        speech(captured["narration"], "coral", voice)
    for preset, theme in (("reveal", "paper"), ("panels", "midnight")):
        folder = root / preset
        folder.mkdir(parents=True, exist_ok=True)
        for name in captured["details"]:
            shutil.copyfile(source / name, folder / name)
        scenes = [
            {
                "kind": "title",
                "layout": "hook",
                "headline": "From build to launch.",
                "subtitle": "CUTROOM",
                "duration": 3.2,
                "motion": preset,
                "narration": "",
            },
            dict(captured),
            {
                "kind": "title",
                "layout": "outro",
                "headline": "Make your next launch move.",
                "subtitle": "Cutroom · Your agent’s video studio",
                "duration": 1.6,
                "motion": "resolve",
                "narration": "",
            },
        ]
        result = render(
            folder,
            source / "raw.webm",
            scenes,
            "Cutroom",
            theme,
            "momentum",
            [None, voice, None],
            lambda i, n, name=preset: print(f"{name}: {i}/{n}", flush=True) if i else None,
        )
        (folder / "export.json").write_text(json.dumps(result, indent=2))
        print(preset, result, flush=True)


if __name__ == "__main__":
    main()
