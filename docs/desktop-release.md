# デスクトップ版のリリース

## 配布物

Windows版はElectronの専用ウィンドウ、PyInstallerで固めたFastAPIバックエンド、
FFmpegをNSISインストーラーへまとめます。Electron自身をYouTube取得処理のNode.jsとしても
利用するため、Node.jsを重複して同梱しません。音源解析とstems分離は初期状態でCPUを選び、
設定の「追加機能」からCPU解析パックを追加します。NVIDIA GPUを使いたい人だけ、解析環境を
NVIDIAへ切り替えてWSL2 CUDAランタイムをセットアップします。

Apple Silicon Mac版は同じUIとFastAPIバックエンドに、PyTorch、NATTEN、all-in-one-fix、
Demucsを含むmacOSネイティブCPU解析環境を同梱します。Intel Macは対象外です。
Apple Developer IDを使用しない無料配布ビルドには、DMG作成前にアドホック署名を施して
アプリバンドル内部の整合性を保証します。これはNotarizationの代替ではありません。

アプリ本体と利用者データは分離されています。

- アプリ本体: NSISが管理するインストールディレクトリ
- 曲、解析結果、設定: `%LOCALAPPDATA%\PracticeLab`
- Windows CPU解析環境: `%LOCALAPPDATA%\PracticeLab\runtime\windows-cpu`
- CUDA解析環境: `%LOCALAPPDATA%\PracticeLab\runtime\wsl\.venv`
- 楽譜抽出環境: 利用者データ内の`runtime/score`

そのため、アプリを更新しても曲、解析結果、CUDA環境は保持されます。

## ローカルビルド

Windowsのリポジトリ直下で実行します。

```powershell
npm install
npm run build
npm run desktop:prepare
npm run desktop:backend
npm run desktop:dist -- --publish=never
```

生成物は`desktop/dist/installer/`に作成されます。`desktop/bin/`、`desktop/build/`、
`desktop/dist/`はGit管理しません。

## GitHub Releases

`.github/workflows/release-desktop.yml`は手動実行時に未公開インストーラーをArtifactとして作成します。
`v1.2.3`形式のタグをpushすると、タグ番号をアプリのバージョンへ設定し、GitHub Releaseへ次を公開します。

- `PracticeLab-Setup-1.2.3.exe`
- `latest.yml`
- Windows差分更新用の`.exe.blockmap`
- `PracticeLab-1.2.3-arm64.dmg`
- `PracticeLab-Windows-CPU-1.2.3.zip`（アプリから必要時に取得）
- `PracticeLab-Score-Windows-1.2.3.zip`（アプリから必要時に取得）
- `PracticeLab-Score-macOS-arm64-1.2.3.zip`（アプリから必要時に取得）
- `PracticeLab-SHA256SUMS.txt`

Windows版は起動後にGitHub Releasesを確認し、新版を取得します。ダウンロード完了後、
画面上の更新ボタンから再起動して適用できます。Mac版はGitHub Releaseから新しいDMGを
取得して手動で入れ替えます。

## 無料・未署名での配布方針

有料のWindowsコード署名証明書とApple Developer Programは使用しません。Windows版は
未署名、Mac版はアドホック署名・未公証で配布します。CIは意図どおり未署名であること、Macの
アプリ内部が壊れていないことを検査し、全配布物のSHA-256をPracticeLab-SHA256SUMS.txtへ
記録します。利用者向け手順は[未署名配布版の案内](../UNSIGNED_DISTRIBUTION.md)に記載します。

## macOS署名とNotarization

現在のApple Silicon Mac版は、GitHub Actionsでアドホック署名した未公証DMGとして配布します。ビルド時に`codesign --verify --deep --strict`でアプリバンドルの整合性を検証し、Gatekeeperから信頼済みと誤認されないことも確認します。利用者向けの起動手順は[未署名配布版の案内](../UNSIGNED_DISTRIBUTION.md)に記載しています。

Developer ID署名とNotarizationは費用をかけない方針のため、現状の対象外です。

## Windowsの解析環境

初期値はCPUです。設定の「追加機能」からCPU解析機能を追加すれば、NVIDIA、WSL2、CUDAを
導入しなくても解析できます。GPUで高速化したい場合だけ「解析環境」でNVIDIAを選択します。

### NVIDIA初回セットアップ

アプリ内診断は次をすべて満たした場合のみ準備完了とします。

1. WindowsからNVIDIA GPUを認識できる
2. WSL2とUbuntuを起動できる
3. WSL2から`nvidia-smi`を実行できる
4. WSL側のPythonでPyTorch CUDA、NATTEN、all-in-one-fix、demucsを読み込める

不足時は`setup_desktop_nvidia.ps1`を別ウィンドウで実行します。WSL2自体がない場合だけ
Windowsの管理者確認が表示され、再起動後にセットアップをもう一度実行します。
