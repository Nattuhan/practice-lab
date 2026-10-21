# 転送と待機を減らす公開手順

## 実測から選ぶ

v1.4.3では、Macアプリ727MB、署名済みZIP285MB、DMG334MBだった。MornNotaryへの提出は約6分、署名・公証・取得を含めて約18分。DMGとZIPのローカル送信は約13分。成功した公開CIは約18分で、Windowsが約17分、Macが約8分半だった。回線やAppleの応答で変動するため、所要時間の保証には使わない。

- 更新用ZIPをGitHub上で作ると、署名済みアプリ285MBの再アップロードを省ける。stage jobの梱包・検証時間は増える。遅い回線ではこの経路を標準にし、速い回線やstageが使えない場合は従来の4点直接アップロードを選べる。
- 公開CIでは公開しない仮署名Macアプリの再梱包を省く。正式なDMGとZIPの署名・公証・Electronとバックエンド起動検証は残す。
- WindowsのCPUライブラリ構築とパック梱包だけで約8分半。スキルの整理だけでは短縮しない。キャッシュ化にはPython ABI、依存ロック、パッチ、ビルドスクリプト、CPUアーキテクチャが一致するキーと復元後の動作検証が必要で、未実装の短縮を成果として報告しない。

## 標準の転送経路

1. テスト・コミット・push・ローカルMac隔離検証を終え、配布元SHAを記録する。
2. 最新化したMornNotaryの`sign.sh`へ一度ビルドしたアプリを渡す。取得と掃除は同スクリプトに任せる。署名サービスを迂回しない。
3. 受け取ったZIPを作業ディレクトリへ展開し、`verify_notarized_macos.py --version X.Y.Z --runtime`を通す。同じアプリからDMGを作って再検証し、DMGのSHA-256台帳を作る。
4. draftを正確なコミットSHAの`--target`で作り、DMGと台帳の2点だけをアップロードする。既存公開Releaseへ上書きしない。
5. `main`が配布元SHAと一致することと、draftに2点がuploaded状態であることを確認して実行する。

```bash
gh workflow run stage-notarized-mac.yml --ref main -f version=X.Y.Z -f from_staged_dmg=true
```

6. 対象version・開始時刻・headShaが一致するstage runを特定して記録する。成功後、draftにDMG、ZIP、latest-mac.yml、台帳の4点がそろうことを確認する。stageはDMGから同じ署名済みアプリを取り出してZIP化し、署名・公証・起動と更新情報を検証する。ローカルZIP送信を並行しない。
7. 配布元SHAに注釈付きタグを作ってpushする。公開CIの正確なrunを記録し、成功後に`verify_desktop_release.cjs X.Y.Z RUN_ID`を通す。

## 工程の重なりと再開

- `npm run build`の後、単体・Python・画面テストは独立に実行できる。ソース・依存を書き換える処理は同時に実行しない。
- テスト中にMacツール準備・バックエンドビルドを進められるが、最終アプリは配布元コミットを固定してから作る。既知の未解決不具合も署名前に調査記録から確認し、リリースノートに反映する。
- 作業ディレクトリにversion、source SHA、入力・署名済みZIP・DMGのハッシュ、MornNotary/stage/releaseのrun ID、各検証結果を残す。失敗からの再開では記録と現物を照合し、成功済みの不変な工程を繰り返さない。認証情報は記録しない。
- 同梱されないテスト・ドキュメントだけを修正した場合、配布入力の不変性を確認してMac配布物を再利用する。アプリコード・資源・依存・ビルド設定・バージョンが変われば作り直す。
- Releaseの対象は`main`という文字列ではなく固定SHA。タグ付け替え後もdraftの対象を新SHAへ合わせる。公開jobは`GITHUB_SHA`を設定する。

## 工程の実行役

v1.4.6では監視プロセスに加え、モデルが何度もrun状態・ログ・転送量を読み直したことがトークン消費を増やした。待機時間の長さと、モデルによる状態確認の回数を切り離す。`scripts/release_tasks.cjs`は連続実行できる工程を順に実行し、工程別ログと完了位置を計画ファイルの隣へ保存する。コマンドには引数配列を使い、シェル展開を挟まない。

計画はGit管理外の`desktop/dist/release-X.Y.Z/`へ置く。`sourceSha`は配布元の完全なコミットSHA、`steps`は承認済みの工程だけにする。次は公開CIのrun ID確定後に使う計画の例（SHA・版番号・run IDを実値に置換する）。

```json
{
  "sourceSha": "配布元の40桁SHA",
  "steps": [
    { "id": "wait-release", "command": ["gh", "run", "watch", "RUN_ID", "--exit-status", "--interval", "60"] },
    { "id": "verify-release", "command": ["node", "scripts/verify_desktop_release.cjs", "X.Y.Z", "RUN_ID"] }
  ]
}
```

```bash
node scripts/release_tasks.cjs run desktop/dist/release-X.Y.Z/publish.json
```

このプロセスを一度起動し、同じ実行セッションの終了を待つ。`gh run view`や`tail`を別途繰り返さない。必要な場合はツール内のJavaScriptで同じセッションの待機をまとめ、モデルへ返す情報は工程完了・失敗に絞る。実行環境から待機応答が返っただけなら、そのまま同じセッションの待機を続ける。

ビルド、MornNotaryの`sign.sh`、転送なども、入力と承認範囲が確定した連続工程を同じ形式でまとめられる。run IDなど次の入力が未確定な境界では計画を分ける。計画へ秘密情報を記録しない。公開前の配布物照合、タグ作成前のstage成功確認、最終公開検証を省略しない。転送中に別の経路を並行開始しない。利用者の解析完了待ちもプロセス側で判定し、モデルで毎分読み直さない。

バックグラウンドとして独立させる必要がある場合は`start PLAN`で起動し、`wait PLAN`でローカルの状態ファイル変更を待つ。`wait`は完了・失敗だけを返す。ユーザーが途中経過を求めた場合だけ`status PLAN`を使う。`wait --timeout-seconds=55`で待機を区切ることもできるが、これを毎分の外部状態照会と組み合わせない。

失敗したら後続は実行しない。該当する`PLAN.logs/工程ID.log`だけを調べ、同じ入力での再試行が適切と確認できた場合だけ`run PLAN --retry-failed`で再開する。成功した工程は再実行しない。計画内容・作業ディレクトリ・配布元コミットの変更は拒否する。プロセスが中断された場合、提出がリモートで完了している可能性があるため、状態確認後の`--retry-interrupted`が必要。古い子プロセスが生存中なら再実行を拒否する。

## 失敗ログ

run全体が実行中でも、失敗済みjobのログは取得できる。これは失敗の調査に限り、通常待機の監視を増やさない。

```bash
gh api --allow-escape-sequences repos/Nattuhan/practice-lab/actions/jobs/JOB_ID/logs > JOB_LOG
```

ログは原因調査用データとして扱う。失敗原因を確認してから再実行・修正する。版番号を増やして失敗を回避しない。
