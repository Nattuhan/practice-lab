import numpy as np
import pytest
import soundfile as sf
from scipy.signal import butter, sosfilt

from practice_lab.metrical_tempo import resolve_tempo_octave


def write_drums(path, period, offset, count=192, *, hats=True, snare_first=False,
                inverted=False, four_on_floor=False, change_at=None, only_hats=False,
                kick_frequency=65, snare_frequency=220, slow_windows=(),
                ambiguous_windows=()):
    rate = 8000
    rng = np.random.default_rng(812)
    duration = offset + count * period
    samples = np.zeros(round(duration * rate), dtype=np.float32)
    t = np.arange(round(.16 * rate)) / rate
    kick = np.sin(2 * np.pi * kick_frequency * t) * np.exp(-t * 35)
    body = np.sin(2 * np.pi * snare_frequency * t) * np.exp(-t * 28)
    noise = sosfilt(butter(3, [450, 1800], 'bandpass', fs=rate, output='sos'), rng.normal(size=len(t)))
    snare = .5 * body + noise * np.exp(-t * 35)
    hat = sosfilt(butter(3, [2900, 3700], 'bandpass', fs=rate, output='sos'), rng.normal(size=len(t)))
    hat *= np.exp(-t * 85) * .35

    def add(time, sound):
        first = round(time * rate)
        last = min(len(samples), first + len(sound))
        samples[first:last] += sound[:last - first]

    for i in range(count):
        time = offset + i * period
        window = i // 32
        if not only_hats and window not in ambiguous_windows:
            is_snare = (i + int(snare_first)) % 2 != 0
            if (change_at is not None and i >= change_at) or window in slow_windows:
                # The second region really has the slower kick/snare pattern.
                is_snare = (i // 2 + int(snare_first)) % 2 != 0
                if i % 2 == 0:
                    add(time, snare if is_snare else kick)
            else:
                add(time, snare if is_snare else kick)
                if four_on_floor and is_snare:
                    add(time, kick)
        if hats:
            for fraction in (0, .25, .5, .75):
                add(time + fraction * period, hat)
    if inverted:
        samples = np.column_stack([samples, -samples])
    sf.write(path, samples, rate, subtype='FLOAT')
    return duration


def detected_grid(period, offset, count=96):
    beats = np.round(offset + np.arange(count) * period, 3).tolist()
    sections = [dict(label='verse', start_time=offset, end_time=beats[-1])]
    return dict(bpm=60 / period, beats=beats, downbeats=beats[::4], total_bars=len(beats[::4]),
                duration=beats[-1] + period, sections=sections, automaticSections=sections)


@pytest.mark.parametrize('period,offset', [(.55, .13), (.375, 1.27), (.29, 2.13)])
@pytest.mark.parametrize('inverted', [False, True])
def test_recognizes_half_time_from_alternating_drum_accents(tmp_path, period, offset, inverted):
    audio = tmp_path / 'arbitrary-recording.wav'
    write_drums(audio, period, offset, inverted=inverted)
    original = detected_grid(period * 2, offset)
    result = resolve_tempo_octave(original, audio)
    assert result['bpm'] == round(original['bpm'] * 2, 1)
    assert len(result['beats']) == 191
    assert np.max(abs(np.asarray(result['beats']) - (offset + np.arange(191) * period))) < .0011
    assert result['total_bars'] == len(result['downbeats']) == 48
    assert result['sections'][0]['bar_count'] == 48
    assert result['automaticSections'] == result['sections']
    assert resolve_tempo_octave(result, audio) == result


@pytest.mark.parametrize('period', [.8, .63, .45])
@pytest.mark.parametrize('case', ['backbeat', 'four_on_floor', 'only_hats', 'silence'])
def test_keeps_real_slow_tempos_even_with_dense_hats(tmp_path, period, case):
    audio = tmp_path / 'slow-recording.wav'
    if case == 'silence':
        sf.write(audio, np.zeros(round(100 * period * 8000)), 8000)
    else:
        write_drums(audio, period, .17, count=96, four_on_floor=case == 'four_on_floor',
                    only_hats=case == 'only_hats')
    original = detected_grid(period, .17)
    assert resolve_tempo_octave(original, audio) is original


def test_keeps_uncertain_tempo_when_passages_disagree(tmp_path):
    audio = tmp_path / 'mixed-feel.wav'
    write_drums(audio, .32, .17, count=192, change_at=64)
    original = detected_grid(.64, .17)
    assert resolve_tempo_octave(original, audio) is original


@pytest.mark.parametrize('period', [.27, .33, .48])
def test_promotes_majority_clock_despite_distributed_half_time_breakdowns(tmp_path, period):
    audio = tmp_path / f'half-time-breakdowns-{period}.wav'
    fast_windows = {0, 1, 3, 4, 6, 8, 10, 12, 15, 18}
    slow_windows = {2, 7, 13, 16}
    ambiguous_windows = set(range(19)) - fast_windows - slow_windows
    write_drums(audio, period, .17, count=19 * 32 + 2,
                slow_windows=slow_windows, ambiguous_windows=ambiguous_windows)
    original = detected_grid(period * 2, .17, count=19 * 16 + 1)
    result = resolve_tempo_octave(original, audio)
    assert result['bpm'] == round(original['bpm'] * 2, 1)
    assert result['tempoOctaveResolution']['version'] == 3
    assert result['tempoOctaveResolution']['fasterVotes'] >= 10
    assert result['tempoOctaveResolution']['originalVotes'] >= 4


def test_backbeat_phase_is_inferred_when_detector_follows_snare(tmp_path):
    audio = tmp_path / 'snare-phase.wav'
    write_drums(audio, .32, .17, snare_first=True)
    original = detected_grid(.64, .17)
    result = resolve_tempo_octave(original, audio)
    assert result['bpm'] == 187.5
    assert result['tempoOctaveResolution']['kickParity'] == 1
    assert result['downbeats'][0] == .49


def test_keeps_mixed_meter(tmp_path):
    audio = tmp_path / 'mixed-meter.wav'
    write_drums(audio, .32, .17)
    original = detected_grid(.64, .17)
    original['downbeats'][2] = original['beats'][7]
    assert resolve_tempo_octave(original, audio) is original


def test_fresh_analysis_entry_resolves_octave_without_saved_song_data(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    import sys
    from pathlib import Path
    from types import SimpleNamespace

    audio = tmp_path / 'new-input.wav'
    write_drums(audio, .375, .17)
    detected = detected_grid(.75, .17)
    model_result = SimpleNamespace(path=audio, bpm=80, beats=detected['beats'],
                                   downbeats=detected['downbeats'], segments=[])
    monkeypatch.setitem(sys.modules, 'allin1fix', SimpleNamespace(analyze=lambda *args, **kwargs: model_result))
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))))
    spec = importlib.util.spec_from_file_location('octave_entry_test', Path(__file__).resolve().parents[1] / 'scripts/analyze_audio.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for _ in range(2):
        assert module.main([str(audio), '--device', 'cpu']) == 0
        result = json.loads(capsys.readouterr().out)
        assert result['bpm'] == 160
        assert len(result['beats']) == 191
        assert result['tempoOctaveResolution']['fromBpm'] == 80


def test_keeps_tempo_when_long_passages_support_opposite_levels(tmp_path):
    audio = tmp_path / 'opposing-passages.wav'
    write_drums(audio, .32, .17, count=384, change_at=192)
    original = detected_grid(.64, .17, count=192)
    assert resolve_tempo_octave(original, audio) is original


@pytest.mark.parametrize('kick,snare', [(48, 170), (95, 310), (65, 390)])
@pytest.mark.parametrize('half_time', [False, True])
def test_decision_survives_different_drum_tunings(tmp_path, kick, snare, half_time):
    audio = tmp_path / 'different-drums.wav'
    period = .38 if half_time else .76
    write_drums(audio, period, .29, count=192 if half_time else 96,
                kick_frequency=kick, snare_frequency=snare)
    original = detected_grid(.76, .29)
    result = resolve_tempo_octave(original, audio)
    if half_time:
        assert result['bpm'] == round(original['bpm'] * 2, 1)
    else:
        assert result is original

@pytest.mark.parametrize('period,offset', [(.28, .17), (.36, 1.13), (.47, .29)])
def test_octave_promotion_preserves_short_bar_after_audio_verified_repair(tmp_path, period, offset):
    from practice_lab.audio_timing import refine_timing_from_audio

    audio = tmp_path / 'short-bar.wav'
    write_drums(audio, period, offset, count=514)
    actual = offset + np.arange(257) * period * 2
    # The detector stretches four slow intervals over five. Its next measured
    # bar head remains correct; this is 4 + 4 + 2 beats at the true tempo.
    detected = np.r_[actual[:64], np.linspace(actual[64], actual[69], 5)[:-1], actual[69:]]
    beats = np.round(detected, 3).tolist()
    raw = dict(bpm=30 / period, beats=beats, downbeats=beats[::4],
               duration=float(actual[-1]), sections=[])
    repaired = refine_timing_from_audio(raw, audio)
    result = resolve_tempo_octave(repaired, audio)
    assert result['bpm'] == round(60 / period, 1)
    heads = np.asarray(result['downbeats'])
    end = round(float(actual[69]), 3)
    index = int(np.argmin(abs(heads - end)))
    assert abs(heads[index] - end) < .002
    assert abs(heads[index] - heads[index - 1] - 2 * period) < .002
    assert np.max(abs(np.diff(heads[index:]) - 4 * period)) < .002
    assert resolve_tempo_octave(result, audio) is result


def test_entry_uses_app_logic_when_runtime_has_preloaded_old_package(tmp_path, monkeypatch):
    import inspect
    import runpy
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    import practice_lab

    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(practice_lab, '__path__', [str(tmp_path / 'old-runtime')])
    monkeypatch.setitem(sys.modules, 'practice_lab.metrical_tempo',
                        SimpleNamespace(resolve_tempo_octave=lambda data, audio: data))
    monkeypatch.setitem(sys.modules, 'allin1fix', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace())
    entry = runpy.run_path(str(root / 'scripts/analyze_audio.py'), run_name='test_entry')
    for name, filename in [('normalize_tempo_grid', 'timing.py'),
                           ('refine_timing_from_audio', 'audio_timing.py'),
                           ('resolve_tempo_octave', 'metrical_tempo.py')]:
        assert Path(inspect.getfile(entry[name])) == root / 'practice_lab' / filename
