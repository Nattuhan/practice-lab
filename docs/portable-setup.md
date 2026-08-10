# 別の利用者・別のPCへの導入

PracticeLabは、アプリのソースだけをGitで共有し、曲・解析結果・キャッシュ・認証情報は各PCに置く構成です。

## 対象環境

| PC | 解析経路 |
|---|---|
| Windows + NVIDIA GPU | WSL2上のCUDA |
| Windows + AMD RadeonまたはGPUなし | WindowsネイティブCPU |
| Apple Silicon Mac | MPSを優先し、非対応処理だけCPU |

WindowsのRadeon GPU専用アクセラレーションは現時点では対象外です。アプリはCPUへフォールバックするため利用できます。Intel MacとLinuxネイティブはサポート対象外です。

## 新しいPCで行うこと

1. Gitでリポジトリをcloneするか、ソースのZIPを展開します。
2. Windowsは `setup.bat`、Apple Silicon Macは `Setup PracticeLab.command` をダブルクリックします。
3. Windowsは `start.bat`、Macは `Start PracticeLab.command` をダブルクリックして起動します。
4. そのPCで使う曲を追加し、解析します。

セットアップはPython環境、解析器、実行に必要な共通ツールを準備し、環境確認まで行います。Macの初回起動でOSに止められた場合は、Finderでファイルを右クリックして「開く」を選びます。

再度セットアップを実行した場合は、最初に既存環境を確認します。正常ならパッケージを再インストールせず、そのまま終了します。不足や破損が検出された場合だけ、リポジトリ内のPython環境を修復します。曲・解析結果・既存の `.env.local` は変更しません。

Macでは、端末にないPython、ffmpeg、Node.jsだけをHomebrewで追加します。Homebrewの自動更新はセットアップ中には実行しません。Playwrightなどの開発・テスト専用ツールは通常セットアップの対象外です。

## 共有しないもの

- `data/` 以下の元音声、動画、解析結果、ジョブ状態、キャッシュ
- `public/audio/`、`public/video/`、`public/results/`、`public/score/`、`public/stems/` の生成物
- `.env.local` のR2認証情報など
- `.venv*` と `node_modules/`

これらは `.gitignore` の対象です。新しい利用者は曲と解析結果を自分のPCで作成します。

## 任意のクラウド閲覧

Cloudflare R2は、同じ利用者が解析済みセッションを別端末から閲覧するための任意機能です。解析そのものや個人間のデータ共有には必須ではありません。利用する場合だけ `.env.local` にPCごとの認証情報を設定します。

## 更新時

ソースを更新したら依存変更の有無にかかわらずセットアップ入口をもう一度実行できます。生成済みの曲データは `data/` に残り、Git更新とは分離されています。更新後は単純な解析を1件行い、使用中の解析経路で動作することを確認してください。
