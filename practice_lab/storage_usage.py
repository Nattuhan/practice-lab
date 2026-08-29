from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import (
    DATA_AUDIO_DIR,
    DATA_DIR,
    DATA_RESULTS_DIR,
    DATA_SCORE_DIR,
    DATA_STEMS_DIR,
    DATA_VIDEO_DIR,
    DATA_WORK_DIR,
    MANIFEST_FILE,
    PUBLIC_AUDIO_DIR,
    PUBLIC_RESULTS_DIR,
    PUBLIC_SCORE_DIR,
    PUBLIC_STEMS_DIR,
    PUBLIC_VIDEO_DIR,
    ROOT_DIR,
)


@dataclass(frozen=True)
class StorageCategory:
    key: str
    label: str
    paths: tuple[Path, ...]
    cleanup: bool = False
    desktop_cleanup: bool = False
    count_toward_total: bool = True


def storage_categories() -> tuple[StorageCategory, ...]:
    return (
        StorageCategory("work", "作業キャッシュ", (DATA_WORK_DIR,), True),
        StorageCategory("browser-cache", "画面・動画キャッシュ", (ROOT_DIR / "Cache",), False, True),
        StorageCategory("logs", "ログ", (ROOT_DIR / "logs", DATA_DIR / "logs"), True),
        StorageCategory("model-cache", "解析モデルキャッシュ", (Path.home() / ".cache" / "torch" / "hub" / "checkpoints",), True),
        StorageCategory("source-audio", "元音声", (DATA_AUDIO_DIR,)),
        StorageCategory("source-video", "元動画", (DATA_VIDEO_DIR,)),
        StorageCategory("source-stems", "元stems", (DATA_STEMS_DIR,)),
        StorageCategory("score-work", "楽譜抽出データ", (DATA_SCORE_DIR,)),
        StorageCategory("results", "解析JSON", (DATA_RESULTS_DIR,)),
        StorageCategory("public-assets", "再生・公開用成果物", (PUBLIC_AUDIO_DIR, PUBLIC_VIDEO_DIR, PUBLIC_STEMS_DIR, PUBLIC_SCORE_DIR, PUBLIC_RESULTS_DIR)),
        StorageCategory("duplicate-video", "重複している再生用動画", (), True, False, False),
        StorageCategory("orphaned-public", "ライブラリにない再生用ファイル", (), True, False, False),
    )


def measure_path(path: Path, *, seen_files: set[tuple[int, int]] | None = None) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if seen_files is not None and identity in seen_files:
            return 0, 0
        if seen_files is not None:
            seen_files.add(identity)
        return stat.st_size, 1
    total = 0
    count = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                stat = item.stat()
                identity = (stat.st_dev, stat.st_ino)
                if seen_files is not None and identity in seen_files:
                    continue
                if seen_files is not None:
                    seen_files.add(identity)
                total += stat.st_size
                count += 1
        except (FileNotFoundError, OSError):
            continue
    return total, count


def storage_report() -> dict:
    categories = []
    total = 0
    seen_files: set[tuple[int, int]] = set()
    for category in storage_categories():
        if category.key in {"duplicate-video", "orphaned-public"}:
            if category.key == "duplicate-video":
                candidate_paths = [source for source, _destination in _duplicate_video_candidates()]
            else:
                candidate_paths = _orphaned_public_candidates()
            size = 0
            files = 0
            for candidate in candidate_paths:
                candidate_size, candidate_files = measure_path(candidate)
                size += candidate_size
                files += candidate_files
        else:
            size = 0
            files = 0
            for path in category.paths:
                path_size, path_files = measure_path(path, seen_files=seen_files)
                size += path_size
                files += path_files
        if category.count_toward_total:
            total += size
        categories.append(
            {
                "key": category.key,
                "label": category.label,
                "bytes": size,
                "files": files,
                "cleanup": category.cleanup,
                "desktopCleanup": category.desktop_cleanup,
            }
        )
    return {"totalBytes": total, "categories": categories}


def _clear_directory(path: Path, *, protected_names: set[str] | None = None) -> tuple[int, int]:
    protected_names = protected_names or set()
    before_bytes, before_files = measure_path(path)
    if not path.exists():
        return 0, 0
    for child in path.iterdir():
        if child.name in protected_names:
            continue
        if child.is_symlink() or child.is_file():
            child.unlink(missing_ok=True)
        elif child.is_dir():
            shutil.rmtree(child)
    after_bytes, after_files = measure_path(path)
    return max(0, before_bytes - after_bytes), max(0, before_files - after_files)


