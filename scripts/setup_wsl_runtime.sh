#!/bin/bash
set -euo pipefail

runtime_root="${1:?runtime directory is required}"
venv="$runtime_root/.venv"

mkdir -p "$runtime_root"
if [[ ! -x "$venv/bin/python" ]]; then
  python3 -m venv "$venv"
fi

"$venv/bin/python" -m pip install --upgrade pip wheel setuptools

# Keep the complete analysis stack on one tested PyTorch ABI. In particular,
# NATTEN must not be allowed to upgrade torch as one of its dependencies.
"$venv/bin/python" -m pip install --force-reinstall \
  "torch==2.6.0" --index-url https://download.pytorch.org/whl/cu126
"$venv/bin/python" -m pip install --force-reinstall --no-deps \
  "torchaudio==2.6.0" --index-url https://download.pytorch.org/whl/cu126
"$venv/bin/python" -m pip install --force-reinstall --no-deps \
  "natten==0.17.5+torch260cu126" -f https://whl.natten.org
# The 2.0.4 release was removed from PyPI. Install the immutable upstream
# release commit instead of depending on a movable branch or a stale index.
"$venv/bin/python" -m pip install \
  "https://github.com/openmirlab/all-in-one-fix/archive/9ba8cac49d441f54e2d89aaefbd44acde8ee2c38.zip" \
  --no-build-isolation

if ! "$venv/bin/python" -c "import madmom" >/dev/null 2>&1; then
  "$venv/bin/python" -m pip install git+https://github.com/CPJKU/madmom
fi

"$venv/bin/python" - <<'PY'
import allin1fix
import demucs_infer
import natten
import torch
from importlib.metadata import version

assert torch.__version__.startswith("2.6.0+cu126"), torch.__version__
assert version("torchaudio").startswith("2.6.0+cu126"), version("torchaudio")
assert natten.__version__.startswith("0.17.5"), natten.__version__
assert torch.cuda.is_available(), "CUDA is not available"
print("GPU:", torch.cuda.get_device_name(0))
print("torch:", torch.__version__)
print("torchaudio:", version("torchaudio"))
print("natten:", natten.__version__)
print("allin1fix:", getattr(allin1fix, "__version__", "unknown"))
PY

touch "$runtime_root/.verified"
