import numpy as np
import pytest
import json
from pathlib import Path

from practice_lab.variable_meter import resolve_variable_meter
from practice_lab.timing import normalize_tempo_grid


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
