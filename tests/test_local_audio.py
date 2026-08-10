import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from practice_lab import app as app_module
from practice_lab import services


class LocalAudioUploadApiTests(unittest.TestCase):
    def test_accepts_m4a_and_queues_persisted_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            captured = {}

            def submit(job_id, description, func, cleanup=None, **metadata):
                captured.update(job_id=job_id, description=description, func=func, cleanup=cleanup, metadata=metadata)
                return {"jobId": job_id, "stage": "queued", "message": description}

            with (
                patch.object(app_module, "DATA_WORK_DIR", work_dir),
                patch.object(app_module, "ensure_directories"),
                patch.object(app_module, "bootstrap_public_data"),
                patch.object(app_module, "export_static_assets"),
                patch.object(app_module, "submit_queued_job", side_effect=submit),
            ):
                client = TestClient(app_module.create_app())
                response = client.post(
                    "/analyze-file",
                    files={"file": ("demo song.m4a", b"audio-content", "audio/mp4")},
                )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["jobId"].startswith("local-"))
            source = next((work_dir / "uploads").glob("*.m4a"))
            self.assertEqual(source.read_bytes(), b"audio-content")
            captured["cleanup"]()
            self.assertFalse(source.exists())

    def test_rejects_non_audio_extension(self):
        with (
            patch.object(app_module, "ensure_directories"),
            patch.object(app_module, "bootstrap_public_data"),
            patch.object(app_module, "export_static_assets"),
        ):
            client = TestClient(app_module.create_app())
            response = client.post(
                "/analyze-file",
                files={"file": ("notes.txt", b"not audio", "text/plain")},
            )

        self.assertEqual(response.status_code, 400)


class LocalAudioServiceTests(unittest.TestCase):
    def test_save_uploaded_audio_removes_oversized_partial_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "upload.wav"
            with self.assertRaisesRegex(ValueError, "500MB以下"):
                services.save_uploaded_audio(io.BytesIO(b"12345"), destination, max_bytes=4)
            self.assertFalse(destination.exists())

    def test_analyzes_audio_without_creating_a_video_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "upload.m4a"
            source.write_bytes(b"source")
            paths = {
                "DATA_RESULTS_DIR": root / "data" / "results",
                "DATA_AUDIO_DIR": root / "data" / "audio",
                "DATA_VIDEO_DIR": root / "data" / "video",
                "DATA_WORK_DIR": root / "data" / "work",
                "PUBLIC_AUDIO_DIR": root / "public" / "audio",
                "PUBLIC_VIDEO_DIR": root / "public" / "video",
            }
            for path in paths.values():
                path.mkdir(parents=True, exist_ok=True)

            def fake_wav(_source, destination):
                destination.write_bytes(b"wav")

            def fake_mp3(_source, destination):
                destination.write_bytes(b"mp3")

            analysis = {
                "bpm": 120.0,
                "total_bars": 1,
                "duration": 2.0,
                "sections": [
                    {
                        "label": "intro",
                        "start_bar": 1,
                        "end_bar": 1,
                        "bar_count": 1,
                        "start_time": 0.0,
                        "end_time": 2.0,
                        "start_time_str": "00:00",
                    }
                ],
                "beats": [0.0, 0.5, 1.0, 1.5],
                "downbeats": [0.0],
            }

            with (
                patch.multiple(services, **paths),
                patch.object(services, "convert_audio_to_wav", side_effect=fake_wav),
                patch.object(services, "convert_wav_to_mp3", side_effect=fake_mp3),
                patch.object(services, "run_analyzer", return_value=analysis),
                patch.object(services, "update_manifest"),
                patch.object(services, "export_static_assets"),
                patch.object(services, "publish_session_to_cloud") as publish,
                patch.object(services, "set_job_status"),
            ):
                result = services.analyze_local_audio(
                    source,
                    "local-test123",
                    "Demo Song",
                    original_filename="Demo Song.m4a",
                )

            self.assertEqual(result["sourceType"], "local_audio")
            self.assertIsNone(result["assets"]["video"])
            self.assertEqual(result["title"], "Demo Song")
            self.assertFalse(source.exists())
            self.assertTrue((paths["DATA_RESULTS_DIR"] / "local-test123.json").exists())
            publish.assert_called_once()
            self.assertIsNone(publish.call_args.args[-1])


if __name__ == "__main__":
    unittest.main()
