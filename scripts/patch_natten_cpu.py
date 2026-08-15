from __future__ import annotations

import sysconfig
from pathlib import Path


def main() -> None:
    testing_path = Path(sysconfig.get_paths()["purelib"]) / "natten" / "utils" / "testing.py"
    source = testing_path.read_text(encoding="utf-8")
    original = "_IS_TRITON_SUPPORTED = get_device_cc() >= 70"
    patched = "_IS_TRITON_SUPPORTED = _IS_CUDA_AVAILABLE and get_device_cc() >= 70"
    if patched in source:
        print("NATTEN CPU compatibility patch is already applied.")
        return
    if original not in source:
        raise RuntimeError(f"Unsupported NATTEN source layout: {testing_path}")
    testing_path.write_text(source.replace(original, patched, 1), encoding="utf-8")
    print(f"Applied NATTEN CPU compatibility patch: {testing_path}")


if __name__ == "__main__":
    main()
