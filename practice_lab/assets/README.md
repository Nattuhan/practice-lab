# Count voice samples

`count_voice.json` and `count_voice_high.json` contain the isolated English count words one through twelve,
16 kHz mono signed 16-bit little-endian PCM encoded as base64. These are synthetic
Samantha speech samples generated locally with macOS `say` at 320 words/minute;
they contain no recording of a user or performer. Leading/trailing silence was
trimmed, peaks normalized to 0.8, and 2 ms edge fades applied.

The high variant raises Samantha's pitch base inside the speech synthesizer.
Generating the voice at the requested pitch preserves natural speech formants;
pitch-shifting the standard PCM after synthesis does not. The UI exposes it as
a voice option under the single `読み上げ` click type.

Regenerate the high variant with `.venv/bin/python scripts/build_count_voice_high.py`.

The browser and export backend read the same asset. Speech is rendered into its
own channel beside the music, so decoder seeking, loops and pitch-preserving
speed changes act on both together. Runtime speech synthesis is not used.
