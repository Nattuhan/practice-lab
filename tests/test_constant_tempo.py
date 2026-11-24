import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from practice_lab.constant_tempo import enforce_constant_tempo


@pytest.mark.parametrize('period,offset', [(.317, 0), (.493, .17), (.731, 1.23)])
def test_compressed_four_and_three_beat_bars_keep_the_source_clock(period, offset):
    # Ground truth is a continuous musical pulse. The detector squeezes eight
    # detections into seven intervals when it cannot represent a 3/4 bar.
    actual = offset + np.arange(200) * period
    compressed = actual[64] + np.array([0, 1, 2, 2.72, 3.54, 4.27, 5.13, 6, 7]) * period
    detected = np.r_[actual[:64], compressed, actual[72:]]
    true_heads = np.r_[np.arange(0, 69, 4), np.arange(71, 200, 4)]
    heads = actual[true_heads].copy()
    heads[17] = compressed[4]
    result = enforce_constant_tempo(dict(bpm=round(60 / period), beats=np.round(detected, 3).tolist(),
                                        downbeats=np.round(heads, 3).tolist(), duration=actual[-1] + period))
    beats = np.array(result['beats'])
    assert np.max(abs(np.diff(beats) - period)) < period * .001
    assert np.max(np.min(abs(actual[:, None] - beats[None, :]), axis=1)) < period * .01
    assert np.max(abs(np.array(result['downbeats']) - actual[true_heads])) < period * .01
    positions = np.argmin(abs(np.array(result['downbeats'])[:, None] - beats[None, :]), axis=1)
    assert np.diff(positions)[16:19].tolist() == [4, 3, 4]
    assert result['tempoMode'] == 'constant'


@pytest.mark.parametrize('meters', [[3] * 16, [4] * 16, [4, 3, 4, 2] * 4])
def test_regular_and_mixed_meters_are_not_recounted_as_four_beats(meters):
    beats = .23 + np.arange(sum(meters) + 1) * .4271
    heads = beats[np.r_[0, np.cumsum(meters)]]
    result = enforce_constant_tempo(dict(bpm=140.5, beats=np.round(beats, 3).tolist(),
                                        downbeats=np.round(heads, 3).tolist(), duration=beats[-1] + .5))
    positions = np.argmin(abs(np.asarray(result['downbeats'])[:, None] - np.asarray(result['beats'])[None, :]), axis=1)
    assert np.diff(positions).tolist() == meters
    assert max(abs(np.asarray(result['beats']) - beats)) < .001


def test_constant_pulse_does_not_extend_clicks_to_the_end_of_the_file():
    beats = [.23 + i * .4271 for i in range(80)]
    result = enforce_constant_tempo(dict(bpm=140.5, beats=beats, downbeats=beats[::4], duration=60))
    assert result['beats'][-1] == pytest.approx(beats[-1], abs=1e-6)


