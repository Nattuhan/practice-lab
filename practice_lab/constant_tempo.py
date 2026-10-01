"""A user-selected constant pulse, independent of the number of beats per bar."""
from math import ceil, floor

import numpy as np

from .timing import bars_from_sections
from .constant_meter import decode_bar_heads, restore_recounted_bar_heads


def enforce_constant_tempo(data: dict, *, detected_downbeats: list[float] | None = None,
                           activations: dict | None = None, activation_fps: float = 100) -> dict:
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
    meter_data, restored_anchors = restore_recounted_bar_heads(
        grid, data, detected_downbeats or [], activations, activation_fps)

    # Keep source-backed timing repairs: they can recover entire missing bars,
    # not just beats. But a four-beat subdivision of a five-pulse span must not
    # manufacture a one-pulse final bar. Discard only such INTERIOR added heads;
    # measured short bars, recovered pickups, and resolved octaves survive.
    measured_heads = sorted(set(meter_data.get("downbeats") or []))
    discarded = 0
    if detected_downbeats and not data.get("tempoOctaveResolution"):
        source_positions = set(np.rint((np.asarray(detected_downbeats) - phase) / period).astype(int))
        positions = np.rint((np.asarray(measured_heads) - phase) / period).astype(int)
        eligible = []
        for index, (head, position) in enumerate(zip(measured_heads, positions)):
            interior = 0 < index < len(positions) - 1
            added = position not in source_positions
            tiny_bar = interior and min(position - positions[index - 1], positions[index + 1] - position) <= 1
            if interior and added and tiny_bar and min(detected_downbeats) < head < max(detected_downbeats):
                discarded += 1
            else:
                eligible.append(head)
        measured_heads = eligible
    heads, meter_diagnostics = decode_bar_heads(grid, measured_heads, activations, activation_fps)
    meter_diagnostics["discardedRepairHeads"] = discarded
    meter_diagnostics["restoredRepairAnchors"] = restored_anchors
    adjusted = {**meter_data, "bpm": round(60 / period, 1), "beats": grid.tolist(),
                "downbeats": heads, "total_bars": len(heads), "tempoMode": "constant",
                "constantTempo": {"version": 3, "period": float(period), "phase": float(phase),
                                  "supportedBeats": int(np.count_nonzero(consistent)),
                                  "detectedBeats": len(beats)}, "constantMeter": meter_diagnostics}
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], heads)
    return adjusted
