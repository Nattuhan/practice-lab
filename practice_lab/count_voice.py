"""Short prerecorded count words shared with the browser's aligned audio."""
import base64
import json
from array import array
from functools import lru_cache

from .config import SOURCE_ROOT


@lru_cache(maxsize=1)
def voice_samples():
    data = json.loads((SOURCE_ROOT / 'practice_lab/assets/count_voice.json').read_text())
    return data['sampleRate'], {int(n): array('h', base64.b64decode(encoded)) for n, encoded in data['samples'].items()}
