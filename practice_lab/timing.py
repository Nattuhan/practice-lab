from math import floor
from statistics import median


def _intervals(beats: list[float]) -> list[float]:
    return [beats[index + 1] - beats[index] for index in range(len(beats) - 1)]


def _has_sustained_double_time(beats: list[float], bpm: float) -> bool:
    if bpm <= 0 or len(beats) < 24:
        return False

    expected = 60.0 / bpm
    intervals = _intervals(beats)
    short_windows = 0
    window_size = 8
    for index in range(0, len(intervals) - window_size + 1):
        value = median(intervals[index : index + window_size])
        if expected * 0.35 <= value <= expected * 0.65:
            short_windows += 1
    return short_windows >= 4


def _expand_to_interval(beats: list[float], target_interval: float) -> list[float]:
    if not beats:
        return []

    expanded = [round(beats[0], 3)]
    for beat in beats[1:]:
        previous = expanded[-1]
        steps = max(1, round((beat - previous) / target_interval))
        for step in range(1, steps + 1):
            expanded.append(round(previous + ((beat - previous) * step / steps), 3))
    return expanded


def _first_downbeat_index(beats: list[float], downbeats: list[float]) -> int:
    if not beats or not downbeats:
        return 0
    first_downbeat = downbeats[0]
    return min(range(len(beats)), key=lambda index: abs(beats[index] - first_downbeat))


def _downbeats_from_grid(beats: list[float], original_downbeats: list[float]) -> list[float]:
    if not beats:
        return []
    start = _first_downbeat_index(beats, original_downbeats)
    return [round(beats[index], 3) for index in range(start, len(beats), 4)]


def _find_stable_leading_transition(beats: list[float], expected: float) -> tuple[int, float] | None:
    intervals = _intervals(beats)
    window_size = 12
    maximum_index = len(intervals) - window_size
    for index in range(4, maximum_index + 1):
        window = intervals[index:index + window_size]
        stable_interval = median(window)
        if any(
            not stable_interval * 0.9 <= interval <= stable_interval * 1.1
            for interval in window[:4]
        ):
            continue
        stable_count = sum(
            stable_interval * 0.9 <= interval <= stable_interval * 1.1
            for interval in window
        )
        if stable_count < window_size - 1 or not expected * 0.88 <= stable_interval <= expected * 1.12:
            continue
        leading = intervals[:index]
        long_count = sum(interval >= stable_interval * 1.25 for interval in leading)
        if long_count < max(4, round(len(leading) * 0.6)):
            continue
        if beats[index] > 30.0:
            continue
        local_tail = [
            interval
            for interval in intervals[index:index + 64]
            if expected * 0.88 <= interval <= expected * 1.12
        ]
        return index, median(local_tail)
    return None


def _fit_stable_grid(
    beats: list[float], transition_index: int, stable_interval: float
) -> tuple[float, float] | None:
    stable_start = min(transition_index + 1, len(beats) - 1)
    stable_beats = [beats[stable_start]]
    for beat in beats[stable_start + 1 :]:
        interval = beat - stable_beats[-1]
        if not stable_interval * 0.75 <= interval <= stable_interval * 1.25:
            break
        stable_beats.append(beat)
    if len(stable_beats) < 12:
        return None

    count = len(stable_beats)
    mean_index = (count - 1) / 2
    mean_time = sum(stable_beats) / count
    denominator = sum((index - mean_index) ** 2 for index in range(count))
    period = sum(
        (index - mean_index) * (beat - mean_time)
        for index, beat in enumerate(stable_beats)
    ) / denominator
    intercept = mean_time - period * mean_index
    if period <= 0:
        return None
    return intercept, period


def _constant_grid(intercept: float, period: float, end_time: float) -> list[float]:
    phase = intercept - floor(intercept / period) * period
    if phase >= period - 0.0005:
        phase = 0.0
    count = floor((end_time - phase) / period) + 1
    return [round(phase + period * index, 3) for index in range(max(0, count))]


