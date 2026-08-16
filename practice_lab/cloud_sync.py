import hashlib
import json
import re
import shutil
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

from .cloud_storage import (
    R2Config,
    STEM_NAMES,
    build_r2_session_assets,
    configure_bucket_cors,
    delete_object_keys,
    download_file,
    load_json_object,
    load_sync_index,
    upload_file,
    upload_json_object,
    upload_sync_index,
)
from .config import (
    DATA_AUDIO_DIR,
    DATA_RESULTS_DIR,
    DATA_STEMS_DIR,
    DATA_VIDEO_DIR,
    DATA_WORK_DIR,
    FOLDERS_FILE,
    MANIFEST_FILE,
    PUBLIC_AUDIO_DIR,
    PUBLIC_DIR,
    PUBLIC_RESULTS_DIR,
    PUBLIC_STEMS_DIR,
    PUBLIC_VIDEO_DIR,
)
from .device_sync import load_local_sync_state, remote_revision, save_local_sync_state, workspace_key
from .storage import build_manifest_entry, export_static_assets, load_manifest, save_json, update_manifest


CACHE_FILE = DATA_WORK_DIR / "r2-sync-cache.json"
REMOTE_DEVICE_STATE_NAME = "device-sync.json"
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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


def _session_candidates(config: R2Config, video_id: str) -> dict[str, Path]:
    base_key = f"{config.prefix}/{video_id}"
    return {
        f"{base_key}/session.json": DATA_RESULTS_DIR / f"{video_id}.json",
        f"{base_key}/audio.mp3": PUBLIC_AUDIO_DIR / f"{video_id}.mp3",
        f"{base_key}/video.mp4": PUBLIC_VIDEO_DIR / f"{video_id}.mp4",
        **{
            f"{base_key}/stems/{stem}.mp3": PUBLIC_STEMS_DIR / video_id / f"{stem}.mp3"
            for stem in STEM_NAMES
        },
    }


def _mapping_digest(files: dict[str, str]) -> str:
    encoded = json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _workspace_key(config: R2Config) -> str:
    return workspace_key(config.endpoint_url, config.bucket, config.prefix)


def _local_session_bundle(config: R2Config, video_id: str, cache: dict[str, dict]) -> dict | None:
    candidates = _session_candidates(config, video_id)
    if not candidates[f"{config.prefix}/{video_id}/session.json"].exists():
        return None
    paths = {key: path for key, path in candidates.items() if path.exists()}
    files = {key: _file_sha256(path, cache) for key, path in paths.items()}
    return {
        "files": files,
        "digest": _mapping_digest(files),
        "modifiedAt": max(path.stat().st_mtime for path in paths.values()),
    }


def _local_session_ids() -> set[str]:
    return {
        path.stem
        for path in DATA_RESULTS_DIR.glob("*.json")
        if path.name not in {"manifest.json", "folders.json"} and SESSION_ID_PATTERN.fullmatch(path.stem)
    }


