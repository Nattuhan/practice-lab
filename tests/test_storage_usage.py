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


if __name__ == "__main__":
    unittest.main()
