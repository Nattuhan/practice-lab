---
name: practice-lab-release
description: Prepare and publish PracticeLab desktop releases, verify local Apple Silicon builds in isolation, or verify automatic updates. Preserve the ordinary signed app and its update channel during local testing; distinguish release versioning from local builds. Use for requested version changes, desktop releases, local app updates, or automatic update verification.
---

# PracticeLab デスクトップリリース

リリース作成やローカルアプリ更新は、ユーザーが明示的に依頼した範囲だけ実行する。タグのpush、GitHub Release公開、`/Applications`のアプリ入れ替えを依頼から推測して勝手に行わない。
同じ会話ですでに依頼・承認された範囲は引き継ぎ、改めて許可を求めない。

## 作業範囲とバージョン

- リリース作成・準備の依頼では、下記の「リリース準備」を適用する。公開は依頼された場合だけ行う。
- 「公開せずローカルで動作確認」では「手元のビルド検証と通常版の自動更新を両立する」を適用し、既存のバージョンを維持する。「このMacを更新」はアプリ内更新を標準とし、ローカルビルドの検証と区別する。いずれも依頼だけで未指定のバージョン変更を追加しない。
- 「次のパッチバージョンを原則とする」は、リリースに向けてバージョンを上げる際の番号の選び方であり、修正・ビルド・ローカル更新のたびに番号を上げる指示ではない。
- 「1.3.0としてリリース」のように番号が指定された場合は、その番号を使う。パッチ番号の原則より指定を優先し、CI失敗や再試行を理由に別の番号へ変更しない。
- 編集前に、依頼された作業、バージョンを維持するか指定値へ変更するか、公開・インストール・検証の対象を整理する。完了前の差分確認でも、ローカル更新だけの依頼にバージョン変更や新バージョンのリリースノートが混入していないことを確認する。

## リリース準備

1. `docs/desktop-release.md`、`.github/workflows/release-desktop.yml`、現在のタグ・Release・作業ツリーを確認する。
2. リリース用にバージョンを上げる場合は、次のパッチバージョンを原則とし、ユーザー指定があれば従う。`package.json`と`package-lock.json`のバージョン、`RELEASE_NOTES.md`の見出し・配布物名・変更点を揃える。
3. フロント生成物を更新し、少なくとも次を実行する。
   - `npm run build`
   - `npm run test:unit`
   - `.venv/bin/python -m pytest -q`（Windowsでは`.venv\Scripts\python.exe`）
   - `npm run test:e2e`
4. 修正内容の再発を直接検出するテストが妥当なら追加する。既存テストの成功だけで今回の不具合を検証済みとは扱わない。
5. `git diff --check`と`git status --short`を確認する。`public/audio/`、`public/video/`、`public/results/`、`public/score/`、`public/stems/`の生成データをコミットしない。

UI・静的ビューア変更を含む場合は、`practice-lab-r2-sync`スキルも使用する。R2同期は明示的に依頼された場合だけ実行する。依頼された同期を実行できない場合は、全件同期へ切り替えず、未実施であることを最終報告する。

## 公開

開始前に [references/efficient-release.md](references/efficient-release.md) を読む。転送経路、工程の並行実行、実測時間、再開・監視方法を確認する。


