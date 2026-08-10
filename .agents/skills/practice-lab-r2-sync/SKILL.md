---
name: practice-lab-r2-sync
description: Safely publish PracticeLab UI, metadata, audio, video, stems, and session changes to Cloudflare R2 using the repository's hash-based incremental sync. Use for any PracticeLab UI/static viewer change, R2 publication, cloud sync, session asset update, or investigation of excessive R2 uploads.
---

# PracticeLab R2 差分同期

R2への通常配信では、未変更の音声・動画を再送しない。

## 通常の配信

リポジトリルートで次の順に実行する。

```powershell
.venv\Scripts\python.exe scripts\export_static.py
.venv\Scripts\python.exe scripts\sync_r2.py
```

`sync_r2.py` はローカルのサイズ・更新日時キャッシュとR2上のSHA-256台帳を比較し、新規・変更・削除だけを同期する。完了出力の `uploaded`、`deleted`、`unchanged` 件数をユーザーへ報告する。

## 強制同期

- 特定セッションだけ再送する場合: `scripts\sync_r2.py --session ID`
- 全セッションを再送する場合: `scripts\sync_r2.py --all-sessions`
- 台帳が存在せず、R2とローカルが一致していると確認済みの場合だけ: `scripts\sync_r2.py --initialize-index`

ユーザーが明示的に要求しない限り、`--all-sessions` を使用しない。台帳の初期化を通常同期として繰り返さない。

## 安全規則

- 同期前に `scripts/sync_r2.py` が差分同期実装のままか確認する。
- `warning: R2 CORS was not updated: AccessDenied` はアップロード完了時には非ブロッキングとして扱う。
- `public/audio/`、`public/video/`、`public/results/`、`public/score/`、`public/stems/` の生成物をコミットしない。
- 同期失敗時に全件同期へ切り替えない。原因を確認して差分同期を再実行する。
