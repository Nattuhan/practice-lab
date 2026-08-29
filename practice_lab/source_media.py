from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FULL_VIDEO_FALLBACK_FORMAT = "b[ext=mp4][height<=720]/b[height<=720]/b"
FULL_VIDEO_FORMAT = (
    "bv*[vcodec^=avc1][height<=1080][ext=mp4]+ba[ext=m4a]/"
    "bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"
)


def normalize_analysis_range(
    start_sec: float | None, end_sec: float | None
) -> tuple[float | None, float | None]:
    start = None if start_sec is None else float(start_sec)
    end = None if end_sec is None else float(end_sec)
    if start is not None and start < 0 or end is not None and end < 0:
        raise ValueError("開始・終了時間は0以上にしてください")
    effective_start = start or 0.0
    if end is not None and end <= effective_start:
        raise ValueError("終了時間は開始時間より後にしてください")
    if effective_start == 0 and end is None:
        return None, None
    return round(effective_start, 3), None if end is None else round(end, 3)


def source_media_cache_paths(source_video_id: str, work_dir: Path) -> tuple[Path, Path]:
    """Return full-source cache files shared by every clip of one video.

    Keeping the untrimmed source lets another range reuse the original quality
    without downloading the same YouTube video again.
    """
    cache_dir = work_dir / "source-media"
    return cache_dir / f"{source_video_id}.wav", cache_dir / f"{source_video_id}.mp4"


def _local_trim_args(start_sec: float | None, end_sec: float | None) -> tuple[list[str], list[str]]:
    start, end = normalize_analysis_range(start_sec, end_sec)
    input_args = ["-ss", f"{start:.3f}"] if start is not None else []
    output_args: list[str] = []
    if end is not None:
        output_args = ["-t", f"{end - (start or 0):.3f}"]
    return input_args, output_args


def trim_audio_range(
    source: Path,
    destination: Path,
    start_sec: float | None,
    end_sec: float | None,
) -> None:
    """Create analysis PCM locally so remote range selection cannot lower quality."""
    start, end = normalize_analysis_range(start_sec, end_sec)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if start is None and end is None:
        shutil.copy2(source, destination)
        return
    input_args, output_args = _local_trim_args(start, end)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            *input_args, "-i", str(source), *output_args,
            "-vn", "-c:a", "pcm_s16le", str(destination), "-y",
        ],
        capture_output=True,
        check=True,
    )


def trim_video_range(
    source: Path,
    destination: Path,
    start_sec: float | None,
    end_sec: float | None,
) -> None:
    """Cut locally and re-encode to keep an exact range with synchronized A/V."""
    start, end = normalize_analysis_range(start_sec, end_sec)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if start is None and end is None:
        shutil.copy2(source, destination)
        return
    input_args, output_args = _local_trim_args(start, end)
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            *input_args, "-i", str(source), *output_args,
            "-map", "0:v:0", "-map", "0:a:0?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(destination), "-y",
        ],
        capture_output=True,
        check=True,
    )


def yt_dlp_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", *args]


def yt_dlp_js_runtime() -> str:
    electron_path = os.environ.get("PRACTICE_LAB_NODE_PATH", "").strip()
    return f"node:{electron_path}" if electron_path else "node"


def yt_dlp_browser_session_args() -> list[str]:
    """Return a local browser session fallback for YouTube's signed streams.

    YouTube occasionally returns unusable anonymous stream URLs even though
    metadata extraction succeeds. A browser session makes yt-dlp use the web
    client and generate a fresh, working URL. This stays local to the device
    and is only attempted after an anonymous 403.
    """
    candidates: list[tuple[str, Path]] = []
    home = Path.home()
    if sys.platform == "darwin":
        candidates = [
            ("chrome", home / "Library/Application Support/Google/Chrome"),
            ("edge", home / "Library/Application Support/Microsoft Edge"),
            ("brave", home / "Library/Application Support/BraveSoftware/Brave-Browser"),
        ]
    elif sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        candidates = [
            ("chrome", local_app_data / "Google/Chrome/User Data"),
            ("edge", local_app_data / "Microsoft/Edge/User Data"),
            ("brave", local_app_data / "BraveSoftware/Brave-Browser/User Data"),
        ]
    else:
        candidates = [
            ("chrome", home / ".config/google-chrome"),
            ("chromium", home / ".config/chromium"),
            ("brave", home / ".config/BraveSoftware/Brave-Browser"),
        ]
    for browser, profile_path in candidates:
        if profile_path.exists():
            return ["--cookies-from-browser", browser, "--remote-components", "ejs:github"]
    return []