1. リリース変更をコミットして`main`へpushし、配布元のコミットIDを固定する。以後ソース変更がない限り、通過済みテストや同じローカルビルドを理由なく繰り返さない。独立した状態確認はまとめて実行する。
2. Macビルドを隔離起動まで検証してから、MornNotaryを`git pull --ff-only`で最新化し、`docs/macos-notarization.md`に従って同リポジトリの`sign.sh`へ同じビルド済み`.app`を渡す。スクリプトが送信、必要時の分割、署名待ち、取得、検証、掃除まで完了させる。通信だけがrun作成前に失敗した場合は、入力ハッシュを維持して同じ提出を再試行する。run作成後に不明となった場合はrunと依頼ブランチを確認してから再試行する。
3. 受け取ったZIPから検証済みDMGとSHA-256台帳を作り、配布元コミットを`--target`に指定したdraftへアップロードする。標準は`stage-notarized-mac.yml`の`from_staged_dmg=true`で更新用ZIPと`latest-mac.yml`をGitHub上で作る経路。ローカルから4点を直接アップロードする経路も利用できる。stageの正確なrunの成功と、4ファイルの名前・サイズ・バージョンを確認してからタグをpushする。
4. 配布物の元になったコミットへ`vX.Y.Z`の注釈付きタグを作成してpushする。未公開リリースの修正では、下記の手順で既存タグを付け替えられる。
5. タグで起動した`release-desktop.yml`の正確なrun IDを記録し、そのrunだけを監視する。Windows、Apple Silicon Mac、`release-metadata`の全jobが成功するまで完了扱いにしない。
6. ワークフローは両OSの成果物検証後、Releaseを非draftかつlatestとして公開する。途中のArtifactを正式Releaseとして代用しない。
7. `node scripts/verify_desktop_release.cjs X.Y.Z RUN_ID`を実行し、公開状態、タグ・配布元コミット・`main`、3 job、必須配布物を一括確認する。公開Releaseに少なくとも次があり、バージョンが一致することを確認する。
   - `PracticeLab-Setup-X.Y.Z.exe`
   - `.exe.blockmap`
   - `latest.yml`
   - `PracticeLab-X.Y.Z-arm64.dmg`
   - `PracticeLab-X.Y.Z-arm64.zip`と`latest-mac.yml`

公開だけが依頼された場合、通常版アプリの置換やアプリ内更新の実行を追加しない。R2同期も別途明示された場合だけ行う。

CI失敗時は失敗stepとログを確認する。一時的な実行環境の問題なら同じコミットの失敗jobを再実行できる。コードや配布物の修正が必要なら、再検証と必要な再ビルド・再署名を行う。未公開の場合は指定バージョンを維持して下記の手順で続行し、CI失敗だけを理由にバージョンを上げない。壊れたReleaseを成功として報告しない。

### 未公開リリースのタグを付け替える

ユーザーの承認に基づき、依頼されたリリースを完成させるための未公開タグの上書きは追加確認なしで行ってよい。タグ・ソース・配布物の不一致を解消し、指定されたバージョンで公開まで進めるための扱いである。公開済み（prereleaseを含む）のタグ・配布物の上書きはこの承認に含めない。

1. 対象Releaseが未公開であることを確認する。draftに戻した公開済みReleaseを未公開と扱わない。旧コミットの公開ワークフローを停止し、終了を確認して競合を防ぐ。
2. 修正・テストを完了してコミット・pushする。Mac本体・同梱資源・バージョン・ビルド設定が変わった場合は再ビルド・再署名・再公証し、draftの4点を一式更新する。テストやドキュメントだけの変更では、配布入力が不変である差分を記録して検証済みMac配布物を再利用できる。Releaseの`--target`には新しいコミットSHAを指定する。
3. 変更前のリモートタグのオブジェクトIDを記録し、タグを配布元コミットへ付け替える。対象タグだけに期待値を指定した`--force-with-lease`でpushする。他者の変更で期待値が一致しない場合は強制上書きせず、状態を確認する。
4. 新コミットで起動した正確なrunを監視し、通常の公開確認まで完了させる。Releaseの対象コミット情報もそろえる。公開状態が変わった場合や未公開を確認できない場合は付け替えを止め、必要な判断をユーザーへ伝える。

DMGが登録済みで更新用ZIPの直接送信だけが失敗した場合も、標準のstage経路へ切り替えられる。先にローカルの同名ZIPアップロードを終了して競合を避ける。stage成功後のZIPと更新情報を正式な組として扱う。詳細は効率化手順を参照する。

## ローカル検証・インストール・自動更新

これらが依頼されたときだけ [references/local-verification.md](references/local-verification.md) を読む。隔離起動、保存済みデータを使うDev版、通常版の置換、アプリ内更新の詳細をまとめている。

## 完了報告

実行した範囲に応じて、テスト結果とローカル更新・起動確認を簡潔に報告する。公開した場合はReleaseへのリンク、バージョン、CI三jobの結果を、R2同期を依頼された場合はその結果を含める。ローカル確認用の場合は公開していないことを明記する。旧アプリをゴミ箱へ移した場合は復元可能であることも伝える。