@pytest.mark.parametrize('period,offset,meter,first_head', [(.34, .19, 3, 18), (.57, .24, 4, 24)])
def test_constant_pulse_extends_over_sparse_intro_to_the_audible_start(tmp_path, period, offset, meter, first_head):
    from practice_lab.audio_timing import refine_timing_from_audio

    pulse = offset + np.arange(96) * period
    notes = pulse[8] + np.array([.33, 2.02, 4.68]) * period
    rate = 8000
    duration = pulse[-1] + period
    time = np.arange(round(duration * rate)) / rate
    bass = np.sin(2 * np.pi * 83 * time)
    playing = np.any((time[:, None] >= notes) & (time[:, None] < notes + .55 * period), axis=1)
    samples = bass * np.where(playing | (time >= pulse[17]), .2, .002)
    audio = tmp_path / 'sparse-bass-opening.wav'
    sf.write(audio, np.column_stack([samples, -samples]), rate, subtype='FLOAT')

    detected = pulse[17:].copy()
    detected[1:4] += np.array([.13, -.08, .07]) * period
    heads = pulse[first_head::meter].tolist()
    data = dict(bpm=round(60 / period, 1), beats=detected.tolist(), downbeats=heads, duration=duration)
    # There is no stable local clock at the first detection for the ordinary
    # source-evidence repair. Constant mode can use the established later pulse.
    assert refine_timing_from_audio(data, audio)['beats'] == data['beats']
    result = enforce_constant_tempo(data, audio_path=audio)
    assert result['beats'] == pytest.approx(pulse[8:], abs=.002)
    expected_heads = pulse[8:first_head][(first_head - 8) % meter::meter].tolist() + heads
    assert result['downbeats'] == pytest.approx(expected_heads, abs=.002)
    assert result['constantTempo']['intro']['insertedBeats'] == 9
    assert result['constantMeter']['meters'] == [meter] * (len(expected_heads) - 1)
    assert result['total_bars'] == len(expected_heads)
    assert enforce_constant_tempo(result, audio_path=audio)['beats'] == result['beats']

    # A quiet lead-in and a single-sample impulse must not acquire a grid.
    samples[playing] = 0
    samples[round(notes[0] * rate)] = .7
    sf.write(audio, samples, rate, subtype='FLOAT')
    assert 'intro' not in enforce_constant_tempo(data, audio_path=audio)['constantTempo']

    # Sustained broadband sound is audible, but it does not establish a bass
    # intro and must not pull the click into audience noise or a false start.
    samples[playing] = .2 * np.random.default_rng(19).normal(size=np.count_nonzero(playing))
    sf.write(audio, samples, rate, subtype='FLOAT')
    assert 'intro' not in enforce_constant_tempo(data, audio_path=audio)['constantTempo']


def test_beats_at_exact_file_boundaries_survive_floating_point_fit():
    beats = (np.arange(191) * .375).tolist()
    result = enforce_constant_tempo(dict(bpm=160, beats=beats, downbeats=beats[::4], duration=beats[-1]))
    assert result['beats'] == beats


def test_inadequate_input_does_not_silently_return_a_variable_pulse():
    with pytest.raises(ValueError, match='拍間隔'):
        enforce_constant_tempo(dict(bpm=120, beats=[0, .3, 1], downbeats=[0], duration=2))


@pytest.mark.parametrize('mode', ['constant', 'variable'])
def test_analyzer_cli_uses_the_selected_assumption_for_new_and_repeated_analysis(tmp_path, monkeypatch, capsys, mode):
    from test_audio_timing import write_attacks
    beats = np.r_[4.17 + np.arange(192) * .5, 4.17 + 191 * .5 + np.arange(1, 129) * .6].tolist()
    beats[1:4] = [beat + jitter for beat, jitter in zip(beats[1:4], (.065, -.04, .035))]
    audio = tmp_path / 'independent-tempo-change.wav'
    write_attacks(audio, beats, beats[-1] + 1)
    samples, rate = sf.read(audio)
    for start in (.335, 1.18):
        first = round(start * rate)
        time = np.arange(round(.32 * rate)) / rate
        samples[first:first + len(time)] = .4 * np.sin(2 * np.pi * 83 * time)
    sf.write(audio, samples, rate, subtype='FLOAT')
    inferred = SimpleNamespace(beats=beats, downbeats=beats[::4], bpm=120, path=audio, segments=[])
    monkeypatch.setitem(sys.modules, 'allin1fix', SimpleNamespace(analyze=lambda *args, **kwargs: inferred))
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False),
                         backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))))
    spec = importlib.util.spec_from_file_location('tempo_cli_test', Path(__file__).resolve().parents[1] / 'scripts/analyze_audio.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Each invocation starts from the source inference, never the previous result.
    for _ in range(2):
        assert module.main([str(audio), '--device', 'cpu', '--tempo-mode', mode]) == 0
        output = json.loads(capsys.readouterr().out)
        intervals = np.diff(output['beats'])
        assert output['tempoMode'] == mode
        if mode == 'constant':
            assert max(intervals) - min(intervals) < 2e-6
            assert output['beats'][0] == pytest.approx(.17, abs=.001)
        else:
            assert max(intervals) > .59
            assert min(intervals) < .51
            assert output['beats'][0] == beats[0]
            assert 'constantTempo' not in output
