"""Build the natural higher-pitched count voice with macOS speech synthesis."""

import base64
import json
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "practice_lab/assets/count_voice_high.json"
SAMPLE_RATE = 16_000
VOICE = "Samantha"
WORDS_PER_MINUTE = 320
# Raising Samantha's pitch inside the synthesizer preserves the voice's formants.
# Post-processing the standard samples by five semitones made consonants metallic.
PITCH_BASE = 52
TARGET_PEAK = 0.8
FADE_SECONDS = 0.002
WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}


def render_word(word: str, output: Path) -> np.ndarray:
    subprocess.run(
        [
            "say",
            "-v",
            VOICE,
            "-r",
            str(WORDS_PER_MINUTE),
            "-o",
            str(output),
            f"[[pbas {PITCH_BASE}]] {word}",
        ],
        check=True,
    )
    samples, _ = librosa.load(output, sr=SAMPLE_RATE, mono=True)
    samples, _ = librosa.effects.trim(samples, top_db=35)
    peak = float(np.max(np.abs(samples)))
    if peak:
        samples *= TARGET_PEAK / peak
    fade_frames = min(round(SAMPLE_RATE * FADE_SECONDS), len(samples) // 2)
    if fade_frames:
        fade = np.linspace(0, 1, fade_frames, endpoint=False, dtype=np.float32)
        samples[:fade_frames] *= fade
        samples[-fade_frames:] *= fade[::-1]
    return samples


def main() -> None:
    rendered: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="practice-lab-count-voice-") as directory:
        temporary_directory = Path(directory)
        for number, word in WORDS.items():
            samples = render_word(word, temporary_directory / f"{number}.aiff")
            pcm = np.rint(np.clip(samples, -1, 1) * 32767).astype("<i2")
            rendered[str(number)] = base64.b64encode(pcm.tobytes()).decode("ascii")
    DESTINATION.write_text(
        json.dumps(
            {
                "sampleRate": SAMPLE_RATE,
                "encoding": "pcm_s16le_base64",
                "synthesizer": "macOS say",
                "voice": VOICE,
                "wordsPerMinute": WORDS_PER_MINUTE,
                "pitchBase": PITCH_BASE,
                "samples": rendered,
            },
            separators=(",", ":"),
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
