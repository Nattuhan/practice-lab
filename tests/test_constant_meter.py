from types import SimpleNamespace
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from practice_lab.constant_meter import decode_bar_heads
from practice_lab.constant_tempo import enforce_constant_tempo


def probabilities(beats, heads, *, fps=100):
    pulse = np.full(round((beats[-1] + 1) * fps), .001)
    downbeat = pulse.copy()
    for time in beats:
        pulse[round(time * fps)] = .6
    for time in heads:
        downbeat[round(time * fps)] = .5
    return {"beat": pulse, "downbeat": downbeat}


@pytest.mark.parametrize('period,offset', [(.317, .11), (.493, .17), (.731, 1.23)])
@pytest.mark.parametrize('rest_bars', [1, 3])
@pytest.mark.parametrize('head_drift', [.48, .45, .28])
def test_silent_short_bar_is_not_moved_onto_the_loud_final_beat(period, offset, rest_bars, head_drift):
    meters = [4] * 16 + [4, 3] + [4] * 16
    beats = offset + np.arange(sum(meters) + 1) * period
    indexes = np.r_[0, np.cumsum(meters)]
    heads = beats[indexes]
    detected = heads.copy()
    # One fixed-meter bar is compressed across a seven-pulse passage. Its
    # intermediate head lies closer to the silent downbeat than to the fill.
    detected[17] -= head_drift * period
    activations = probabilities(beats, heads)
    for time in beats[indexes[17]:indexes[17 + rest_bars]]:
        frame = round(time * 100)
        activations['beat'][frame] = .08
        activations['downbeat'][frame] = .001
    fill = round((heads[17] - period) * 100)
    activations['beat'][fill] = .6
    activations['downbeat'][fill] = .58
    aligned, diagnostics = decode_bar_heads(beats, detected.tolist(), activations)
    assert aligned == heads.tolist()
    assert diagnostics['meters'] == meters


@pytest.mark.parametrize('meter', [3, 4])
@pytest.mark.parametrize('period,offset', [(.31, 0), (.49, .37), (.73, 2.21)])
def test_phrase_continuity_resolves_one_ambiguous_head_without_changing_meter(meter, period, offset):
    beats = offset + np.arange(meter * 20 + 1) * period
    actual = beats[::meter]
    detected = actual.copy()
    detected[8] += .52 * period
    # Nearest-head snapping alone would produce meter+1 followed by meter-1.
    assert np.diff(np.rint((detected - offset) / period))[7:9].tolist() == [meter + 1, meter - 1]
    aligned, diagnostics = decode_bar_heads(beats, detected.tolist(), probabilities(beats, actual))
    assert aligned == actual.tolist()
    assert diagnostics['changedHeads'] == 1
    assert diagnostics['meters'] == [meter] * 20


def test_two_and_five_beat_bars_are_not_forced_to_four():
    meters = [4, 5, 4, 3, 4, 2, 4] * 4
    beats = .21 + np.arange(sum(meters) + 1) * .437
    heads = beats[np.r_[0, np.cumsum(meters)]]
    # An empty recording interval must not erase a head or enforce one meter.
    aligned, diagnostics = decode_bar_heads(beats, heads.tolist())
    assert aligned == heads.tolist()
    assert diagnostics['meters'] == meters


def test_four_beat_audio_repair_cannot_split_a_detected_long_bar():
    meters = [4] * 12 + [5] + [4] * 12 + [3] + [4] * 12
    beats = .17 + np.arange(sum(meters) + 1) * .5
    heads = beats[np.r_[0, np.cumsum(meters)]]
    manufactured = heads[12] + 4 * .5
    data = dict(bpm=120, beats=beats.tolist(), downbeats=sorted([*heads.tolist(), manufactured]),
                duration=float(beats[-1]), sections=[dict(start_time=0, end_time=float(beats[-1]))])
    fixed = enforce_constant_tempo(data, detected_downbeats=heads.tolist())
    assert fixed['constantMeter']['meters'] == meters
    assert len(fixed['downbeats']) == len(heads)
    assert fixed['sections'][0]['end_bar'] <= len(heads)


