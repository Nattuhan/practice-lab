# Static library mode

Static library mode is the always-on viewer for analyzed sessions.

The local FastAPI app remains the management app:

- analyze YouTube URLs
- re-analyze
- extract scores
- upload session assets to R2

The static library app can be hosted on Cloudflare Pages and only reads files
from R2:

- `sessions/manifest.json`
- `sessions/{video_id}/session.json`
- `sessions/{video_id}/audio.mp3`
- `sessions/{video_id}/video.mp4`

Score Extractor is intentionally not part of the static library. It is a
management-side tool because it creates new assets and depends on the backend.

## Static app URL

The sync script can upload the static viewer itself to R2. Use your own public
R2 base URL when documenting or configuring a deployment:

```text
https://<public-r2-domain>/index.html
```

This keeps the app and `sessions/*` assets on the same origin, which avoids
browser CORS issues.

## Cloudflare Pages

Use these settings:

```text
Build command: none
Build output directory: public
```

The static app falls back to:

```text
https://<public-r2-domain>/sessions/manifest.json
```

When the FastAPI server is present, the same `public/` files still work as the
management app and read local `results/manifest.json`.

For public deployments, inject `window.PRACTICE_LAB_CONFIG` before `app.js` and
set `libraryBaseUrl`, `manifestUrl`, or `foldersUrl` instead of hard-coding a
personal R2 URL in the tracked source.

If using Cloudflare Pages on a different hostname, configure R2 CORS for that
Pages origin.

## Refresh data

After local analysis, upload the latest assets:

```powershell
python scripts\sync_r2.py
```

The sync script also configures read CORS on the R2 bucket so Cloudflare Pages
can fetch JSON, audio, and video assets when the API token has permission. If
the token is only `Object Read & Write`, CORS setup may need to be done in the
Cloudflare dashboard.
