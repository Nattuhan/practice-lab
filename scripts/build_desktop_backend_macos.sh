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

# OpenCV bundles its own OpenSSL under cv2/.dylibs. Leaving that copy in place
# can make the dynamic loader choose a libcrypto that is incompatible with
# Python's ssl module, so the packaged backend exits before startup. Replace
# the duplicates with the exact libraries used by the build Python.
backend_internal="$repo_root/desktop/dist/backend/practice-lab-backend/_internal"
cv2_dylibs="$backend_internal/cv2/.dylibs"
python_ssl_module="$("$python_bin" -c 'import _ssl; print(_ssl.__file__)')"
find "$cv2_dylibs" -maxdepth 1 -type f \( -name 'libcrypto.3.dylib' -o -name 'libssl.3.dylib' \) -delete
find "$backend_internal" -maxdepth 1 -type l \( -name 'libcrypto.3.dylib' -o -name 'libssl.3.dylib' \) -delete
for library in libcrypto.3.dylib libssl.3.dylib; do
  source_library="$(otool -L "$python_ssl_module" | awk -v suffix="/$library" '$1 ~ suffix "$" { print $1; exit }')"
  if [[ ! -f "$source_library" ]]; then
    echo "OpenSSL library used by Python was not found: $library" >&2
    exit 1
  fi
  cp "$source_library" "$backend_internal/$library"
done
