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

    def test_browser_session_requires_a_readable_cookie_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            chrome = home / "Library/Application Support/Google/Chrome"
            (chrome / "Default").mkdir(parents=True)
            with patch.object(source_media.sys, "platform", "darwin"), patch.object(source_media.Path, "home", return_value=home):
                self.assertEqual(source_media.yt_dlp_browser_session_args(), [])
                (chrome / "Default/Network").mkdir()
                (chrome / "Default/Network/Cookies").write_bytes(b"test")
                self.assertEqual(source_media.yt_dlp_browser_session_args()[1], "chrome")

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

    def test_audio_retries_403_with_an_explicit_player_client(self):
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

            # The player client retry costs no browser access, so it comes first.
            self.assertNotIn("--extractor-args", commands[0])
            self.assertEqual(len(commands), 2)
            self.assertIn("--extractor-args", commands[1])
            self.assertIn(
                f"youtube:player_client={source_media.DEFAULT_YOUTUBE_PLAYER_CLIENTS}",
                commands[1],
            )
            self.assertNotIn("--cookies-from-browser", commands[1])
            self.assertNotIn("--download-sections", commands[1])
            self.assertEqual(destination.read_bytes(), b"audio")
            self.assertEqual(trim.call_args.args[2:], (3.0, None))

    def test_audio_falls_back_to_browser_session_after_player_client_403(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.wav"
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                if "--cookies-from-browser" not in command:
                    return subprocess.CompletedProcess(command, 1, "", "HTTP Error 403: Forbidden")
                output = Path(command[command.index("-o") + 1].replace("%(ext)s", "wav"))
                output.write_bytes(b"audio")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run):
                source_media.download_wav("https://youtu.be/example", destination)

            self.assertEqual(len(commands), 3)
            self.assertIn("--extractor-args", commands[1])
            self.assertIn("--cookies-from-browser", commands[2])
            self.assertEqual(destination.read_bytes(), b"audio")

    def test_player_client_failure_still_reaches_the_browser_session(self):
        # web_embedded needs a JS runtime; without one yt-dlp reports a missing
        # format rather than a 403, which must not cancel the cookie retry.
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.wav"
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                if "--cookies-from-browser" in command:
                    output = Path(command[command.index("-o") + 1].replace("%(ext)s", "wav"))
                    output.write_bytes(b"audio")
                    return subprocess.CompletedProcess(command, 0, "", "")
                if "--extractor-args" in command:
                    return subprocess.CompletedProcess(
                        command, 1, "", "ERROR: Requested format is not available"
                    )
                return subprocess.CompletedProcess(command, 1, "", "HTTP Error 403: Forbidden")

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run):
                source_media.download_wav("https://youtu.be/example", destination)

            self.assertEqual(len(commands), 3)
            self.assertEqual(destination.read_bytes(), b"audio")

    def test_anonymous_non_403_failure_still_stops_immediately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.wav"
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                return subprocess.CompletedProcess(command, 1, "", "ERROR: Video unavailable")

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run):
                with self.assertRaisesRegex(RuntimeError, "Video unavailable"):
                    source_media.download_wav("https://youtu.be/example", destination)

            self.assertEqual(len(commands), 1)

    def test_player_client_retry_can_be_disabled(self):
        with patch.dict(os.environ, {"PRACTICE_LAB_YTDLP_PLAYER_CLIENTS": "off"}, clear=False):
            self.assertEqual(source_media.yt_dlp_player_client_args(), [])

    def test_player_client_retry_is_overridable(self):
        with patch.dict(os.environ, {"PRACTICE_LAB_YTDLP_PLAYER_CLIENTS": "tv,web_safari"}, clear=False):
            self.assertEqual(
                source_media.yt_dlp_player_client_args(),
                ["--extractor-args", "youtube:player_client=tv,web_safari"],
            )

    def test_recognises_the_cookie_database_errors_yt_dlp_actually_reports(self):
        # Observed from a packaged Windows build while Chrome was running.
        self.assertTrue(
            source_media.is_cookie_database_error(
                "ERROR: Could not copy Chrome cookie database. See "
                "https://github.com/yt-dlp/yt-dlp/issues/7271 for more info"
            )
        )
        # yt-dlp's other wording, used when the database is absent rather than locked.
        self.assertTrue(
            source_media.is_cookie_database_error(
                'ERROR: could not find chrome cookies database in "/nonexistent"'
            )
        )
        self.assertFalse(source_media.is_cookie_database_error("HTTP Error 403: Forbidden"))

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
                if len(commands) < 2:
                    return subprocess.CompletedProcess(command, 1, "", "HTTP Error 403: Forbidden")
                output = Path(command[command.index("-o") + 1].replace("%(ext)s", "mp4"))
                output.write_bytes(b"fallback")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run), patch.object(source_media.time, "sleep"):
                source_media.download_video("https://youtu.be/example", destination)

            self.assertEqual(commands[1][commands[1].index("-f") + 1], source_media.FULL_VIDEO_FALLBACK_FORMAT)
            self.assertNotIn("--cookies-from-browser", commands[1])
            self.assertEqual(destination.read_bytes(), b"fallback")

    def test_cookie_failure_keeps_original_403_visible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "result.mp4"
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                # Verbatim wording of a packaged Windows build with Chrome running.
                error = ("ERROR: Could not copy Chrome cookie database. See "
                         "https://github.com/yt-dlp/yt-dlp/issues/7271 for more info"
                         if "--cookies-from-browser" in command
                         else "HTTP Error 403: Forbidden")
                return subprocess.CompletedProcess(command, 1, "", error)

            with patch.object(source_media, "yt_dlp_browser_session_args", return_value=["--cookies-from-browser", "chrome"]), patch.object(source_media, "run_process", side_effect=fake_run), patch.object(source_media.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "(?s)HTTP Error 403.*Browser-cookie retry failed"):
                    source_media.download_video("https://youtu.be/example", destination)

            # Two formats anonymously, two with the player client, then cookies.
            self.assertEqual(len(commands), 5)
            self.assertEqual(commands[1][commands[1].index("-f") + 1], source_media.FULL_VIDEO_FALLBACK_FORMAT)
            self.assertIn("--extractor-args", commands[2])
            self.assertIn("--cookies-from-browser", commands[4])


if __name__ == "__main__":
    unittest.main()
