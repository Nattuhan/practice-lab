"""Decode bar boundaries on a fixed pulse, separately from tempo tracking.

The upstream tracker fits one meter to the whole recording. Its continuous
bar-head estimates still contain useful phrase information, even where it
squeezes a short bar into four detections. Align those estimates jointly;
neither a loud fill nor an unplayed downbeat should reset the musical pulse.
"""
from math import log

import numpy as np


def _pulse_evidence(beats: np.ndarray, activations: dict | None, fps: float) -> tuple[np.ndarray, np.ndarray]:
    period = float(np.median(np.diff(beats)))
    evidence = np.zeros(len(beats))
    pulse_evidence = np.zeros(len(beats))
    if activations is not None:
        beat_probability = np.asarray(activations["beat"], dtype=float)
        head_probability = np.asarray(activations["downbeat"], dtype=float)
        if (fps <= 0 or beat_probability.ndim != 1 or head_probability.shape != beat_probability.shape
                or not np.all(np.isfinite(beat_probability)) or not np.all(np.isfinite(head_probability))):
            raise ValueError("小節頭の推論確率が不正です")
        radius = max(1, round(min(.05, .1 * period) * fps))
        for index, time in enumerate(beats):
            frame = round(float(time) * fps)
            left, right = max(0, frame - radius), min(len(beat_probability), frame + radius + 1)
            if right > left:
                pulse = float(beat_probability[left:right].max())
                head = float(head_probability[left:right].max())
                pulse_evidence[index] = np.clip(pulse, 0, 1)
                evidence[index] = np.clip(head / max(pulse, .05), 0, 1)
    return pulse_evidence, evidence


def restore_recounted_bar_heads(beats: np.ndarray, data: dict, detected_heads: list[float],
                               activations: dict | None, fps: float) -> tuple[dict, list[float]]:
    """Recheck bar phase after an audio repair has recounted the whole track.

    Six real pulses compressed into four detections can be a four-beat bar
    followed by a short bar. Repairing that pulse must not erase the measured
    right-hand head and move every later bar by two beats. But actual missed
    beats do require recounting: compare the two bar phases with this run's
    model probabilities instead of always trusting either interpretation.
    """
    repair = data.get("audioTimingRepair") or {}
    if not activations or not detected_heads or data.get("tempoOctaveResolution"):
        return data, []
    spans = repair.get("spans") or []
    if not any(span.get("rebuild_downbeats") for span in spans):
        return data, []
    period = float(np.median(np.diff(beats)))
    pulse, evidence = _pulse_evidence(beats, activations, fps)
    original = np.asarray(sorted(set(detected_heads)), dtype=float)
    repaired = np.asarray(data.get("downbeats") or [], dtype=float)
    if not len(repaired):
        return data, []
    original_indexes = np.rint((original - beats[0]) / period).astype(int)
    repaired_indexes = np.rint((repaired - beats[0]) / period).astype(int)
    restored = []
    corrected_spans = []
    for span in spans:
        corrected = dict(span)
        if span.get("rebuild_downbeats"):
            end = float(span["end"])
            anchor = round((end - beats[0]) / period)
            measured = ((original >= end - .12 * period) & (original < end + 32 * period)
                        & (original_indexes >= 0) & (original_indexes < len(beats)))
            indexes = original_indexes[measured]
            times = original[measured]
            indexes = indexes[abs(times - beats[indexes]) < .12 * period][:4]
            if len(indexes) == 4 and indexes[0] == anchor:
                alternatives = repaired_indexes[np.argmin(abs(
                    repaired[:, None] - beats[indexes][None, :]), axis=0)]
                if np.all((alternatives >= 0) & (alternatives < len(beats))):
                    # Conditional head odds, weighted by the weaker pulse,
                    # require four nearby observations and 4:1 total evidence.
                    # A silent/uncertain candidate contributes little. Weak
                    # evidence cannot undo the established missed-beat repair.
                    reliability = np.minimum(pulse[indexes], pulse[alternatives])
                    gain = float(np.sum(reliability * np.log(
                        (evidence[indexes] + .05) / (evidence[alternatives] + .05))))
                    if gain > log(4):
                        corrected["rebuild_downbeats"] = False
                        corrected["preserve_end_downbeat"] = True
                        restored.append(float(beats[anchor]))
        corrected_spans.append(corrected)
    if not restored:
        return data, []

    # Reapply this run's source-supported repairs to its measured heads, not
    # the already recounted heads. This retains recovered whole bars and the
    # intro/outro while restoring the proven short-bar phase.
    from .audio_timing import _apply_verified_grid
    source_heads = sorted(set(original.tolist() + [float(head) for head in repaired
                              if head < original[0] or head > original[-1]]))
    correction = {**repair, "spans": corrected_spans}
    outro = correction.pop("outro", None)
    corrected = _apply_verified_grid({**data, "downbeats": source_heads}, correction)
    if outro:
        # The outro's old offset was inferred AFTER the bad global recount.
        # Continue the restored bar phase instead of reintroducing that offset.
        outro = dict(outro)
        anchor = round((outro["start"] - beats[0]) / period)
        preceding = [head for head in corrected["downbeats"] if head <= outro["start"] + .001]
        if preceding:
            previous = round((preceding[-1] - beats[0]) / period)
            outro["downbeatOffset"] = (anchor - previous) % 4
        corrected = _apply_verified_grid(corrected, {"spans": [], "outro": outro})
        correction["outro"] = outro
    corrected["audioTimingRepair"] = {**correction, "version": 6}
    return corrected, restored


