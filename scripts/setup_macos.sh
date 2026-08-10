#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

step() {
  printf '\n[PracticeLab setup] %s\n' "$1"
}

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "このセットアップはApple Silicon Mac専用です。" >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrewが必要です。次の公式サイトからインストールして、もう一度実行してください。" >&2
  echo "https://brew.sh/" >&2
  open "https://brew.sh/"
  exit 1
fi

missing_formulas=()
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  missing_formulas+=(ffmpeg)
fi
if ! command -v node >/dev/null 2>&1; then
  missing_formulas+=(node)
fi
if [[ ! -x .venv/bin/python ]] && ! brew --prefix python@3.11 >/dev/null 2>&1; then
  missing_formulas+=(python@3.11)
fi

if (( ${#missing_formulas[@]} > 0 )); then
  step "不足している共通ツールを準備しています: ${missing_formulas[*]}"
  HOMEBREW_NO_AUTO_UPDATE=1 brew install "${missing_formulas[@]}"
fi

if [[ ! -f .env.local ]]; then
  cp .env.example .env.local
fi

if [[ ! -f public/app.js ]]; then
  step "ブラウザ用ファイルがないため構築しています"
  npm install
  npm run build
fi

if [[ -x .venv/bin/python ]]; then
  step "既存環境がそのまま使えるか確認しています"
  if ANALYZER_EXECUTOR=native ANALYZER_DEVICE=auto .venv/bin/python scripts/check_env.py >/dev/null 2>&1; then
    echo "既存環境は正常です。依存パッケージを変更せずに利用します。"
    exit 0
  fi
  step "既存環境に不足している依存を修復しています"
fi

if [[ ! -x .venv/bin/python ]]; then
  step "Python環境を作成しています"
  PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
  "$PYTHON" -m venv .venv
fi

step "アプリの依存パッケージをインストールしています"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements/app.txt

step "Apple Silicon用の解析環境をインストールしています"
.venv/bin/python -m pip install "torch==2.6.0"
.venv/bin/python -m pip install "natten==0.17.5" --no-build-isolation
.venv/bin/python -m pip install "all-in-one-fix==2.0.4" --no-build-isolation

step "環境を確認しています"
ANALYZER_EXECUTOR=native ANALYZER_DEVICE=auto .venv/bin/python scripts/check_env.py

echo
echo "セットアップが完了しました。"
