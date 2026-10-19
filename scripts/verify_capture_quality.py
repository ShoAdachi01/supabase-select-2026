"""2x capture acceptance: measured frame size, fps, storage. Click timing uses verify_directed_capture."""

import argparse
import json
import sys
from pathlib import Path

# raw.webm stays on the worker (only film.mp4 and storyboard.json are uploaded, 50 MiB bucket limit).
MAX_BYTES = 1200 * 1024 * 1024  # worker-disk budget, matching the screencast byte cap
BUCKET_LIMIT = 50 * 1024 * 1024  # file_size_limit in supabase/config.toml


def file_size(path: Path) -> int:
    return path.stat().st_size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    folder = parser.parse_args().folder
    metrics = json.loads((folder / "capture-metrics.json").read_text())
    checks = {
        "decoded width 3840": metrics["width"] == 3840,
        "fps >= 20": metrics["fps"] >= 20,
        "raw size within worker budget": metrics["bytes"] <= MAX_BYTES,
    }
    film = folder / "film.mp4"
    if film.exists():
        checks["uploaded film within 50 MiB bucket limit"] = file_size(film) <= BUCKET_LIMIT
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}: {name} ({metrics})")
    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
