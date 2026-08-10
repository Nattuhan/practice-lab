import importlib
import platform
from pathlib import Path
import shutil
import subprocess
import sys


REQUIRED_COMMANDS = ("ffmpeg", "ffprobe", "node")
REQUIRED_MODULES = ("fastapi", "uvicorn", "yt_dlp", "librosa", "numpy", "multipart")
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
WSL_PYTHON = REPO_ROOT / ".venv-wsl" / "bin" / "python"

from practice_lab.analyzer_backend import resolve_backend, to_wsl_path


def main() -> int:
    print(f"Python: {sys.version}")
    print(f"Executable: {sys.executable}")

    failures = []
    warnings = []

    recommended = (3, 11) if platform.system() == "Darwin" else (3, 10)
    if sys.version_info[:2] != recommended:
        warnings.append(f"Python {recommended[0]}.{recommended[1]} is recommended.")

    for command in REQUIRED_COMMANDS:
        resolved = shutil.which(command)
        if resolved:
            print(f"[ok] command {command}: {resolved}")
        else:
            failures.append(f"Missing command: {command}")

    for module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            print(f"[ok] module {module_name}: {version}")
        except Exception as exc:
            failures.append(f"Import failed for {module_name}: {exc}")

    try:
        subprocess.run([sys.executable, "-c", "from practice_lab.app import create_app; create_app()"], check=True)
        print("[ok] app import smoke test passed")
    except subprocess.CalledProcessError as exc:
        failures.append(f"App smoke test failed: exit {exc.returncode}")

    try:
        backend = resolve_backend(wsl_python=WSL_PYTHON)
        print(f"[ok] analyzer backend: {backend.label} ({backend.executor})")
    except RuntimeError as exc:
        failures.append(str(exc))
        backend = None

    if backend and backend.executor == "wsl":
        wsl_exe = shutil.which("wsl.exe")
        if not wsl_exe:
            failures.append("Missing command: wsl.exe")
        else:
            try:
                subprocess.run(
                    [
                        wsl_exe,
                        "bash",
                        "-lc",
                        (
                            f"cd {to_wsl_path(REPO_ROOT)} && "
                            "test -x .venv-wsl/bin/python && "
                            ".venv-wsl/bin/python -c \"import allin1fix, torch, torchaudio; print(allin1fix.__version__)\""
                        ),
                    ],
                    check=True,
                )
                print("[ok] WSL analyzer import smoke test passed")
            except subprocess.CalledProcessError as exc:
                failures.append(f"WSL analyzer smoke test failed: exit {exc.returncode}")
    elif backend:
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import allin1fix, demucs_infer, torch; print(allin1fix.__version__, torch.__version__)",
                ],
                check=True,
            )
            print("[ok] native analyzer import smoke test passed")
        except subprocess.CalledProcessError as exc:
            failures.append(f"Native analyzer smoke test failed: exit {exc.returncode}")

    if failures:
        print("\nEnvironment check failed:")
        for failure in failures:
            print(f"- {failure}")
        if warnings:
            print("\nWarnings:")
            for warning in warnings:
                print(f"- {warning}")
        return 1

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")

    print("\nEnvironment looks usable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
