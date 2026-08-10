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
    maximum_index = min(len(intervals) - window_size, 24)
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


def _repair_sparse_leading_grid(data: dict) -> dict:
    bpm = float(data.get("bpm") or 0.0)
    beats = [float(beat) for beat in data.get("beats") or []]
    if bpm <= 0 or len(beats) < 20:
        return data

    transition = _find_stable_leading_transition(beats, 60.0 / bpm)
    if transition is None:
        return data
    transition_index, stable_interval = transition
    anchor = beats[transition_index]
    stable_downbeats = [
        float(downbeat)
        for downbeat in data.get("downbeats") or []
        if float(downbeat) >= anchor - stable_interval * 0.25
    ]
    if not stable_downbeats:
        return data
    reference = stable_downbeats[0]
    source_reference_index = min(
        range(transition_index, len(beats)),
        key=lambda index: abs(beats[index] - reference),
    )
    earliest = max(0.0, beats[0] - stable_interval * 1.05)
    leading = [round(reference, 3)]
    value = reference - stable_interval
    while value >= earliest:
        leading.append(round(value, 3))
        value -= stable_interval
    repaired_beats = list(reversed(leading)) + [
        round(beat, 3) for beat in beats[source_reference_index + 1:]
    ]
    reference_index = min(
        range(len(repaired_beats)),
        key=lambda index: abs(repaired_beats[index] - reference),
    )
    phase = reference_index % 4
    repaired_downbeats = [
        beat for index, beat in enumerate(repaired_beats) if index % 4 == phase
    ]

    adjusted = dict(data)
    adjusted["beats"] = repaired_beats
    adjusted["downbeats"] = repaired_downbeats
    adjusted["total_bars"] = len(repaired_downbeats)
    adjusted["sections"] = bars_from_sections(
        list(data.get("sections") or []), repaired_downbeats
    )
    return adjusted


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
    return adjusted_sections


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
