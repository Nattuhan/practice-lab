from __future__ import annotations

from pathlib import Path

import soundfile as sf
import torch

__version__ = "shim"


def load(filepath: str | Path):
    audio, sample_rate = sf.read(str(filepath), always_2d=True, dtype="float32")
    tensor = torch.from_numpy(audio.T.copy())
    return tensor, sample_rate


def save(
    filepath: str | Path,
    src: torch.Tensor,
    sample_rate: int,
    encoding: str | None = None,
    bits_per_sample: int | None = None,
):
    path = Path(filepath)
    wav = src.detach().cpu()
    if wav.ndim == 1:
        wav = wav.unsqueeze(0)
    audio = wav.transpose(0, 1).numpy()

    subtype = None
    if encoding == "PCM_F":
        subtype = "FLOAT"
    elif bits_per_sample == 24:
        subtype = "PCM_24"
    elif bits_per_sample == 32:
        subtype = "PCM_32"
    else:
        subtype = "PCM_16"

    sf.write(str(path), audio, sample_rate, subtype=subtype)
