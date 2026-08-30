import subprocess
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from practice_lab import source_media


class YtDlpDownloadTests(unittest.TestCase):
    def setUp(self):
        source_media._prefer_ipv4 = False

    def test_packaged_app_uses_electron_as_the_node_runtime(self):
        with patch.dict(os.environ, {"PRACTICE_LAB_NODE_PATH": "/Applications/PracticeLab.app/Contents/MacOS/PracticeLab"}, clear=False):
            runtime = source_media.yt_dlp_js_runtime()
        self.assertEqual(runtime, "node:/Applications/PracticeLab.app/Contents/MacOS/PracticeLab")

    def test_filters_python_deprecation_from_download_error(self):
        message = source_media.yt_dlp_error(
            "Deprecated Feature: Support for Python version 3.10 has been deprecated. Please update to Python 3.11 or above\n"
            "ERROR: unable to download video data: HTTP Error 403: Forbidden",
            "failed",
        )

        self.assertNotIn("Deprecated Feature", message)
        self.assertIn("HTTP Error 403", message)

    def test_title_timeout_retries_over_ipv4_and_remembers_the_route(self):
        commands = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            if len(commands) == 1:
                raise subprocess.TimeoutExpired(command, 10)
            return subprocess.CompletedProcess(command, 0, "Demo title\n", "")

        with patch.object(source_media, "run_process", side_effect=fake_run):
            title = source_media.get_title("https://youtu.be/example", "example")
            source_media.get_title("https://youtu.be/second", "second")

        self.assertEqual(title, "Demo title")
        self.assertNotIn("--force-ipv4", commands[0])
        self.assertIn("--force-ipv4", commands[1])
        self.assertIn("--force-ipv4", commands[2])

    def test_title_failure_uses_video_id_fallback(self):
        with patch.object(source_media, "run_process", side_effect=subprocess.TimeoutExpired(["yt-dlp"], 10)):
            title = source_media.get_title("https://youtu.be/example", "example")

        self.assertEqual(title, "example")

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

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run), patch.object(source_media.time, "sleep"):
                source_media.download_video("https://youtu.be/example", destination)

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

            def fake_trim(source, target, *_range):
                target.write_bytes(source.read_bytes())

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run), patch.object(source_media, "trim_audio_range", side_effect=fake_trim) as trim:
                source_media.download_wav("https://youtu.be/example", destination, 3, None)

            self.assertIn("--cookies-from-browser", commands[1])
            self.assertNotIn("--download-sections", commands[1])
            self.assertEqual(destination.read_bytes(), b"audio")
            self.assertEqual(trim.call_args.args[2:], (3.0, None))

    def test_video_range_downloads_full_quality_then_trims_locally(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.mp4"
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                output = Path(command[command.index("-o") + 1].replace("%(ext)s", "mp4"))
                output.write_bytes(b"full-video")
                return subprocess.CompletedProcess(command, 0, "", "")

            def fake_trim(source, target, *_range):
                target.write_bytes(source.read_bytes())

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=[]), patch.object(source_media, "run_process", side_effect=fake_run), patch.object(source_media, "trim_video_range", side_effect=fake_trim) as trim:
                source_media.download_video("https://youtu.be/example", destination, 30.5, 95)

            self.assertEqual(commands[0][commands[0].index("-f") + 1], source_media.FULL_VIDEO_FORMAT)
            self.assertNotIn("--download-sections", commands[0])
            self.assertEqual(trim.call_args.args[2:], (30.5, 95.0))
            self.assertEqual(destination.read_bytes(), b"full-video")

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

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run), patch.object(source_media.time, "sleep"):
                source_media.download_video("https://youtu.be/example", destination)

            self.assertEqual(commands[2][commands[2].index("-f") + 1], source_media.FULL_VIDEO_FALLBACK_FORMAT)
            self.assertEqual(destination.read_bytes(), b"fallback")


if __name__ == "__main__":
    unittest.main()
