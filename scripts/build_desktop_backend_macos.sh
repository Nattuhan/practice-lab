#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python_bin="${PYTHON_BIN:-$repo_root/.venv/bin/python}"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "The macOS desktop backend must be built on an Apple Silicon Mac." >&2
  exit 1
fi
if [[ ! -x "$python_bin" ]]; then
  echo "Python environment not found: $python_bin" >&2
  exit 1
fi

"$python_bin" -m pip install -r "$repo_root/requirements/desktop-build.txt"
"$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name practice-lab-backend \
  --paths "$repo_root" \
  --collect-all rapidocr_onnxruntime \
  --collect-all yt_dlp \
  --collect-all torch \
  --collect-all natten \
  --collect-all allin1fix \
  --collect-all demucs_infer \
  --hidden-import practice_lab.compute_device \
  --hidden-import practice_lab.jpop_sections \
  --hidden-import practice_lab.timing \
  --distpath "$repo_root/desktop/dist/backend" \
  --workpath "$repo_root/desktop/build/backend" \
  --specpath "$repo_root/desktop/build" \
  "$repo_root/desktop/backend_entry.py"
