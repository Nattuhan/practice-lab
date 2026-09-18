"""Conservative beat repair supported by attacks in the source audio.

Timing alone cannot distinguish syncopation from a real tempo change. Compare
source attacks too; for short ambiguous rhythmic aliases, preserve a strongly
established clock unless the recording decisively supports the changed pulse.
"""
from pathlib import Path
from statistics import median

import numpy as np
import soundfile as sf
from scipy.signal import find_peaks

from .timing import bars_from_sections


def _attacks(audio: sf.SoundFile, start: float, end: float, relative_threshold: float,
             beat_period: float | None = None) -> list[tuple[float, float]]:
    rate = audio.samplerate
    first = max(0, int(start * rate))
    audio.seek(first)
    samples = audio.read(max(0, int(end * rate) - first), always_2d=True, dtype="float32")
    # Scale onset resolution and peak separation with the musical pulse so
    # the same rhythm is evaluated consistently at different playback tempos.
    hop_seconds = beat_period / 64 if beat_period else .005
    separation = beat_period / 3 if beat_period else .1
    hop = max(1, round(rate * hop_seconds))
    count = len(samples) // hop
    if count < 4:
        return []
    # Average channel power, not samples: opposite stereo phases must not cancel.
    power = np.mean(samples[:count * hop].reshape(count, hop, -1) ** 2, axis=(1, 2))
    envelope = np.sqrt(power)
    onset = np.maximum(0, envelope - np.r_[envelope[:2], envelope[:-2]])
    maximum = float(onset.max())
    if maximum <= 1e-7:
        return []
    indexes, properties = find_peaks(onset, distance=max(1, round(separation * rate / hop)),
                                    prominence=maximum * relative_threshold)
    return [(round((first + int(index) * hop) / rate, 3), float(strength))
            for index, strength in zip(indexes, properties["prominences"])]


def _candidate_spans(data: dict) -> list[tuple[float, float, float]]:
    downbeats = data.get("downbeats") or []
    bpm = float(data.get("bpm") or 0)
    if bpm <= 0 or len(downbeats) < 12:
        return []
    bar = 240 / bpm
    gaps = np.diff(downbeats)
    candidates = []
    index = 3
    while index < len(gaps) - 3:
        if not 1.08 * bar <= gaps[index] <= 1.3 * bar:
            index += 1
            continue
        first = index
        while index < len(gaps) and 1.08 * bar <= gaps[index] <= 1.3 * bar:
            index += 1
        if index > len(gaps) - 3 or not 4 <= index - first <= 16:
            continue
        before, after = gaps[first - 3:first], gaps[index:index + 3]
        flank = list(before) + list(after)
        period = median(flank) / 4
        # Both sides must independently agree. A sustained tempo change is not
        # an error, even if its own beat intervals are very regular.
        if any(abs(gap / (4 * period) - 1) > 0.04 for gap in flank):
            continue
        if abs(median(before) / median(after) - 1) > 0.025:
            continue
        candidates.append((float(downbeats[first]), float(downbeats[index]), period))
    return candidates


