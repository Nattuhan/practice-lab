# R2静的閲覧版

R2静的閲覧版は、デスクトップ版で解析済みの曲を別端末から再生するための読み取り専用画面です。

## デスクトップ版との違い

デスクトップ版は管理アプリです。YouTube・音声ファイルの解析、パート分離、楽譜抽出、ライブラリ編集、処理履歴、R2同期を実行します。

静的閲覧版はR2上の解析済みファイルを読むだけです。曲の一覧表示と再生、セクション移動、ループ、速度変更、クリック、公開済みstemsの再生に対応します。

解析、処理履歴、設定、削除、アップロードは表示も実行もしません。端末内の`jobs.json`、ログ、設定、R2認証情報は公開対象外です。

## オブジェクト構成

```text
index.html
app.js
styles.css
sessions/manifest.json
sessions/folders.json
sessions/{session_id}/session.json
sessions/{session_id}/audio.mp3
sessions/{session_id}/video.mp4
sessions/{session_id}/stems/*.mp3
```

## 静的モード

公開時は`window.PRACTICE_LAB_CONFIG`で静的モードを指定します。

```html
<script>
window.PRACTICE_LAB_CONFIG = {
  mode: "static",
  libraryBaseUrl: "sessions"
};
</script>
```

FastAPIが存在するローカル版では、同じUIファイルが管理アプリとして動作します。静的モードでは、バックエンド専用機能を実行するAPI呼び出しを行いません。

## 更新

静的閲覧版へ反映する変更がある場合だけ、次を実行します。

```bash
python scripts/export_static.py
python scripts/sync_r2.py
```

`sync_r2.py`はSHA-256台帳を比較し、新規・変更・削除だけを反映します。未変更の音声・動画を再送しません。

デスクトップ専用の解析機能、処理履歴、ローカル設定だけを変更した場合は、R2同期は不要です。

## CORS

閲覧ページとR2のホスト名が異なる場合は、Cloudflare側で閲覧ページのオリジンに対する`GET`と`HEAD`を許可します。詳細は[cloudflare-r2.md](cloudflare-r2.md)を参照してください。
