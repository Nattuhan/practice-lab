import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_data_directory_can_be_shared_without_sharing_the_app_home(tmp_path: Path) -> None:
    app_home = tmp_path / "dev-profile"
    shared_data = tmp_path / "normal-profile" / "data"
    shared_runtime = tmp_path / "normal-profile" / "runtime"
    env = {
        **os.environ,
        "PRACTICE_LAB_HOME": str(app_home),
        "PRACTICE_LAB_DATA_DIR": str(shared_data),
        "PRACTICE_LAB_RUNTIME_DIR": str(shared_runtime),
        "PRACTICE_LAB_SKIP_ENV_FILE": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", "from practice_lab.config import DATA_DIR, PUBLIC_DIR, RUNTIME_DIR; print(DATA_DIR); print(PUBLIC_DIR); print(RUNTIME_DIR)"],
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
    ]
