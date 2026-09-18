"""Resolve a half-time estimate using repeated bass/backbeat alternation.

Onset density alone cannot distinguish quarter notes from hi-hat subdivisions.
Compare the *timbre* of alternating attacks at the detected and doubled pulse;
keep the model's estimate when the recording does not resolve that ambiguity.
"""
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import stft

from .timing import bars_from_sections


def _accent_features(audio: sf.SoundFile, start: float, end: float) -> tuple[np.ndarray, np.ndarray]:
    rate = audio.samplerate
    first = max(0, int(start * rate))
    audio.seek(first)
    samples = audio.read(max(0, int(end * rate) - first), always_2d=True, dtype="float32")
    size = 2 ** int(np.ceil(np.log2(rate * .04)))
    hop = max(1, round(rate * .005))
    if len(samples) < size:
        return np.empty(0), np.empty((3, 0))
    frequencies, times, spectrum = stft(samples.T, fs=rate, nperseg=size, noverlap=size - hop)
    # Channel magnitudes avoid cancellation of opposite-phase stereo signals.
    magnitude = np.mean(abs(spectrum), axis=0)
    features = []
    # Bass attack, drum body, and mid-band attack. Exclude cymbal-dominated
    # treble: a busy hi-hat alone is not evidence for doubling the musical beat.
    for low, high in ((35, 130), (130, 400), (400, 2000)):
        energy = np.sqrt(np.sum(magnitude[(frequencies >= low) & (frequencies < high)] ** 2, axis=0))
        features.append(np.maximum(0, energy - np.r_[energy[:2], energy[:-2]]))
    return times + first / rate, np.asarray(features)


def _alternation(accents: np.ndarray) -> tuple[float, int]:
    difference = np.mean(accents[::2], axis=0) - np.mean(accents[1::2], axis=0)
    # Pool the body bands so a drum's tuning does not have to place its
    # resonance on a particular side of the band boundary. Simultaneous
    # broadband accents, or hats between identical kicks, are not a backbeat.
    body_difference = float(np.mean(difference[1:]))
    scores = [min(difference[0], -body_difference),
              min(-difference[0], body_difference)]
    parity = int(np.argmax(scores))
    return float(scores[parity]), parity


def resolve_tempo_octave(data: dict, audio_path: Path) -> dict:
    """Promote only when several independent passages support the faster beat."""
    beats = np.asarray(data.get("beats") or [], dtype=float)
    downbeats = np.asarray(data.get("downbeats") or [], dtype=float)
    bpm = float(data.get("bpm") or 0)
    if bpm <= 0 or len(beats) < 65 or not len(downbeats) or np.any(np.diff(beats) <= 0):
        return data
    # A BPM change must describe the existing pulse, not repair a mismatched
    # numeric label; timing repair is a separate, earlier step in the pipeline.
    if abs(np.median(np.diff(beats)) * bpm / 60 - 1) > .1:
        return data
    bar_positions = np.argmin(abs(downbeats[:, None] - beats[None, :]), axis=1)
    if np.any(np.diff(bar_positions) != 4):
        return data
    votes = []
    eligible = 0
    with sf.SoundFile(audio_path) as audio:
        # Each vote covers four detected bars; process bounded windows instead
        # of retaining a full-song multichannel spectrogram in memory.
        for index in range(0, len(beats) - 16, 16):
            window = beats[index:index + 17]
            period = float(np.median(np.diff(window)))
            if np.max(abs(np.diff(window) / period - 1)) > .12:
                continue
            eligible += 1
            fast = np.sort(np.r_[window[:-1], (window[:-1] + window[1:]) / 2])
            times, features = _accent_features(audio, window[0] - period, window[-1] + period)
            if not len(times):
                continue
            accents = []
            for beat in fast:
                nearby = (times >= beat - .035 * period) & (times <= beat + .05 * period)
                accents.append(features[:, nearby].max(axis=1) if nearby.any() else np.zeros(3))
            accents = np.asarray(accents)
            scale = np.percentile(accents, 90, axis=0)
            if np.min(scale) < 1e-7:
                continue
            # Both hypotheses use the SAME normalization; normalizing each
            # separately would amplify tiny leakage at unsupported beat times.
            accents = np.minimum(accents / scale, 2)
            slow, _ = _alternation(accents[::2])
            double, parity = _alternation(accents)
            if double > .15 and double - slow > .1:
                votes.append((index, 2, parity))
            elif slow > .15 and slow - double > .1:
                votes.append((index, 1, parity))
    faster = [vote for vote in votes if vote[1] == 2]
    # Demand repeated, distributed evidence, and a strong majority among
    # decisive passages. Fills and breakdowns may be ambiguous, but one riff
    # must not set the tempo of an otherwise unresolved recording.
    # Real songs can keep the same quarter-note tempo while several breakdowns
    # use a half-time backbeat. A two-thirds majority still requires broad,
    # repeated evidence while allowing those slower-feel passages to coexist.
    if (len(faster) < 4 or len(faster) < eligible / 3 or len(faster) < (2 / 3) * len(votes)
            or faster[-1][0] - faster[0][0] < len(beats) / 2):
        return data
    parity_counts = np.bincount([vote[2] for vote in faster], minlength=2)
    kick_parity = int(np.argmax(parity_counts))
    if parity_counts[kick_parity] < .8 * len(faster):
        return data
    expanded = np.sort(np.r_[beats, (beats[:-1] + beats[1:]) / 2])
    first_bar = int(np.argmin(abs(expanded - downbeats[0])))
    # Retain the detector's bar anchor; if it followed the snare, use the
    # preceding bass-beat position supported by the consistent accent phase.
    if first_bar % 2 != kick_parity:
        first_bar -= 1
    first_bar = max(first_bar, kick_parity)
    new_beats = np.round(expanded, 3).tolist()
    new_downbeats = new_beats[first_bar::4]
    adjusted = {**data, "bpm": round(bpm * 2, 1), "beats": new_beats,
                "downbeats": new_downbeats, "total_bars": len(new_downbeats)}
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], new_downbeats)
    adjusted["tempoOctaveResolution"] = {
        "version": 2, "factor": 2, "fromBpm": bpm, "toBpm": adjusted["bpm"],
        "eligibleWindows": eligible, "fasterVotes": len(faster),
        "originalVotes": len(votes) - len(faster), "kickParity": kick_parity,
    }
    return adjusted
