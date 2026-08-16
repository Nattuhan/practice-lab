# PracticeLab

[プライバシー](PRIVACY.md) · [セキュリティ](SECURITY.md) · [第三者ソフトウェア](THIRD_PARTY_NOTICES.md)

YouTube 音源を解析して、楽曲構成、拍、小節、練習用再生、動画からの譜面画像抽出をまとめて扱うローカル実行ツールです。

主な機能:

- Music Structure 解析
  YouTube 音源から BPM、拍、ダウンビート、セクション、小節範囲を推定します。
- 練習用プレイヤー
  解析済み音源と動画を同期して再生し、セクションジャンプ、ループ、クリック、速度変更ができます。
- Score Extractor
  動画内の譜面領域を切り出し、重複フレームを除去して PNG と ZIP に書き出します。A4、A3 見開き、縦長 PNG に対応しています。
- 静的閲覧版の書き出し
  解析済みセッションを `public/` に同期し、静的ホスティング向けに公開できます。
- ライブラリ管理
  曲名・タグ検索、未練習の絞り込み、最近練習した順の並べ替えに対応します。音声の再生を開始した時点で練習済みになります。
- セクション編集
  自動解析した小節範囲を分割・結合・名称変更でき、自動解析結果へ戻すこともできます。
- 再起動復旧
  処理中にアプリを終了したジョブを保存し、次回起動時に利用者が「再開」を押して続行できます。
- 容量とキャッシュ
  データ種別ごとの使用量を確認し、再生成できる作業キャッシュ・ログ・解析モデルだけを整理できます。

このリポジトリでは、ソースコードと生成物を分けて扱います。

- Git で管理するもの
  アプリ本体、静的 UI、本当に必要な補助スクリプト
- Git で管理しないもの
  解析結果 JSON、公開用 mp3、作業キャッシュ、ログ

## サポート環境

正式な対象は **Windows 10/11** と **Apple Silicon Mac** です。解析器は利用可能な
アクセラレーターを自動選択し、利用できない処理はCPUで実行します。

| 環境 | 状態 | 備考 |
|---|---|---|
| Windows 10/11 + NVIDIA | サポート対象 | WSL2経由でCUDAを使用します |
| Windows 10/11、NVIDIAなし | サポート対象 | WindowsネイティブCPUで解析します |
| Apple Silicon Mac | サポート対象 | MPSを優先し、処理単位でCPUへフォールバックします |
| Intel Mac | 対象外 | CPUで動作する可能性はありますが検証しません |
| Linux ネイティブ | 対象外 | Windows内部のWSLはNVIDIA解析用の実装詳細です |

`ANALYZER_DEVICE` と `STEM_DEVICE` は通常 `auto` のまま使用します。問題の切り分け時には
`cuda`、`mps`、`cpu` を明示できます。

## リポジトリ境界

- `start.bat`
  Windows 用の起動入口。まずこれを実行する
- `practice_lab/`
  FastAPI アプリ本体
- `public/`
  追跡対象は `index.html` `app.js` `styles.css` のみ
- `public/results/`
  生成物。Git では管理しない
- `public/audio/`
  生成物。Git では管理しない
- `data/`
  ランタイム専用。Git では管理しない
- `docs/`
  設計メモや作業計画など、実行に不要なドキュメント
- `data/audio/`
  解析用 `wav` キャッシュ
- `data/results/`
  正本の解析結果 JSON
- `data/work/`
  `allin1fix` / `demucs` の中間生成物
- `main.py`
  ASGI エントリポイント
- `requirements/`
  Windows アプリ用と WSL 解析用の依存ファイル
- `scripts/`
  環境確認、静的書き出し、GitHub Pages 公開、WSL 解析用の補助スクリプト

## 必要なもの

- Windows 10/11 または Apple Silicon Mac
- WindowsはPython 3.10、MacはPython 3.11
- WindowsでNVIDIAを使う場合だけWSL2 Ubuntu
- `ffmpeg`
- Node.js
  `yt-dlp` の YouTube 取得処理で使用します。

## 依存の切り分け

- `.venv`
  FastAPI サーバーと UI 用。`requirements/app-py310.txt` または `requirements/app.txt` を使う
- `.venv-wsl`
  Windows＋NVIDIAでのみ使用するWSL解析用環境

Windows＋NVIDIAではアプリ用PythonとWSL解析用Pythonを分けます。Windows CPUとMacでは
`all-in-one-fix` をアプリと同じネイティブ環境に入れます。

## セットアップ

通常はリポジトリ直下のセットアップ入口をダブルクリックします。

Windows:

```text
setup.bat
```

Apple Silicon Mac:

```text
Setup PracticeLab.command
```

ターミナルからは `scripts/setup_windows.ps1` または `scripts/setup_macos.sh` を直接実行できます。

