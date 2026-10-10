from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .process_manager import run_process

FULL_VIDEO_FALLBACK_FORMAT = "b[ext=mp4][height<=720]/b[height<=720]/b"
FULL_VIDEO_FORMAT = (
    "bv*[vcodec^=avc1][height<=1080][ext=mp4]+ba[ext=m4a]/"
    "bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"
)
DEFAULT_YOUTUBE_PLAYER_CLIENTS = "web_embedded"
# yt-dlp words an unusable browser cookie store two ways, depending on whether
# it failed to locate the database or to copy it. Match both.
COOKIE_DATABASE_ERROR_MARKERS = ("cookie database", "cookies database")
_prefer_ipv4 = False


def extract_video_id(url: str) -> str | None:
    """Music and regular YouTube URLs identify the same source and cache."""
    try:
        parsed = urlparse(url)
        if parsed.hostname == "youtu.be":
            return parsed.path.lstrip("/").split("?")[0] or None
        if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com", "music.youtube.com"):
            return parse_qs(parsed.query).get("v", [None])[0]
    except ValueError:
        return None
    return None


def get_thumbnail_url(url: str) -> str | None:
    """Keep the source artwork, rather than guessing an image from a video frame.

    Artwork is optional: a metadata timeout must not prevent audio analysis.
    """
    try:
        result = run_yt_dlp(
            "--print", "thumbnail", "--no-playlist", "--js-runtimes", yt_dlp_js_runtime(), url,
            capture_output=True, text=True, timeout=10, ipv4_retry_timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    thumbnail = result.stdout.strip()
    if result.returncode == 0 and thumbnail.startswith("https://"):
        return thumbnail
    return None


def is_cookie_database_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in COOKIE_DATABASE_ERROR_MARKERS)


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
    run_process(
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
    run_process(
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


def extract_wav_from_video(source: Path, destination: Path) -> None:
    """Create the canonical analysis WAV from the exact playback video timeline."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_process(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", str(source), "-vn", "-acodec", "pcm_s16le", "-ar", "44100",
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


def run_yt_dlp(
    *args: str,
    timeout: float,
    ipv4_retry_timeout: float | None = None,
    **run_kwargs,
) -> subprocess.CompletedProcess[str]:
    """Run yt-dlp and fall back to IPv4 when the default route times out."""
    global _prefer_ipv4

    def run(force_ipv4: bool, command_timeout: float) -> subprocess.CompletedProcess[str]:
        network_args = ["--force-ipv4"] if force_ipv4 else []
        return run_process(
            yt_dlp_command(*network_args, *args),
            timeout=command_timeout,
            **run_kwargs,
        )

    if _prefer_ipv4:
        return run(True, ipv4_retry_timeout or timeout)
    try:
        return run(False, timeout)
    except subprocess.TimeoutExpired:
        result = run(True, ipv4_retry_timeout or timeout)
        _prefer_ipv4 = True
        return result


def yt_dlp_player_client_args() -> list[str]:
    """Return an explicit YouTube player client for the retry after a 403.

    YouTube periodically stops serving media to the player clients yt-dlp
    selects by default: metadata extraction still succeeds, then the stream
    download answers 403. Naming a client that is still served recovers the
    download without waiting for a new yt-dlp release, which matters most on
    Windows where the packaged build cannot update yt-dlp by itself.

    Set PRACTICE_LAB_YTDLP_PLAYER_CLIENTS to try other clients, or to "off"
    to skip this retry entirely.
    """
    clients = os.environ.get("PRACTICE_LAB_YTDLP_PLAYER_CLIENTS", "").strip()
    clients = clients or DEFAULT_YOUTUBE_PLAYER_CLIENTS
    if clients.lower() in {"off", "none"}:
        return []
    return ["--extractor-args", f"youtube:player_client={clients}"]


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
        try:
            profiles = [profile_path / "Default", *profile_path.glob("Profile *")]
            cookie_files = (
                cookie_file
                for profile in profiles
                for cookie_file in (profile / "Network/Cookies", profile / "Cookies")
            )
            # A browser directory alone is not enough: macOS may deny access to
            # its contents, and yt-dlp would then hide the original 403 error.
            if any(cookie_file.is_file() and os.access(cookie_file, os.R_OK) for cookie_file in cookie_files):
                return ["--cookies-from-browser", browser, "--remote-components", "ejs:github"]
        except OSError:
            continue
    return []


def yt_dlp_retry_tiers() -> list[list[str]]:
    """Extra yt-dlp arguments to try, in order, after an anonymous attempt.

    Each tier is only reached when the previous one failed with a 403, so a
    working anonymous download still costs a single yt-dlp run. The player
    client retry comes before the browser session because it needs no access
    to the user's browser profile.
    """
    tiers = [[]]
    for extra_args in (yt_dlp_player_client_args(), yt_dlp_browser_session_args()):
        if extra_args:
            tiers.append(extra_args)
    return tiers


def yt_dlp_error(stderr: str, fallback: str) -> str:
    lines = [
        line for line in (stderr or fallback).splitlines()
        if not line.startswith("Deprecated Feature: Support for Python version")
    ]
    message = "\n".join(lines).strip() or fallback
    if "HTTP Error 403" in message or "Forbidden" in message:
        return f"{message}\n\nYouTube temporarily rejected the video stream."
    return message


def get_title(url: str, fallback: str = "Unknown") -> str:
    try:
        result = run_yt_dlp(
            "--print", "title", "--no-playlist", "--js-runtimes", yt_dlp_js_runtime(), url,
            capture_output=True,
            text=True,
            timeout=10,
            ipv4_retry_timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return fallback
    return result.stdout.strip() or fallback


def download_wav(
    url: str,
    destination: Path,
    start_sec: float | None = None,
    end_sec: float | None = None,
) -> None:
    """Download the complete source audio, then apply any range locally."""
    start_sec, end_sec = normalize_analysis_range(start_sec, end_sec)
    attempt_args = yt_dlp_retry_tiers()
    last_error = "yt-dlp failed"
    anonymous_error = ""
    with tempfile.TemporaryDirectory() as temp_dir:
        for index, extra_args in enumerate(attempt_args):
            result = run_yt_dlp(
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
            if not extra_args:
                anonymous_error = last_error
            elif is_cookie_database_error(last_error):
                raise RuntimeError(f"{anonymous_error}\n\nBrowser-cookie retry failed: {last_error}")
            if "403" not in last_error and "Forbidden" not in last_error:
                if not extra_args or index + 1 == len(attempt_args):
                    raise RuntimeError(last_error)
                # A retry tier can fail for its own reasons, such as a player
                # client that needs a JS runtime. Keep the error the anonymous
                # attempt reported and let the remaining tiers run.
                last_error = anonymous_error or last_error

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
    anonymous_error = ""
    attempt_tiers = yt_dlp_retry_tiers()
    with tempfile.TemporaryDirectory() as temp_dir:
        # Exhaust every format of one tier before moving to the next. A failed
        # cookie read must not prevent the lower-bandwidth format from working.
        for attempt, extra_args in enumerate(attempt_tiers):
            for format_index, candidate in enumerate(format_candidates):
                output_base = f"video-{format_index}-{attempt}"
                result = run_yt_dlp(
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
                if not extra_args:
                    anonymous_error = last_error
                elif is_cookie_database_error(last_error):
                    raise RuntimeError(f"{anonymous_error}\n\nBrowser-cookie retry failed: {last_error}")
                if "403" not in last_error and "Forbidden" not in last_error:
                    if not extra_args or attempt + 1 == len(attempt_tiers):
                        raise RuntimeError(last_error)
                    # A retry tier can fail for its own reasons, such as a player
                    # client that needs a JS runtime. Keep the error the anonymous
                    # attempt reported and let the remaining tiers run.
                    last_error = anonymous_error or last_error
            if attempt + 1 < len(attempt_tiers):
                time.sleep(1)
    raise RuntimeError(last_error)
