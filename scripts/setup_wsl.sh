#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

verify_runtime() {
  .venv-wsl/bin/python - <<'PY'
import allin1fix, natten, torch, torchaudio
if not torch.cuda.is_available():
    raise SystemExit(1)
if not str(torch.__version__).startswith("2.6.0"):
    raise SystemExit(1)
if not str(natten.__version__).startswith("0.17.5"):
    raise SystemExit(1)
PY
}

if [[ -x ".venv-wsl/bin/python" ]] && verify_runtime >/dev/null 2>&1; then
  echo "既存のWSL CUDA解析環境は正常です。依存パッケージを変更せずに利用します。"
  exit 0
fi

if [[ ! -d ".venv-wsl" ]]; then
  python3 -m venv .venv-wsl
else
  echo "既存のWSL CUDA解析環境に不足している依存を修復します。"
fi

.venv-wsl/bin/python -m pip install --upgrade pip

# Use PyTorch 2.6.0 cu126 with the matching NATTEN CUDA wheel.
.venv-wsl/bin/python -m pip install --force-reinstall \
  --no-deps \
  torch==2.6.0 \
  --index-url https://download.pytorch.org/whl/cu126

# torchaudio's CUDA wheel is unstable in this environment, so keep the lightweight CPU build.
.venv-wsl/bin/python -m pip install --force-reinstall \
  --no-deps \
  torchaudio==2.6.0 \
  --index-url https://download.pytorch.org/whl/cpu

# Install the matching libnatten-enabled wheel explicitly.
.venv-wsl/bin/python -m pip install --force-reinstall \
  --no-deps \
  "natten==0.17.5+torch260cu126" \
  -f https://whl.natten.org

# Install the analyzer package and all inference dependencies after
# the ABI-sensitive torch/natten pair is in place.
.venv-wsl/bin/python -m pip install \
  all-in-one-fix==2.0.4 \
  --no-build-isolation

# madmom occasionally needs a manual install.
if ! .venv-wsl/bin/python - <<'PY'
import madmom
PY
then
  .venv-wsl/bin/python -m pip install git+https://github.com/CPJKU/madmom
fi

.venv-wsl/bin/python - <<'PY'
import allin1fix, natten, torch, torchaudio
print("allin1fix", getattr(allin1fix, "__version__", "unknown"))
print("torch", torch.__version__)
print("natten", natten.__version__)
print("torchaudio", torchaudio.__version__)
print("has_libnatten", getattr(natten, "HAS_LIBNATTEN", "unknown"))
print("cuda", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("CUDA is required, but torch.cuda.is_available() is false.")
PY
