import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from practice_lab import services


class YtDlpDownloadTests(unittest.TestCase):
    def test_filters_python_deprecation_from_download_error(self):
        message = services.yt_dlp_error(
            "Deprecated Feature: Support for Python version 3.10 has been deprecated. Please update to Python 3.11 or above\n"
            "ERROR: unable to download video data: HTTP Error 403: Forbidden",
            "failed",
        )

        self.assertNotIn("Deprecated Feature", message)
        self.assertIn("HTTP Error 403", message)

    def test_retries_403_with_a_fresh_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.mp4"
            calls = 0

            def fake_run(command, **_kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return subprocess.CompletedProcess(command, 1, "", "HTTP Error 403: Forbidden")
                output = Path(command[command.index("-o") + 1].replace("%(ext)s", "mp4"))
                output.write_bytes(b"video")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(services, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(services.subprocess, "run", side_effect=fake_run), patch.object(services.time, "sleep"):
                services.download_video("https://youtu.be/example", destination)

            self.assertEqual(calls, 2)
            self.assertEqual(destination.read_bytes(), b"video")

    def test_audio_retries_403_with_local_browser_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.wav"
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                if len(commands) == 1:
                    return subprocess.CompletedProcess(command, 1, "", "HTTP Error 403: Forbidden")
                output = Path(command[command.index("-o") + 1].replace("%(ext)s", "wav"))
                output.write_bytes(b"audio")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(services, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(services.subprocess, "run", side_effect=fake_run):
                services.download_wav("https://youtu.be/example", destination, 3, None)

            self.assertIn("--cookies-from-browser", commands[1])
            self.assertEqual(destination.read_bytes(), b"audio")

    def test_falls_back_to_progressive_mp4_after_repeated_403(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.mp4"
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                if len(commands) < 3:
                    return subprocess.CompletedProcess(command, 1, "", "HTTP Error 403: Forbidden")
                output = Path(command[command.index("-o") + 1].replace("%(ext)s", "mp4"))
                output.write_bytes(b"fallback")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(services, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(services.subprocess, "run", side_effect=fake_run), patch.object(services.time, "sleep"):
                services.download_video("https://youtu.be/example", destination)

            self.assertEqual(commands[2][commands[2].index("-f") + 1], services.FULL_VIDEO_FALLBACK_FORMAT)
            self.assertEqual(destination.read_bytes(), b"fallback")


if __name__ == "__main__":
    unittest.main()