def _recover_alias_heads(beats: np.ndarray, selected: np.ndarray,
                         tracked_beats: np.ndarray | None, pulse: np.ndarray) -> tuple[np.ndarray, list[float]]:
    """Recover bars lost when the tracker temporarily counts half the pulse.

    Fitting the correct constant clock fills missed pulses, but simply keeping
    the tracker's four detections per bar then produces eight spoken counts.
    Require the same surrounding meter, measured half-density tracking, and
    source classifier support for the omitted pulses. A genuinely long bar
    with a full pulse track, or a sparse passage without evidence, survives.
    """
    if tracked_beats is None or len(selected) < 6:
        return selected, []
    lengths = np.diff(selected)
    values, counts = np.unique(lengths, return_counts=True)
    meter = int(values[np.argmax(counts)])
    if meter < 2 or counts.max() <= len(lengths) / 2:
        return selected, []
    doubled = lengths == 2 * meter
    starts = np.flatnonzero(doubled & ~np.r_[False, doubled[:-1]])
    ends = np.flatnonzero(doubled & ~np.r_[doubled[1:], False]) + 1
    period = float(np.median(np.diff(beats)))
    tracked = np.asarray(tracked_beats, dtype=float)
    recovered = []
    for start, end in zip(starts, ends):
        if (start < 2 or end + 2 > len(lengths)
                or np.any(lengths[start - 2:start] != meter)
                or np.any(lengths[end:end + 2] != meter)):
            continue
        left, right = selected[start], selected[end]
        observed = tracked[(tracked >= beats[left] - .25 * period)
                           & (tracked <= beats[right] + .25 * period)]
        if (len(observed) < meter + 1 or observed[0] > beats[left] + period
                or observed[-1] < beats[right] - period):
            continue
        # A half-time tracker can drift in phase through a quiet transition.
        # Throwing away off-grid detections makes that failure invisible. Its
        # middle half of intervals and overall density must both still support
        # half the fitted pulse; a brief sparse patch in a full track cannot.
        lower, upper = np.quantile(np.diff(observed) / period, [.25, .75])
        density = 2 * (len(observed) - 1) / (right - left)
        if lower < 1.75 or upper > 2.25 or abs(density - 1) > .2:
            continue
        # Compare neighboring pulses at the SAME local volume. Pooling the
        # median of quiet subdivisions with unrelated loud tracked pulses
        # rejects real subdivisions when the arrangement changes. Silence is
        # uninformative, and a lone strong pulse cannot establish subdivision.
        pairs = pulse[left:right].reshape(-1, 2)
        stronger, weaker = pairs.max(axis=1), pairs.min(axis=1)
        informative = stronger >= .05
        supported = weaker >= np.maximum(.05, .25 * stronger)
        if (np.count_nonzero(informative) < max(meter, len(pairs) / 2)
                or np.count_nonzero(supported) < np.count_nonzero(informative) / 2):
            continue
        recovered.extend((selected[start:end] + meter).tolist())
    if not recovered:
        return selected, []
    return np.unique(np.r_[selected, recovered]), beats[recovered].tolist()


