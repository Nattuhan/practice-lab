from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import importlib
import importlib.util
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path
from typing import Callable

from .config import ROOT_DIR


RELEASE_API = "https://api.github.com/repos/Nattuhan/practice-lab/releases/tags/v{version}"
LATEST_RELEASE_API = "https://api.github.com/repos/Nattuhan/practice-lab/releases/latest"
CPU_FEATURE_KEY = "windows-cpu"
MAC_ANALYSIS_FEATURE_KEY = "mac-analysis"
SCORE_FEATURE_KEY = "score"
CPU_RUNTIME_ABI = "abi-1"
MAC_ANALYSIS_RUNTIME_ABI = "abi-1"
SCORE_RUNTIME_ABI = "abi-1"


def app_version() -> str:
    return os.environ.get("PRACTICE_LAB_VERSION", "").strip()


def windows_cpu_asset_name(version: str | None = None) -> str:
    resolved = version or app_version()
    if not resolved:
        raise RuntimeError("アプリのバージョンを確認できません")
    return f"PracticeLab-Windows-CPU-{resolved}.zip"


def _feature_root(feature_key: str) -> Path:
    return ROOT_DIR / "runtime" / feature_key


def _stable_runtime_dir(feature_key: str, runtime_abi: str) -> Path:
    return _feature_root(feature_key) / runtime_abi


def _cleanup_legacy_runtimes(feature_root: Path, keep: Path) -> None:
    if not feature_root.is_dir():
        return
    for child in feature_root.iterdir():
        managed_name = child.name.startswith("abi-") or all(part.isdigit() for part in child.name.split("."))
        if child == keep or not child.is_dir() or not managed_name:
            continue
        try:
            shutil.rmtree(child)
        except OSError:
            # A running Windows executable can temporarily keep DLLs locked.
            # The compatible runtime remains usable and cleanup is retried on
            # the next feature check or installation.
            continue


def _resolve_compatible_runtime(feature_key: str, runtime_abi: str, marker: Path) -> Path:
    feature_root = _feature_root(feature_key)
    stable = feature_root / runtime_abi
    if (stable / marker).exists():
        _cleanup_legacy_runtimes(feature_root, stable)
        return stable
    if not feature_root.is_dir():
        return stable
    candidates = sorted(
        (
            child for child in feature_root.iterdir()
            if child.is_dir() and child != stable and not child.name.startswith("abi-")
        ),
        key=lambda child: child.stat().st_mtime_ns,
        reverse=True,
    )
    for candidate in candidates:
        if not (candidate / marker).exists():
            continue
        try:
            candidate.replace(stable)
        except OSError:
            return candidate
        _cleanup_legacy_runtimes(feature_root, stable)
        return stable
    return stable


def windows_cpu_runtime_dir() -> Path:
    executable_name = "practice-lab-cpu-runtime.exe" if platform.system() == "Windows" else "practice-lab-cpu-runtime"
    return _resolve_compatible_runtime(
        CPU_FEATURE_KEY,
        CPU_RUNTIME_ABI,
        Path("practice-lab-cpu-runtime") / executable_name,
    )


def windows_cpu_runtime_executable() -> Path:
    name = "practice-lab-cpu-runtime.exe" if platform.system() == "Windows" else "practice-lab-cpu-runtime"
    return windows_cpu_runtime_dir() / "practice-lab-cpu-runtime" / name


def mac_analysis_asset_name(version: str | None = None) -> str:
    resolved = version or app_version()
    if not resolved:
        raise RuntimeError("アプリのバージョンを確認できません")
    return f"PracticeLab-Analysis-macOS-arm64-{resolved}.zip"


def mac_analysis_runtime_dir() -> Path:
    return _resolve_compatible_runtime(
        MAC_ANALYSIS_FEATURE_KEY,
        MAC_ANALYSIS_RUNTIME_ABI,
        Path("practice-lab-analysis-runtime") / "practice-lab-analysis-runtime",
    )


def mac_analysis_runtime_executable() -> Path:
    return mac_analysis_runtime_dir() / "practice-lab-analysis-runtime" / "practice-lab-analysis-runtime"


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


def score_runtime_dir() -> Path:
    return _resolve_compatible_runtime(
        SCORE_FEATURE_KEY,
        SCORE_RUNTIME_ABI,
        Path("score-pack") / "site-packages" / "rapidocr_onnxruntime",
    )


def score_site_packages() -> Path:
    return score_runtime_dir() / "score-pack" / "site-packages"


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
        MAC_ANALYSIS_FEATURE_KEY: {
            "available": platform.system() == "Darwin" and platform.machine() == "arm64",
            "installed": mac_analysis_runtime_executable().is_file(),
            "version": app_version(),
            "bytes": _directory_size(mac_analysis_runtime_dir()),
        },
        SCORE_FEATURE_KEY: {
            "available": score_platform_name() != "unsupported",
            "installed": score_installed,
            "version": app_version(),
            "bytes": _directory_size(score_path),
        },
    }


