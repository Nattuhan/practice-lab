"""A user-selected constant pulse, independent of the number of beats per bar."""
from math import ceil, floor
from pathlib import Path

import numpy as np

from .audio_timing import sparse_bass_onset
from .timing import bars_from_sections
from .constant_meter import _pulse_evidence, decode_bar_heads, restore_recounted_bar_heads


class ConstantTempoFitError(ValueError):
    """The detected beats do not define a usable constant grid."""


def fit_constant_grid(data: dict) -> tuple[np.ndarray, dict]:
    """Fit the selected constant clock without decoding or changing its meter."""
    beats = np.asarray(data.get("beats") or [], dtype=float)
    bpm = float(data.get("bpm") or 0)
    if bpm <= 0 or len(beats) < 4 or np.any(~np.isfinite(beats)) or np.any(np.diff(beats) <= 0):
        raise ConstantTempoFitError("一定テンポの拍間隔を特定できませんでした。テンポ変化ありで解析してください")

    # The numeric BPM identifies the metrical octave, not a precise clock.
    # Fit an uninterrupted run, then use phase-consistent beats throughout the
    # recording. Local tracking aliases and rests must not change this pulse.
    gaps = np.diff(beats)
    nominal = 60 / bpm
    plausible = gaps[(gaps >= .75 * nominal) & (gaps <= 1.25 * nominal)]
    if not len(plausible):
        raise ConstantTempoFitError("一定テンポの拍間隔を特定できませんでした。テンポ変化ありで解析してください")
    typical = float(np.median(plausible))
    cuts = np.r_[0, np.flatnonzero(abs(gaps / typical - 1) > .08) + 1, len(beats)]
    left, right = max(zip(cuts[:-1], cuts[1:]), key=lambda span: span[1] - span[0])
    if right - left < 4:
        raise ConstantTempoFitError("一定テンポの拍間隔を特定できませんでした。テンポ変化ありで解析してください")
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
    if len(grid) < 2:
        raise ConstantTempoFitError("曲の範囲に一定テンポの拍を配置できませんでした")
    return grid, {"version": 3, "period": float(period), "phase": float(phase),
                  "supportedBeats": int(np.count_nonzero(consistent)), "detectedBeats": len(beats)}


def constant_tempo_conflict(detected: dict, fixed: dict, activations: dict | None, fps: float) -> dict | None:
    """Require sustained audio evidence against the fitted beat phase."""
    beats = np.asarray(detected["beats"], dtype=float)
    if activations is None or len(beats) < 24:
        return None
    grid = np.asarray(fixed["beats"], dtype=float)
    period = fixed["constantTempo"]["period"]
    indexes = np.clip(np.rint((beats - grid[0]) / period).astype(int), 0, len(grid) - 1)
    tracked_pulse, _ = _pulse_evidence(beats, activations, fps)
    fixed_pulse, _ = _pulse_evidence(grid, activations, fps)
    # A fill, quiet passage, or a displaced model detection alone is weak
    # evidence. Require repeated detections that are substantially off the
    # clock and whose model confidence clearly favors the variable pulse.
    displaced = abs(beats - grid[indexes]) > .2 * period
    conflict = displaced & (tracked_pulse >= .08) & (fixed_pulse[indexes] < 2 / 3 * tracked_pulse)
    votes = np.convolve(conflict, np.ones(12, dtype=int), mode="valid")
    pairs = np.flatnonzero((votes[:-12] >= 4) & (votes[12:] >= 4) & (votes[:-12] + votes[12:] >= 10))
    if not len(pairs):
        return None
    start = int(pairs[0])
    return {"reason": "beat_phase_conflict", "start": float(beats[start]), "end": float(beats[start + 23]),
            "conflictingBeats": int(votes[start] + votes[start + 12])}


def enforce_constant_tempo(data: dict, *, audio_path: Path | None = None,
                           detected_downbeats: list[float] | None = None,
                           activations: dict | None = None, activation_fps: float = 100) -> dict:
    grid, clock = fit_constant_grid(data)
    period, phase = clock["period"], clock["phase"]
    beats = np.asarray(data.get("beats") or [], dtype=float)
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
    heads, meter_diagnostics = decode_bar_heads(grid, measured_heads, activations, activation_fps,
                                              tracked_beats=beats)
    if audio_path is not None:
        # Under the explicit constant-tempo assumption, use the fitted pulse
        # for the missing prefix. Sparse or syncopated notes delimit the
        # audible intro but need not furnish a second independent clock.
        onset = sparse_bass_onset(audio_path, float(grid[0]), period)
        if onset is not None:
            first_index = round((grid[0] - phase) / period)
            start_index = max(ceil((-phase - .0000005) / period), round((onset - phase) / period))
            if start_index < first_index:
                prefix = np.round(phase + np.arange(start_index, first_index) * period, 6)
                grid = np.r_[prefix, grid]
                clock["intro"] = {"audioStart": onset, "insertedBeats": len(prefix)}
                # Use a repeated meter from the following bars. Fill up to
                # the first measured head: the old pickup can span a whole
                # bar, even if the fitted pulse already covers that part.
                meters = meter_diagnostics["meters"][:4]
                values, counts = np.unique(meters, return_counts=True)
                if len(values) and max(counts) >= 3:
                    meter = int(values[np.argmax(counts)])
                    head_index = round((heads[0] - grid[0]) / period)
                    prefix_heads = grid[head_index % meter:head_index:meter].tolist() if meter >= 2 else []
                    heads = prefix_heads + heads
                    meter_diagnostics["alignedBars"] = len(heads)
                    meter_diagnostics["meters"] = np.rint(np.diff(heads) / period).astype(int).tolist()
    meter_diagnostics["discardedRepairHeads"] = discarded
    meter_diagnostics["restoredRepairAnchors"] = restored_anchors
    adjusted = {**meter_data, "bpm": round(60 / period, 1), "beats": grid.tolist(),
                "downbeats": heads, "total_bars": len(heads), "tempoMode": "constant",
                "constantTempo": clock, "constantMeter": meter_diagnostics}
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], heads)
    return adjusted
