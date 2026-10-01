"""A user-selected constant pulse, independent of the number of beats per bar."""
from math import ceil, floor

import numpy as np

from .timing import bars_from_sections


def enforce_constant_tempo(data: dict) -> dict:
    beats = np.asarray(data.get("beats") or [], dtype=float)
    bpm = float(data.get("bpm") or 0)
    if bpm <= 0 or len(beats) < 4 or np.any(~np.isfinite(beats)) or np.any(np.diff(beats) <= 0):
        raise ValueError("一定テンポの拍間隔を特定できませんでした。テンポ変化ありで解析してください")

    # The numeric BPM identifies the metrical octave, not a precise clock.
    # Fit an uninterrupted run, then use phase-consistent beats throughout the
    # recording. Local tracking aliases and rests must not change this pulse.
    gaps = np.diff(beats)
    nominal = 60 / bpm
    plausible = gaps[(gaps >= .75 * nominal) & (gaps <= 1.25 * nominal)]
    if not len(plausible):
        raise ValueError("一定テンポの拍間隔を特定できませんでした。テンポ変化ありで解析してください")
    typical = float(np.median(plausible))
    cuts = np.r_[0, np.flatnonzero(abs(gaps / typical - 1) > .08) + 1, len(beats)]
    left, right = max(zip(cuts[:-1], cuts[1:]), key=lambda span: span[1] - span[0])
    if right - left < 4:
        raise ValueError("一定テンポの拍間隔を特定できませんでした。テンポ変化ありで解析してください")
    period, phase = np.polyfit(np.arange(right - left), beats[left:right], 1)
    for _ in range(5):
        indexes = np.rint((beats - phase) / period)
        consistent = abs(beats - (phase + indexes * period)) < .1 * period
        period, phase = np.polyfit(indexes[consistent], beats[consistent], 1)

    # Keep the detected musical extent; declaring a constant tempo does not
    # authorize extending clicks into trailing silence or a free-time ending.
    # A fitted zero can be a tiny negative float. Respect output precision so
    # that rounding noise cannot discard a real beat at the start of the file.
    first = max(ceil((-phase - .0000005) / period), round((beats[0] - phase) / period))
    duration = float(data.get("duration") or beats[-1])
    last = min(floor((duration - phase + .0000005) / period), round((beats[-1] - phase) / period))
    grid = np.round(phase + np.arange(first, last + 1) * period, 6)

    # Bar heads follow the SAME clock. Snap measured heads individually rather
    # than regenerating every fourth beat, so a 3/4 bar remains three beats.
    head_indexes = np.unique(np.rint((np.asarray(data.get("downbeats") or []) - phase) / period).astype(int))
    head_indexes = head_indexes[(head_indexes >= first) & (head_indexes <= last)]
    heads = np.round(phase + head_indexes * period, 6).tolist()
    adjusted = {**data, "bpm": round(60 / period, 1), "beats": grid.tolist(),
                "downbeats": heads, "total_bars": len(heads), "tempoMode": "constant",
                "constantTempo": {"version": 1, "period": float(period), "phase": float(phase),
                                  "supportedBeats": int(np.count_nonzero(consistent)),
                                  "detectedBeats": len(beats)}}
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], heads)
    return adjusted
