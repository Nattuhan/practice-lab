import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from practice_lab.config import (
    DATA_WORK_DIR,
    FOLDERS_FILE,
    MANIFEST_FILE,
    PUBLIC_AUDIO_DIR,
    PUBLIC_DIR,
    PUBLIC_STEMS_DIR,
    PUBLIC_VIDEO_DIR,
    ensure_directories,
)
from practice_lab.cloud_storage import (
    STEM_NAMES,
    build_r2_session_assets,
    configure_bucket_cors,
    delete_object_keys,
    get_r2_config,
    load_sync_index,
    upload_file,
    upload_sync_index,
)
from practice_lab.storage import build_manifest_entry, export_static_assets, load_manifest, save_json, update_manifest

CACHE_FILE = DATA_WORK_DIR / "r2-sync-cache.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="新規・変更・削除されたファイルだけをR2へ同期します")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--session",
        action="append",
        default=[],
        metavar="ID",
        help="指定セッションを変更判定に関係なく再アップロードします（複数指定可）",
    )
    group.add_argument(
        "--all-sessions",
        action="store_true",
        help="全セッションの音声・動画を強制的に再アップロードします",
    )
    group.add_argument(
        "--initialize-index",
        action="store_true",
        help="R2が現在のローカル内容と一致している前提で、同期インデックスだけを作成します",
    )
    return parser.parse_args()


def load_hash_cache() -> dict[str, dict]:
    if not CACHE_FILE.exists():
        return {}
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def file_sha256(path: Path, cache: dict[str, dict]) -> str:
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


def prepare_session_metadata(config) -> list[dict]:
    manifest = load_manifest()
    changed = False
    for entry in manifest:
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


def desired_files(config, manifest: list[dict]) -> dict[str, Path]:
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


def main() -> None:
    args = parse_args()
    ensure_directories()
    config = get_r2_config()
    if config is None:
        raise SystemExit("R2_ENABLED=1 と R2接続設定が必要です")
    if config.configure_cors:
        configure_bucket_cors(config)

    manifest = prepare_session_metadata(config)
    files = desired_files(config, manifest)
    cache = load_hash_cache()
    local_index = {key: file_sha256(path, cache) for key, path in files.items()}
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    save_json(CACHE_FILE, cache)

    remote_index = load_sync_index(config)
    if remote_index is None and not (args.initialize_index or args.all_sessions):
        raise SystemExit(
            "R2同期インデックスがありません。現在のR2がローカルと一致している場合は "
            "--initialize-index を一度だけ実行してください"
        )

    if args.initialize_index:
        upload_sync_index(config, local_index)
        print(f"initialized sync index for {len(local_index)} files; asset uploads: 0")
        return

    remote_index = remote_index or {}
    forced_ids = set(args.session)
    uploaded = []
    unchanged = 0
    for key, path in files.items():
        session_forced = any(key.startswith(f"{config.prefix}/{video_id}/") for video_id in forced_ids)
        force = args.all_sessions and key.startswith(f"{config.prefix}/") and key not in {
            f"{config.prefix}/manifest.json",
            f"{config.prefix}/folders.json",
        }
        if not force and not session_forced and remote_index.get(key) == local_index[key]:
            unchanged += 1
            continue
        upload_file(config, path, key)
        uploaded.append(key)

    removed = sorted(set(remote_index) - set(local_index))
    if removed:
        delete_object_keys(config, removed)
    if uploaded or removed or remote_index != local_index:
        upload_sync_index(config, local_index)

    print(f"uploaded {len(uploaded)} changed files; deleted {len(removed)} stale files; unchanged {unchanged}")
    for key in uploaded:
        print(f"uploaded {key}")
    for key in removed:
        print(f"deleted {key}")


if __name__ == "__main__":
    main()