def _audio_supported_spans(audio: sf.SoundFile, start: float, end: float, period: float) -> list[dict]:
    beat_count = round((end - start) / (4 * period)) * 4
    if not 16 <= beat_count <= 64:
        return []
    fitted_period = (end - start) / beat_count
    if abs(fitted_period / period - 1) > 0.025:
        return []
    attacks = _attacks(audio, start - 0.08, end + 0.08, 0.3)
    if len(attacks) < 6:
        return []
    times = [time for time, _ in attacks]
    positions = [(time - start) / fitted_period for time in times]
    eighths = [round(position * 2) for position in positions]
    # Infer each accent's eighth-note position from the audio; no particular
    # accent sequence or song identity is prescribed. Require both offbeats and
    # independently audible bar heads across the span before filling its grid.
    if (any(abs(position - eighth / 2) > 0.14 for position, eighth in zip(positions, eighths))
            or len(set(eighths)) != len(eighths)
            or sum(eighth % 2 != 0 for eighth in eighths) < 2
            or eighths[0] != 0 or eighths[-1] != beat_count * 2):
        return []
    if max(abs(times[0] - start), abs(times[-1] - end)) > period * 0.1:
        return []
    anchors = [(time, eighth // 2) for time, eighth in zip(times, eighths) if eighth % 8 == 0]
    if len(anchors) < 3:
        return []
    anchors[0], anchors[-1] = (start, 0), (end, beat_count)
    return [{"start": left[0], "end": right[0], "intervals": right[1] - left[1]}
            for left, right in zip(anchors, anchors[1:])]


def _missing_intro(audio: sf.SoundFile, data: dict) -> dict | None:
    beats = data.get("beats") or []
    downbeats = data.get("downbeats") or []
    if len(beats) < 32 or not downbeats:
        return None
    leading = np.asarray(beats[:32], dtype=float)
    period, _ = np.polyfit(np.arange(len(leading)), leading, 1)
    first = float(beats[0])
    if first < 2 * period:
        return None
    if any(abs(gap / period - 1) > 0.1 for gap in np.diff(leading)):
        return None
    first_head_index = int(round((downbeats[0] - first) / period))
    if not 0 <= first_head_index < 4:
        return None
    if any(abs((downbeats[i] - first) / period - (first_head_index + i * 4)) > 0.15
           for i in range(min(8, len(downbeats)))):
        return None

    rate = audio.samplerate
    audio.seek(0)
    samples = audio.read(min(audio.frames, int((first + 16 * period) * rate)),
                         always_2d=True, dtype="float32")
    frame = max(1, round(rate * period / 2))
    frame_count = len(samples) // frame
    if frame_count < 8:
        return None
    rms = np.sqrt(np.mean(samples[:frame_count * frame].reshape(frame_count, frame, -1) ** 2,
                          axis=(1, 2)))
    frame_times = (np.arange(frame_count) + 1) * frame / rate
    after = rms[(frame_times >= first) & (frame_times <= first + 8 * period)]
    if not len(after):
        return None
    threshold = max(1e-4, float(np.percentile(after, 75)) * .03)
    before_mask = frame_times <= first
    before_times, before_active = frame_times[before_mask], rms[before_mask] > threshold
    active_indexes = np.flatnonzero(before_active)
    if not len(active_indexes):
        return None
    # The beat-scaled frames above establish continuity; use finer frames for
    # the actual boundary so a frame beginning in silence does not add a beat.
    edge_frame = max(1, round(rate * min(.02, period / 16)))
    edge_count = min(len(samples), int(first * rate)) // edge_frame
    edge_rms = np.sqrt(np.mean(
        samples[:edge_count * edge_frame].reshape(edge_count, edge_frame, -1) ** 2,
        axis=(1, 2)))
    edge_active = np.flatnonzero(edge_rms > threshold)
    if not len(edge_active):
        return None
    audible_start = float(edge_active[0] * edge_frame / rate)
    attacks = [attack for attack in _attacks(audio, 0, first + period / 2, .035, period)
               if attack[0] >= audible_start - period / 2]
    intervals = int(np.floor((first - audible_start) / period + .5))
    if not 2 <= intervals <= min(32, int(first / period)):
        return None

    active_rms = rms[before_mask][active_indexes[0]:]
    active_fraction = float(np.mean(before_active[active_indexes[0]:]))
    smooth_change = (float(np.median(abs(np.diff(active_rms))))
                     / max(float(np.median(active_rms)), 1e-7))
    sustained_intro = active_fraction >= .8 and smooth_change < .12
    if len(attacks) >= 2 and not sustained_intro:
        times, strengths = np.asarray(attacks).T
        positions = (times - first) / period
        eighth_distance = abs(positions * 2 - np.rint(positions * 2)) / 2
        if (times[-1] - times[0] < period
                or np.average(eighth_distance < .12, weights=strengths) < .6
                or np.average(eighth_distance, weights=strengths) > .12):
            return None
    elif not sustained_intro:
        return None
    return {"start": first, "period": round(float(period), 6),
            "intervals": intervals, "firstDownbeatIndex": first_head_index}


def _missing_outro(audio: sf.SoundFile, data: dict) -> dict | None:
    """Extend a proven constant clock when the detector drops the song ending."""
    beats = np.asarray(data.get("beats") or [], dtype=float)
    downbeats = np.asarray(data.get("downbeats") or [], dtype=float)
    if len(beats) < 64 or len(downbeats) < 16:
        return None
    gaps = np.diff(beats)
    typical = float(np.median(gaps))
    if typical <= 0 or np.any(gaps <= 0):
        return None
    cuts = np.r_[0, np.flatnonzero(abs(gaps / typical - 1) > .1) + 1, len(beats)]
    left, right = max(zip(cuts[:-1], cuts[1:]), key=lambda pair: pair[1] - pair[0])
    if right - left < 32:
        return None
    period, phase = np.polyfit(np.arange(right - left), beats[left:right], 1)
    for _ in range(4):
        indexes = np.rint((beats - phase) / period)
        consistent = abs(beats - (phase + indexes * period)) < .12 * period
        if np.count_nonzero(consistent) < 32:
            return None
        period, phase = np.polyfit(indexes[consistent], beats[consistent], 1)
    if np.mean(consistent) < .8:
        return None

    # If the terminal detections first drift away from the established clock,
    # replace from the last reliable beat. Otherwise extend after the last beat.
    bad = np.flatnonzero(abs(gaps / period - 1) > .1)
    tail_bad = bad[bad >= max(0, len(gaps) - 64)]
    anchor_index = int(tail_bad[0]) if len(tail_bad) else len(beats) - 1
    anchor = float(beats[anchor_index])
    duration = min(float(data.get("duration") or audio.frames / audio.samplerate),
                   audio.frames / audio.samplerate)
    if duration - anchor < 4 * period:
        return None

    # Find the end of the contiguous audible tail. This lets a proven clock
    # continue through held notes and fades, where no new onset exists. Stop at
    # the first sustained silence instead of extending into later video audio.
    rate = audio.samplerate
    first = max(0, int((anchor - 16 * period) * rate))
    audio.seek(first)
    samples = audio.read(max(0, int(duration * rate) - first), always_2d=True,
                         dtype="float32")
    frame = max(1, round(rate * period / 2))
    frame_count = len(samples) // frame
    if frame_count < 8:
        return None
    rms = np.sqrt(np.mean(samples[:frame_count * frame].reshape(frame_count, frame, -1) ** 2,
                          axis=(1, 2)))
    frame_times = first / rate + (np.arange(frame_count) + 1) * frame / rate
    before = rms[frame_times <= anchor]
    if not len(before):
        return None
    threshold = max(1e-4, float(np.percentile(before, 75)) * .03)
    tail_mask = frame_times > anchor
    tail_times, tail_active = frame_times[tail_mask], rms[tail_mask] > threshold
    if not np.any(tail_active):
        return None
    stop = len(tail_active)
    inactive_run = 0
    for index, active in enumerate(tail_active):
        inactive_run = 0 if active else inactive_run + 1
        if inactive_run >= 4:
            stop = index - inactive_run + 1
            break
    active_indexes = np.flatnonzero(tail_active[:stop])
    if not len(active_indexes):
        return None
    audible_end = float(tail_times[active_indexes[-1]])
    intervals = int(np.floor((audible_end - anchor) / period + .1))
    if intervals < 4:
        return None
    end = anchor + intervals * period
    attacks = [attack for attack in _attacks(audio, anchor, duration, .1, period)
               if attack[0] <= audible_end + period / 2]
    active_rms = rms[tail_mask][:stop]
    active_fraction = float(np.mean(tail_active[:stop]))
    smooth_change = (float(np.median(abs(np.diff(active_rms))))
                     / max(float(np.median(active_rms[tail_active[:stop]])), 1e-7))
    sustained_tail = active_fraction >= .8 and smooth_change < .12
    required_attacks = max(3, min(8, intervals // 2))
    if len(attacks) >= required_attacks and not sustained_tail:
        times, strengths = np.asarray(attacks).T
        positions = (times - anchor) / period
        quarter_distance = abs(positions - np.rint(positions))
        eighth_distance = abs(positions * 2 - np.rint(positions * 2)) / 2
        if (np.average(eighth_distance < .12, weights=strengths) < .65
                or np.average(quarter_distance < .12, weights=strengths) < .2
                or np.average(eighth_distance, weights=strengths) > .1):
            return None
        if len(tail_bad):
            original = beats[anchor_index:]
            old_distance = np.min(abs(times[:, None] - original[None, :]), axis=1) / period
            if float(np.average(old_distance - quarter_distance, weights=strengths)) < .08:
                return None
        strong = strengths >= float(np.max(strengths)) * .15
        supported_quarters = np.rint(positions[strong & (quarter_distance < .12)]).astype(int)
        if len(supported_quarters):
            intervals = max(intervals, int(np.max(supported_quarters)))
            end = anchor + intervals * period
        # Drum fills can weaken quarter-note accents, but every eight-beat
        # window must retain some phase evidence.
        window_starts = np.arange(anchor, max(anchor, end - 8 * period), 8 * period).tolist()
        window_starts.append(max(anchor, end - 8 * period))
        for window_start in window_starts:
            window_end = min(end, window_start + 8 * period)
            mask = (times >= window_start) & (times <= window_end)
            if np.count_nonzero(mask) < 3:
                return None
            if (np.average(eighth_distance[mask] < .12, weights=strengths[mask]) < .4
                    and np.average(eighth_distance[mask], weights=strengths[mask]) > .15):
                return None
    else:
        # Sparse onsets are valid only for a continuously sounding held/fading
        # ending. Pulses at a conflicting tempo leave inactive gaps and fail.
        if not sustained_tail:
            return None
    previous_heads = downbeats[downbeats <= anchor + .12 * period]
    if not len(previous_heads):
        return None
    downbeat_offset = int(round((anchor - previous_heads[-1]) / period)) % 4
    return {"start": round(anchor, 3), "end": round(float(end), 3),
            "intervals": intervals, "downbeatOffset": downbeat_offset}


def _apply_verified_grid(data: dict, correction: dict) -> dict:
    beats = list(data["beats"])
    downbeats = list(data.get("downbeats") or [])
    for span in correction["spans"]:
        start, end, count = span["start"], span["end"], span["intervals"]
        grid = [round(start + (end - start) * i / count, 3) for i in range(count + 1)]
        beats = sorted([b for b in beats if b < start or b > end] + grid)
        heads = grid[::4]
        if span.get("preserve_end_downbeat") and end not in heads:
            # A short bar may end the bridge. Its right anchor is measured,
            # so never shift every later bar just to enforce four-beat meter.
            heads.append(end)
        downbeats = sorted([b for b in downbeats if b < start or b > end] + heads)
    if any(span.get("rebuild_downbeats") for span in correction["spans"]):
        # A missed beat changes subsequent bar numbering too. Keep the first
        # measured bar head and count the repaired beats, not the old detections.
        first = min(range(len(beats)), key=lambda i: abs(beats[i] - data["downbeats"][0]))
        downbeats = beats[first::4]
    if correction.get("intro"):
        anchor = correction["intro"]["start"]
        period = correction["intro"]["period"]
        intervals = correction["intro"]["intervals"]
        head_index = correction["intro"]["firstDownbeatIndex"]
        leading = [(i, round(anchor - i * period, 3))
                   for i in range(intervals, -1, -1)]
        beats = sorted([b for b in beats if b > anchor] + [b for _, b in leading])
        downbeats = sorted([b for b in downbeats if b > anchor]
                           + [b for i, b in leading if (i + head_index) % 4 == 0])
    if correction.get("outro"):
        outro = correction["outro"]
        anchor, end, count = outro["start"], outro["end"], outro["intervals"]
        grid = [round(anchor + (end - anchor) * i / count, 3) for i in range(count + 1)]
        beats = sorted([b for b in beats if b < anchor] + grid)
        offset = int(outro["downbeatOffset"])
        heads = [beat for index, beat in enumerate(grid) if (offset + index) % 4 == 0]
        downbeats = sorted([b for b in downbeats if b < anchor] + heads)
    adjusted = {**data, "beats": beats, "downbeats": downbeats, "total_bars": len(downbeats)}
    for key in ("sections", "automaticSections"):
        if key in data:
            adjusted[key] = bars_from_sections(data[key], downbeats)
    return adjusted


def _dominant_grid_spans(audio: sf.SoundFile, data: dict) -> list[dict]:
    """Bridge detector failures only when the recording supports a stable grid.

    A rounded BPM is not a clock: fit the period from a long uninterrupted run,
    then refine it with phase-consistent detections. Never derive the clock from
    the number of detections inside a failed span (beats may be missing there).
    """
    beats = np.asarray(data.get("beats") or [], dtype=float)
    downbeats = np.asarray(data.get("downbeats") or [], dtype=float)
    if len(beats) < 64 or len(downbeats) < 16:
        return []
    # Recounting bars is only safe for a consistently detected four-beat meter.
    # Preserve mixed meters rather than extending a majority meter over them.
    detected_bar_positions = np.argmin(abs(downbeats[:, None] - beats[None, :]), axis=1)
    meter_steps = np.diff(detected_bar_positions)
    if np.any(~np.isin(meter_steps, [2, 4])) or np.mean(meter_steps == 4) < .8:
        return []
    mixed_meter = bool(np.any(meter_steps == 2))
    gaps = np.diff(beats)
    typical = float(np.median(gaps))
    if typical <= 0 or np.any(gaps <= 0):
        return []
    cuts = np.r_[0, np.flatnonzero(abs(gaps / typical - 1) > .1) + 1, len(beats)]
    left, right = max(zip(cuts[:-1], cuts[1:]), key=lambda pair: pair[1] - pair[0])
    if right - left < 32:
        return []
    period, phase = np.polyfit(np.arange(right - left), beats[left:right], 1)
    for _ in range(4):
        indexes = np.rint((beats - phase) / period)
        consistent = abs(beats - (phase + indexes * period)) < .12 * period
        if np.count_nonzero(consistent) < 32:
            return []
        period, phase = np.polyfit(indexes[consistent], beats[consistent], 1)
    if np.mean(consistent) < .8:
        return []
    # Verify the meter from adjacent measured bar heads. An absolute phase
    # vote would reject a missing-beat failure halfway through a track because
    # all subsequent detected bar numbers can be shifted by that failure.
    bar_indexes = np.rint((downbeats - phase) / period).astype(int)
    on_grid = abs(downbeats - (phase + bar_indexes * period)) < .08 * period
    bar_steps = np.diff(bar_indexes)
    if np.mean((bar_steps > 0) & (bar_steps % 4 == 0)) < .8:
        return []
    anchors = downbeats[on_grid]
    candidates = []
    for start, end in zip(anchors[:-1], anchors[1:]):
        count = int(round((end - start) / period))
        inner = beats[(beats >= start - .001) & (beats <= end + .001)]
        expected = np.linspace(start, end, count + 1)
        if (len(inner) == len(expected)
                and np.max(abs(inner - expected)) < .12 * period
                and np.max(abs(np.diff(inner) / period - 1)) < .1):
            continue
        if candidates and abs(candidates[-1][1] - start) < .001:
            candidates[-1] = (candidates[-1][0], end)
        else:
            candidates.append((start, end))
    verified = []
    for start, end in candidates:
        count = int(round((end - start) / period))
        fitted = (end - start) / count
        if abs(fitted / period - 1) > .015:
            continue
        inner = beats[(beats >= start - .001) & (beats <= end + .001)]
        ratios = np.diff(inner) / fitted
        octave_sparse = (len(ratios) >= 8
                         and np.mean(abs(ratios - 2) < .08) >= .9)
        if octave_sparse:
            # A detector can keep the numeric tempo while returning every
            # other beat for long passages. Only fill that octave gap when
            # strong source attacks consistently prefer the established
            # full-rate grid over the detected half-rate grid. A genuine
            # half-time passage keeps its strong attacks near `inner` and is
            # therefore rejected by the old-vs-new comparison.
            supported = True
            window_starts = np.arange(start, max(start, end - 16 * fitted), 16 * fitted).tolist()
            window_starts.append(max(start, end - 16 * fitted))
            for window_start in window_starts:
                window_end = min(end, window_start + 16 * fitted)
                attacks = _attacks(audio, window_start, window_end, .1, fitted)
                if len(attacks) < 6:
                    supported = False
                    break
                times, strengths = np.asarray(attacks).T
                old_distance = np.min(abs(times[:, None] - inner[None, :]), axis=1) / fitted
                positions = (times - start) / fitted
                new_distance = abs(positions - np.rint(positions))
                old_fit = float(np.average(old_distance, weights=strengths))
                new_fit = float(np.average(new_distance, weights=strengths))
                if old_fit < .35 or new_fit > .34 or old_fit - new_fit < .1:
                    supported = False
                    break
            if supported:
                verified.append({"start": float(start), "end": float(end), "intervals": count,
                                 "rebuild_downbeats": bool(count % 4) and not mixed_meter,
                                 **({"preserve_end_downbeat": True} if mixed_meter else {})})
                continue
        # Half-time beat tracking can place audible attacks on sixteenths.
        # Keep the same fractional tolerance at either rhythmic resolution.
        for subdivisions in (2, 4):
            # Test every four-bar window, including the final window. Strong audio
            # support elsewhere must not conceal an actual local tempo change.
            supported = True
            evidence_gain = []
            window_starts = np.arange(start, max(start, end - 16 * fitted), 16 * fitted).tolist()
            window_starts.append(max(start, end - 16 * fitted))
            for window_start in window_starts:
                window_end = min(end, window_start + 16 * fitted)
                attacks = _attacks(audio, window_start, window_end, .1, fitted * 2 / subdivisions)
                if len(attacks) < min(6, max(3, count - 1)):
                    supported = False
                    break
                times, strengths = np.asarray(attacks).T
                positions = (times - start) / fitted
                original = beats[(beats >= start - period) & (beats <= end + period)]
                old_distance = np.min(abs(times[:, None] - original[None, :]), axis=1) / fitted
                new_distance = abs(positions - np.rint(positions))
                # Windows packages Python 3.10, which cannot unpack inside a
                # subscription (np.r_[...]). Concatenation keeps the same grid.
                original_subdivisions = np.sort(np.concatenate([original, *[
                    original[:-1] + np.diff(original) * i / subdivisions for i in range(1, subdivisions)]]))
                old_subdivision_distance = np.min(
                    abs(times[:, None] - original_subdivisions[None, :]), axis=1) / fitted
                new_subdivision_distance = abs(positions * subdivisions - np.rint(positions * subdivisions)) / subdivisions
                # Require improved audio alignment, not just a plausible constant
                # clock. Quarter-note evidence detects missed attacks; subdivision
                # evidence distinguishes syncopation from a genuinely changing pulse.
                evidence_gain.append([
                    float(np.average(np.minimum(old_distance, .25) - np.minimum(new_distance, .25),
                                     weights=strengths)),
                    float(np.average((old_subdivision_distance - new_subdivision_distance) * subdivisions / 2, weights=strengths)),
                ])
                aligned = abs(positions * subdivisions - np.rint(positions * subdivisions)) < .24
                quarter_support = np.average(new_distance < .12, weights=strengths)
                if (np.mean(aligned) < .6 or np.average(aligned, weights=strengths) < .7
                        or quarter_support < .2):
                    supported = False
                    break
            # Unaffected bars can dilute the gain. Require a measurable local
            # improvement without worsening the average alignment of the span.
            gains = np.asarray(evidence_gain)
            if (supported and np.any((np.mean(gains, axis=0) > 0)
                                     & (np.max(gains, axis=0) > .02))):
                verified.append({"start": float(start), "end": float(end), "intervals": count,
                                 "rebuild_downbeats": bool(count % 4) and not mixed_meter,
                                 **({"preserve_end_downbeat": True} if mixed_meter else {})})
                break
        else:
            # A short syncopated fill / rest can make absolute onset alignment
            # weak even though the proposed clock beats the detector's drift.
            # Only use this continuity prior with a near-unanimous track clock,
            # stable phase on BOTH sides, and no decisive contrary audio evidence.
            if np.mean(consistent) < .95 or not 4 <= count <= 32:
                continue
            before = beats[(beats < start) & (beats >= start - 8 * period)]
            after = beats[(beats > end) & (beats <= end + 8 * period)]
            if min(len(before), len(after)) < 6:
                continue
            if any(np.max(abs(np.diff(flank) / fitted - 1)) > .1 for flank in (before, after)):
                continue
            attacks = _attacks(audio, start, end, .1, fitted)
            if len(attacks) < 6:
                continue
            times, strengths = np.asarray(attacks).T
            original = beats[(beats >= start - period) & (beats <= end + period)]
            old_sub = np.sort(np.r_[original, (original[:-1] + original[1:]) / 2])
            old_error = np.min(abs(times[:, None] - old_sub[None, :]), axis=1) / fitted
            positions = (times - start) / fitted
            new_error = abs(positions * 2 - np.rint(positions * 2)) / 2
            gain = float(np.average(old_error - new_error, weights=strengths))
            # Decisive conflicting audio (including a genuine local tempo change) must
            # still win over the continuity prior. Do not fill unsupported silence.
            ratios = np.diff(original) / fitted
            drift = ratios[abs(ratios - 1) > .12]
            rhythmic_alias = (len(drift) >= 4 and np.mean(np.min(
                abs(drift[:, None] - np.asarray([2/3, 3/4, 4/3, 3/2])[None, :]), axis=1) < .07) >= .8)
            old_fit = float(np.average(old_error, weights=strengths))
            new_fit = float(np.average(new_error, weights=strengths))
            # Around an eighth-note lattice, uninformative onset phase has
            # expected distance 1/8 beat. When neither fit is decisive and the
            # detector follows a rhythmic subdivision, retain the long clock.
            # A clearly audible changed pulse fits the old grid much better and
            # is excluded even when its tempo ratio happens to be rational.
            ambiguous_alias = rhythmic_alias and old_fit > .08 and new_fit < .13 and gain > -.04
            if ((gain > .02 and np.average(new_error < .12, weights=strengths) > .4)
                    or ambiguous_alias):
                verified.append({"start": float(start), "end": float(end), "intervals": count,
                                 "preserve_end_downbeat": True})
    return verified


def refine_timing_from_audio(data: dict, audio_path: Path) -> dict:
    """Repair source-supported drift or short ambiguous aliases of a stable pulse."""
    with sf.SoundFile(audio_path) as audio:
        dominant_spans = _dominant_grid_spans(audio, data)
        if dominant_spans:
            data = _apply_verified_grid(data, {"spans": dominant_spans})
        intro = _missing_intro(audio, data)
        outro = _missing_outro(audio, data)
        spans = list(dominant_spans)
        for start, end, period in _candidate_spans(data):
            spans.extend(_audio_supported_spans(audio, start, end, period))
    if not intro and not outro and not spans:
        return data
    correction = {"spans": spans}
    if intro:
        correction["intro"] = intro
    if outro:
        correction["outro"] = outro
    adjusted = _apply_verified_grid(data, correction)
    adjusted["audioTimingRepair"] = {"version": 4, **correction}
    return adjusted
