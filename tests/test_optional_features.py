import tempfile
import unittest
import io
import hashlib
import json
import os
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch

from practice_lab import optional_features


class OptionalFeatureTests(unittest.TestCase):
    def test_unpublished_version_uses_latest_abi_compatible_pack(self):
        compatible = {
            "name": "PracticeLab-Windows-CPU-1.1.5.zip",
            "browser_download_url": "https://example.test/cpu.zip",
            "digest": "sha256:" + "a" * 64,
        }
        latest = io.BytesIO(json.dumps({"assets": [compatible]}).encode("utf-8"))
        missing = urllib.error.HTTPError("https://example.test/v1.1.6", 404, "missing", {}, None)
        with (
            patch.object(optional_features, "_local_feature_asset", return_value=None),
            patch.object(optional_features.urllib.request, "urlopen", side_effect=[missing, latest]),
        ):
            asset = optional_features._release_asset(
                "1.1.6",
                "PracticeLab-Windows-CPU-1.1.6.zip",
                "PracticeLab-Windows-CPU-",
                "CPU解析パック",
            )

        self.assertEqual(asset["name"], "PracticeLab-Windows-CPU-1.1.5.zip")

    def test_local_compatible_pack_is_preferred_for_release_testing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "PracticeLab-Score-macOS-arm64-1.1.5.zip"
            archive.write_bytes(b"local-pack")
            with patch.dict(os.environ, {"PRACTICE_LAB_FEATURE_PACK_DIR": temp_dir}, clear=False):
                asset = optional_features._local_feature_asset(
                    "PracticeLab-Score-macOS-arm64-1.1.6.zip",
                    "PracticeLab-Score-macOS-arm64-",
                )

        self.assertEqual(asset["name"], archive.name)
        self.assertTrue(asset["compatible"])

    def test_windows_cpu_asset_name_uses_the_app_version(self):
        self.assertEqual(
            optional_features.windows_cpu_asset_name("1.2.3"),
            "PracticeLab-Windows-CPU-1.2.3.zip",
        )

    def test_mac_analysis_runtime_uses_stable_abi_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(optional_features, "ROOT_DIR", Path(temp_dir)):
                executable = optional_features.mac_analysis_runtime_executable()

        self.assertIn(optional_features.MAC_ANALYSIS_RUNTIME_ABI, executable.parts)
        self.assertEqual(executable.name, "practice-lab-analysis-runtime")

    def test_mac_analysis_installer_restores_executable_permission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "PracticeLab-Analysis-macOS-arm64-1.1.6.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "practice-lab-analysis-runtime/practice-lab-analysis-runtime",
                    b"runtime",
                )
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            asset = {
                "name": archive.name,
                "browser_download_url": archive.as_uri(),
                "digest": f"sha256:{digest}",
            }
            with (
                patch.object(optional_features, "ROOT_DIR", root),
                patch.object(optional_features, "_release_asset", return_value=asset),
                patch.object(optional_features.platform, "system", return_value="Darwin"),
                patch.object(optional_features.platform, "machine", return_value="arm64"),
                patch.object(optional_features, "app_version", return_value="1.1.6"),
                patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1"}, clear=False),
            ):
                optional_features.install_mac_analysis_runtime()
                executable = optional_features.mac_analysis_runtime_executable()
                self.assertTrue(os.access(executable, os.X_OK))

    def test_windows_cpu_status_detects_the_compatible_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(optional_features, "ROOT_DIR", Path(temp_dir)),
                patch.object(optional_features.platform, "system", return_value="Windows"),
                patch.object(optional_features, "app_version", return_value="1.2.3"),
            ):
                executable = optional_features.windows_cpu_runtime_executable()
                self.assertIn(optional_features.CPU_RUNTIME_ABI, executable.parts)
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"runtime")
                status = optional_features.feature_status()[optional_features.CPU_FEATURE_KEY]
        self.assertTrue(status["available"])
        self.assertTrue(status["installed"])

    def test_legacy_score_runtime_is_reused_and_old_versions_are_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            feature_root = root / "runtime" / optional_features.SCORE_FEATURE_KEY
            legacy = feature_root / "1.1.4" / "score-pack" / "site-packages" / "rapidocr_onnxruntime"
            stale = feature_root / "1.1.3" / "score-pack" / "site-packages" / "rapidocr_onnxruntime"
            legacy.mkdir(parents=True)
            stale.mkdir(parents=True)
            (legacy / "__init__.py").write_text("", encoding="utf-8")
            with patch.object(optional_features, "ROOT_DIR", root):
                resolved = optional_features.score_runtime_dir()
            self.assertEqual(resolved, feature_root / optional_features.SCORE_RUNTIME_ABI)
            self.assertTrue((resolved / "score-pack" / "site-packages" / "rapidocr_onnxruntime").is_dir())
            self.assertFalse((feature_root / "1.1.4").exists())
            self.assertFalse((feature_root / "1.1.3").exists())

    def test_incompatible_abi_runtime_is_not_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_runtime = (
                root / "runtime" / optional_features.SCORE_FEATURE_KEY / "abi-0"
                / "score-pack" / "site-packages" / "rapidocr_onnxruntime"
            )
            old_runtime.mkdir(parents=True)
            with patch.object(optional_features, "ROOT_DIR", root):
                resolved = optional_features.score_runtime_dir()
            self.assertEqual(resolved.name, optional_features.SCORE_RUNTIME_ABI)
            self.assertFalse(resolved.exists())
            self.assertTrue(old_runtime.exists())

    def test_uninstall_removes_every_cpu_runtime_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            feature_root = root / "runtime" / optional_features.CPU_FEATURE_KEY
            for version in ("1.1.4", optional_features.CPU_RUNTIME_ABI):
                executable = feature_root / version / "practice-lab-cpu-runtime" / "practice-lab-cpu-runtime.exe"
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b"runtime")
            with (
                patch.object(optional_features, "ROOT_DIR", root),
                patch.object(optional_features.platform, "system", return_value="Windows"),
            ):
                status = optional_features.uninstall_windows_cpu_runtime()
            self.assertFalse(feature_root.exists())
            self.assertFalse(status["installed"])

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
