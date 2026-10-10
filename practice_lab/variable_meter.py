"""Track bar position on the measured pulse, allowing meter changes at bar heads.

The upstream decoder chooses one 3- or 4-beat HMM for the entire recording.
Decode the model's beat-synchronous head evidence jointly instead: tempo is
already represented by beat timestamps and must not be refitted here.
"""
from math import log

import numpy as np

from .constant_meter import _pulse_evidence
from .timing import bars_from_sections


def resolve_variable_meter(data: dict, activations: dict | None, fps: float = 100) -> dict:
    beats = np.asarray(data.get("beats") or [], dtype=float)
    heads = np.asarray(data.get("downbeats") or [], dtype=float)
    if activations is None or len(beats) < 12 or not len(heads) or np.any(np.diff(beats) <= 0):
        return data
    # Map each measured head to its nearest actual beat, not a global BPM clock.
    source = np.unique(np.argmin(abs(beats[:, None] - heads), axis=0))
    meters = sorted({3, 4, *(int(n) for n in np.diff(source) if 2 <= n <= 12)})
    states = [(meter, position) for meter in meters for position in range(meter)]
    pulse, head = _pulse_evidence(beats, activations, fps)
    reliability = pulse / (pulse + .05)
    probability = np.clip(head, .01, .99)
    emissions = np.column_stack((np.log(probability), np.log1p(-probability))) * reliability[:, None]
    # Match the conservative metrical switch prior in madmom's beat-synchronous
    # bar decoder. A change needs repeated model evidence, not one loud accent.
    change_probability = 1e-7
    switch = log(change_probability / (len(meters) - 1))
    stay = log(1 - change_probability)
    scores = np.full(len(states), -log(len(states)))
    parents = []
    for index in range(len(beats)):
        next_scores = np.full(len(states), -np.inf)
        parent = np.zeros(len(states), dtype=int)
        for target, (meter, position) in enumerate(states):
            observation = emissions[index, 0 if position == 0 else 1]
            if index == 0:
                next_scores[target] = scores[target] + observation
                continue
            if position:
                candidates = [(states.index((meter, position - 1)), 0)]
            else:
                candidates = [(states.index((previous, previous - 1)), stay if previous == meter else switch)
                              for previous in meters]
            previous, transition = max(candidates, key=lambda item: scores[item[0]] + item[1])
            next_scores[target] = scores[previous] + transition + observation
            parent[target] = previous
        parents.append(parent)
        scores = next_scores
    state = int(np.argmax(scores))
    selected = []
    for index in range(len(beats) - 1, -1, -1):
        if states[state][1] == 0:
            selected.append(index)
        state = int(parents[index][state])
    selected = np.asarray(selected[::-1], dtype=int)
    old_mask = np.zeros(len(beats), dtype=bool)
    old_mask[source] = True
    old_score = float(np.sum(np.where(old_mask, emissions[:, 0], emissions[:, 1]))) - log(len(states))
    gain = float(scores.max() - old_score)
    # Uninformative/silent passages retain the detected boundaries. Record the
    # evidence only when it overcomes the switch prior and improves the old path.
    if gain <= log(4) or np.array_equal(selected, source):
        return data
    new_heads = beats[selected].tolist()
    adjusted = {**data, "downbeats": new_heads, "total_bars": len(new_heads),
                "variableMeter": {"version": 1, "evidenceGain": round(gain, 3),
                                  "meters": np.diff(selected).tolist()}}
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], new_heads)
    return adjusted