def decode_bar_heads(beats: np.ndarray, detected_heads: list[float],
                     activations: dict | None = None, fps: float = 100, *,
                     tracked_beats: np.ndarray | None = None) -> tuple[list[float], dict]:
    period = float(np.median(np.diff(beats)))
    positions = (np.asarray(detected_heads, dtype=float) - beats[0]) / period
    positions = np.unique(positions[np.isfinite(positions)])
    positions = positions[(positions >= -.5) & (positions <= len(beats) - .5)]
    if not len(positions):
        return [], {"version": 3, "detectedBars": 0, "alignedBars": 0, "changedHeads": 0,
                    "meters": [], "recoveredHeads": []}

    # Conditional head evidence is bounded: a rest is not negative infinity
    # and a loud last beat cannot win on its own.
    pulse_evidence, evidence = _pulse_evidence(beats, activations, fps)

    # A head has two neighboring pulse candidates. The state also remembers
    # the previous bar length, so isolated ambiguous heads do not create a
    # short/long pair inside a stable meter. Switching meter costs log(4), but
    # is allowed at every bar; no four-beat-only states or song rules exist.
    # A quarter-pulse timing uncertainty makes a whole-beat displacement much
    # more expensive than a meter change. Model evidence contributes at most
    # half a cost unit, preserving silent heads supported by phrase timing.
    layers = []
    for index, position in enumerate(positions):
        candidates = sorted({int(np.floor(position)), int(np.ceil(position))})
        candidates = [candidate for candidate in candidates if 0 <= candidate < len(beats)]
        # The two candidates are alternative BAR positions, not alternative
        # beat clocks. If one falls in a rest, local classification of that
        # unplayed beat is unreliable. Weight their comparison by the weaker
        # pulse evidence so a loud fill cannot outvote a silent boundary.
        reliability = min((pulse_evidence[candidate] for candidate in candidates), default=0)
        current = {}
        for candidate in candidates:
            cost = .5 * ((candidate - position) / .25) ** 2 - .5 * reliability * evidence[candidate]
            if index == 0:
                current[(candidate, 0)] = (cost, None)
                continue
            for (previous, previous_meter), (total, _) in layers[-1].items():
                meter = candidate - previous
                if meter <= 0:
                    continue
                switch = log(4) if previous_meter and previous_meter != meter else 0
                value = total + cost + switch
                state = (candidate, meter)
                if state not in current or value < current[state][0]:
                    current[state] = (value, (previous, previous_meter))
        if not current:
            # Silently collapsing two detections onto one beat hides an
            # unresolved bar topology. Let the job fail visibly instead.
            raise ValueError("一定テンポで小節頭を整列できませんでした。テンポ変化ありで解析してください")
        layers.append(current)

    state = min(layers[-1], key=lambda key: layers[-1][key][0])
    selected = []
    for layer in reversed(layers):
        selected.append(state[0])
        state = layer[state][1]
    selected = np.asarray(selected[::-1], dtype=int)
    changed = int(np.count_nonzero(selected != np.rint(positions).astype(int)))
    selected, recovered = _recover_alias_heads(beats, selected, tracked_beats, pulse_evidence)
    return beats[selected].tolist(), {
        "version": 3, "detectedBars": len(positions), "alignedBars": len(selected),
        "changedHeads": changed, "meters": np.diff(selected).tolist(), "recoveredHeads": recovered,
    }
