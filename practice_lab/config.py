import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT_DIR / "public"
DATA_DIR = ROOT_DIR / "data"
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


def ensure_directories() -> None:
    for path in (
        PUBLIC_DIR,
        DATA_DIR,
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

    if not MANIFEST_FILE.exists():
        MANIFEST_FILE.write_text("[]", encoding="utf-8")
    if not FOLDERS_FILE.exists():
        FOLDERS_FILE.write_text("[]", encoding="utf-8")
