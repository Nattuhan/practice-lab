# デスクトップ版のリリース

## 配布物

Windows版はElectronの専用ウィンドウ、PyInstallerで固めたFastAPIバックエンド、Node.js、
FFmpegをNSISインストーラーへまとめます。音源解析とstems分離は同梱バックエンドではなく、
WSL2上のCUDAランタイムで実行します。

Apple Silicon Mac版は同じUIとFastAPIバックエンドに、PyTorch、NATTEN、all-in-one-fix、
Demucsを含むmacOSネイティブCPU解析環境を同梱します。Intel Macは対象外です。

アプリ本体と利用者データは分離されています。

- アプリ本体: NSISが管理するインストールディレクトリ
- 曲、解析結果、設定: `%LOCALAPPDATA%\PracticeLab`
- CUDA解析環境: `%LOCALAPPDATA%\PracticeLab\runtime\wsl\.venv`

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
- 差分更新用の`.blockmap`
- `PracticeLab-1.2.3-arm64.dmg`
- `PracticeLab-1.2.3-arm64.zip`
- `latest-mac.yml`

デスクトップアプリは起動後にGitHub Releasesを確認し、新版を取得します。ダウンロード完了後、
画面上の更新ボタンから再起動して適用できます。

## Windowsコード署名

正式配布ではGitHub ActionsのRepository secretsへ次を登録します。

- `WINDOWS_CERTIFICATE`: Base64化したコード署名証明書
- `WINDOWS_CERTIFICATE_PASSWORD`: 証明書のパスワード

未登録でも開発用インストーラーは生成できますが、Windowsに発行元不明の警告が表示されます。

## macOS署名とNotarization

正式タグではApple Developer ProgramのDeveloper ID Application証明書とNotarizationを必須にします。
GitHub ActionsのRepository secretsへ次を登録します。

- `MACOS_CERTIFICATE`: Developer ID Application証明書を含む`.p12`のBase64値
- `MACOS_CERTIFICATE_PASSWORD`: `.p12`のパスワード
- `APPLE_ID`: Apple Developer ProgramのApple ID
- `APPLE_APP_SPECIFIC_PASSWORD`: App用パスワード
- `APPLE_TEAM_ID`: Developer Team ID

正式タグで一つでも不足するとリリースを停止します。ビルド後は`codesign`、Gatekeeperの`spctl`、
Notarization ticketの`stapler`を検証します。

要件の根拠:

- [Apple: Notarizing macOS software before distribution](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [electron-builder: macOS Notarization](https://www.electron.build/docs/notarization/)

## NVIDIA初回セットアップ

アプリ内診断は次をすべて満たした場合のみ準備完了とします。

1. WindowsからNVIDIA GPUを認識できる
2. WSL2とUbuntuを起動できる
3. WSL2から`nvidia-smi`を実行できる
4. WSL側のPythonでPyTorch CUDA、NATTEN、all-in-one-fix、demucsを読み込める

不足時は`setup_desktop_nvidia.ps1`を別ウィンドウで実行します。WSL2自体がない場合だけ
Windowsの管理者確認が表示され、再起動後にセットアップをもう一度実行します。