別の利用者・別のPCへ導入するときは、リポジトリをcloneまたはZIPで展開し、上記のセットアップ入口を実行します。
`data/` と `public/{audio,video,results,score,stems}/` はGitに含めないため、曲と解析結果は各PCで個別に作成されます。
環境変数は `.env.example` を元に各PCの `.env.local` へ保存し、認証情報は共有・コミットしません。
詳しくは [`docs/portable-setup.md`](docs/portable-setup.md) を参照してください。

### 1. アプリ用 venv

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements/app-py310.txt
```

### Windows＋NVIDIAのWSL解析用 venv

GPU 解析は `torch 2.6.0 cu126 + natten 0.17.5+torch260cu126` の組み合わせを前提にします。これは NATTEN の公式ホイールがあり、`all-in-one-fix 2.0.4` と互換が取れる構成です。

```bash
bash scripts/setup_wsl.sh
```

`madmom` の自動導入に失敗する場合は次を追加で実行します。

```bash
pip install git+https://github.com/CPJKU/madmom
```

Windows＋NVIDIAではWSL CUDAを使用します。NVIDIAのないWindowsとMacでは共通の
ネイティブ解析コマンドを使用します。

WSL では `torchaudio` の CUDA/ABI 相性が崩れやすいため、リポジトリ直下の
[`torchaudio/__init__.py`](torchaudio/__init__.py) に最小shimを置いています。
`all-in-one-fix` と `demucs_infer` が使う `load/save` だけを満たす目的です。

環境確認:

```powershell
python scripts\check_env.py
```

## 起動

Windows では、リポジトリ直下の `start.bat` を実行します。

```powershell
.\start.bat
```

起動後、ブラウザで `http://127.0.0.1:8000` を自動で開きます。
すでに同じポートで PracticeLab が動いている場合は、その画面を開くだけで終了します。
8000 番が別プロセスで使われている場合は、8001 以降の空きポートで起動します。

ブラウザを自動で開きたくない場合:

```powershell
.\start.bat -NoBrowser
```

手動で起動する場合:

```powershell
python -m uvicorn main:app --reload
```

Apple Silicon Macでは `Start PracticeLab.command` をダブルクリックします。ターミナルからは
`bash scripts/start_macos.sh` でも起動できます。

## Windowsデスクトップ版

Windows＋NVIDIAを最初のデスクトップ配布対象にしています。GitHub Releasesの
`PracticeLab-Setup-<version>.exe`からインストールすると、専用ウィンドウで起動し、
Python、Node.js、FFmpegを個別に起動する必要はありません。

初回起動時には、NVIDIA GPU、WSL2、WSL内CUDA、解析ライブラリを順番に診断します。
不足している場合は画面の「NVIDIAセットアップ」から準備できます。解析用CUDA環境は
初回のみユーザーのアプリデータ領域へインストールされ、通常のアプリ更新では再取得しません。
曲、解析結果、設定もアプリ本体とは別のユーザーデータ領域に保存されます。

リリースと署名、自動更新の構成は [`docs/desktop-release.md`](docs/desktop-release.md) を参照してください。

## ライブラリと復旧の仕様

- 音声の再生開始を「練習済み」とし、練習回数と最終練習日時を端末内の解析JSONへ保存します。
- タグも端末内の解析JSONへ保存します。曲名・タグ検索、未練習の絞り込み、追加順・曲名順・最近練習した順を利用できます。
- 実行中のジョブは `data/jobs.json` に保存します。異常終了や再起動後は自動実行せず、画面の「再開」を押したときだけ新しいジョブとして再投入します。
- 容量画面から削除できるのは再生成可能なキャッシュだけです。元音声、動画、stems、解析JSON、楽譜成果物は削除対象になりません。

## フロントエンド開発とテスト

ブラウザ用ソースは `frontend/src/` に置き、`public/app.js` を生成します。外部CDNには依存せず、固定バージョンのnpmパッケージをバンドルします。

```powershell
npm install
npx playwright install chromium
npm run build
npm run test:unit
npm run test:e2e
.venv\Scripts\python.exe -m pytest -q
```

E2Eテストは、主要画面の表示、タブ切り替え、ジョブ再開、ライブラリ検索、セクション編集、容量整理を確認します。

`start.bat` は `scripts/start.ps1` を呼び出し、前面コンソールで `uvicorn --log-level info --no-access-log` を起動します。Windows ではまず安定起動を優先し、`--reload` は使っていません。
解析中はサーバー側コンソールにも `Queued` `Preparing source separation` `Extracting spectrograms` `Analyzing ...` などの進捗が時刻付きで表示されます。
`/jobs/...` の進捗ポーリングはアクセスログに出しません。

