import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from .cloud_storage import (
    R2Config,
    STEM_NAMES,
    build_r2_session_assets,
    configure_bucket_cors,
    delete_object_keys,
    load_sync_index,
    upload_file,
    upload_sync_index,
)
from .config import (
    DATA_WORK_DIR,
    FOLDERS_FILE,
    MANIFEST_FILE,
    PUBLIC_AUDIO_DIR,
    PUBLIC_DIR,
    PUBLIC_STEMS_DIR,
    PUBLIC_VIDEO_DIR,
)
from .storage import build_manifest_entry, export_static_assets, load_manifest, save_json, update_manifest


CACHE_FILE = DATA_WORK_DIR / "r2-sync-cache.json"


def _load_hash_cache() -> dict[str, dict]:
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _file_sha256(path: Path, cache: dict[str, dict]) -> str:
    stat = path.stat()
    cache_key = str(path.resolve())
    cached = cache.get(cache_key, {})
    if cached.get("size") == stat.st_size and cached.get("mtimeNs") == stat.st_mtime_ns:
        digest = cached.get("sha256")
        if isinstance(digest, str):
            return digest
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    cache[cache_key] = {"size": stat.st_size, "mtimeNs": stat.st_mtime_ns, "sha256": value}
    return value


def _prepare_session_metadata(config: R2Config) -> list[dict]:
    changed = False
    for entry in load_manifest():
        video_id = entry["id"]
        result_file = MANIFEST_FILE.parent / f"{video_id}.json"
        if not result_file.exists():
            continue
        data = json.loads(result_file.read_text(encoding="utf-8"))
        video_file = PUBLIC_VIDEO_DIR / f"{video_id}.mp4"
        cloud_assets = build_r2_session_assets(video_id, config, include_video=video_file.exists())
        merged = {**data.get("assets", {}), **cloud_assets}
        if merged == data.get("assets", {}):
            continue
        data["assets"] = merged
        save_json(result_file, data)
        update_manifest(build_manifest_entry(data, entry_date=entry.get("date") or ""))
        changed = True
    if changed:
        export_static_assets()
    return load_manifest()


def _desired_files(config: R2Config, manifest: list[dict]) -> dict[str, Path]:
    files = {
        "index.html": PUBLIC_DIR / "index.html",
        "app.js": PUBLIC_DIR / "app.js",
        "styles.css": PUBLIC_DIR / "styles.css",
        f"{config.prefix}/manifest.json": MANIFEST_FILE,
        f"{config.prefix}/folders.json": FOLDERS_FILE,
    }
    for entry in manifest:
        video_id = entry["id"]
        base_key = f"{config.prefix}/{video_id}"
        candidates = {
            f"{base_key}/session.json": MANIFEST_FILE.parent / f"{video_id}.json",
            f"{base_key}/audio.mp3": PUBLIC_AUDIO_DIR / f"{video_id}.mp3",
            f"{base_key}/video.mp4": PUBLIC_VIDEO_DIR / f"{video_id}.mp4",
            **{
                f"{base_key}/stems/{stem}.mp3": PUBLIC_STEMS_DIR / video_id / f"{stem}.mp3"
                for stem in STEM_NAMES
            },
        }
        files.update({key: path for key, path in candidates.items() if path.exists()})
    return {key: path for key, path in files.items() if path.exists()}


def sync_cloud_incremental(
    config: R2Config,
    *,
    progress: Callable[[str], None] | None = None,
    check_canceled: Callable[[], None] | None = None,
) -> dict:
    notify = progress or (lambda _message: None)
    check = check_canceled or (lambda: None)
    export_static_assets()
    if config.configure_cors:
        notify("R2の公開設定を確認しています")
        configure_bucket_cors(config)

    notify("同期するファイルを確認しています")
    manifest = _prepare_session_metadata(config)
    files = _desired_files(config, manifest)
    cache = _load_hash_cache()
    local_index = {key: _file_sha256(path, cache) for key, path in files.items()}
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_json(CACHE_FILE, cache)

    remote_index = load_sync_index(config) or {}
    uploaded: list[str] = []
    unchanged = 0
    for key, path in files.items():
        check()
        if remote_index.get(key) == local_index[key]:
            unchanged += 1
            continue
        notify(f"アップロード中: {key}")
        upload_file(config, path, key)
        uploaded.append(key)

    removed = sorted(set(remote_index) - set(local_index))
    if removed:
        notify("不要になった公開ファイルを整理しています")
        delete_object_keys(config, removed)
    if uploaded or removed or remote_index != local_index:
        upload_sync_index(config, local_index)
    return {
        "uploaded": len(uploaded),
        "deleted": len(removed),
        "unchanged": unchanged,
        "viewerUrl": f"{config.public_base_url}/index.html" if config.public_base_url else None,
    }
