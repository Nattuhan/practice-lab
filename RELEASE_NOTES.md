# PracticeLab v1.0.2

音楽の解析と練習をひとつの画面で行えるデスクトップアプリです。

## ダウンロード

- **Windows**: `PracticeLab-Setup-1.0.2.exe`
- **macOS（Apple Silicon）**: `PracticeLab-1.0.2-arm64.dmg`

## v1.0.2の修正

- 一部のYouTube動画で解析開始時に403エラーが発生する問題を修正
- 匿名での再取得が拒否された場合、端末内のChrome系ブラウザのYouTubeセッションを使って再試行
- Windows版に同梱するYouTube取得処理を更新

## 主な機能

- YouTube URL・音声ファイルの解析
- 楽曲構成と小節の表示・編集
- テンポ変更、クリック、区間リピートに対応した練習プレイヤー
- ボーカル、ドラム、ベース、その他のパート分離
- NVIDIA GPUを利用したWindows向け解析環境
- Cloudflare R2を利用した端末間同期
- 暗号化接続ファイルによる別端末の追加
