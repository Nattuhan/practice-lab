# Scripts

補助スクリプト置き場です。普段の起動はリポジトリ直下の `start.bat` を使います。

- `check_env.py`: Windows 側と WSL 側の環境確認
- `setup_windows.ps1`: Windowsアプリと解析環境のセットアップ
- `setup_macos.sh`: Apple Silicon Mac用セットアップ
- `start.ps1`: `start.bat` から呼ばれる Windows 起動スクリプト
- `start_macos.sh`: Apple Silicon Mac用起動スクリプト
- `export_static.py`: `data/` の生成物を `public/` に同期
- `refresh_public.bat`: `export_static.py` の Windows ラッパー
- `publish_pages.bat`: `public/` を `gh-pages` に公開
- `setup_wsl.sh`: WSL 側の解析環境セットアップ
- `sync_r2.py`: ハッシュ比較で新規・変更・削除だけを Cloudflare R2 に同期。初回は `--initialize-index`、強制再送は `--session ID` または `--all-sessions`
- `verify_desktop_release.cjs`: 公開したデスクトップ版のCI、タグ、`main`、Release、必須配布物を一括検証
- `analyze_audio.py`: CUDA、MPS、CPUを選択する共通解析コマンド
- `build_count_voice_high.py`: 標準の読み上げ音声から5半音高い同じ長さの音声を再生成
- `split_stems.py`: CUDA、MPS、CPUを選択する共通stems分離コマンド
- `wsl_analyze.py` / `wsl_split_stems.py`: 旧呼び出しとの互換ラッパー
