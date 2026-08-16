# Cloudflare R2 sync

R2 sync is optional. When `R2_ENABLED` is not set, the app keeps using local
`public/audio`, `public/video`, and `public/results` files.

## Desktop app

The packaged desktop app does not include a shared bucket or developer
credentials. Each user opens **Settings > Cloud integration** and connects
their own Cloudflare R2 bucket. Non-secret values are stored under that OS
user's PracticeLab application-data directory. The secret access key is kept
separately with Electron `safeStorage` (DPAPI on Windows and Keychain-backed
storage on macOS).

After setup, the top-bar action performs a bidirectional device sync through
that user's bucket. Sessions missing on another device are downloaded rather
than treated as deletions. Only deletions made through PracticeLab propagate
to other devices. Per-device playback volume and playback position remain
local. Without a configured bucket the action opens the cloud-integration
settings instead.

## Add another device securely

The desktop settings can export the saved R2 connection as a
`.practicelab-link` file. The file contains the bucket settings and S3
credentials encrypted with scrypt and AES-256-GCM. PracticeLab displays a
separate 128-bit decryption code after saving the file. Transfer the file and
code through separate channels, import them on the other device, and remove
the transfer file after a successful import. The imported secret is then
stored with Electron `safeStorage` on that device.

The transfer file does not create a new Cloudflare token. Both devices use
the same scoped R2 token until the user rotates it in Cloudflare. For stronger
per-device revocation, create separate bucket-scoped R2 tokens instead.

The environment-variable setup below remains available for source development
and automation scripts.

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