def _load_local_folders() -> list[dict]:
    try:
        payload = json.loads(FOLDERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _safe_remote_files(config: R2Config, video_id: str, entry: dict | None) -> dict[str, str]:
    if not SESSION_ID_PATTERN.fullmatch(video_id):
        return {}
    allowed = set(_session_candidates(config, video_id))
    files = (entry or {}).get("files", {})
    if not isinstance(files, dict):
        return {}
    return {
        key: str(digest)
        for key, digest in files.items()
        if key in allowed and isinstance(digest, str) and SHA256_PATTERN.fullmatch(digest)
    }


def active_remote_file_index(config: R2Config, remote_state: dict | None) -> dict[str, str]:
    sessions = (remote_state or {}).get("sessions", {})
    if not isinstance(sessions, dict):
        return {}
    return {
        key: digest
        for video_id, entry in sessions.items()
        if isinstance(video_id, str) and isinstance(entry, dict) and not entry.get("deleted")
        for key, digest in _safe_remote_files(config, video_id, entry).items()
    }


def _download_verified_file(
    config: R2Config,
    key: str,
    destination: Path,
    expected_digest: str,
    *,
    max_bytes: int,
) -> None:
    staging = destination.with_suffix(f"{destination.suffix}.device-sync")
    staging.unlink(missing_ok=True)
    try:
        download_file(config, key, staging, max_bytes=max_bytes)
        digest = hashlib.sha256()
        with staging.open("rb") as source:
            for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_digest:
            raise RuntimeError(f"R2上のファイルの整合性を確認できませんでした: {key}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)


def _download_remote_session(config: R2Config, video_id: str, entry: dict) -> None:
    destinations = _session_candidates(config, video_id)
    safe_files = _safe_remote_files(config, video_id, entry)
    session_key = f"{config.prefix}/{video_id}/session.json"
    if session_key not in safe_files:
        raise RuntimeError(f"R2上の曲データに解析結果がありません: {video_id}")
    _download_verified_file(
        config,
        session_key,
        destinations[session_key],
        safe_files[session_key],
        max_bytes=16 * 1024**2,
    )
    result_file = DATA_RESULTS_DIR / f"{video_id}.json"
    try:
        payload = json.loads(result_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result_file.unlink(missing_ok=True)
        raise RuntimeError(f"R2上の曲データが不正です: {video_id}") from exc
    if payload.get("id") != video_id or not isinstance(payload.get("title"), str) or "bpm" not in payload:
        result_file.unlink(missing_ok=True)
        raise RuntimeError(f"R2上の曲データが不正です: {video_id}")
    for key, digest in safe_files.items():
        if key == session_key:
            continue
        destination = destinations.get(key)
        if destination is not None:
            _download_verified_file(config, key, destination, digest, max_bytes=8 * 1024**3)
    update_manifest(
        build_manifest_entry(
            payload,
            entry_date=str(entry.get("entryDate") or date.today().isoformat()),
        )
    )


def _delete_local_session(video_id: str) -> None:
    for path in (
        DATA_RESULTS_DIR / f"{video_id}.json",
        DATA_AUDIO_DIR / f"{video_id}.wav",
        DATA_AUDIO_DIR / f"{video_id}.mp3",
        DATA_VIDEO_DIR / f"{video_id}.mp4",
        PUBLIC_RESULTS_DIR / f"{video_id}.json",
        PUBLIC_AUDIO_DIR / f"{video_id}.mp3",
        PUBLIC_VIDEO_DIR / f"{video_id}.mp4",
    ):
        path.unlink(missing_ok=True)
    for directory in (DATA_STEMS_DIR / video_id, PUBLIC_STEMS_DIR / video_id):
        if directory.exists():
            shutil.rmtree(directory)
    save_json(MANIFEST_FILE, [item for item in load_manifest() if item.get("id") != video_id])
    folders = []
    for folder in _load_local_folders():
        folders.append({
            **folder,
            "sessionIds": [item for item in folder.get("sessionIds", []) if item != video_id],
        })
    save_json(FOLDERS_FILE, folders)


def _migrate_remote_device_state(config: R2Config, remote_index: dict[str, str]) -> dict:
    sessions: dict[str, dict] = {}
    prefix = f"{config.prefix}/"
    for key, digest in remote_index.items():
        if not key.startswith(prefix):
            continue
        relative = key[len(prefix):]
        parts = relative.split("/")
        if len(parts) < 2 or parts[0] in {"manifest.json", "folders.json", "sync-index.json"}:
            continue
        video_id = parts[0]
        entry = sessions.setdefault(video_id, {
            "deviceId": "legacy",
            "updatedAt": 0,
            "entryDate": date.today().isoformat(),
            "files": {},
        })
        entry["files"][key] = digest
    for entry in sessions.values():
        entry["digest"] = _mapping_digest(entry["files"])
    folders_key = f"{config.prefix}/folders.json"
    state = {"version": 1, "sessions": sessions, "devices": {}}
    if folders_key in remote_index:
        state["folders"] = {
            "deviceId": "legacy",
            "updatedAt": 0,
            "digest": remote_index[folders_key],
            "key": folders_key,
        }
    return state


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

    notify("端末間で同期するファイルを確認しています")
    manifest = _prepare_session_metadata(config)
    cache = _load_hash_cache()
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    remote_index = load_sync_index(config) or {}
    remote_state_key = f"{config.prefix}/{REMOTE_DEVICE_STATE_NAME}"
    remote_state = load_json_object(config, remote_state_key)
    if not isinstance(remote_state, dict):
        remote_state = _migrate_remote_device_state(config, remote_index)
    remote_state.setdefault("version", 1)
    if not isinstance(remote_state.get("sessions"), dict):
        remote_state["sessions"] = {}
    if not isinstance(remote_state.get("devices"), dict):
        remote_state["devices"] = {}
    local_state = load_local_sync_state()
    workspace_key = _workspace_key(config)
    if local_state.get("workspaceKey") != workspace_key:
        local_state["workspaceKey"] = workspace_key
        local_state["sessions"] = {}
        local_state["tombstones"] = {}
        local_state["folders"] = {}
    local_sessions = {
        video_id: bundle
        for video_id in _local_session_ids()
        if (bundle := _local_session_bundle(config, video_id, cache)) is not None
    }
    remote_sessions = remote_state["sessions"]
    tombstones = local_state["tombstones"]
    manifest_dates = {item["id"]: item.get("date") or date.today().isoformat() for item in manifest}
    downloaded: list[str] = []
    deleted_local: list[str] = []
    deleted_remote: list[str] = []
    removed_remote_files: set[str] = set()
    conflicts: list[dict[str, str]] = []
    now = time.time()

    for video_id in sorted(set(local_sessions) | set(remote_sessions) | set(tombstones)):
        check()
        if not SESSION_ID_PATTERN.fullmatch(video_id):
            conflicts.append({"sessionId": str(video_id)[:128], "kept": "ignored-invalid-id"})
            continue
        local = local_sessions.get(video_id)
        remote = remote_sessions.get(video_id)
        previous = local_state["sessions"].get(video_id, {})
        tombstone = tombstones.get(video_id)
        if local and tombstone and local["modifiedAt"] > float(tombstone.get("deletedAt") or 0):
            tombstones.pop(video_id, None)
            tombstone = None

        if tombstone:
            deleted_at = float(tombstone.get("deletedAt") or now)
            remote_time = float((remote or {}).get("updatedAt") or (remote or {}).get("deletedAt") or 0)
            if remote and not remote.get("deleted") and remote_time > deleted_at:
                tombstones.pop(video_id, None)
                notify(f"別端末の新しい変更を取得中: {video_id}")
                _download_remote_session(config, video_id, remote)
                downloaded.append(video_id)
            else:
                keys = list(_safe_remote_files(config, video_id, remote))
                if keys:
                    delete_object_keys(config, keys)
                    for key in keys:
                        remote_index.pop(key, None)
                    deleted_remote.append(video_id)
                remote_sessions[video_id] = {
                    "deleted": True,
                    "deletedAt": deleted_at,
                    "updatedAt": deleted_at,
                    "deviceId": tombstone.get("deviceId") or local_state["deviceId"],
                    "files": {},
                }
                if local:
                    _delete_local_session(video_id)
                    deleted_local.append(video_id)
            continue

        if remote and remote.get("deleted"):
            remote_changed = remote_revision(remote) != previous.get("remoteRevision", "")
            local_changed = bool(local and local["digest"] != previous.get("localDigest", ""))
            if local and local_changed and local["modifiedAt"] > float(remote.get("deletedAt") or 0):
                conflicts.append({"sessionId": video_id, "kept": "local"})
                remote = None
            elif remote_changed or not previous:
                if local:
                    _delete_local_session(video_id)
                    deleted_local.append(video_id)
                tombstones[video_id] = {
                    "deletedAt": float(remote.get("deletedAt") or now),
                    "deviceId": remote.get("deviceId") or "remote",
                }
                continue

        if local is None and remote and not remote.get("deleted"):
            notify(f"別端末の曲を取得中: {video_id}")
            _download_remote_session(config, video_id, remote)
            downloaded.append(video_id)
            continue
        if local is None:
            continue
        if remote is None or remote.get("deleted"):
            remote_sessions[video_id] = {
                "deviceId": local_state["deviceId"],
                "updatedAt": max(now, local["modifiedAt"]),
                "entryDate": manifest_dates.get(video_id, date.today().isoformat()),
                "files": local["files"],
                "digest": local["digest"],
            }
            continue

        local_changed = local["digest"] != previous.get("localDigest", "")
        remote_changed = remote_revision(remote) != previous.get("remoteRevision", "")
        if local["digest"] == remote.get("digest"):
            continue
        if remote_changed and not local_changed:
            notify(f"別端末の変更を取得中: {video_id}")
            _download_remote_session(config, video_id, remote)
            downloaded.append(video_id)
            continue
        if local_changed and not remote_changed:
            removed_remote_files.update(set(_safe_remote_files(config, video_id, remote)) - set(local["files"]))
            remote_sessions[video_id] = {
                **remote,
                "deviceId": local_state["deviceId"],
                "updatedAt": max(now, local["modifiedAt"]),
                "entryDate": manifest_dates.get(video_id, remote.get("entryDate") or date.today().isoformat()),
                "files": local["files"],
            }
            remote_sessions[video_id]["digest"] = _mapping_digest(remote_sessions[video_id]["files"])
            continue
        if not local_changed and not remote_changed:
            continue

        keep_local = local["modifiedAt"] >= float(remote.get("updatedAt") or 0)
        conflicts.append({"sessionId": video_id, "kept": "local" if keep_local else "remote"})
        if keep_local:
            removed_remote_files.update(set(_safe_remote_files(config, video_id, remote)) - set(local["files"]))
            remote_sessions[video_id] = {
                **remote,
                "deviceId": local_state["deviceId"],
                "updatedAt": max(now, local["modifiedAt"]),
                "entryDate": manifest_dates.get(video_id, remote.get("entryDate") or date.today().isoformat()),
                "files": local["files"],
            }
            remote_sessions[video_id]["digest"] = _mapping_digest(remote_sessions[video_id]["files"])
        else:
            notify(f"競合した曲の新しい版を取得中: {video_id}")
            _download_remote_session(config, video_id, remote)
            downloaded.append(video_id)

    folders_key = f"{config.prefix}/folders.json"
    remote_folders = remote_state.get("folders") if isinstance(remote_state.get("folders"), dict) else None
    folder_digest = _file_sha256(FOLDERS_FILE, cache)
    folder_modified = FOLDERS_FILE.stat().st_mtime
    previous_folders = local_state.get("folders") if isinstance(local_state.get("folders"), dict) else {}
    if remote_folders is None:
        remote_folders = {
            "deviceId": local_state["deviceId"],
            "updatedAt": max(now, folder_modified),
            "digest": folder_digest,
            "key": folders_key,
        }
        remote_state["folders"] = remote_folders
    elif folder_digest != remote_folders.get("digest"):
        local_changed = folder_digest != previous_folders.get("localDigest", "")
        remote_changed = remote_revision(remote_folders) != previous_folders.get("remoteRevision", "")
        if not previous_folders and not _load_local_folders():
            local_changed = False
        keep_local = local_changed and (
            not remote_changed or folder_modified >= float(remote_folders.get("updatedAt") or 0)
        )
        if keep_local:
            if remote_changed:
                conflicts.append({"sessionId": "folders", "kept": "local"})
            remote_folders = {
                "deviceId": local_state["deviceId"],
                "updatedAt": max(now, folder_modified),
                "digest": folder_digest,
                "key": folders_key,
            }
            remote_state["folders"] = remote_folders
        elif remote_changed:
            if local_changed:
                conflicts.append({"sessionId": "folders", "kept": "remote"})
            notify("別端末のフォルダー構成を取得しています")
            download_file(config, remote_folders.get("key") or folders_key, FOLDERS_FILE)
            folder_digest = _file_sha256(FOLDERS_FILE, cache)

    export_static_assets()
    manifest = _prepare_session_metadata(config)
    files = _desired_files(config, manifest)
    local_index = {key: _file_sha256(path, cache) for key, path in files.items()}
    if removed_remote_files:
        delete_object_keys(config, sorted(removed_remote_files))
        for key in removed_remote_files:
            remote_index.pop(key, None)
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

    active_remote_files = active_remote_file_index(config, remote_state)
    final_index = {**active_remote_files, **local_index}
    remote_state["devices"][local_state["deviceId"]] = {
        "name": local_state.get("deviceName") or "PracticeLab device",
        "lastSeenAt": now,
    }
    upload_json_object(config, remote_state_key, remote_state)
    upload_sync_index(config, final_index)
    save_json(CACHE_FILE, cache)

    refreshed_sessions = {}
    for video_id in _local_session_ids():
        bundle = _local_session_bundle(config, video_id, cache)
        remote = remote_sessions.get(video_id)
        if bundle and remote and not remote.get("deleted"):
            refreshed_sessions[video_id] = {
                "localDigest": bundle["digest"],
                "remoteRevision": remote_revision(remote),
            }
    local_state["sessions"] = refreshed_sessions
    local_state["folders"] = {
        "localDigest": _file_sha256(FOLDERS_FILE, cache),
        "remoteRevision": remote_revision(remote_state.get("folders")),
    }
    local_state["lastSyncedAt"] = now
    save_local_sync_state(local_state)
    return {
        "uploaded": len(uploaded),
        "downloaded": len(set(downloaded)),
        "deleted": len(set(deleted_local) | set(deleted_remote)),
        "deletedSessionIds": sorted(set(deleted_local) | set(deleted_remote)),
        "conflicts": conflicts,
        "unchanged": unchanged,
        "deviceId": local_state["deviceId"],
        "deviceCount": len(remote_state["devices"]),
        "viewerUrl": f"{config.public_base_url}/index.html" if config.public_base_url else None,
    }
