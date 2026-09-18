from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from practice_lab.audio_timing import refine_timing_from_audio


def write_attacks(path, times, duration, *, inverted_stereo=False):
    rate = 8000
    audio = np.zeros(round(duration * rate))
    t = np.arange(round(.065 * rate)) / rate
    pulse = .7 * np.sin(2 * np.pi * 870 * t) * np.exp(-t * 65)
    for time in times:
        i = round(time * rate)
        if i < 0 or i + len(pulse) > len(audio):
            continue
        audio[i:i + len(pulse)] += pulse
    if inverted_stereo:
        audio = np.column_stack([audio, -audio])
    sf.write(path, audio, rate, subtype='FLOAT')


def drifting_detection(period, offset):
    start = offset + 16 * period
    end = start + 32 * period
    downbeats = ([offset + i * 4 * period for i in range(4)]
                 + np.linspace(start, end, 8).tolist()
                 + [end + i * 4 * period for i in range(1, 9)])
    beats = [round(left + (right - left) * i / 4, 3)
             for left, right in zip(downbeats, downbeats[1:]) for i in range(4)]
    beats.append(round(downbeats[-1], 3))
    return dict(bpm=60 / period, beats=beats, downbeats=[round(b, 3) for b in downbeats],
                duration=beats[-1] + period, sections=[dict(start_time=0, end_time=beats[-1])]), start, end


