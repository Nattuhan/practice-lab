import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from practice_lab import optional_features


class OptionalFeatureTests(unittest.TestCase):
    def test_windows_cpu_asset_name_uses_the_app_version(self):
        self.assertEqual(
            optional_features.windows_cpu_asset_name("1.2.3"),
            "PracticeLab-Windows-CPU-1.2.3.zip",
        )

    def test_windows_cpu_status_detects_the_versioned_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(optional_features, "ROOT_DIR", Path(temp_dir)),
                patch.object(optional_features.platform, "system", return_value="Windows"),
                patch.object(optional_features, "app_version", return_value="1.2.3"),
            ):
                executable = optional_features.windows_cpu_runtime_executable()
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"runtime")
                status = optional_features.feature_status()[optional_features.CPU_FEATURE_KEY]
        self.assertTrue(status["available"])
        self.assertTrue(status["installed"])

    def test_feature_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "feature.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape.txt", "unsafe")
            with self.assertRaisesRegex(RuntimeError, "不正なパス"):
                optional_features._safe_extract(archive, root / "destination")


if __name__ == "__main__":
    unittest.main()