def test_audio_supported_intro_heads_and_resolved_metrical_octave_survive():
    beats = np.arange(80) * .5
    heads = beats[::4].tolist()
    data = dict(bpm=120, beats=beats.tolist(), downbeats=heads, duration=beats[-1])
    result = enforce_constant_tempo(data, detected_downbeats=heads[1:])
    assert result['downbeats'] == heads
    result = enforce_constant_tempo({**data, 'tempoOctaveResolution': {'fromBpm': 60}},
                                   detected_downbeats=heads[::2])
    assert result['downbeats'] == heads


def test_audio_supported_recovery_of_a_whole_bar_is_not_undone(tmp_path):
    from test_audio_timing import drifting_detection, write_attacks
    from practice_lab.audio_timing import refine_timing_from_audio
    original, start, end = drifting_detection(.5, .17)
    audio = tmp_path / 'repeated-syncopation.wav'
    attacks = [start + (i // 2 * 8 + (3.5 if i % 2 else 0)) * .5 for i in range(9)]
    write_attacks(audio, attacks, original['duration'])
    repaired = refine_timing_from_audio(original, audio)
    assert len(repaired['downbeats']) > len(original['downbeats'])
    result = enforce_constant_tempo(repaired, detected_downbeats=original['downbeats'])
    assert result['downbeats'] == repaired['downbeats']
    assert all(meter == 4 for meter in result['constantMeter']['meters'])


def test_a_measured_one_pulse_bar_is_preserved():
    meters = [4, 1, 4] * 10
    beats = .13 + np.arange(sum(meters) + 1) * .5
    heads = beats[np.r_[0, np.cumsum(meters)]].tolist()
    result = enforce_constant_tempo(dict(bpm=120, beats=beats.tolist(), downbeats=heads, duration=beats[-1]),
                                    detected_downbeats=heads)
    assert result['constantMeter']['meters'] == meters
    assert result['constantMeter']['discardedRepairHeads'] == 0


@pytest.mark.parametrize('period,offset', [(.317, .11), (.493, 1.23), (.731, .17)])
@pytest.mark.parametrize('short_bar', [True, False])
@pytest.mark.parametrize('missing_outro', [False, True])
def test_source_head_evidence_distinguishes_a_hidden_short_bar_from_missed_beats(tmp_path, period, offset, short_bar, missing_outro):
    from test_audio_timing import write_attacks
    from practice_lab.audio_timing import refine_timing_from_audio
    actual = offset + np.arange(320) * period
    if short_bar:
        # Four detections compress six real pulses. The inner short-bar head
        # is unplayed; its measured right anchor and later bars are reliable.
        detected = np.r_[actual[:160], np.linspace(actual[160], actual[166], 5), actual[167:]]
        head_indexes = np.r_[np.arange(0, 164, 4), np.arange(164, 166, 2), np.arange(166, 320, 4)]
    else:
        # Actual missing detections shift the model's later bar labels. Here
        # the source classifier supports the reconstructed four-beat phase.
        detected = np.delete(actual, [160, 161])
        head_indexes = np.arange(0, 320, 4)
    if missing_outro:
        detected = detected[detected <= actual[-13] + 1e-8]
    raw_beats = np.round(detected, 3).tolist()
    raw = dict(bpm=60 / period, beats=raw_beats, downbeats=raw_beats[::4], duration=actual[-1] + period)
    audio = tmp_path / 'independent-bar-phase.wav'
    write_attacks(audio, actual, raw['duration'])
    repaired = refine_timing_from_audio(raw, audio)
    assert any(span.get('rebuild_downbeats') for span in repaired['audioTimingRepair']['spans'])
    frames = int(raw['duration'] * 100) + 1
    pulse, head = np.zeros(frames), np.zeros(frames)
    for position in actual:
        pulse[round(position * 100)] = .8
        head[round(position * 100)] = .008
    for index in head_indexes:
        if short_bar and index == 164:
            continue
        head[round(actual[index] * 100)] = .72
    result = enforce_constant_tempo(repaired, detected_downbeats=raw['downbeats'],
                                   activations={'beat': pulse, 'downbeat': head})
    assert np.max(abs(np.asarray(result['downbeats']) - actual[head_indexes])) < .003
    if missing_outro:
        assert result['audioTimingRepair']['outro']['intervals'] == 12
    if short_bar:
        assert result['constantMeter']['meters'][40:43] == [4, 2, 4]
        assert len(result['constantMeter']['restoredRepairAnchors']) == 1
        assert result['audioTimingRepair']['spans'][0]['preserve_end_downbeat']
    else:
        assert result['constantMeter']['restoredRepairAnchors'] == []
        assert set(result['constantMeter']['meters']) == {4}


def test_a_measured_six_beat_bar_without_tracking_failure_is_not_split():
    meters = [4] * 12 + [6] + [4] * 12
    beats = .17 + np.arange(sum(meters) + 1) * .5
    heads = beats[np.r_[0, np.cumsum(meters)]].tolist()
    result = enforce_constant_tempo(dict(bpm=120, beats=beats.tolist(), downbeats=heads, duration=beats[-1]),
                                    detected_downbeats=heads)
    assert result['constantMeter']['meters'] == meters


def test_another_missed_beat_repair_cannot_erase_a_preserved_short_bar():
    from practice_lab.audio_timing import _apply_verified_grid
    beats = .17 + np.arange(240) * .5
    raw = dict(beats=beats.tolist(), downbeats=beats[::4].tolist())
    correction = {'spans': [
        {'start': beats[40], 'end': beats[45], 'intervals': 5, 'rebuild_downbeats': True},
        {'start': beats[160], 'end': beats[166], 'intervals': 6, 'preserve_end_downbeat': True},
    ]}
    result = _apply_verified_grid(raw, correction)
    expected = beats[np.r_[np.arange(0, 166, 4), np.arange(166, len(beats), 4)]]
    assert np.max(abs(np.asarray(result['downbeats']) - expected)) < .001


def test_invalid_probabilities_and_unresolvable_heads_fail_visibly():
    beats = np.arange(20) * .5
    with pytest.raises(ValueError, match='推論確率'):
        decode_bar_heads(beats, [0, 2, 4], {'beat': [0, 1], 'downbeat': [np.nan, 1]})
    with pytest.raises(ValueError, match='小節頭を整列'):
        decode_bar_heads(beats, [2, 2.01, 2.02])


@pytest.mark.parametrize('mode', ['constant', 'variable'])
def test_fresh_entry_requests_evidence_only_for_constant_and_keeps_the_short_bar(tmp_path, monkeypatch, capsys, mode):
    from test_audio_timing import write_attacks
    period, offset = .43, .19
    beats = offset + np.arange(200) * period
    compressed = beats[64] + np.array([0, 1, 2, 2.72, 3.54, 4.27, 5.13, 6, 7]) * period
    detections = np.r_[beats[:64], compressed, beats[72:]]
    indexes = np.r_[np.arange(0, 69, 4), np.arange(71, 200, 4)]
    heads = beats[indexes].copy()
    heads[17] = compressed[4]
    audio = tmp_path / 'independent-mixed-meter.wav'
    write_attacks(audio, np.delete(beats, 68), beats[-1] + period)
    activations = probabilities(beats, beats[indexes])
    activations['downbeat'][round(beats[68] * 100)] = .001
    activations['downbeat'][round(beats[67] * 100)] = .58
    calls = []

    def infer(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(path=audio, bpm=round(60/period), beats=detections.tolist(),
                               downbeats=heads.tolist(), segments=[],
                               activations=activations if kwargs['include_activations'] else None)

    monkeypatch.setitem(sys.modules, 'allin1fix', SimpleNamespace(analyze=infer))
    monkeypatch.setitem(sys.modules, 'allin1fix.config', SimpleNamespace(Config=lambda: SimpleNamespace(fps=100)))
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False),
                         backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))))
    spec = importlib.util.spec_from_file_location('mixed_meter_entry', Path(__file__).resolve().parents[1]/'scripts/analyze_audio.py')
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    for _ in range(2):
        entry.main([str(audio), '--device', 'cpu', '--tempo-mode', mode])
        result = json.loads(capsys.readouterr().out)
        if mode == 'constant':
            assert result['constantMeter']['meters'][16:19] == [4, 3, 4]
            assert np.max(abs(np.diff(result['beats']) - period)) < .0001
        else:
            assert 'constantMeter' not in result
            assert max(np.diff(result['beats'])) - min(np.diff(result['beats'])) > .05
    assert len(calls) == 2
    assert all(call['include_activations'] is (mode == 'constant') for call in calls)