@pytest.mark.parametrize('period,offset', [(.31, .11), (.5, .17), (.7, .23)])
@pytest.mark.parametrize('offbeat', [3.5, 4.5])
def test_corrects_audio_supported_syncopation_at_different_tempos_and_positions(tmp_path, period, offset, offbeat):
    data, start, end = drifting_detection(period, offset)
    attacks = [start + (i // 2 * 8 + (offbeat if i % 2 else 0)) * period for i in range(9)]
    audio = tmp_path / 'unrelated-name.wav'
    write_attacks(audio, attacks, data['duration'], inverted_stereo=True)
    result = refine_timing_from_audio(data, audio)
    fixed = [beat for beat in result['beats'] if round(start, 3) <= beat <= round(end, 3)]
    assert len(fixed) == 33
    assert max(abs((b - a) - period) for a, b in zip(fixed, fixed[1:])) < .006
    assert 'audioTimingRepair' in result
    assert 'timingCorrection' not in result
    assert [b for b in result['beats'] if b < start or b > end] == [b for b in data['beats'] if b < start or b > end]
    assert refine_timing_from_audio(result, audio) == result


@pytest.mark.parametrize('case', ['real_tempo_change', 'silence', 'unrelated_attacks'])
def test_keeps_genuine_tempo_change_or_unsupported_span(tmp_path, case):
    data, start, end = drifting_detection(.5, .17)
    if case == 'real_tempo_change':
        attacks = [b for b in data['beats'] if start <= b <= end]
    elif case == 'silence':
        attacks = []
    else:
        attacks = [start + .14 + (i // 2 * 8 + (3.5 if i % 2 else 0)) * .5 for i in range(9)]
    audio = tmp_path / 'song.wav'
    write_attacks(audio, attacks, data['duration'])
    assert refine_timing_from_audio(data, audio) is data


@pytest.mark.parametrize('period', [.3, .45, .65])
def test_backfills_missing_intro_only_with_audio_support(tmp_path, period):
    first = 4.5 * period
    beats = [round(first + i * period, 3) for i in range(48)]
    data = dict(bpm=60 / period, beats=beats, downbeats=beats[::4], duration=beats[-1] + period)
    audio = tmp_path / 'intro.wav'
    write_attacks(audio, [first - 3.5 * period, first - .5 * period], data['duration'])
    result = refine_timing_from_audio(data, audio)
    assert result['beats'][:5] == [round(first - i * period, 3) for i in range(4, -1, -1)]
    assert result['downbeats'][:2] == [round(first - 4 * period, 3), round(first, 3)]
    assert result['beats'][4:] == beats
    assert refine_timing_from_audio(result, audio) == result
    write_attacks(audio, [], data['duration'])
    assert refine_timing_from_audio(data, audio) is data
    write_attacks(audio, [first - 3.2 * period, first - .2 * period], data['duration'])
    assert refine_timing_from_audio(data, audio) is data


def test_backfills_held_intro_before_first_detected_beat(tmp_path):
    period, first = .44, 6.38
    beats = [round(first + i * period, 3) for i in range(64)]
    data = dict(bpm=60/period, beats=beats, downbeats=beats[2::4],
                duration=beats[-1]+period)
    audio = tmp_path / 'held-intro.wav'
    write_attacks(audio, beats, data['duration'])
    samples, rate = sf.read(audio, dtype='float32')
    start = round((first - 6 * period) * rate)
    end = round(first * rate)
    time = np.arange(end - start) / rate
    fade_in = np.minimum(1, time / period)
    samples[start:end] += .2 * np.sin(2 * np.pi * 220 * time) * fade_in
    sf.write(audio, samples, rate, subtype='FLOAT')
    result = refine_timing_from_audio(data, audio)
    assert len(result['beats']) >= len(beats) + 5
    assert result['beats'][0] < first - 4 * period
    assert max(np.diff(result['beats'][:8])) < period * 1.01
    assert refine_timing_from_audio(result, audio) == result


def test_fresh_analyzer_output_is_repaired_without_session_identity_or_saved_correction(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    import sys
    from types import SimpleNamespace

    data, start, end = drifting_detection(.5, .17)
    audio = tmp_path / 'brand-new-recording.wav'
    attacks = [start + (i // 2 * 8 + (3.5 if i % 2 else 0)) * .5 for i in range(9)]
    write_attacks(audio, attacks, data['duration'])
    result = SimpleNamespace(beats=data['beats'], downbeats=data['downbeats'], bpm=data['bpm'],
                             path=audio, segments=[])
    monkeypatch.setitem(sys.modules, 'allin1fix', SimpleNamespace(analyze=lambda *args, **kwargs: result))
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))))
    spec = importlib.util.spec_from_file_location('fresh_analyzer_test', Path(__file__).resolve().parents[1] / 'scripts/analyze_audio.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for _ in range(2):
        assert module.main([str(audio), '--device', 'cpu']) == 0
        output = json.loads(capsys.readouterr().out)
        assert len([b for b in output['beats'] if start <= b <= end]) == 33
        assert 'audioTimingRepair' in output
        assert 'timingCorrection' not in output


def test_accent_pattern_is_inferred_instead_of_matching_a_specific_riff(tmp_path):
    data, start, end = drifting_detection(.5, .17)
    positions = [0, 1.5, 4, 6.5, 8, 11.5, 16, 19.5, 24, 25.5, 28, 30.5, 32]
    audio = tmp_path / 'different-rhythm.wav'
    write_attacks(audio, [start + beat * .5 for beat in positions], data['duration'])
    result = refine_timing_from_audio(data, audio)
    assert len([b for b in result['beats'] if start <= b <= end]) == 33
    assert [span['intervals'] for span in result['audioTimingRepair']['spans']] == [4, 4, 8, 8, 4, 4]


def irregular_detection(period, offset):
    actual = offset + np.arange(320) * period
    detected = actual.copy()
    # A syncopated passage causes phase drift, followed by missing detections.
    detected[160:184] += np.sin(np.linspace(0, np.pi, 24)) * period * .45
    detected = np.delete(detected, [190, 194, 198, 202])
    beats = np.round(detected, 3).tolist()
    return dict(bpm=round(60 / period), beats=beats, downbeats=beats[::4],
                duration=float(actual[-1] + period),
                sections=[dict(start_time=0, end_time=float(actual[-1]))]), actual


@pytest.mark.parametrize('period,offset', [(.317, .19), (.493, 1.13), (.683, .07)])
def test_repairs_phase_drift_and_missing_beats_from_audio(tmp_path, period, offset):
    data, actual = irregular_detection(period, offset)
    audio = tmp_path / 'recording.wav'
    write_attacks(audio, actual, data['duration'], inverted_stereo=True)
    result = refine_timing_from_audio(data, audio)
    assert len(result['beats']) == len(actual)
    assert np.max(abs(np.asarray(result['beats']) - actual)) < .002
    assert np.max(abs(np.asarray(result['downbeats']) - actual[::4])) < .002
    assert refine_timing_from_audio(result, audio) == result


@pytest.mark.parametrize('period,offset', [(.33, .19), (.49, 1.13), (.68, .37)])
def test_restores_long_leading_and_trailing_half_rate_detections(tmp_path, period, offset):
    actual = offset + np.arange(480) * period
    detected = np.r_[actual[:96:2], actual[96:384], actual[384::2]]
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60/period, beats=beats, downbeats=beats[::4],
                duration=actual[-1]+period,
                sections=[dict(start_time=0, end_time=actual[-1])])
    audio = tmp_path / 'octave-mixed-grid.wav'
    write_attacks(audio, actual, data['duration'])
    result = refine_timing_from_audio(data, audio)
    # Repair only between measured bar anchors; do not extrapolate beats past
    # the final detection into a possibly silent outro.
    assert len(result['beats']) > len(beats)
    for span in result['audioTimingRepair']['spans']:
        repaired = np.asarray([beat for beat in result['beats']
                               if span['start'] <= beat <= span['end']])
        expected = actual[(actual >= span['start'] - .001) & (actual <= span['end'] + .001)]
        assert len(repaired) == len(expected)
        assert np.max(abs(repaired - expected)) < .002
    assert result['bpm'] == data['bpm']
    assert refine_timing_from_audio(result, audio) == result


def test_keeps_genuine_half_time_passages_in_octave_mixed_detection(tmp_path):
    period, offset = .5, .17
    actual = offset + np.arange(480) * period
    detected = np.r_[actual[:96:2], actual[96:384], actual[384::2]]
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60/period, beats=beats, downbeats=beats[::4],
                duration=actual[-1]+period)
    audio = tmp_path / 'real-half-time-passages.wav'
    # The outer passages genuinely carry strong attacks only at half rate.
    attacks = np.r_[actual[:96:2], actual[96:384], actual[384::2]]
    write_attacks(audio, attacks, data['duration'])
    assert refine_timing_from_audio(data, audio) is data


@pytest.mark.parametrize('period,offset', [(.33, .19), (.49, 1.13), (.68, .37)])
def test_extends_source_supported_constant_clock_through_missing_outro(tmp_path, period, offset):
    actual = offset + np.arange(360) * period
    detected = actual[:-24]
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60/period, beats=beats, downbeats=beats[::4],
                duration=actual[-1]+period,
                sections=[dict(start_time=0, end_time=actual[-1]+period)])
    audio = tmp_path / 'missing-outro.wav'
    write_attacks(audio, actual, data['duration'])
    result = refine_timing_from_audio(data, audio)
    assert np.max(abs(np.asarray(result['beats']) - actual)) < .002
    assert result['audioTimingRepair']['outro']['intervals'] == 24
    assert result['bpm'] == data['bpm']
    assert refine_timing_from_audio(result, audio) == result


def test_replaces_drifting_terminal_detections_with_source_supported_clock(tmp_path):
    period, offset = .41, .23
    actual = offset + np.arange(360) * period
    detected = np.r_[actual[:-24], actual[-24] + np.arange(16) * period * 1.5]
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60/period, beats=beats, downbeats=beats[::4],
                duration=actual[-1]+period)
    audio = tmp_path / 'drifting-outro.wav'
    write_attacks(audio, actual, data['duration'])
    result = refine_timing_from_audio(data, audio)
    assert np.max(abs(np.asarray(result['beats']) - actual)) < .002
    assert refine_timing_from_audio(result, audio) == result