## Music Structure 解析フロー

1. アプリを起動する
2. ブラウザから YouTube URL を投げる
3. 元音声は `data/audio/*.wav` に保存される
4. 解析結果は `data/results/*.json` に保存される
5. 再生用音声は `ffmpeg loudnorm` を通した `public/audio/*.mp3` に保存される
6. 公開用 JSON は `public/results/*.json` に同期される

`data/work/` にできる `spec/` や `demix/` は中間生成物です。Git 管理しません。

## Score Extractor

`Score Extractor` タブでは、動画の一部領域を譜面として抽出できます。

主な設定:

- `Region`
  譜面が動画の上側か下側かを選びます。
- `Height`
  切り出す高さを動画高さに対する割合で指定します。
- `Interval`
  何秒ごとにサンプリングするかを指定します。
- `Diff`
  似ているフレームを除外するための差分しきい値です。
- `Trim Start` / `Trim End`
  抽出後に先頭または末尾のフレームを指定枚数だけ捨てます。動画終端の黒画面などを落とす用途です。
- `Output`
  `A4 Pages`、`A3 2-up Pages`、`Long PNG` から出力形式を選びます。

出力画像と ZIP は `public/score/` 配下に同期されます。元動画と作業ファイルは `data/score/` 配下に保存されます。

## 静的成果物の更新

```powershell
python scripts\export_static.py
python scripts\export_static.py --metadata-only
```

Windows:

```powershell
scripts\refresh_public.bat
scripts\refresh_public.bat --metadata-only
```

## GitHub Pages

`public/` の UI ソースは Git 管理しますが、`public/audio/` と `public/results/` は生成物なので main ブランチには含めません。

`scripts\publish_pages.bat` は、現在の `public/` の中身を一時 publish ディレクトリへコピーして、そのディレクトリから `gh-pages` に force push します。main ブランチを生成物で汚さないための運用です。

```powershell
scripts\publish_pages.bat
scripts\publish_pages.bat --metadata-only
```

## Cloudflare R2

解析成果物を別デバイスから読むための R2 同期は任意です。設定方法は
[`docs/cloudflare-r2.md`](docs/cloudflare-r2.md) を参照してください。

## 静的閲覧版

解析済みセッションだけを別デバイスから見る静的閲覧版は Cloudflare Pages に
`public/` を置くだけで動きます。詳細は
[`docs/static-library.md`](docs/static-library.md) を参照してください。

## 利用条件とコンテンツの権利

PracticeLabのソースコードは [`LICENSE`](LICENSE) に記載したMIT Licenseで公開します。ただし、インストールされる第三者製パッケージ、学習済みモデル、利用者が入力する音源・動画には、それぞれ別の利用条件が適用されます。

- 自分が権利を持つ、または解析・複製の許可を得た音源と動画だけを使用してください。
- YouTubeなど外部サービスのコンテンツを扱う場合は、そのサービスの利用規約と適用法令を確認し、遵守してください。YouTubeの利用条件は [YouTube Terms of Service](https://www.youtube.com/static?template=terms) で確認できます。
- このリポジトリには、利用者が取得・生成した音源、動画、stems、楽譜画像、解析結果を含めません。それらを公開・共有する場合の権利確認は利用者の責任で行ってください。
- `madmom`のソースコードはBSDライセンスですが、付属する学習済みモデルとデータはCC BY-NC-SA 4.0です。これらを利用する解析機能には非商用条件が適用されます。商用利用を検討する場合は、[madmomの公式ライセンス](https://github.com/CPJKU/madmom/blob/master/LICENSE) を確認してください。
- PracticeLabのMIT Licenseは、第三者製パッケージやモデルのライセンス条件を変更するものではありません。

## 無料配布版

Windows版とApple Silicon Mac版は、有料のコード署名証明書を使用せず無料で配布します。OSには「不明な発行元」または「開発元を確認できない」と表示されます。配布ファイル名は通常の製品名とし、署名状態と初回起動方法はReleaseの案内に明記します。Mac版は壊れたアプリと判定されないようアドホック署名を施します。GitHub ReleaseにはWindows用EXEと自動更新メタデータ、Mac用DMGだけを掲載します。詳細は[`UNSIGNED_DISTRIBUTION.md`](UNSIGNED_DISTRIBUTION.md)を参照してください。

Windows版はアプリ内更新に対応します。コード署名が必須となるMacの自動更新は使用せず、アプリから最新版のGitHub Releaseを開いて手動更新します。

## 方針

- ソースコードと生成物を混ぜない
- `data/` と `public/{audio,results}` はランタイム生成物として扱う
- 解析バックエンドは `allin1` ではなく、保守されている `all-in-one-fix` を使う
- 生成物が必要なら書き出すが、main ブランチには原則コミットしない
