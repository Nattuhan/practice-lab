"""Build the higher count voice from the checked-in standard samples."""

import base64
import json
from pathlib import Path

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "practice_lab/assets/count_voice.json"
DESTINATION = ROOT / "practice_lab/assets/count_voice_high.json"
SEMITONES = 5
TARGET_PEAK = 0.8
FADE_SECONDS = 0.002


def main() -> None:
    source = json.loads(SOURCE.read_text())
    sample_rate = int(source["sampleRate"])
    rendered: dict[str, str] = {}
    for number, encoded in source["samples"].items():
        samples = np.frombuffer(base64.b64decode(encoded), dtype="<i2").astype(np.float32) / 32768
        # Pitch shift keeps the sample count unchanged, so both variants occupy
        # the same beat window and speed changes stretch them identically.
        shifted = librosa.effects.pitch_shift(samples, sr=sample_rate, n_steps=SEMITONES)
        peak = float(np.max(np.abs(shifted)))
        if peak:
            shifted *= TARGET_PEAK / peak
        fade_frames = min(round(sample_rate * FADE_SECONDS), len(shifted) // 2)
        if fade_frames:
            fade = np.linspace(0, 1, fade_frames, endpoint=False, dtype=np.float32)
            shifted[:fade_frames] *= fade
            shifted[-fade_frames:] *= fade[::-1]
        pcm = np.rint(np.clip(shifted, -1, 1) * 32767).astype("<i2")
        rendered[number] = base64.b64encode(pcm.tobytes()).decode("ascii")
    DESTINATION.write_text(json.dumps({
        "sampleRate": sample_rate,
        "encoding": "pcm_s16le_base64",
        "pitchSemitones": SEMITONES,
        "samples": rendered,
    }, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
