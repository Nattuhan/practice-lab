# Cloudflare R2 sync

R2 sync is optional. When `R2_ENABLED` is not set, the app keeps using local
`public/audio`, `public/video`, and `public/results` files.

## Required environment

For day-to-day use, create `.env.local` and fill in the real values.
`.env.local` is ignored by Git.

```powershell
notepad .env.local
```

The app reads `.env` and `.env.local` automatically on startup. Existing OS
environment variables win over values in those files.

The same values can also be set directly in PowerShell:

```powershell
$env:R2_ENABLED="1"
$env:R2_BUCKET="practice-lab"
$env:CLOUDFLARE_ACCOUNT_ID="<account id>"
$env:R2_ACCESS_KEY_ID="<access key id>"
$env:R2_SECRET_ACCESS_KEY="<secret access key>"
$env:R2_PUBLIC_BASE_URL="https://assets.example.com"
```

`R2_ENDPOINT_URL` can be used instead of `CLOUDFLARE_ACCOUNT_ID`.

Optional:

```powershell
$env:R2_PREFIX="sessions"
$env:R2_REQUIRED="1"
```

`R2_REQUIRED=1` makes analysis fail if upload fails. Without it, upload errors
are logged and local analysis still completes.

## CORS

CORS is bucket configuration, so the routine object upload token should not
try to rewrite it on every sync. Configure the bucket once in the Cloudflare
dashboard under **R2 > bucket > Settings > CORS policy**. Allow `GET` and
`HEAD` from the site origin that serves PracticeLab (and from localhost when
needed for local testing).

`sync_r2.py` therefore skips CORS updates by default. If an intentionally
admin-scoped R2 token is being used, automatic updates can be enabled with:

```powershell
$env:R2_CONFIGURE_CORS="1"
```

Cloudflare requires an **Admin Read & Write** R2 token to edit bucket
configuration. Do not enable this for the normal bucket-scoped Object Read &
Write upload token.

## Object layout

```text
sessions/manifest.json
sessions/{video_id}/session.json
sessions/{video_id}/audio.mp3
sessions/{video_id}/video.mp4
```

## Sync existing local sessions

```powershell
python scripts\sync_r2.py
```
