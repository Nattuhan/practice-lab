#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/python ]]; then
  echo "先に Setup PracticeLab.command をダブルクリックしてください。" >&2
  exit 1
fi

PORT="$(${PRACTICE_LAB_PYTHON:-.venv/bin/python} - <<'PY'
import socket
for port in range(8000, 8021):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("利用可能なポートがありません")
PY
)"
URL="http://127.0.0.1:${PORT}"

(
  for _ in $(seq 1 60); do
    if curl -fsS "${URL}/healthz" >/dev/null 2>&1; then
      open "$URL"
      exit 0
    fi
    sleep 0.5
  done
) &

echo "PracticeLabを ${URL} で起動します。終了するには Control+C を押してください。"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --log-level info --no-access-log
