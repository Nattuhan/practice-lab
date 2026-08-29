# PracticeLab v1.1.5

インストール容量と解析環境の選びやすさを改善し、設定・履歴・ストレージ管理を整理したリリースです。

## ダウンロード

- **Windows 10/11**: `PracticeLab-Setup-1.1.5.exe`
- **macOS（Apple Silicon）**: `PracticeLab-1.1.5-arm64.dmg`

Windows CPU解析と楽譜抽出は、アプリの「設定 → 追加機能」から必要な場合だけ追加できます。追加パックをReleaseページから手動で展開する必要はありません。

## v1.1.5の変更

- Windowsの初期解析環境をCPUに変更し、NVIDIA、WSL2、CUDAなしでも利用できるように改善
- NVIDIA GPU解析を任意の高速化オプションとして分離
- MacではApple Silicon CPU環境だけを表示し、不要なNVIDIA・WSL設定を非表示化
- 楽譜抽出を任意の追加機能へ分離し、基本インストーラーを軽量化
- 追加機能をアプリ更新後も再利用し、旧バージョンのパックを自動整理
- Electron内蔵Node.jsを再利用し、重複していたNode.js同梱を廃止
- macOSのFFprobeをApple Siliconネイティブ版へ変更
- 処理履歴、ストレージ、追加機能を設定画面へ統合
- Electronの画面・動画キャッシュを設定から整理できるように改善
- 同一内容の元動画と再生用動画をハードリンク化し、重複容量を削減
- ライブラリに紐づかない再生用ファイルを安全に整理する機能を追加
- 未署名配布版のインストール手順と、配布物のSHA-256一覧を追加

## 配布される追加パック

- `PracticeLab-Windows-CPU-1.1.5.zip`
- `PracticeLab-Score-Windows-1.1.5.zip`
- `PracticeLab-Score-macOS-arm64-1.1.5.zip`
- `PracticeLab-SHA256SUMS.txt`

追加パックはアプリがSHA-256を検証してから展開します。

## 未署名版について

このリリースは費用のかかるWindowsコード署名証明書とApple Developer IDを使用していません。WindowsではSmartScreen、MacではGatekeeperの確認が表示される場合があります。詳しい起動方法はリポジトリの`UNSIGNED_DISTRIBUTION.md`を参照してください。
