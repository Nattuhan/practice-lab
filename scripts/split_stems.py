from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from demucs_infer.separate import main as demucs_main

from practice_lab.compute_device import is_acceleration_compatibility_error, select_torch_device


def replace_device(args: list[str], device: str) -> list[str]:
    values = list(args)
    for flag in ("--device", "-d"):
        if flag in values:
            index = values.index(flag)
            values[index + 1] = device
            return values
    return ["--device", device, *values]


def requested_device(args: list[str]) -> str:
    for flag in ("--device", "-d"):
        if flag in args:
            return args[args.index(flag) + 1]
    return "auto"


def main(argv: list[str] | None = None):
    args = list(sys.argv[1:] if argv is None else argv)
    requested = requested_device(args)
    selected = select_torch_device(requested)
    resolved_args = replace_device(args, selected)
    if selected == "mps":
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    try:
        return demucs_main(resolved_args)
    except RuntimeError as exc:
        if requested != "auto" or selected != "mps" or not is_acceleration_compatibility_error(exc):
            raise
        print(f"[INFO] MPS backend is unavailable for stem separation; retrying on CPU: {exc}", file=sys.stderr)
        return demucs_main(replace_device(args, "cpu"))


if __name__ == "__main__":
    raise SystemExit(main())
