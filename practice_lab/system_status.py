from __future__ import annotations

import os
import platform
import shutil
import subprocess
import importlib.util
from pathlib import Path

from .analyzer_backend import to_wsl_path
from .config import ROOT_DIR, SOURCE_ROOT, default_wsl_python
from .optional_features import windows_cpu_runtime_executable


def _run(command: list[str], *, timeout: int = 12) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def get_system_status() -> dict:
    system = platform.system()
    desktop = os.environ.get("PRACTICE_LAB_DESKTOP") == "1"
    requested_mode = os.environ.get("PRACTICE_LAB_ANALYSIS_MODE", "cpu").strip().lower()
    analysis_mode = "nvidia" if system == "Windows" and requested_mode == "nvidia" else "cpu"
    status = {
        "desktop": desktop,
        "platform": system,
        "analysisMode": analysis_mode,
        "analysisLabel": "NVIDIA GPU・WSL2 CUDA" if analysis_mode == "nvidia" else ("Apple Silicon CPU" if system == "Darwin" else "CPU"),
        "nvidia": {"available": False, "name": None},
        "wsl": {"available": False, "cudaAvailable": False},
        "runtime": {"available": False},
        "ready": system != "Windows",
        "setupSupported": desktop and system == "Windows" and analysis_mode == "nvidia",
        "cpuSetupSupported": desktop and system == "Windows" and analysis_mode == "cpu",
    }
    if not desktop:
        status["ready"] = True
        return status
    if system != "Windows":
        status["runtime"]["available"] = True
        return status

    if analysis_mode == "cpu":
        required_modules = ("torch", "allin1fix", "demucs_infer")
        bundled_runtime = all(importlib.util.find_spec(name) is not None for name in required_modules)
        status["runtime"]["available"] = bundled_runtime or windows_cpu_runtime_executable().is_file()
        status["ready"] = status["runtime"]["available"]
        if not status["ready"]:
            status["message"] = "CPU解析機能を追加すると、NVIDIA環境なしで解析できます"
        return status

    nvidia_smi = shutil.which("nvidia-smi.exe") or shutil.which("nvidia-smi")
    if nvidia_smi:
        result = _run([nvidia_smi, "--query-gpu=name", "--format=csv,noheader"])
        if result and result.returncode == 0:
            names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            status["nvidia"] = {"available": True, "name": ", ".join(names) or "NVIDIA GPU"}

    wsl_exe = shutil.which("wsl.exe")
    if wsl_exe:
        result = _run([wsl_exe, "bash", "-lc", "true"])
        status["wsl"]["available"] = bool(result and result.returncode == 0)
        if status["wsl"]["available"]:
            cuda = _run([wsl_exe, "bash", "-lc", "nvidia-smi -L >/dev/null 2>&1"])
            status["wsl"]["cudaAvailable"] = bool(cuda and cuda.returncode == 0)

    wsl_python = default_wsl_python()
    verified_marker = wsl_python.parent.parent.parent / ".verified"
    if verified_marker.is_file():
        status["runtime"]["available"] = True
    elif wsl_exe and os.path.lexists(wsl_python):
        smoke = _run([
            wsl_exe,
            "bash",
            "-lc",
            f"{to_wsl_path(wsl_python)} -c 'import allin1fix, demucs_infer, torch; assert torch.cuda.is_available()'",
        ], timeout=45)
        status["runtime"]["available"] = bool(smoke and smoke.returncode == 0)

    status["ready"] = all((
        status["nvidia"]["available"],
        status["wsl"]["available"],
        status["wsl"]["cudaAvailable"],
        status["runtime"]["available"],
    ))
    return status


def launch_nvidia_setup() -> dict:
    if os.environ.get("PRACTICE_LAB_DESKTOP") != "1" or platform.system() != "Windows":
        raise RuntimeError("NVIDIAセットアップはWindowsデスクトップ版でのみ利用できます")
    script = SOURCE_ROOT / "scripts" / "setup_desktop_nvidia.ps1"
    if not script.is_file():
        raise RuntimeError("NVIDIAセットアップスクリプトが見つかりません")
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", str(script),
            "-AppHome", str(ROOT_DIR),
            "-ResourceDir", str(SOURCE_ROOT),
        ],
        cwd=ROOT_DIR,
        creationflags=creation_flags,
    )
    return {"started": True}
