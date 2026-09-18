# 1.4.0の公開とMac自動更新検証

2026-09-18、PracticeLab 1.4.0を公開した。

- 配布元コミット: `9e473e84543ec2091f90435934cb5c32e18ee617`
- [署名・Apple公証](https://github.com/matsufriends/MornNotary/actions/runs/35292549665): 成功。
- [公証済み成果物の配布準備](https://github.com/Nattuhan/practice-lab/actions/runs/35293164608): 成功。
- [公開チェック](https://github.com/Nattuhan/practice-lab/actions/runs/35293350846): Windows・Mac・release-metadataすべて成功。
- [正式リリース](https://github.com/Nattuhan/practice-lab/releases/tag/v1.4.0): 非draft・非prerelease、latest。両OSの更新情報も1.4.0。

最初の未公開タグでは、WindowsのPython 3.10が解析処理の添字内アンパック構文を受け付けずテスト収集に失敗した。計算内容を保った配列連結へ修正し、Pythonテスト279件と4 subtests、単体テスト65件が成功。利用者の明示承認を得て未公開タグを修正コミットへ付け替え、Macアプリを再ビルド・再署名・再公証した。旧タグの実行は停止し、その成果物を公開していない。

## 自動更新の実行結果

正式署名済み1.3.2のコピーを`desktop/dist/update-verification-1.4.0/PracticeLab.app`に置き、独立した`--user-data-dir`と自動更新有効・クラウド無効の設定で起動した。通常版の設定や秘密情報はコピーしていない。

1. 起動だけで1.4.0を検出し、公開ZIPを自動ダウンロードした。配布先や更新情報のモックは使用していない。
2. 「再起動して更新」ボタンから実際の更新処理を呼び出し、検証用アプリが1.4.0へ置き換わった。
3. 署名の整合性、同じ専用プロファイルによる1.4.0の起動、バックエンド応答、自動更新モード、検証用データの保持を確認した。
4. 通常の`/Applications/PracticeLab.app`と設定の変更がないことを検証前後の比較で確認した。

Macの更新機構が検証用起動引数を引き継ぐとは仮定していない。[Squirrelの更新要求](https://github.com/Squirrel/Squirrel.Mac/blob/master/Squirrel/SQRLShipItRequest.m)に任意の起動引数を保存する項目がないため、検証プロセスだけで`autoUpdater.autoRunAppAfterInstall=false`を設定し、実更新後に同じ専用プロファイルで起動し直した。これは検出・取得・適用・隔離再起動の検証であり、通常版の自動再起動やインストール完了を意味しない。配布コード・通常版設定は変更していない。

検証記録は`desktop/dist/update-verification-1.4.0/applied.json`、`updater.log`、`downloaded.png`、`updated.png`。初回の検証スクリプトでは評価コンテキストに`require`がなく終了したが、スクリプトを修正して上記の全工程を再実行・確認した。

## 普段使い版の状態

この検証で普段使い版を置換していない。現在の通常版は仮署名の1.3.2で起動時更新が無効のため、自動更新を利用するには正式署名版への初回移行と設定変更が別途必要。検証用コピーの成功と区別する。