def _repair_sparse_leading_grid(data: dict) -> dict:
    bpm = float(data.get("bpm") or 0.0)
    beats = [float(beat) for beat in data.get("beats") or []]
    if bpm <= 0 or len(beats) < 20:
        return data

    transition = _find_stable_leading_transition(beats, 60.0 / bpm)
    if transition is None:
        return data
    transition_index, stable_interval = transition
    fitted = _fit_stable_grid(beats, transition_index, stable_interval)
    if fitted is None:
        return data
    intercept, fitted_period = fitted
    repaired_beats = _constant_grid(intercept, fitted_period, beats[-1])
    repaired_downbeats = _downbeats_from_grid(
        repaired_beats,
        [float(downbeat) for downbeat in data.get("downbeats") or []],
    )

    adjusted = dict(data)
    adjusted["bpm"] = round(60.0 / fitted_period, 1)
    adjusted["beats"] = repaired_beats
    adjusted["downbeats"] = repaired_downbeats
    adjusted["total_bars"] = len(repaired_downbeats)
    adjusted["sections"] = bars_from_sections(
        list(data.get("sections") or []), repaired_downbeats
    )
    return adjusted


def normalize_section_bar_ranges(sections: list[dict], total_bars: int) -> list[dict]:
    if not sections or total_bars < 1:
        return [dict(section) for section in sections]
    if len(sections) > total_bars:
        return [dict(section) for section in sections]

    normalized = []
    next_start = 1
    for index, section in enumerate(sections):
        remaining = len(sections) - index - 1
        max_end = total_bars - remaining
        raw_end = int(section.get("end_bar") or next_start)
        end_bar = total_bars if index == len(sections) - 1 else max(next_start, min(max_end, raw_end))
        adjusted = dict(section)
        adjusted["start_bar"] = next_start
        adjusted["end_bar"] = end_bar
        adjusted["bar_count"] = end_bar - next_start + 1
        normalized.append(adjusted)
        next_start = end_bar + 1
    return normalized


def bars_from_sections(sections: list[dict], downbeats: list[float]) -> list[dict]:
    def time_to_bar(value: float) -> int:
        for index, downbeat in enumerate(downbeats):
            if downbeat >= value - 0.1:
                return index + 1
        return len(downbeats)

    adjusted_sections = []
    for section in sections:
        start_bar = time_to_bar(float(section.get("start_time", 0.0)))
        end_bar = max(start_bar, time_to_bar(float(section.get("end_time", 0.0))) - 1)
        adjusted = dict(section)
        adjusted["start_bar"] = start_bar
        adjusted["end_bar"] = end_bar
        adjusted["bar_count"] = end_bar - start_bar + 1
        adjusted_sections.append(adjusted)
    return normalize_section_bar_ranges(adjusted_sections, len(downbeats))


def normalize_tempo_grid(data: dict) -> dict:
    bpm = float(data.get("bpm") or 0.0)
    beats = [float(beat) for beat in data.get("beats") or []]
    adjusted = data
    if _has_sustained_double_time(beats, bpm):
        adjusted_bpm = round(bpm * 2, 1)
        target_interval = 60.0 / adjusted_bpm
        adjusted_beats = _expand_to_interval(beats, target_interval)
        adjusted_downbeats = _downbeats_from_grid(
            adjusted_beats,
            [float(downbeat) for downbeat in data.get("downbeats") or []],
        )

        adjusted = dict(data)
        adjusted["bpm"] = adjusted_bpm
        adjusted["beats"] = adjusted_beats
        adjusted["downbeats"] = adjusted_downbeats
        adjusted["total_bars"] = len(adjusted_downbeats)
        adjusted["sections"] = bars_from_sections(list(data.get("sections") or []), adjusted_downbeats)
    return _repair_sparse_leading_grid(adjusted)
