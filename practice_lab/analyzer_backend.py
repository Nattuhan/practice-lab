from __future__ import annotations

import os
import platform
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnalyzerBackend:
    executor: str
    device: str
    label: str


def resolve_backend(
    *,
    purpose: str = "analyzer",
    system: str | None = None,
    wsl_python: Path | None = None,
) -> AnalyzerBackend:
    system = system or platform.system()
    executor = os.environ.get("ANALYZER_EXECUTOR", "auto").strip().lower() or "auto"
    device_key = "STEM_DEVICE" if purpose == "stems" else "ANALYZER_DEVICE"
    device = os.environ.get(device_key, "auto").strip().lower() or "auto"

    if executor not in {"auto", "native", "wsl"}:
        raise RuntimeError("ANALYZER_EXECUTOR は auto、native、wsl のいずれかを指定してください")
    if device not in {"auto", "cuda", "mps", "cpu"}:
        raise RuntimeError(f"{device_key} は auto、cuda、mps、cpu のいずれかを指定してください")

    # A Linux venv's python entry is a symlink that Windows cannot stat, while
    # os.path.lexists can still detect it from the host filesystem.
    has_wsl_runtime = bool(wsl_python and os.path.lexists(wsl_python))
    if executor == "auto":
        executor = "wsl" if system == "Windows" and has_wsl_runtime and device in {"auto", "cuda"} else "native"

    if executor == "wsl":
        if system != "Windows":
            raise RuntimeError("WSL解析はWindowsでのみ利用できます")
        if not has_wsl_runtime:
            raise RuntimeError("WSL解析環境がありません。先にセットアップを実行してください")
        resolved_device = "cuda" if device == "auto" else device
        if resolved_device == "mps":
            raise RuntimeError("MPSはmacOSネイティブ解析でのみ利用できます")
        return AnalyzerBackend("wsl", resolved_device, f"WSL {resolved_device.upper()}")

    label_device = {"auto": "自動選択", "cuda": "CUDA", "mps": "Apple MPS", "cpu": "CPU"}[device]
    return AnalyzerBackend("native", device, label_device)


def to_wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    tail = resolved.as_posix().split(":", 1)[-1].lstrip("/")
    return f"/mnt/{drive}/{tail}"


def analyzer_command(
    backend: AnalyzerBackend,
    *,
    script: Path,
    audio_path: Path,
    work_dir: Path,
    wsl_python: Path,
    native_executable: Path | None = None,
) -> tuple[list[str], Path | None]:
    if backend.executor == "native":
        return (
            [str(native_executable or sys.executable), str(script), str(audio_path), "--device", backend.device],
            work_dir,
        )
    shell_command = (
        f"export PYTHONPATH={shlex.quote(to_wsl_path(script.parent.parent))}:$PYTHONPATH && "
        f"cd {shlex.quote(to_wsl_path(work_dir))} && "
        f"{shlex.quote(to_wsl_path(wsl_python))} {shlex.quote(to_wsl_path(script))} "
        f"{shlex.quote(to_wsl_path(audio_path))} --device {shlex.quote(backend.device)}"
    )
    return (["wsl.exe", "bash", "-lc", shell_command], None)


def stem_command(
    backend: AnalyzerBackend,
    *,
    script: Path,
    audio_path: Path,
    output_dir: Path,
    work_dir: Path,
    wsl_python: Path,
    native_executable: Path | None = None,
) -> tuple[list[str], Path | None]:
    args = [
        "--device", backend.device,
        "--out", str(output_dir),
        "--filename", "{stem}.{ext}",
        str(audio_path),
    ]
    if backend.executor == "native":
        return ([str(native_executable or sys.executable), str(script), *args], work_dir)
    shell_command = (
        f"export PYTHONPATH={shlex.quote(to_wsl_path(script.parent.parent))}:$PYTHONPATH && "
        f"cd {shlex.quote(to_wsl_path(work_dir))} && "
        f"{shlex.quote(to_wsl_path(wsl_python))} {shlex.quote(to_wsl_path(script))} "
        f"--device {shlex.quote(backend.device)} "
        f"--out {shlex.quote(to_wsl_path(output_dir))} "
        "--filename '{stem}.{ext}' "
        f"{shlex.quote(to_wsl_path(audio_path))}"
    )
    return (["wsl.exe", "bash", "-lc", shell_command], None)
