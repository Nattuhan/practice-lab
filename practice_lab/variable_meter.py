"""Track bar position on the measured pulse, allowing meter changes at bar heads.

The upstream decoder chooses one 3- or 4-beat HMM for the entire recording.
Decode the model's beat-synchronous head evidence jointly instead: tempo is
already represented by beat timestamps and must not be refitted here.
"""
from math import log
from pathlib import Path

import numpy as np

from .constant_meter import _pulse_evidence
from .timing import bars_from_sections


def _bar_texture(audio, beats: np.ndarray) -> np.ndarray:
    """Compare timbre at beat subdivisions, including unaccented bar heads."""
    from scipy.signal import stft
    rate = audio.samplerate
    first = max(0, int(beats[0] * rate))
    audio.seek(first)
    samples = audio.read(max(0, int(beats[-1] * rate) - first), always_2d=True, dtype='float32')
    size = 2 ** int(np.ceil(np.log2(rate * .04)))
    if len(samples) < size:
        return np.empty((0, 0))
    frequencies, times, spectrum = stft(samples.T, fs=rate, nperseg=size, noverlap=size - max(1, round(rate * .01)))
    magnitude = np.mean(abs(spectrum), axis=0)
    times += first / rate
    edges = np.geomspace(80, min(8000, rate / 2), 21)
    bands = [np.log1p(100 * magnitude[(frequencies >= low) & (frequencies < high)].mean(axis=0))
             for low, high in zip(edges[:-1], edges[1:]) if np.any((frequencies >= low) & (frequencies < high))]
    if not bands:
        return np.empty((0, 0))
    bands = np.asarray(bands)
    texture = []
    for start, end in zip(beats[:-1], beats[1:]):
        cells = []
        for left, right in zip(np.linspace(start, end, 5)[:-1], np.linspace(start, end, 5)[1:]):
            frames = (times >= left) & (times < right)
            cells.append(bands[:, frames].mean(axis=1) if frames.any() else bands[:, np.argmin(abs(times - (left + right) / 2))])
        texture.append(np.concatenate(cells))
    texture = np.asarray(texture)
    # Normalize timbre bands together over this local window. Stereo magnitude
    # avoids cancellation; four within-beat cells retain syncopated riff shape.
    return (texture - texture.mean(axis=0)) / np.maximum(texture.std(axis=0), .01)


def _refine_changes(beats, selected, head, audio_path):
    """Refine established meter changes using the audio's bar recurrence.

    Missing head attacks can delay the model's switch by whole common cycles.
    Only compare phase-compatible boundaries near an already proven change;
    this does not invent a new meter from a loud fill or a section marker.
    """
    if audio_path is None:
        return selected, []
    import soundfile as sf
    original = selected.copy()
    intervals = np.diff(original)
    changes = np.flatnonzero(intervals[1:] != intervals[:-1]) + 1
    adjustments = []
    with sf.SoundFile(audio_path) as audio:
        for position in changes:
            before, after = int(intervals[position - 1]), int(intervals[position])
            left_position, right_position = max(0, position - 12), min(len(original) - 1, position + 12)
            if (np.any(intervals[left_position:position] != before)
                    or np.any(intervals[position:right_position] != after)):
                continue
            left, boundary, right = original[[left_position, position, right_position]]
            candidates = [i for i in range(left + 4 * before, right - 4 * after + 1)
                          if (i - boundary) % before == 0 and (i - boundary) % after == 0 and head[i] >= .5]
            if boundary not in candidates or len(candidates) < 2:
                continue
            texture = _bar_texture(audio, beats[left:right + 1])
            if len(texture) < 8 or np.max(abs(texture)) < 1e-6:
                continue
            errors = {meter: np.r_[np.zeros(meter), np.mean((texture[meter:] - texture[:-meter]) ** 2, axis=1)]
                      for meter in (before, after)}
            def cost(index):
                k = index - left
                return float(errors[before][before:k].sum() + errors[after][k + after:].sum())
            best = min(candidates, key=cost)
            # Each beat's correlated spectral bands count as one observation.
            # Estimate residual variance locally, rather than tuning a gain to
            # a song. Require 4:1 Gaussian evidence over the current boundary.
            k = best - left
            residual = np.r_[errors[before][before:k], errors[after][k + after:]]
            variance = max(float(residual.mean()), 1e-6)
            gain = (cost(boundary) - cost(best)) / (2 * variance)
            margin = max(before, after)
            before_gain = float((errors[after][margin:k] - errors[before][margin:k]).sum()) / (2 * variance)
            after_gain = float((errors[before][k + margin:] - errors[after][k + margin:]).sum()) / (2 * variance)
            # A timbre/volume change alone is not a meter change: both sides
            # must favor their respective bar recurrence over the alternative.
            if best == boundary or min(gain, before_gain, after_gain) <= log(4):
                continue
            replacement = np.r_[np.arange(left, best, before), np.arange(best, right, after)]
            selected = np.unique(np.r_[selected[selected < left], replacement, selected[selected >= right]])
            adjustments.append({'from': float(beats[boundary]), 'to': float(beats[best]),
                                'evidenceGain': round(gain, 3)})
    return selected, adjustments


def resolve_variable_meter(data: dict, activations: dict | None, fps: float = 100,
                           audio_path: Path | None = None) -> dict:
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
    selected, boundaries = _refine_changes(beats, selected, head, audio_path)
    new_heads = beats[selected].tolist()
    adjusted = {**data, "downbeats": new_heads, "total_bars": len(new_heads),
                "variableMeter": {"version": 2, "evidenceGain": round(gain, 3),
                                  "meters": np.diff(selected).tolist()}}
    if boundaries:
        adjusted['variableMeter']['boundaries'] = boundaries
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], new_heads)
    return adjusted
