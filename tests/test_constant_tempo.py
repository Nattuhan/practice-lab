import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

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
    beats = np.r_[.17 + np.arange(192) * .5, .17 + 191 * .5 + np.arange(1, 129) * .6].tolist()
    audio = tmp_path / 'independent-tempo-change.wav'
    write_attacks(audio, beats, beats[-1] + 1)
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
        else:
            assert max(intervals) > .59
            assert min(intervals) < .51
            assert 'constantTempo' not in output
