import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from practice_lab import storage_usage


class StorageUsageTests(unittest.TestCase):
    def test_reports_category_sizes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "cache.bin").write_bytes(b"12345")
            category = storage_usage.StorageCategory("work", "作業キャッシュ", (root,), True)
            with patch.object(storage_usage, "storage_categories", return_value=(category,)):
                report = storage_usage.storage_report()
        self.assertEqual(report["totalBytes"], 5)
        self.assertEqual(report["categories"][0]["files"], 1)

    def test_cleanup_preserves_resumable_uploads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "analysis").mkdir()
            (root / "analysis" / "cache.bin").write_bytes(b"cache")
            (root / "uploads").mkdir()
            (root / "uploads" / "resume.wav").write_bytes(b"source")
            category = storage_usage.StorageCategory("work", "作業キャッシュ", (root,), True)
            with patch.object(storage_usage, "storage_categories", return_value=(category,)):
                result = storage_usage.cleanup_storage(["work"])
            self.assertGreater(result["removedBytes"], 0)
            self.assertTrue((root / "uploads" / "resume.wav").exists())

    def test_report_counts_hardlinked_files_only_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.bin"
            linked = root / "linked.bin"
            source.write_bytes(b"12345")
            linked.hardlink_to(source)
            categories = (
                storage_usage.StorageCategory("source", "元", (source,)),
                storage_usage.StorageCategory("public", "公開", (linked,)),
            )
            with patch.object(storage_usage, "storage_categories", return_value=categories):
                report = storage_usage.storage_report()
        self.assertEqual(report["totalBytes"], 5)

    def test_duplicate_public_video_cleanup_replaces_the_copy_with_a_hardlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_video = root / "data"
            public_video = root / "public"
            data_video.mkdir()
            public_video.mkdir()
            source = data_video / "song.mp4"
            destination = public_video / "song.mp4"
            source.write_bytes(b"same-video")
            destination.write_bytes(b"same-video")
            os.utime(destination, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
            category = storage_usage.StorageCategory("duplicate-video", "重複動画", (), True, False, False)
            with (
                patch.object(storage_usage, "DATA_VIDEO_DIR", data_video),
                patch.object(storage_usage, "PUBLIC_VIDEO_DIR", public_video),
                patch.object(storage_usage, "storage_categories", return_value=(category,)),
            ):
                result = storage_usage.cleanup_storage(["duplicate-video"])
            self.assertGreater(result["removedBytes"], 0)
            self.assertTrue(source.samefile(destination))

    def test_orphan_cleanup_preserves_known_sessions_and_score_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_results = root / "data-results"
            public_audio = root / "audio"
            public_video = root / "video"
            public_stems = root / "stems"
            public_results = root / "results"
            public_score = root / "score"
            for directory in (data_results, public_audio, public_video, public_stems, public_results, public_score):
                directory.mkdir()
            manifest = data_results / "manifest.json"
            manifest.write_text(json.dumps([{"id": "known"}]), encoding="utf-8")
            (public_audio / "known.mp3").write_bytes(b"keep")
            (public_audio / "orphan.mp3").write_bytes(b"remove")
            (public_stems / "orphan").mkdir()
            (public_stems / "orphan" / "vocals.wav").write_bytes(b"remove")
            (public_score / "old-score").mkdir()
            (public_score / "old-score" / "page.png").write_bytes(b"keep-score")
            category = storage_usage.StorageCategory("orphaned-public", "孤立", (), True, False, False)
            with (
                patch.object(storage_usage, "DATA_RESULTS_DIR", data_results),
                patch.object(storage_usage, "MANIFEST_FILE", manifest),
                patch.object(storage_usage, "PUBLIC_AUDIO_DIR", public_audio),
                patch.object(storage_usage, "PUBLIC_VIDEO_DIR", public_video),
                patch.object(storage_usage, "PUBLIC_STEMS_DIR", public_stems),
                patch.object(storage_usage, "PUBLIC_RESULTS_DIR", public_results),
                patch.object(storage_usage, "PUBLIC_SCORE_DIR", public_score),
                patch.object(storage_usage, "storage_categories", return_value=(category,)),
            ):
                result = storage_usage.cleanup_storage(["orphaned-public"])
            self.assertGreater(result["removedBytes"], 0)
            self.assertTrue((public_audio / "known.mp3").exists())
            self.assertFalse((public_audio / "orphan.mp3").exists())
            self.assertFalse((public_stems / "orphan").exists())
            self.assertTrue((public_score / "old-score" / "page.png").exists())


if __name__ == "__main__":
    unittest.main()
