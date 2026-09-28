"""Resolve a half-time estimate using repeated bass/backbeat alternation.

Onset density alone cannot distinguish quarter notes from hi-hat subdivisions.
Compare the *timbre* of alternating attacks at the detected and doubled pulse;
keep the model's estimate when the recording does not resolve that ambiguity.
"""
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.ndimage import median_filter
from scipy.signal import resample_poly, stft

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


def _harmonic_subdivision_ratio(audio: sf.SoundFile, beats: np.ndarray) -> float:
    """Compare pitched attacks at detected beats and their intervening pulse.

    A half-time drum groove may lack kick/snare alternation at the faster
    quarter note. Separate sustained harmonic content from drum transients so
    repeated guitar or keyboard attacks can support that pulse independently.
    """
    period = float(np.median(np.diff(beats)))
    rate = audio.samplerate
    first = max(0, int((beats[0] - period) * rate))
    audio.seek(first)
    samples = audio.read(max(0, int((beats[-1] + period) * rate) - first),
                         always_2d=True, dtype="float32")
    if len(samples) < 2048:
        return 0.0
    factor = max(1, round(rate / 11025))
    # Retain a real channel when an opposite-phase stereo mix would cancel.
    mono = samples.mean(axis=1)
    if np.mean(mono ** 2) < .25 * np.mean(samples ** 2):
        mono = samples[:, 0]
    mono = resample_poly(mono, 1, factor)
    sample_rate = rate / factor
    size = min(2048, 2 ** int(np.floor(np.log2(len(mono)))))
    hop = max(1, round(sample_rate * .0116))
    frequencies, times, spectrum = stft(mono, fs=sample_rate, nperseg=size,
                                        noverlap=size - min(hop, size - 1))
    magnitude = abs(spectrum)
    harmonic = median_filter(magnitude, size=(1, 31))
    percussive = median_filter(magnitude, size=(31, 1))
    harmonic_magnitude = magnitude * harmonic ** 2 / (harmonic ** 2 + percussive ** 2 + 1e-12)
    band = harmonic_magnitude[(frequencies >= 130) & (frequencies < min(2500, sample_rate / 2))]
    if not len(band):
        return 0.0
    onset = np.r_[0, np.maximum(0, np.diff(band, axis=1)).sum(axis=0)]
    times += first / rate

    def strengths(positions: np.ndarray) -> np.ndarray:
        values = []
        for position in positions:
            nearby = (times >= position - .025) & (times <= position + .05)
            values.append(float(onset[nearby].max()) if nearby.any() else 0.0)
        return np.asarray(values)

    onbeat = strengths(beats[:-1])
    between = strengths((beats[:-1] + beats[1:]) / 2)
    baseline = float(np.median(onbeat))
    return float(np.median(between) / baseline) if baseline > 1e-7 else 0.0


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
    subdivision_candidates = []
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
            # Require a pitched bass pulse as well as the harmonic evidence
            # checked below; dense hats or guitar eighths alone are ambiguous.
            low_onbeat = float(np.median(accents[::2, 0]))
            if low_onbeat > 1e-7 and np.median(accents[1::2, 0]) >= .65 * low_onbeat:
                subdivision_candidates.append((index, window.copy()))
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
    alternating_support = (len(faster) >= 4 and len(faster) >= eligible / 3
                           and len(faster) >= (2 / 3) * len(votes)
                           and faster[-1][0] - faster[0][0] >= len(beats) / 2)
    kick_parity = None
    if alternating_support:
        parity_counts = np.bincount([vote[2] for vote in faster], minlength=2)
        kick_parity = int(np.argmax(parity_counts))
        alternating_support = parity_counts[kick_parity] >= .8 * len(faster)
        if not alternating_support:
            kick_parity = None
    if not alternating_support:
        # Two-thirds of independent four-bar windows must carry both pitched
        # and bass attacks on the faster grid, with no dominant slow backbeat.
        # This is a musical-pulse choice, not a way to fill missing onsets.
        slow_votes = sum(vote[1] == 1 for vote in votes)
        if (eligible < 4 or bpm * 2 > 240
                or len(subdivision_candidates) < (2 / 3) * eligible
                or slow_votes >= eligible / 2):
            return data
        with sf.SoundFile(audio_path) as audio:
            supported = [index for index, window in subdivision_candidates
                         if _harmonic_subdivision_ratio(audio, window) >= .75]
        if (len(supported) < (2 / 3) * eligible
                or supported[-1] - supported[0] < len(beats) / 2):
            return data
    expanded = np.sort(np.r_[beats, (beats[:-1] + beats[1:]) / 2])
    first_bar = int(np.argmin(abs(expanded - downbeats[0])))
    # Retain the detector's bar anchor; if it followed the snare, use the
    # preceding bass-beat position supported by the consistent accent phase.
    if kick_parity is not None and first_bar % 2 != kick_parity:
        first_bar -= 1
    first_bar = max(first_bar, kick_parity or 0)
    new_beats = np.round(expanded, 3).tolist()
    # A repaired half-time span can contain an odd number of slow beats:
    # after promotion its remainder is a two-beat bar, not a tempo change.
    # Timing repair may have recounted slow bars globally to restore missed
    # beats. Recover its measured right-hand bar anchor at the final meter
    # resolution instead of carrying that recount through every later bar.
    anchors = {first_bar}
    for span in data.get("audioTimingRepair", {}).get("spans", []):
        if not span.get("rebuild_downbeats") or span.get("intervals", 0) % 2 != 1:
            continue
        position = int(np.argmin(abs(expanded - span["end"])))
        if (position > first_bar and (position - first_bar) % 2 == 0
                and abs(expanded[position] - span["end"]) < .01):
            anchors.add(position)
    boundaries = sorted(anchors) + [len(new_beats)]
    new_downbeats = [new_beats[index]
                     for left, right in zip(boundaries[:-1], boundaries[1:])
                     for index in range(left, right, 4)]
    adjusted = {**data, "bpm": round(bpm * 2, 1), "beats": new_beats,
                "downbeats": new_downbeats, "total_bars": len(new_downbeats)}
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], new_downbeats)
    adjusted["tempoOctaveResolution"] = {
        "version": 3 if alternating_support else 4,
        "method": "alternating_backbeat" if alternating_support else "bass_and_harmonic_subdivision",
        "factor": 2, "fromBpm": bpm, "toBpm": adjusted["bpm"],
        "eligibleWindows": eligible, "fasterVotes": len(faster),
        "originalVotes": len(votes) - len(faster), "kickParity": kick_parity,
        "preservedBarAnchors": [new_beats[index] for index in sorted(anchors) if index != first_bar],
    }
    return adjusted
