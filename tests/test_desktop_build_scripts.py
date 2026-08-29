from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windows_cpu_runtime_bundles_common_frozen_modules() -> None:
    script = (REPO_ROOT / "scripts" / "build_desktop_cpu_runtime.ps1").read_text(
        encoding="utf-8"
    )

    assert "--collect-all yt_dlp" in script
