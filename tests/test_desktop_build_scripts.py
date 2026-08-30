from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_windows_cpu_runtime_bundles_common_frozen_modules() -> None:
    script = (REPO_ROOT / "scripts" / "build_desktop_cpu_runtime.ps1").read_text(
        encoding="utf-8"
    )

    assert "--collect-all yt_dlp" in script


def test_windows_electron_runtime_check_waits_for_gui_executable() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "release-desktop.yml").read_text(
        encoding="utf-8"
    )

    assert "Start-Process" in workflow
    assert "-Wait `" in workflow
    assert "process.ExitCode" in workflow


def test_mac_base_app_excludes_analysis_runtime_and_builds_it_as_a_pack() -> None:
    backend_script = (REPO_ROOT / "scripts" / "build_desktop_backend_macos.sh").read_text(encoding="utf-8")
    analysis_script = (REPO_ROOT / "scripts" / "build_desktop_analysis_runtime_macos.sh").read_text(encoding="utf-8")

    assert "--exclude-module torch" in backend_script
    assert "--exclude-module allin1fix" in backend_script
    assert "--collect-all torch" in analysis_script
    assert "PracticeLab-Analysis-macOS-arm64-" in analysis_script
