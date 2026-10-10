import numpy as np
import pytest
import json
from pathlib import Path

from practice_lab.variable_meter import resolve_variable_meter
from practice_lab.timing import normalize_tempo_grid
from practice_lab.variable_meter import _refine_changes


def evidence(beats, indexes):
    pulse = np.full(round((beats[-1] + 1) * 100), .001)
    heads = pulse.copy()
    for time in beats:
        pulse[round(time * 100)] = .8
        heads[round(time * 100)] = .02
    for time in beats[indexes]:
        heads[round(time * 100)] = .75
    return {"beat": pulse, "downbeat": heads}


@pytest.mark.parametrize('period', [.37, .5, .8])
def test_sustained_three_beat_passage_is_not_forced_to_whole_track_four(period):
    meters = [4] * 20 + [3] * 24 + [4] * 20
    indexes = np.r_[0, np.cumsum(meters)]
    beats = np.arange(indexes[-1] + 1) * period + .2
    data = {"bpm": 60 / period, "beats": beats.tolist(), "downbeats": beats[::4].tolist()}
    result = resolve_variable_meter(data, evidence(beats, indexes))
    assert result['variableMeter']['meters'] == meters
    assert result['beats'] == data['beats']
    assert result['bpm'] == data['bpm']


def test_tempo_changes_do_not_change_the_meter_or_force_fast_clock_over_intro():
    beats = np.r_[np.arange(81) * .8, 64 + np.arange(1, 81) * .375]
    data = {"tempoMode": "variable", "bpm": 160, "beats": beats.tolist(),
            "downbeats": beats[::4].tolist()}
    assert normalize_tempo_grid(data) == data
    assert resolve_variable_meter(data, evidence(beats, np.arange(0, len(beats), 4))) == data


def test_silence_and_no_activations_keep_original_boundaries():
    beats = np.arange(101) * .5
    data = {'beats': beats.tolist(), 'downbeats': beats[::4].tolist()}
    assert resolve_variable_meter(data, None) == data
    silence = {'beat': np.zeros(5200), 'downbeat': np.zeros(5200)}
    assert resolve_variable_meter(data, silence) == data


@pytest.mark.parametrize('scale,offset', [(1, 0), (1.5, 17.3)])
def test_real_model_evidence_decodes_late_three_beats_without_fixed_song_times(scale, offset):
    fixture = json.loads((Path(__file__).parent / 'fixtures/variable-meter-model-evidence.json').read_text())
    beats = np.asarray(fixture['beats']) * scale + offset
    heads = np.asarray(fixture['downbeats']) * scale + offset
    pulse = np.zeros(round((beats[-1] + 1) * 100))
    downbeat = pulse.copy()
    indexes = np.round(beats * 100).astype(int)
    pulse[indexes] = fixture['pulse']
    # The fixture stores the sampled head/pulse ratio, not edited bar heads.
    downbeat[indexes] = np.asarray(fixture['head']) * np.maximum(fixture['pulse'], .05)
    data = {'beats': beats.tolist(), 'downbeats': heads.tolist()}
    result = resolve_variable_meter(data, {'beat': pulse, 'downbeat': downbeat})
    assert result['variableMeter']['meters'] == [4] * 85 + [3] * 36
    assert result['beats'] == data['beats']


def texture_audio(path, beats, meters, *, opposite_stereo=False, timbre_switch=None):
    """A repeating timbral rhythm, not model head probabilities or a fixture clock."""
    import soundfile as sf
    rate = 16000
    audio = np.zeros(int((beats[-1] + 1) * rate))
    beat_index = 0
    for meter in meters:
        for position in range(meter):
            start = round(beats[beat_index] * rate)
            duration = min(.12, (beats[beat_index + 1] - beats[beat_index]) / 2)
            t = np.arange(round(duration * rate)) / rate
            frequency = 110 + 180 * position
            if timbre_switch is not None and beat_index >= timbre_switch:
                frequency += 2000
            attack = np.sin(2 * np.pi * frequency * t) * np.exp(-t / .035)
            audio[start:start + len(t)] += attack
            beat_index += 1
    sf.write(path, np.column_stack((audio, -audio)) if opposite_stereo else audio, rate)


@pytest.mark.parametrize('period,offset,opposite', [(.37, .2, False), (.5, 3.1, True), (.8, .7, False)])
def test_audio_recurrence_recovers_change_when_first_unaccented_heads_are_missed(tmp_path, period, offset, opposite):
    meters = [4] * 24 + [3] * 28
    real_indexes = np.r_[0, np.cumsum(meters)]
    beats = np.arange(real_indexes[-1] + 1) * period + offset
    actual = 24 * 4
    delayed = actual + 12  # Common cycle of both meters, not a time in seconds.
    selected = np.r_[np.arange(0, delayed, 4), np.arange(delayed, len(beats), 3)]
    probability = np.full(len(beats), .02)
    probability[real_indexes] = .9
    path = tmp_path / 'missing-heads.wav'
    texture_audio(path, beats, meters, opposite_stereo=opposite)
    result, changes = _refine_changes(beats, selected, probability, path)
    assert result.tolist() == real_indexes.tolist()
    assert changes[0]['to'] == beats[actual]


def test_timbre_change_without_changed_bar_recurrence_does_not_move_boundary(tmp_path):
    meters = [4] * 48
    beats = np.arange(sum(meters) + 1) * .5 + .2
    selected = np.r_[np.arange(0, 96, 4), np.arange(96, len(beats), 3)]
    probability = np.full(len(beats), .9)
    path = tmp_path / 'still-four.wav'
    texture_audio(path, beats, meters, timbre_switch=96)
    result, changes = _refine_changes(beats, selected, probability, path)
    assert np.array_equal(result, selected)
    assert changes == []


def test_two_delayed_changes_are_refined_without_reusing_changed_array_positions(tmp_path):
    meters = [4] * 24 + [3] * 28 + [4] * 24
    indexes = np.r_[0, np.cumsum(meters)]
    beats = np.arange(indexes[-1] + 1) * .4 + .3
    first, second = 96 + 12, 180 + 12
    selected = np.r_[np.arange(0, first, 4), np.arange(first, second, 3), np.arange(second, len(beats), 4)]
    head = np.full(len(beats), .02)
    head[indexes] = .9
    path = tmp_path / 'two-changes.wav'
    texture_audio(path, beats, meters)
    result, changes = _refine_changes(beats, selected, head, path)
    assert result.tolist() == indexes.tolist()
    assert len(changes) == 2
