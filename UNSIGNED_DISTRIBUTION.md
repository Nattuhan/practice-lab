# 未署名配布版のインストール

PracticeLabは費用のかかるコード署名証明書やApple Developer Programを使用せず、GitHub Releasesから無料配布しています。そのため、OSから「発行元を確認できない」という警告が表示されます。必ず公式の[GitHub Releases](https://github.com/Nattuhan/practice-lab/releases/latest)から取得してください。

## ダウンロードを確認する

同じReleaseにある`PracticeLab-SHA256SUMS.txt`には、各インストーラーのSHA-256が記録されています。

macOSではターミナルで次を実行し、表示された値がファイル内の値と一致することを確認できます。

```bash
shasum -a 256 ~/Downloads/PracticeLab-*-arm64.dmg
```

WindowsではPowerShellで確認できます。

```powershell
Get-FileHash "$HOME\Downloads\PracticeLab-Setup-*.exe" -Algorithm SHA256
```

## Mac（Apple Silicon）

1. DMGを開き、PracticeLabを「アプリケーション」へドラッグします。
2. Finderの「アプリケーション」でPracticeLabをControlキーを押しながらクリックし、「開く」を選びます。
3. 確認画面でもう一度「開く」を選びます。

通常のダブルクリックで拒否された場合は、システム設定の「プライバシーとセキュリティ」に表示されるPracticeLabの「このまま開く」も利用できます。Intel Macには対応していません。

## Windows 10/11

1. インストーラーを起動します。
2. Microsoft Defender SmartScreenが表示されたら、ファイル名と入手元が公式Releaseであることを確認します。
3. 「詳細情報」から実行を選びます。

解析はCPUが初期値です。NVIDIAやWSL2は必須ではありません。初回は設定の「追加機能」からWindows CPU解析機能を追加してください。NVIDIA GPUで高速化したい場合だけ、設定の「解析環境」でNVIDIAを選んでセットアップします。

## 更新

Windows版はアプリ内で更新を確認できます。Mac版は新しいDMGを公式Releaseから取得し、アプリケーション内の旧版と入れ替えます。曲、設定、処理履歴、追加機能はアプリ本体とは別の場所に保存されるため、通常の更新では消えません。