def test_extends_constant_clock_through_held_fading_outro(tmp_path):
    period, offset = .46, .21
    actual = offset + np.arange(320) * period
    detected = actual[:-20]
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60/period, beats=beats, downbeats=beats[::4],
                duration=actual[-1]+period)
    audio = tmp_path / 'held-fade.wav'
    write_attacks(audio, detected, data['duration'])
    samples, rate = sf.read(audio, dtype='float32')
    start = round(detected[-1] * rate)
    tail = np.arange(len(samples) - start) / rate
    fade = np.maximum(0, 1 - tail / (20 * period))
    samples[start:] += .2 * np.sin(2 * np.pi * 220 * tail) * fade
    sf.write(audio, samples, rate, subtype='FLOAT')
    result = refine_timing_from_audio(data, audio)
    assert len(result['beats']) > len(beats) + 16
    assert max(np.diff(result['beats'][-20:])) < period * 1.01
    assert refine_timing_from_audio(result, audio) == result


@pytest.mark.parametrize('case', ['silence', 'different_phase', 'different_tempo'])
def test_does_not_extend_outro_without_matching_source_clock(tmp_path, case):
    period, offset = .47, .17
    actual = offset + np.arange(360) * period
    detected = actual[:-24]
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60/period, beats=beats, downbeats=beats[::4],
                duration=actual[-1]+period)
    if case == 'silence':
        attacks = detected
    elif case == 'different_phase':
        attacks = np.r_[detected, actual[-24:] + .25 * period]
    else:
        attacks = np.r_[detected, actual[-24] + np.arange(24) * period * .8]
    audio = tmp_path / f'{case}.wav'
    write_attacks(audio, attacks, data['duration'])
    assert refine_timing_from_audio(data, audio) is data