def yt_dlp_error(stderr: str, fallback: str) -> str:
    lines = [
        line for line in (stderr or fallback).splitlines()
        if not line.startswith("Deprecated Feature: Support for Python version")
    ]
    message = "\n".join(lines).strip() or fallback
    if "HTTP Error 403" in message or "Forbidden" in message:
        return f"{message}\n\nYouTube temporarily rejected the video stream. PracticeLab retried anonymously and with a local browser session when available, but YouTube still returned 403."
    return message


def get_title(url: str) -> str:
    result = subprocess.run(
        yt_dlp_command("--print", "title", "--no-playlist", "--js-runtimes", yt_dlp_js_runtime(), url),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() or "Unknown"


def download_wav(
    url: str,
    destination: Path,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> None:
    """Download the complete source audio, then apply any range locally."""
    start_sec, end_sec = normalize_analysis_range(start_sec, end_sec)
    session_args = yt_dlp_browser_session_args()
    attempt_args = [[], session_args] if session_args else [[]]
    last_error = "yt-dlp failed"
    with tempfile.TemporaryDirectory() as temp_dir:
        for index, extra_args in enumerate(attempt_args):
            result = subprocess.run(
                yt_dlp_command(
                    *extra_args,
                    "-x",
                    "--audio-format",
                    "wav",
                    "-o",
                    os.path.join(temp_dir, f"audio-{index}.%(ext)s"),
                    "--no-playlist",
                    "--js-runtimes",
                    yt_dlp_js_runtime(),
                    url,
                ),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                files = list(Path(temp_dir).glob(f"audio-{index}.wav"))
                if not files:
                    raise RuntimeError("wav not found")
                if start_sec is not None or end_sec is not None:
                    trim_audio_range(files[0], destination, start_sec, end_sec)
                else:
                    shutil.move(str(files[0]), str(destination))
                return
            last_error = yt_dlp_error(result.stderr, "yt-dlp failed")
            if "403" not in last_error and "Forbidden" not in last_error:
                raise RuntimeError(last_error)

    raise RuntimeError(last_error)


def download_video(
    url: str,
    destination: Path,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> None:
    """Download a high-quality complete video, then apply any range locally.

    yt-dlp range downloads tend to select a progressive MP4, which can be only
    360p even when a higher-quality DASH video stream exists.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    start_sec, end_sec = normalize_analysis_range(start_sec, end_sec)
    format_candidates = [FULL_VIDEO_FORMAT, FULL_VIDEO_FALLBACK_FORMAT]
    last_error = "yt-dlp video download failed"
    session_args = yt_dlp_browser_session_args()
    with tempfile.TemporaryDirectory() as temp_dir:
        for format_index, candidate in enumerate(format_candidates):
            attempt_args = [[], session_args] if session_args and format_index == 0 else [[]]
            for attempt, extra_args in enumerate(attempt_args):
                output_base = f"video-{format_index}-{attempt}"
                result = subprocess.run(
                    yt_dlp_command(
                        *extra_args,
                        "-f",
                        candidate,
                        "--merge-output-format",
                        "mp4",
                        "--retries",
                        "3",
                        "--fragment-retries",
                        "3",
                        "--retry-sleep",
                        "1",
                        "-o",
                        os.path.join(temp_dir, f"{output_base}.%(ext)s"),
                        "--no-playlist",
                        "--js-runtimes",
                        yt_dlp_js_runtime(),
                        url,
                    ),
                    capture_output=True,
                    text=True,
                    timeout=240,
                )
                if result.returncode == 0:
                    files = list(Path(temp_dir).glob(f"{output_base}*.mp4"))
                    if not files:
                        raise RuntimeError("mp4 not found")
                    if start_sec is not None or end_sec is not None:
                        trim_video_range(files[0], destination, start_sec, end_sec)
                    else:
                        shutil.move(str(files[0]), str(destination))
                    return
                last_error = yt_dlp_error(result.stderr, "yt-dlp video download failed")
                if "403" not in last_error and "Forbidden" not in last_error:
                    raise RuntimeError(last_error)
                if attempt + 1 < len(attempt_args):
                    time.sleep(1)
    raise RuntimeError(last_error)
