import argparse
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import sync_r2


class IncrementalR2SyncTests(unittest.TestCase):
    def test_uploads_only_changed_files_and_deletes_stale_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unchanged = root / "index.html"
            changed = root / "app.js"
            unchanged.write_text("same", encoding="utf-8")
            changed.write_text("new", encoding="utf-8")
            unchanged_hash = hashlib.sha256(b"same").hexdigest()
            config = MagicMock(prefix="sessions", configure_cors=False)

            with (
                patch.object(sync_r2, "parse_args", return_value=argparse.Namespace(session=[], all_sessions=False, initialize_index=False)),
                patch.object(sync_r2, "ensure_directories"),
                patch.object(sync_r2, "get_r2_config", return_value=config),
                patch.object(sync_r2, "prepare_session_metadata", return_value=[]),
                patch.object(sync_r2, "desired_files", return_value={"index.html": unchanged, "app.js": changed}),
                patch.object(sync_r2, "CACHE_FILE", root / "cache.json"),
                patch.object(sync_r2, "load_sync_index", return_value={"index.html": unchanged_hash, "app.js": "old", "stale.mp3": "old"}),
                patch.object(sync_r2, "upload_file") as upload,
                patch.object(sync_r2, "delete_object_keys") as delete,
                patch.object(sync_r2, "upload_sync_index") as upload_index,
            ):
                sync_r2.main()

            upload.assert_called_once_with(config, changed, "app.js")
            delete.assert_called_once_with(config, ["stale.mp3"])
            uploaded_files = upload_index.call_args.args[1]
            self.assertEqual(set(uploaded_files), {"index.html", "app.js"})

    def test_initialization_uploads_only_the_hash_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_file = root / "app.js"
            app_file.write_text("content", encoding="utf-8")
            config = MagicMock(prefix="sessions", configure_cors=False)

            with (
                patch.object(sync_r2, "parse_args", return_value=argparse.Namespace(session=[], all_sessions=False, initialize_index=True)),
                patch.object(sync_r2, "ensure_directories"),
                patch.object(sync_r2, "get_r2_config", return_value=config),
                patch.object(sync_r2, "prepare_session_metadata", return_value=[]),
                patch.object(sync_r2, "desired_files", return_value={"app.js": app_file}),
                patch.object(sync_r2, "CACHE_FILE", root / "cache.json"),
                patch.object(sync_r2, "load_sync_index", return_value=None),
                patch.object(sync_r2, "upload_file") as upload,
                patch.object(sync_r2, "upload_sync_index") as upload_index,
            ):
                sync_r2.main()

            upload.assert_not_called()
            upload_index.assert_called_once()


if __name__ == "__main__":
    unittest.main()
