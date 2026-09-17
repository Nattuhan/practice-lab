# Count voice samples

`count_voice.json` contains the isolated English count words one through twelve,
16 kHz mono signed 16-bit little-endian PCM encoded as base64. These are synthetic
Samantha speech samples generated locally with macOS `say` at 320 words/minute;
they contain no recording of a user or performer. Leading/trailing silence was
trimmed, peaks normalized to 0.8, and 2 ms edge fades applied.

The browser and export backend read the same asset. Speech is rendered into its
own channel beside the music, so decoder seeking, loops and pitch-preserving
speed changes act on both together. Runtime speech synthesis is not used.