@pytest.mark.parametrize('case', ['tempo_change', 'silence', 'different_phase', 'accelerando'])
def test_dominant_tempo_does_not_override_conflicting_local_audio(tmp_path, case):
    period = .493
    data, actual = irregular_detection(period, .17)
    if case == 'tempo_change':
        # The recording itself follows the varying detections.
        attacks = data['beats']
    elif case == 'silence':
        attacks = [b for b in actual if b < actual[156] or b > actual[204]]
    elif case == 'different_phase':
        attacks = [b + (.25 * period if actual[156] <= b <= actual[204] else 0) for b in actual]
    else:
        attacks = list(actual[:156])
        attacks += (actual[156] + np.cumsum(np.linspace(.8, 1.2, 48)) * period).tolist()
        attacks += list(actual[205:])
    audio = tmp_path / 'variable.wav'
    write_attacks(audio, attacks, data['duration'])
    result = refine_timing_from_audio(data, audio)
    # No smoothing of a passage whose sound does not support the proposed clock.
    assert result['beats'] == data['beats']


def test_local_tempo_change_is_not_hidden_by_long_constant_surroundings(tmp_path):
    period = .5
    actual = np.r_[.17 + np.arange(160) * period,
                   80.17 + np.arange(24) * .6,
                   94.57 + np.arange(160) * period]
    beats = np.round(actual, 3).tolist()
    data = dict(bpm=120, beats=beats, downbeats=beats[::4], duration=beats[-1] + period)
    audio = tmp_path / 'tempo-change.wav'
    write_attacks(audio, actual, data['duration'])
    assert refine_timing_from_audio(data, audio) is data


@pytest.mark.parametrize('missing', [1, 2, 3])
@pytest.mark.parametrize('period', [.32, .64])
def test_missing_beats_restore_subsequent_bar_count(tmp_path, missing, period):
    actual = .17 + np.arange(320) * period
    detected = np.delete(actual, np.arange(160, 160 + missing))
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60 / period, beats=beats, downbeats=beats[::4], duration=actual[-1] + period)
    audio = tmp_path / 'missed-beats.wav'
    write_attacks(audio, actual, data['duration'])
    result = refine_timing_from_audio(data, audio)
    assert len(result['beats']) == len(actual)
    assert np.max(abs(np.asarray(result['beats']) - actual)) < .002
    assert np.max(abs(np.asarray(result['downbeats']) - actual[::4])) < .002
    assert refine_timing_from_audio(result, audio) == result


