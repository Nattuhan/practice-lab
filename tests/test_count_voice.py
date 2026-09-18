import json
import wave
from unittest.mock import patch

from practice_lab import services
from practice_lab.count_voice import voice_samples


def test_export_uses_numbered_voice_and_restarts_at_short_bar(tmp_path):
    rate, voices = voice_samples()
    assert rate == 16000 and set(voices) == set(range(1,13))
    counts = [1,2,3,4,1,2,1,2,3,4]
    with patch.object(services, 'DATA_WORK_DIR', tmp_path):
        path = services.create_export_click_track([i*.36 for i in range(10)],80,'voice',click_counts=counts)
    with wave.open(str(path)) as wav:
        data = wav.readframes(wav.getnframes());width=wav.getsampwidth();out_rate=wav.getframerate()
    # The identical "one" occurs at each measured bar head, including after 2/4.
    def chunk(i):
        start=round(i*.36*out_rate)*width
        return data[start:start+round(.15*out_rate)*width]
    assert chunk(0)==chunk(4)==chunk(6)
    assert chunk(0)!=chunk(1)


def test_export_supports_high_voice_variant(tmp_path):
    _, normal = voice_samples()
    _, high = voice_samples('high')
    assert high[1] != normal[1]
    with patch.object(services, 'DATA_WORK_DIR', tmp_path):
        path = services.create_export_click_track(
            [0], 80, 'voice', voice_pitch='high', click_counts=[1]
        )
    with wave.open(str(path)) as wav:
        rendered = wav.readframes(wav.getnframes())
    assert rendered[:2000] != bytes(2000)


def test_high_voice_is_naturally_synthesized_at_requested_pitch():
    from practice_lab.config import SOURCE_ROOT

    high = json.loads((SOURCE_ROOT / 'practice_lab/assets/count_voice_high.json').read_text())
    assert high['voice'] == 'Samantha'
    assert high['pitchBase'] == 52
    _, standard_samples = voice_samples('standard')
    _, high_samples = voice_samples('high')
    assert set(standard_samples) == set(high_samples) == set(range(1, 13))
    assert all(high_samples[number] != standard_samples[number] for number in range(1, 13))
