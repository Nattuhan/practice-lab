"""Check a saved analysis result against an observed timing regression.

This is a development gate, not part of music analysis. Expected values are
supplied by the investigator and never influence the analyzer's output.
"""

import argparse
import json
import math
from pathlib import Path
from statistics import median


def verify_result(
    result_path: Path,
    *,
    bpm: float,
    window: tuple[float, float],
    last_beat_between: tuple[float, float],
    fresh_after: Path | None = None,
    bpm_tolerance: float = 1.0,
    interval_tolerance: float = 0.05,
    minimum_grid_coverage: float = 0.95,
) -> dict:
    if bpm <= 0 or bpm_tolerance < 0 or not 0 < interval_tolerance < 1:
        raise ValueError("BPM and tolerances must be valid positive values")
    if not 0 <= minimum_grid_coverage <= 1:
        raise ValueError("grid coverage must be between 0 and 1")
    start, end = window
    first_allowed, last_allowed = last_beat_between
    if start < 0 or end <= start or first_allowed < 0 or last_allowed < first_allowed:
        raise ValueError("window and last-beat bounds must be ordered")
    if fresh_after and result_path.stat().st_mtime_ns <= fresh_after.stat().st_mtime_ns:
        raise AssertionError("result was not regenerated after the start marker")

    data = json.loads(result_path.read_text(encoding="utf-8"))
    actual_bpm = float(data["bpm"])
    beats = [float(value) for value in data["beats"]]
    if not beats or any(not math.isfinite(beat) for beat in beats):
        raise AssertionError("beat list is empty or contains non-finite values")
    if any(right <= left for left, right in zip(beats, beats[1:])):
        raise AssertionError("beats must be strictly increasing")
    if abs(actual_bpm - bpm) > bpm_tolerance:
        raise AssertionError(f"BPM {actual_bpm:g} is outside {bpm:g} ± {bpm_tolerance:g}")

    # Check every interval in the stable passage. A median alone can hide a
    # half-tempo section occupying a large minority of the selected passage.
    gaps = [right - left for left, right in zip(beats, beats[1:])
            if start <= left and right <= end]
    if len(gaps) < 16:
        raise AssertionError(f"only {len(gaps)} intervals in the selected passage")
    expected_period = 60 / bpm
    coverage = sum(abs(gap - expected_period) <= interval_tolerance * expected_period
                   for gap in gaps) / len(gaps)
    if coverage < minimum_grid_coverage:
        raise AssertionError(
            f"grid coverage {coverage:.1%} is below {minimum_grid_coverage:.1%}"
        )
    if not first_allowed <= beats[-1] <= last_allowed:
        raise AssertionError(
            f"last beat {beats[-1]:.3f}s is outside {first_allowed:g}–{last_allowed:g}s"
        )
    return {"bpm": actual_bpm, "intervals": len(gaps),
            "medianInterval": round(median(gaps), 4),
            "gridCoverage": round(coverage, 4), "lastBeat": beats[-1]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mark-start", type=Path,
                        help="write a marker immediately before starting app reanalysis")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--fresh-after", type=Path,
                        help="require result modification after this marker; also confirm the app job completed")
    parser.add_argument("--bpm", type=float)
    parser.add_argument("--window", nargs=2, type=float, metavar=("START", "END"))
    parser.add_argument("--last-beat-between", nargs=2, type=float,
                        metavar=("EARLIEST", "LATEST"))
    parser.add_argument("--bpm-tolerance", type=float, default=1.0)
    parser.add_argument("--interval-tolerance", type=float, default=0.05)
    parser.add_argument("--minimum-grid-coverage", type=float, default=0.95)
    args = parser.parse_args()
    if args.mark_start:
        if any((args.result, args.fresh_after, args.bpm, args.window, args.last_beat_between)):
            parser.error("--mark-start must be used alone")
        args.mark_start.parent.mkdir(parents=True, exist_ok=True)
        args.mark_start.touch()
        print(f"Analysis start marked: {args.mark_start}")
        return 0
    if not all((args.result, args.fresh_after, args.bpm, args.window,
                args.last_beat_between)):
        parser.error("result verification requires --result, --fresh-after, --bpm, "
                     "--window and --last-beat-between")
    try:
        summary = verify_result(
            args.result, bpm=args.bpm, window=tuple(args.window),
            last_beat_between=tuple(args.last_beat_between),
            fresh_after=args.fresh_after, bpm_tolerance=args.bpm_tolerance,
            interval_tolerance=args.interval_tolerance,
            minimum_grid_coverage=args.minimum_grid_coverage,
        )
    except (AssertionError, KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Timing regression FAILED: {exc}\n")
    print("Timing regression passed: " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
