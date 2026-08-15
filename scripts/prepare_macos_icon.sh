#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
source_png="$repo_root/desktop/assets/practicelab-icon.png"
output="$repo_root/desktop/assets/practicelab-icon.icns"
temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/practicelab-icon.XXXXXX")"
iconset="$temporary_root/PracticeLab.iconset"
trap 'rm -rf "$temporary_root"' EXIT

mkdir -p "$iconset"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$source_png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$source_png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$output"
echo "Prepared macOS application icon."
