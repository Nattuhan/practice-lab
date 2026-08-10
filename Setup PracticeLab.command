#!/bin/bash
set -o pipefail
cd "$(dirname "$0")"
bash scripts/setup_macos.sh
status=$?
echo
if [[ $status -eq 0 ]]; then
  echo "セットアップが完了しました。Start PracticeLab.command をダブルクリックして起動できます。"
else
  echo "セットアップに失敗しました。上のメッセージを確認してください。"
fi
read -r -p "Enterキーで閉じます。"
exit $status
