import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_data_directory_can_be_shared_without_sharing_the_app_home(tmp_path: Path) -> None:
    app_home = tmp_path / "dev-profile"
    shared_data = tmp_path / "normal-profile" / "data"
    shared_runtime = tmp_path / "normal-profile" / "runtime"
    shared_public = tmp_path / "normal-profile" / "public"
    env = {
        **os.environ,
        "PRACTICE_LAB_HOME": str(app_home),
        "PRACTICE_LAB_DATA_DIR": str(shared_data),
        "PRACTICE_LAB_RUNTIME_DIR": str(shared_runtime),
        "PRACTICE_LAB_PUBLIC_AUDIO_DIR": str(shared_public / "audio"),
        "PRACTICE_LAB_PUBLIC_VIDEO_DIR": str(shared_public / "video"),
        "PRACTICE_LAB_PUBLIC_SCORE_DIR": str(shared_public / "score"),
        "PRACTICE_LAB_PUBLIC_STEMS_DIR": str(shared_public / "stems"),
        "PRACTICE_LAB_SKIP_ENV_FILE": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", "from practice_lab.config import DATA_DIR, PUBLIC_DIR, PUBLIC_AUDIO_DIR, PUBLIC_VIDEO_DIR, PUBLIC_SCORE_DIR, PUBLIC_STEMS_DIR, RUNTIME_DIR; print(DATA_DIR); print(PUBLIC_DIR); print(RUNTIME_DIR); print(PUBLIC_AUDIO_DIR); print(PUBLIC_VIDEO_DIR); print(PUBLIC_SCORE_DIR); print(PUBLIC_STEMS_DIR)"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.splitlines() == [
        str(shared_data),
        str(app_home / "public"),
        str(shared_runtime),
        str(shared_public / "audio"),
        str(shared_public / "video"),
        str(shared_public / "score"),
        str(shared_public / "stems"),
    ]