def _same_contents(first: Path, second: Path) -> bool:
    def digest(path: Path) -> bytes:
        checksum = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(chunk)
        return checksum.digest()

    return digest(first) == digest(second)


def _duplicate_video_candidates() -> list[tuple[Path, Path]]:
    candidates = []
    if not DATA_VIDEO_DIR.exists() or not PUBLIC_VIDEO_DIR.exists():
        return candidates
    for source in DATA_VIDEO_DIR.glob("*.mp4"):
        destination = PUBLIC_VIDEO_DIR / source.name
        try:
            if destination.is_file() and not os.path.samefile(source, destination):
                source_stat = source.stat()
                destination_stat = destination.stat()
                if source_stat.st_size == destination_stat.st_size and source_stat.st_mtime_ns == destination_stat.st_mtime_ns:
                    candidates.append((source, destination))
        except OSError:
            continue
    return candidates


def _deduplicate_public_videos() -> tuple[int, int]:
    saved_bytes = 0
    optimized_files = 0
    for source, destination in _duplicate_video_candidates():
        if not _same_contents(source, destination):
            continue
        with tempfile.NamedTemporaryFile(prefix=f".{destination.name}-", dir=destination.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
        temporary_path.unlink(missing_ok=True)
        try:
            os.link(source, temporary_path)
            temporary_path.replace(destination)
            saved_bytes += source.stat().st_size
            optimized_files += 1
        except OSError:
            pass
        finally:
            temporary_path.unlink(missing_ok=True)
    return saved_bytes, optimized_files


def _known_session_ids() -> set[str]:
    known = {
        path.stem
        for path in DATA_RESULTS_DIR.glob("*.json")
        if path.name not in {"manifest.json", "folders.json"}
    }
    try:
        manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
        if isinstance(manifest, list):
            known.update(str(item["id"]) for item in manifest if isinstance(item, dict) and item.get("id"))
    except (FileNotFoundError, OSError, ValueError):
        pass
    return known


def _orphaned_public_candidates() -> list[Path]:
    known = _known_session_ids()
    candidates: list[Path] = []
    for directory in (PUBLIC_AUDIO_DIR, PUBLIC_VIDEO_DIR):
        if directory.is_dir():
            candidates.extend(path for path in directory.iterdir() if path.is_file() and path.stem not in known)
    if PUBLIC_STEMS_DIR.is_dir():
        candidates.extend(path for path in PUBLIC_STEMS_DIR.iterdir() if path.name not in known)
    if PUBLIC_RESULTS_DIR.is_dir():
        candidates.extend(
            path for path in PUBLIC_RESULTS_DIR.glob("*.json")
            if path.name not in {"manifest.json", "folders.json"} and path.stem not in known
        )
    return candidates


def _clear_orphaned_public() -> tuple[int, int]:
    removed_bytes = 0
    removed_files = 0
    for path in _orphaned_public_candidates():
        size, files = measure_path(path)
        try:
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                continue
        except OSError:
            continue
        removed_bytes += size
        removed_files += files
    return removed_bytes, removed_files


def cleanup_storage(categories: list[str]) -> dict:
    allowed = {category.key: category for category in storage_categories() if category.cleanup}
    requested = list(dict.fromkeys(categories))
    if not requested or any(key not in allowed for key in requested):
        raise ValueError("削除対象のキャッシュ種別が不正です")

    removed_bytes = 0
    removed_files = 0
    for key in requested:
        if key == "duplicate-video":
            size, files = _deduplicate_public_videos()
            removed_bytes += size
            removed_files += files
            continue
        if key == "orphaned-public":
            size, files = _clear_orphaned_public()
            removed_bytes += size
            removed_files += files
            continue
        category = allowed[key]
        for path in category.paths:
            protected = {"uploads", "stem-exports", "r2-sync-cache.json"} if key == "work" else set()
            size, files = _clear_directory(path, protected_names=protected)
            removed_bytes += size
            removed_files += files
    return {
        "removedBytes": removed_bytes,
        "removedFiles": removed_files,
        "report": storage_report(),
    }
