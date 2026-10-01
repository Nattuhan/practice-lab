"""Decode bar boundaries on a fixed pulse, separately from tempo tracking.

The upstream tracker fits one meter to the whole recording. Its continuous
bar-head estimates still contain useful phrase information, even where it
squeezes a short bar into four detections. Align those estimates jointly;
neither a loud fill nor an unplayed downbeat should reset the musical pulse.
"""
from math import log

import numpy as np


def decode_bar_heads(beats: np.ndarray, detected_heads: list[float],
                     activations: dict | None = None, fps: float = 100) -> tuple[list[float], dict]:
    period = float(np.median(np.diff(beats)))
    positions = (np.asarray(detected_heads, dtype=float) - beats[0]) / period
    positions = np.unique(positions[np.isfinite(positions)])
    positions = positions[(positions >= -.5) & (positions <= len(beats) - .5)]
    if not len(positions):
        return [], {"version": 1, "detectedBars": 0, "alignedBars": 0, "changedHeads": 0, "meters": []}

    evidence = np.zeros(len(beats))
    pulse_evidence = np.zeros(len(beats))
    if activations is not None:
        beat_probability = np.asarray(activations["beat"], dtype=float)
        head_probability = np.asarray(activations["downbeat"], dtype=float)
        if (fps <= 0 or beat_probability.ndim != 1 or head_probability.shape != beat_probability.shape
                or not np.all(np.isfinite(beat_probability)) or not np.all(np.isfinite(head_probability))):
            raise ValueError("小節頭の推論確率が不正です")
        # Use the same small neighborhood at every pulse. Conditional head
        # evidence separates a backbeat from a downbeat, but is bounded: a rest
        # is not negative infinity and a loud last beat cannot win on its own.
        radius = max(1, round(min(.05, .1 * period) * fps))
        for index, time in enumerate(beats):
            frame = round(float(time) * fps)
            left, right = max(0, frame - radius), min(len(beat_probability), frame + radius + 1)
            if right > left:
                pulse = float(beat_probability[left:right].max())
                head = float(head_probability[left:right].max())
                pulse_evidence[index] = np.clip(pulse, 0, 1)
                evidence[index] = np.clip(head / max(pulse, .05), 0, 1)

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
    return beats[selected].tolist(), {
        "version": 1, "detectedBars": len(positions), "alignedBars": len(selected),
        "changedHeads": int(np.count_nonzero(selected != np.rint(positions).astype(int))),
        "meters": np.diff(selected).tolist(),
    }
