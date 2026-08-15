import os
import shutil
from pathlib import Path


SOURCE_ROOT = Path(os.environ.get("PRACTICE_LAB_RESOURCE_DIR", Path(__file__).resolve().parent.parent)).resolve()
ROOT_DIR = Path(os.environ.get("PRACTICE_LAB_HOME", SOURCE_ROOT)).resolve()
PUBLIC_SOURCE_DIR = SOURCE_ROOT / "public"
PUBLIC_DIR = ROOT_DIR / "public"
DATA_DIR = ROOT_DIR / "data"
RUNTIME_DIR = ROOT_DIR / "runtime"
DATA_AUDIO_DIR = DATA_DIR / "audio"
DATA_VIDEO_DIR = DATA_DIR / "video"
DATA_SCORE_DIR = DATA_DIR / "score"
DATA_STEMS_DIR = DATA_DIR / "stems"
DATA_RESULTS_DIR = DATA_DIR / "results"
DATA_WORK_DIR = DATA_DIR / "work"
PUBLIC_AUDIO_DIR = PUBLIC_DIR / "audio"
PUBLIC_VIDEO_DIR = PUBLIC_DIR / "video"
PUBLIC_SCORE_DIR = PUBLIC_DIR / "score"
PUBLIC_STEMS_DIR = PUBLIC_DIR / "stems"
PUBLIC_RESULTS_DIR = PUBLIC_DIR / "results"
MANIFEST_FILE = DATA_RESULTS_DIR / "manifest.json"
FOLDERS_FILE = DATA_RESULTS_DIR / "folders.json"


def _parse_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_files() -> None:
    if os.environ.get("PRACTICE_LAB_SKIP_ENV_FILE") == "1" or os.environ.get("MUSIC_STRUCTURE_SKIP_ENV_FILE") == "1":
        return
    for env_file in (ROOT_DIR / ".env", ROOT_DIR / ".env.local"):
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = _parse_env_value(value)


load_env_files()


def default_wsl_python() -> Path:
    configured = os.environ.get("PRACTICE_LAB_WSL_PYTHON")
    if configured:
        return Path(configured)

    # Source development can share the verified desktop CUDA runtime instead
    # of keeping a second multi-gigabyte WSL environment in the repository.
    local_app_data = os.environ.get("LOCALAPPDATA")
    if ROOT_DIR == SOURCE_ROOT and local_app_data:
        shared_runtime = Path(local_app_data) / "PracticeLab" / "runtime" / "wsl"
        shared_python = shared_runtime / ".venv" / "bin" / "python"
        if os.path.lexists(shared_python) and (shared_runtime / ".verified").is_file():
            return shared_python

    if ROOT_DIR == SOURCE_ROOT:
        return SOURCE_ROOT / ".venv-wsl" / "bin" / "python"
    return RUNTIME_DIR / "wsl" / ".venv" / "bin" / "python"


def ensure_directories() -> None:
    for path in (
        PUBLIC_DIR,
        DATA_DIR,
        RUNTIME_DIR,
        DATA_AUDIO_DIR,
        DATA_VIDEO_DIR,
        DATA_SCORE_DIR,
        DATA_STEMS_DIR,
        DATA_RESULTS_DIR,
        DATA_WORK_DIR,
        PUBLIC_AUDIO_DIR,
        PUBLIC_VIDEO_DIR,
        PUBLIC_SCORE_DIR,
        PUBLIC_STEMS_DIR,
        PUBLIC_RESULTS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)

    # Installed builds keep immutable UI assets beside the executable and all
    # writable state under the user's application-data directory. Refreshing
    # these three files on startup makes app updates visible without touching
    # sessions, audio, scores, or credentials.
    if PUBLIC_SOURCE_DIR != PUBLIC_DIR:
        for name in ("index.html", "app.js", "styles.css"):
            source = PUBLIC_SOURCE_DIR / name
            if source.is_file():
                shutil.copy2(source, PUBLIC_DIR / name)

    if not MANIFEST_FILE.exists():
        MANIFEST_FILE.write_text("[]", encoding="utf-8")
    if not FOLDERS_FILE.exists():
        FOLDERS_FILE.write_text("[]", encoding="utf-8")
