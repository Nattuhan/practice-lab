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
  --collect-all yt_dlp \
  --collect-all torch \
  --collect-all natten \
  --collect-all allin1fix \
  --collect-all demucs_infer \
  --hidden-import practice_lab.score_extractor \
  --exclude-module cv2 \
  --exclude-module rapidocr_onnxruntime \
  --exclude-module onnxruntime \
  --exclude-module pyclipper \
  --exclude-module shapely \
  --hidden-import practice_lab.compute_device \
  --hidden-import practice_lab.jpop_sections \
  --hidden-import practice_lab.timing \
  --distpath "$repo_root/desktop/dist/backend" \
  --workpath "$repo_root/desktop/build/backend" \
  --specpath "$repo_root/desktop/build" \
  "$repo_root/desktop/backend_entry.py"

# Bind the packaged SSL module to the exact OpenSSL libraries used by the build
# Python. Older all-in-one builds also contained OpenCV's private copies; keep
# the cleanup conditional so the base app can exclude the optional score pack.
backend_internal="$repo_root/desktop/dist/backend/practice-lab-backend/_internal"
cv2_dylibs="$backend_internal/cv2/.dylibs"
python_ssl_module="$("$python_bin" -c 'import _ssl; print(_ssl.__file__)')"
if [[ -d "$cv2_dylibs" ]]; then
  find "$cv2_dylibs" -maxdepth 1 -type f \( -name 'libcrypto.3.dylib' -o -name 'libssl.3.dylib' \) -delete
fi
find "$backend_internal" -maxdepth 1 -type l \( -name 'libcrypto.3.dylib' -o -name 'libssl.3.dylib' \) -delete
for library in libcrypto.3.dylib libssl.3.dylib; do
  source_library="$(otool -L "$python_ssl_module" | awk -v suffix="/$library" '$1 ~ suffix "$" { print $1; exit }')"
  if [[ ! -f "$source_library" ]]; then
    echo "OpenSSL library used by Python was not found: $library" >&2
    exit 1
  fi
  cp "$source_library" "$backend_internal/$library"
done

# Bind Python's SSL extensions directly to the copies beside the packaged
# runtime. A generic @rpath lookup can otherwise reuse OpenCV's incompatible
# libcrypto when Electron launches the backend, even though a direct runtime
# check succeeds. Also remove the build machine's absolute Python.framework
# dependency from libssl so clean Macs use the bundled copy.
packaged_ssl_module="$(find "$backend_internal/lib-dynload" -maxdepth 1 -name '_ssl*.so' -print -quit)"
packaged_hashlib_module="$(find "$backend_internal/lib-dynload" -maxdepth 1 -name '_hashlib*.so' -print -quit)"
if [[ ! -f "$packaged_ssl_module" || ! -f "$packaged_hashlib_module" ]]; then
  echo "Packaged Python SSL extensions were not found" >&2
  exit 1
fi
install_name_tool -id '@rpath/libcrypto.3.dylib' "$backend_internal/libcrypto.3.dylib"
install_name_tool -id '@rpath/libssl.3.dylib' "$backend_internal/libssl.3.dylib"
install_name_tool \
  -change "$(otool -L "$backend_internal/libssl.3.dylib" | awk '$1 ~ /\/libcrypto\.3\.dylib$/ { print $1; exit }')" \
  '@loader_path/libcrypto.3.dylib' \
  "$backend_internal/libssl.3.dylib"
install_name_tool -change '@rpath/libssl.3.dylib' '@loader_path/../libssl.3.dylib' "$packaged_ssl_module"
install_name_tool -change '@rpath/libcrypto.3.dylib' '@loader_path/../libcrypto.3.dylib' "$packaged_ssl_module"
install_name_tool -change '@rpath/libcrypto.3.dylib' '@loader_path/../libcrypto.3.dylib' "$packaged_hashlib_module"

# install_name_tool invalidates the PyInstaller-provided ad-hoc signatures.
# Sign every modified Mach-O explicitly; signing only the outer .app does not
# cover arbitrary extension modules nested under Resources/backend.
for component in \
  "$backend_internal/libcrypto.3.dylib" \
  "$backend_internal/libssl.3.dylib" \
  "$packaged_ssl_module" \
  "$packaged_hashlib_module"; do
  codesign --force --sign - "$component"
done