def _local_feature_asset(expected_name: str, compatible_prefix: str) -> dict | None:
    configured = os.environ.get("PRACTICE_LAB_FEATURE_PACK_DIR", "").strip()
    candidates = [Path(configured)] if configured else []
    if not getattr(sys, "frozen", False):
        candidates.append(ROOT_DIR / "desktop" / "dist" / "installer")
    for directory in candidates:
        if not directory.is_dir():
            continue
        exact = directory / expected_name
        matches = [exact] if exact.is_file() else sorted(
            directory.glob(f"{compatible_prefix}*.zip"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        if not matches:
            continue
        source = matches[0].resolve()
        checksum = hashlib.sha256()
        with source.open("rb") as input_file:
            for chunk in iter(lambda: input_file.read(4 * 1024 * 1024), b""):
                checksum.update(chunk)
        digest = checksum.hexdigest()
        return {
            "name": source.name,
            "browser_download_url": source.as_uri(),
            "digest": f"sha256:{digest}",
            "compatible": source.name != expected_name,
        }
    return None


def _load_release(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PracticeLab"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _release_asset(version: str, expected_name: str, compatible_prefix: str, label: str) -> dict:
    local_asset = _local_feature_asset(expected_name, compatible_prefix)
    if local_asset:
        return local_asset
    try:
        release = _load_release(RELEASE_API.format(version=version))
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        release = _load_release(LATEST_RELEASE_API)
    asset = next((item for item in release.get("assets", []) if item.get("name") == expected_name), None)
    if not asset:
        asset = next(
            (
                item for item in release.get("assets", [])
                if str(item.get("name") or "").startswith(compatible_prefix)
                and str(item.get("name") or "").endswith(".zip")
            ),
            None,
        )
    if not asset:
        raise RuntimeError(f"{label}の互換パックがReleaseにありません: {expected_name}")
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
    asset = _release_asset(version, asset_name, "PracticeLab-Windows-CPU-", "CPU解析パック")
    destination = _stable_runtime_dir(CPU_FEATURE_KEY, CPU_RUNTIME_ABI)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=destination.parent) as temp_dir:
        temp_root = Path(temp_dir)
        archive = temp_root / str(asset.get("name") or asset_name)
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
    _cleanup_legacy_runtimes(destination.parent, destination)
    return feature_status()[CPU_FEATURE_KEY]


def uninstall_windows_cpu_runtime() -> dict:
    feature_root = _feature_root(CPU_FEATURE_KEY)
    if feature_root.exists():
        shutil.rmtree(feature_root)
    return feature_status()[CPU_FEATURE_KEY]


def install_mac_analysis_runtime(progress: Callable[[str], None] | None = None) -> dict:
    if (
        platform.system() != "Darwin"
        or platform.machine() != "arm64"
        or os.environ.get("PRACTICE_LAB_DESKTOP") != "1"
    ):
        raise RuntimeError("Mac解析パックはApple Silicon Macデスクトップ版でのみ追加できます")
    version = app_version()
    asset_name = mac_analysis_asset_name(version)
    asset = _release_asset(
        version,
        asset_name,
        "PracticeLab-Analysis-macOS-arm64-",
        "Mac解析パック",
    )
    destination = _stable_runtime_dir(MAC_ANALYSIS_FEATURE_KEY, MAC_ANALYSIS_RUNTIME_ABI)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=destination.parent) as temp_dir:
        temp_root = Path(temp_dir)
        archive = temp_root / str(asset.get("name") or asset_name)
        if progress:
            progress("Mac解析パックを確認しています")
        actual_digest = _download(str(asset["browser_download_url"]), archive, "Mac解析パック", progress)
        expected_digest = str(asset["digest"]).removeprefix("sha256:")
        if actual_digest.lower() != expected_digest.lower():
            raise RuntimeError("Mac解析パックのSHA-256が一致しません")
        staged = temp_root / "extracted"
        staged.mkdir()
        if progress:
            progress("Mac解析パックを展開しています")
        _safe_extract(archive, staged)
        expected_executable = staged / "practice-lab-analysis-runtime" / "practice-lab-analysis-runtime"
        if not expected_executable.is_file():
            raise RuntimeError("Mac解析パックの実行ファイルが見つかりません")
        expected_executable.chmod(
            expected_executable.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
    _cleanup_legacy_runtimes(destination.parent, destination)
    return feature_status()[MAC_ANALYSIS_FEATURE_KEY]


def uninstall_mac_analysis_runtime() -> dict:
    feature_root = _feature_root(MAC_ANALYSIS_FEATURE_KEY)
    if feature_root.exists():
        shutil.rmtree(feature_root)
    return feature_status()[MAC_ANALYSIS_FEATURE_KEY]


def install_score_runtime(progress: Callable[[str], None] | None = None) -> dict:
    if score_platform_name() == "unsupported" or os.environ.get("PRACTICE_LAB_DESKTOP") != "1":
        raise RuntimeError("楽譜抽出パックは対応するデスクトップ版でのみ追加できます")
    version = app_version()
    asset_name = score_asset_name(version)
    compatible_prefix = f"PracticeLab-Score-{score_platform_name()}-"
    asset = _release_asset(version, asset_name, compatible_prefix, "楽譜抽出パック")
    destination = _stable_runtime_dir(SCORE_FEATURE_KEY, SCORE_RUNTIME_ABI)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=destination.parent) as temp_dir:
        temp_root = Path(temp_dir)
        archive = temp_root / str(asset.get("name") or asset_name)
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
    _cleanup_legacy_runtimes(destination.parent, destination)
    if not score_runtime_available():
        raise RuntimeError("楽譜抽出パックを読み込めませんでした")
    return feature_status()[SCORE_FEATURE_KEY]


def uninstall_score_runtime() -> dict:
    feature_root = _feature_root(SCORE_FEATURE_KEY)
    if feature_root.exists():
        shutil.rmtree(feature_root)
    return {"available": score_platform_name() != "unsupported", "installed": False, "version": app_version(), "bytes": 0}
