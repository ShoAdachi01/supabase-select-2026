"""Bounded video-generation adapters. Generated backgrounds never replace app evidence."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from server.video_providers import checked, setting

GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta"


def generation_capabilities() -> dict:
    return {
        "sora": bool(setting("OPENAI_API_KEY")),
        "veo": bool(setting("GEMINI_API_KEY") or setting("GOOGLE_API_KEY")),
    }


def start_generation(provider: str, prompt: str, seconds: int) -> dict:
    direction = (
        "Create an original premium product-launch motion background. "
        "No written text, no logos, no people, no software UI. "
        "Smooth cinematic easing. Leave negative space for independently rendered typography. "
        "No dialogue; generated audio will be discarded. Visual direction: " + prompt
    )
    if provider == "veo":
        key = setting("GEMINI_API_KEY") or setting("GOOGLE_API_KEY")
        if not key:
            raise ValueError("Configure GEMINI_API_KEY for Veo animations.")
        response = httpx.post(
            f"{GOOGLE_BASE}/models/{setting('VEO_MODEL', 'veo-3.1-fast-generate-preview')}:predictLongRunning",
            headers={"x-goog-api-key": key},
            json={
                "instances": [{"prompt": direction}],
                "parameters": {
                    "aspectRatio": "16:9",
                    "durationSeconds": seconds,
                    "resolution": "720p",
                    "sampleCount": 1,
                },
            },
            timeout=90,
        )
        if response.status_code == 429:
            raise ValueError(
                "Veo generation quota is exhausted or unavailable. Check Gemini billing and rate limits; built-in title animations still work."
            )
        checked(response, "Veo")
        name = response.json().get("name", "")
        if not name.startswith("models/") or "/operations/" not in name or ".." in name:
            raise ValueError("Veo returned an invalid operation.")
        return {"provider": provider, "operation": name, "seconds": seconds}
    key = setting("OPENAI_API_KEY")
    if not key:
        raise ValueError("Configure OPENAI_API_KEY for Sora animations.")
    response = checked(
        httpx.post(
            "https://api.openai.com/v1/videos",
            headers={"Authorization": f"Bearer {key}"},
            files={
                name: (None, value)
                for name, value in {
                    "model": setting("SORA_MODEL", "sora-2"),
                    "prompt": direction,
                    "seconds": str(seconds),
                    "size": "1280x720",
                }.items()
            },
            timeout=90,
        ),
        "Sora",
    )
    return {"provider": provider, "operation": response.json()["id"], "seconds": seconds}


def poll_generation(operation: dict) -> tuple[str, str | None]:
    if operation["provider"] == "veo":
        key = setting("GEMINI_API_KEY") or setting("GOOGLE_API_KEY")
        result = checked(
            httpx.get(
                f"{GOOGLE_BASE}/{operation['operation']}",
                headers={"x-goog-api-key": key},
                timeout=60,
            ),
            "Veo",
        ).json()
        if result.get("error"):
            raise ValueError(
                "Veo could not generate this animation. Try a different visual prompt."
            )
        if not result.get("done"):
            return "generating", None
        samples = (
            result.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", [])
        )
        if not samples:
            raise ValueError("Veo returned no usable video. Try a different visual prompt.")
        return "complete", samples[0]["video"]["uri"]
    result = checked(
        httpx.get(
            f"https://api.openai.com/v1/videos/{operation['operation']}",
            headers={"Authorization": f"Bearer {setting('OPENAI_API_KEY')}"},
            timeout=60,
        ),
        "Sora",
    ).json()
    if result["status"] == "failed":
        raise ValueError("Sora could not generate this animation. Try a different visual prompt.")
    return result["status"], None


def download_generation(operation: dict, uri: str | None, path: Path):
    if operation["provider"] == "veo":
        url = urlsplit(uri or "")
        if (
            url.scheme != "https"
            or url.hostname != "generativelanguage.googleapis.com"
            or url.username
            or url.password
        ):
            raise ValueError("Veo returned an invalid download location.")
        headers = {"x-goog-api-key": setting("GEMINI_API_KEY") or setting("GOOGLE_API_KEY")}
        endpoint = uri
    else:
        headers = {"Authorization": f"Bearer {setting('OPENAI_API_KEY')}"}
        endpoint = f"https://api.openai.com/v1/videos/{operation['operation']}/content"
    # Follow only provider-approved redirects without forwarding keys to another host.
    with httpx.Client(timeout=180) as client:
        for _ in range(4):
            with client.stream("GET", endpoint, headers=headers) as response:
                if response.is_redirect:
                    location = response.headers.get("location", "")
                    target = urlsplit(location)
                    if (
                        target.scheme != "https"
                        or not target.hostname
                        or not (
                            target.hostname.endswith(".googleapis.com")
                            or target.hostname.endswith(".googleusercontent.com")
                            or target.hostname.endswith(".openai.com")
                        )
                    ):
                        raise ValueError("The video provider returned an unsupported redirect.")
                    endpoint, headers = location, {}
                    continue
                checked(response, "Video download")
                count = 0
                with path.open("wb") as output:
                    for data in response.iter_bytes():
                        count += len(data)
                        if count > 100 * 1024 * 1024:
                            raise ValueError("Generated clip exceeds 100 MB.")
                        output.write(data)
                return
    raise ValueError("The video download exceeded its redirect limit.")


def generate_file(provider: str, prompt: str, seconds: int, path: Path, checkpoint=lambda: None):
    operation = start_generation(provider, prompt, seconds)
    path.with_suffix(".operation.json").write_text(json.dumps(operation))
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        checkpoint()
        status, uri = poll_generation(operation)
        if status == "complete" or status == "completed":
            download_generation(operation, uri, path)
            return
        time.sleep(5)
    raise ValueError("Video generation timed out. The provider operation is saved for recovery.")
