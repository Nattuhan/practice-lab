from __future__ import annotations

import shutil
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
    PUBLIC_AUDIO_DIR,
    PUBLIC_RESULTS_DIR,
    PUBLIC_SCORE_DIR,
    PUBLIC_STEMS_DIR,
    PUBLIC_VIDEO_DIR,
)


@dataclass(frozen=True)
class StorageCategory:
    key: str
    label: str
    paths: tuple[Path, ...]
    cleanup: bool = False


def storage_categories() -> tuple[StorageCategory, ...]:
    return (
        StorageCategory("work", "作業キャッシュ", (DATA_WORK_DIR,), True),
        StorageCategory("logs", "ログ", (DATA_DIR / "logs",), True),
        StorageCategory("model-cache", "解析モデルキャッシュ", (Path.home() / ".cache" / "torch" / "hub" / "checkpoints",), True),
        StorageCategory("source-audio", "元音声", (DATA_AUDIO_DIR,)),
        StorageCategory("source-video", "元動画", (DATA_VIDEO_DIR,)),
        StorageCategory("source-stems", "元stems", (DATA_STEMS_DIR,)),
        StorageCategory("score-work", "楽譜抽出データ", (DATA_SCORE_DIR,)),
        StorageCategory("results", "解析JSON", (DATA_RESULTS_DIR,)),
        StorageCategory("public-assets", "再生・公開用成果物", (PUBLIC_AUDIO_DIR, PUBLIC_VIDEO_DIR, PUBLIC_STEMS_DIR, PUBLIC_SCORE_DIR, PUBLIC_RESULTS_DIR)),
    )


def measure_path(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    if path.is_file():
        return path.stat().st_size, 1
    total = 0
    count = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
                count += 1
        except (FileNotFoundError, OSError):
            continue
    return total, count


def storage_report() -> dict:
    categories = []
    total = 0
    for category in storage_categories():
        size = 0
        files = 0
        for path in category.paths:
            path_size, path_files = measure_path(path)
            size += path_size
            files += path_files
        total += size
        categories.append(
            {
                "key": category.key,
                "label": category.label,
                "bytes": size,
                "files": files,
                "cleanup": category.cleanup,
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


def cleanup_storage(categories: list[str]) -> dict:
    allowed = {category.key: category for category in storage_categories() if category.cleanup}
    requested = list(dict.fromkeys(categories))
    if not requested or any(key not in allowed for key in requested):
        raise ValueError("削除対象のキャッシュ種別が不正です")

    removed_bytes = 0
    removed_files = 0
    for key in requested:
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
