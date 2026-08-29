from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import importlib
import importlib.util
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .config import ROOT_DIR


RELEASE_API = "https://api.github.com/repos/Nattuhan/practice-lab/releases/tags/v{version}"
CPU_FEATURE_KEY = "windows-cpu"
SCORE_FEATURE_KEY = "score"


def app_version() -> str:
    return os.environ.get("PRACTICE_LAB_VERSION", "").strip()


def windows_cpu_asset_name(version: str | None = None) -> str:
    resolved = version or app_version()
    if not resolved:
        raise RuntimeError("アプリのバージョンを確認できません")
    return f"PracticeLab-Windows-CPU-{resolved}.zip"


def windows_cpu_runtime_dir(version: str | None = None) -> Path:
    resolved = version or app_version()
    return ROOT_DIR / "runtime" / CPU_FEATURE_KEY / resolved


def windows_cpu_runtime_executable(version: str | None = None) -> Path:
    name = "practice-lab-cpu-runtime.exe" if platform.system() == "Windows" else "practice-lab-cpu-runtime"
    return windows_cpu_runtime_dir(version) / "practice-lab-cpu-runtime" / name


def score_platform_name() -> str:
    if platform.system() == "Windows":
        return "Windows"
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "macOS-arm64"
    return "unsupported"


def score_asset_name(version: str | None = None) -> str:
    resolved = version or app_version()
    if not resolved:
        raise RuntimeError("アプリのバージョンを確認できません")
    return f"PracticeLab-Score-{score_platform_name()}-{resolved}.zip"


def score_runtime_dir(version: str | None = None) -> Path:
    resolved = version or app_version()
    return ROOT_DIR / "runtime" / SCORE_FEATURE_KEY / resolved


def score_site_packages(version: str | None = None) -> Path:
    return score_runtime_dir(version) / "score-pack" / "site-packages"


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file() and not item.is_symlink())


def activate_score_pack() -> bool:
    site_packages = score_site_packages()
    if not site_packages.is_dir():
        return False
    value = str(site_packages)
    if value not in sys.path:
        sys.path.insert(0, value)
        importlib.invalidate_caches()
    return True


def score_runtime_available() -> bool:
    activate_score_pack()
    return all(importlib.util.find_spec(name) is not None for name in ("cv2", "PIL", "rapidocr_onnxruntime"))


def feature_status() -> dict:
    cpu_executable = windows_cpu_runtime_executable()
    score_path = score_runtime_dir()
    score_installed = score_path.is_dir()
    if not getattr(sys, "frozen", False):
        score_installed = score_installed or score_runtime_available()
    return {
        CPU_FEATURE_KEY: {
            "available": platform.system() == "Windows",
            "installed": cpu_executable.is_file(),
            "version": app_version(),
            "bytes": _directory_size(windows_cpu_runtime_dir()),
        },
        SCORE_FEATURE_KEY: {
            "available": score_platform_name() != "unsupported",
            "installed": score_installed,
            "version": app_version(),
            "bytes": _directory_size(score_path),
        },
    }


def _release_asset(version: str, expected_name: str, label: str) -> dict:
    request = urllib.request.Request(
        RELEASE_API.format(version=version),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PracticeLab"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    asset = next((item for item in release.get("assets", []) if item.get("name") == expected_name), None)
    if not asset:
        raise RuntimeError(f"{label}がReleaseにありません: {expected_name}")
    digest = str(asset.get("digest") or "")
    if not digest.startswith("sha256:"):
        raise RuntimeError(f"{label}のSHA-256を確認できません")
    return asset


def _download(url: str, destination: Path, label: str, progress: Callable[[str], None] | None = None) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "PracticeLab"})
    checksum = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            checksum.update(chunk)
            downloaded += len(chunk)
            if progress and total:
                progress(f"{label}をダウンロード中 ({downloaded * 100 // total}%)")
    return checksum.hexdigest()


def _safe_extract(archive: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if target != destination_root and destination_root not in target.parents:
                raise RuntimeError("追加機能パックに不正なパスが含まれています")
        bundle.extractall(destination)


def install_windows_cpu_runtime(progress: Callable[[str], None] | None = None) -> dict:
    if platform.system() != "Windows" or os.environ.get("PRACTICE_LAB_DESKTOP") != "1":
        raise RuntimeError("CPU解析パックはWindowsデスクトップ版でのみ追加できます")
    version = app_version()
    asset_name = windows_cpu_asset_name(version)
    asset = _release_asset(version, asset_name, "CPU解析パック")
    destination = windows_cpu_runtime_dir(version)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp_dir:
        temp_root = Path(temp_dir)
        archive = temp_root / asset_name
        if progress:
            progress("CPU解析パックを確認しています")
        actual_digest = _download(str(asset["browser_download_url"]), archive, "CPU解析パック", progress)
        expected_digest = str(asset["digest"]).removeprefix("sha256:")
        if actual_digest.lower() != expected_digest.lower():
            raise RuntimeError("CPU解析パックのSHA-256が一致しません")
        staged = temp_root / "extracted"
        staged.mkdir()
        if progress:
            progress("CPU解析パックを展開しています")
        _safe_extract(archive, staged)
        expected_executable = staged / "practice-lab-cpu-runtime" / "practice-lab-cpu-runtime.exe"
        if not expected_executable.is_file():
            raise RuntimeError("CPU解析パックの実行ファイルが見つかりません")
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
    return feature_status()[CPU_FEATURE_KEY]


def uninstall_windows_cpu_runtime() -> dict:
    destination = windows_cpu_runtime_dir()
    if destination.exists():
        shutil.rmtree(destination)
    return feature_status()[CPU_FEATURE_KEY]


def install_score_runtime(progress: Callable[[str], None] | None = None) -> dict:
    if score_platform_name() == "unsupported" or os.environ.get("PRACTICE_LAB_DESKTOP") != "1":
        raise RuntimeError("楽譜抽出パックは対応するデスクトップ版でのみ追加できます")
    version = app_version()
    asset_name = score_asset_name(version)
    asset = _release_asset(version, asset_name, "楽譜抽出パック")
    destination = score_runtime_dir(version)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp_dir:
        temp_root = Path(temp_dir)
        archive = temp_root / asset_name
        if progress:
            progress("楽譜抽出パックを確認しています")
        actual_digest = _download(str(asset["browser_download_url"]), archive, "楽譜抽出パック", progress)
        expected_digest = str(asset["digest"]).removeprefix("sha256:")
        if actual_digest.lower() != expected_digest.lower():
            raise RuntimeError("楽譜抽出パックのSHA-256が一致しません")
        staged = temp_root / "extracted"
        staged.mkdir()
        if progress:
            progress("楽譜抽出パックを展開しています")
        _safe_extract(archive, staged)
        if not (staged / "score-pack" / "site-packages" / "rapidocr_onnxruntime").is_dir():
            raise RuntimeError("楽譜抽出パックのライブラリが見つかりません")
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
    if not score_runtime_available():
        raise RuntimeError("楽譜抽出パックを読み込めませんでした")
    return feature_status()[SCORE_FEATURE_KEY]


def uninstall_score_runtime() -> dict:
    destination = score_runtime_dir()
    if destination.exists():
        shutil.rmtree(destination)
    return {"available": score_platform_name() != "unsupported", "installed": False, "version": app_version(), "bytes": 0}
