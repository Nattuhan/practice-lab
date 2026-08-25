# Repository Instructions

- Cloudflare/R2への配信、同期、UI・静的ビューア変更では、リポジトリ内の `$practice-lab-r2-sync` スキルを使用する。
- PracticeLabのデスクトップリリース作成、GitHub Release公開、公開DMGからのMac更新では、リポジトリ内の `$practice-lab-release` スキルを使用する。
- UI or static viewer changes that affect Cloudflare/R2 delivery must be followed by:
  - `.venv\Scripts\python.exe scripts\export_static.py`
  - `.venv\Scripts\python.exe scripts\sync_r2.py`
- Treat `warning: R2 CORS was not updated: AccessDenied` as non-blocking when uploads complete; it means the token lacks CORS-write permission, not that asset upload failed.
- Do not commit generated runtime assets under `public/audio/`, `public/video/`, `public/results/`, `public/score/`, or `public/stems/`.
