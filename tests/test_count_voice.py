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