def test_keeps_three_beat_meter(tmp_path):
    data, actual = irregular_detection(.493, .17)
    data['downbeats'] = data['beats'][::3]
    audio = tmp_path / 'waltz.wav'
    write_attacks(audio, actual, data['duration'])
    assert refine_timing_from_audio(data, audio) is data


@pytest.mark.parametrize('period,offset', [(.4, .23), (.64, 1.17), (.8, 2.31)])
def test_dense_subdivisions_support_half_time_detections(tmp_path, period, offset):
    data, actual = irregular_detection(period, offset)
    audio = tmp_path / 'half-time.wav'
    attacks = offset + np.arange(1277) * period / 4
    write_attacks(audio, attacks, data['duration'])
    result = refine_timing_from_audio(data, audio)
    assert len(result['beats']) == len(actual)
    assert np.max(abs(np.asarray(result['beats']) - actual)) < .002
    assert result['bpm'] == data['bpm']


def test_keeps_mixed_meter_when_recounting_would_erase_short_bars(tmp_path):
    data, actual = irregular_detection(.493, .17)
    positions = list(range(0, 80, 4)) + list(range(80, 92, 3)) + list(range(92, len(data['beats']), 4))
    data['downbeats'] = [data['beats'][i] for i in positions]
    audio = tmp_path / 'mixed-meter.wav'
    write_attacks(audio, actual, data['duration'])
    assert refine_timing_from_audio(data, audio) is data


@pytest.mark.parametrize('period,offset', [(.3, .23), (.5, 1.13), (.7, .37)])
def test_short_syncopation_repairs_pulse_without_erasing_two_beat_bar(tmp_path, period, offset):
    actual = offset + np.arange(400) * period
    # Twelve detections follow accents at 4/3 of the pulse for sixteen beats.
    detected = np.r_[actual[:160], np.linspace(actual[160], actual[176], 13), actual[177:]]
    beats = np.round(detected, 3).tolist()
    # A genuine two-beat bar occurs later. It is independent of the missed beats.
    positions = list(range(0, 224, 4)) + list(range(222, len(beats), 4))
    data = dict(bpm=60/period, beats=beats, downbeats=[beats[i] for i in positions], duration=actual[-1]+period)
    audio = tmp_path / 'syncopated-short-bar.wav'
    attacks = list(actual[:160]) + list(actual[160] + np.arange(0, 16, .75) * period) + list(actual[176:])
    write_attacks(audio, attacks, data['duration'])
    result = refine_timing_from_audio(data, audio)
    fixed = np.asarray(result['beats'])
    assert len(fixed) == len(actual)
    assert np.max(abs(fixed - actual)) < .002
    # Repairing a fill must not recount subsequent short bars into 4/4.
    assert [b for b in result['downbeats'] if b > actual[180]] == [b for b in data['downbeats'] if b > actual[180]]


@pytest.mark.parametrize('period', [.3, .5, .7])
def test_short_real_rational_tempo_change_is_not_mistaken_for_syncopation(tmp_path, period):
    actual = .23 + np.arange(400) * period
    detected = np.r_[actual[:160], np.linspace(actual[160], actual[176], 13), actual[177:]]
    beats = np.round(detected, 3).tolist()
    data = dict(bpm=60/period, beats=beats, downbeats=beats[::4], duration=actual[-1]+period)
    audio = tmp_path / 'real-metric-modulation.wav'
    write_attacks(audio, beats, data['duration'])
    assert refine_timing_from_audio(data, audio)['beats'] == beats
