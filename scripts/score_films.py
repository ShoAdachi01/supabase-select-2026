"""Frames-only critic calibration: score finished films repeatedly and report the spread.

A measurement, not a test: it always exits 0. Uses the configured reasoning provider (API credits).
"""

import argparse
import json
import statistics
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

from server.video_direction import CRITIC, chunked_sheets, usage_record
from server.video_direction_models import AXES, FilmReview
from server.video_providers import reason

CRITIC_FRAMES_ONLY = (
    CRITIC.removesuffix("Return JSON matching this schema: ")
    + "No plan or capture metadata is available; judge only visible frames; "
    + "leave blocking empty unless clearly visible.\n"
    + "Return JSON matching this schema: "
)
MAX_SECONDS = 60
FRAMES_PER_SHEET = 4
TILE = (784, 441)  # 2x2 tiles: 1568 px wide, the image long-edge cap


def film_sheets(film: Path, index: int, work: Path) -> list[str]:
    """Sample fps=2 at 960x540 and tile 4 per sheet.

    Frames are named preview-{film}-{frame}.jpg so the contact_sheet allow-list accepts them.
    """
    work.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-y",
            "-t",
            str(MAX_SECONDS),
            "-i",
            str(film),
            "-vf",
            "fps=2,scale=960:540:force_original_aspect_ratio=decrease",
            str(work / f"preview-{index}-%d.jpg"),
        ],
        capture_output=True,
        timeout=300,
    )
    frames = sorted(
        work.glob(f"preview-{index}-*.jpg"), key=lambda p: int(p.stem.rsplit("-", 1)[1])
    )
    if completed.returncode or not frames:
        raise ValueError(f"Could not sample frames from {film}.")
    items = [(p.name, f"{n / 2:.1f}s") for n, p in enumerate(frames)]
    return chunked_sheets(work, items, f"review-{index}", FRAMES_PER_SHEET, tile=TILE, columns=2)


def score_run(prompt: str, sheets: list[str], provider: str, model: str) -> dict:
    telemetry: dict = {}
    record: dict = {"scores": None, "usage": None, "error": None}
    try:
        raw = reason(
            prompt,
            sheets,
            motion=True,
            provider=provider,
            model=model,
            max_tokens=12000,
            telemetry=telemetry,
        )
        record["scores"] = FilmReview.model_validate(raw).scores()
    except Exception as error:  # invalid output or provider failure must not end the measurement
        record["error"] = f"{type(error).__name__}: {str(error)[:300]}"
    record["usage"] = usage_record(telemetry)
    return record


def summarize(runs: list[dict]) -> dict:
    valid = [r["scores"] for r in runs if r["scores"]]
    summary = {}
    for axis in AXES:
        values = [s[axis] for s in valid]
        summary[axis] = {
            "mean": statistics.mean(values) if values else None,
            "stdev": (statistics.stdev(values) if len(values) > 1 else 0.0) if values else None,
        }
    return {"valid_runs": len(valid), "summary": summary, "runs": runs}


def cell(stats: dict) -> str:
    if stats["mean"] is None:
        return "n/a"
    return f"{stats['mean']:.2f} ± {stats['stdev']:.2f}"


def print_table(results: dict) -> None:
    header = ["film", *AXES, "valid runs"]
    rows = [header]
    for film, result in results.items():
        if "error" in result:
            rows.append([film, *(["n/a"] * len(AXES)), f"0/0 ({result['error']})"])
            continue
        rows.append(
            [
                Path(film).parent.name + "/" + Path(film).name,
                *(cell(result["summary"][a]) for a in AXES),
                f"{result['valid_runs']}/{len(result['runs'])}",
            ]
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    for row in rows:
        print("  ".join(value.ljust(widths[i]) for i, value in enumerate(row)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--films", nargs="+", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--out", type=Path, default=Path(".cutroom/verification/critic-calibration")
    )
    parser.add_argument("--provider", default="claude")
    parser.add_argument("--model", default="claude-opus-5-5")
    args = parser.parse_args()
    prompt = CRITIC_FRAMES_ONLY + json.dumps(FilmReview.model_json_schema())
    args.out.mkdir(parents=True, exist_ok=True)
    results = {}
    with tempfile.TemporaryDirectory() as scratch:
        for index, film in enumerate(args.films):
            try:
                sheets = film_sheets(film, index, Path(scratch) / f"film-{index}")
            except Exception as error:  # one unreadable film must not discard the others
                message = f"{type(error).__name__}: {str(error)[:300]}"
                results[str(film)] = {"error": message, "valid_runs": 0, "runs": []}
            else:
                runs = [
                    score_run(prompt, sheets, args.provider, args.model) for _ in range(args.runs)
                ]
                results[str(film)] = summarize(runs)
            # Written after every film so a crash keeps the results already paid for.
            (args.out / "scores.json").write_text(json.dumps(results, indent=2))
    print_table(results)


if __name__ == "__main__":
    main()
