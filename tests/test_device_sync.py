import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from practice_lab import cloud_sync
from practice_lab.cloud_storage import R2Config
from practice_lab.device_sync import load_local_sync_state, record_session_deletions


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DeviceSyncStateTests(unittest.TestCase):
    def test_device_id_is_stable_and_deletions_become_tombstones(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "device-sync-state.json"
            first = load_local_sync_state(state_file)
            record_session_deletions(["song-1"], deleted_at=123.0, path=state_file)
            second = load_local_sync_state(state_file)

            self.assertEqual(first["deviceId"], second["deviceId"])
            self.assertEqual(second["tombstones"]["song-1"]["deletedAt"], 123.0)


class BidirectionalR2SyncTests(unittest.TestCase):
    def _paths(self, root: Path) -> dict:
        paths = {
            "DATA_RESULTS_DIR": root / "data" / "results",
            "DATA_AUDIO_DIR": root / "data" / "audio",
            "DATA_VIDEO_DIR": root / "data" / "video",
            "DATA_STEMS_DIR": root / "data" / "stems",
            "DATA_WORK_DIR": root / "data" / "work",
            "PUBLIC_DIR": root / "public",
            "PUBLIC_RESULTS_DIR": root / "public" / "results",
            "PUBLIC_AUDIO_DIR": root / "public" / "audio",
            "PUBLIC_VIDEO_DIR": root / "public" / "video",
            "PUBLIC_STEMS_DIR": root / "public" / "stems",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        paths["MANIFEST_FILE"] = paths["DATA_RESULTS_DIR"] / "manifest.json"
        paths["FOLDERS_FILE"] = paths["DATA_RESULTS_DIR"] / "folders.json"
        paths["MANIFEST_FILE"].write_text("[]", encoding="utf-8")
        paths["FOLDERS_FILE"].write_text("[]", encoding="utf-8")
        paths["CACHE_FILE"] = paths["DATA_WORK_DIR"] / "r2-sync-cache.json"
        return paths

    def _config(self) -> R2Config:
        return R2Config(
            bucket="bucket",
            endpoint_url="https://example.invalid",
            access_key_id="id",
            secret_access_key="secret",
            prefix="sessions",
        )

    def test_remote_index_only_preserves_allowed_active_session_files(self):
        config = self._config()
        valid_digest = sha256(b"session")
        state = {
            "sessions": {
                "song-1": {
                    "files": {
                        "sessions/song-1/session.json": valid_digest,
                        "sessions/song-1/../../secret": valid_digest,
                        "other-prefix/song-1/audio.mp3": valid_digest,
                    }
                },
                "deleted-song": {
                    "deleted": True,
                    "files": {"sessions/deleted-song/session.json": valid_digest},
                },
            }
        }

        self.assertEqual(
            cloud_sync.active_remote_file_index(config, state),
            {"sessions/song-1/session.json": valid_digest},
        )

    def test_remote_only_song_is_downloaded_instead_of_deleted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            config = self._config()
            session_bytes = json.dumps({
                "id": "song-1",
                "title": "Remote song",
                "bpm": 120,
                "assets": {},
            }).encode("utf-8")
            audio_bytes = b"remote audio"
            folder_bytes = json.dumps([{"id": "folder-1", "name": "練習曲", "sessionIds": ["song-1"]}]).encode("utf-8")
            files = {
                "sessions/song-1/session.json": sha256(session_bytes),
                "sessions/song-1/audio.mp3": sha256(audio_bytes),
            }
            folder_digest = sha256(folder_bytes)
            remote_state = {
                "version": 1,
                "devices": {"remote-device": {"name": "Laptop", "lastSeenAt": 10}},
                "folders": {"deviceId": "remote-device", "updatedAt": 10, "digest": folder_digest, "key": "sessions/folders.json"},
                "sessions": {
                    "song-1": {
                        "deviceId": "remote-device",
                        "updatedAt": 10,
                        "entryDate": "2026-08-16",
                        "files": files,
                        "digest": cloud_sync._mapping_digest(files),
                    }
                },
            }
            local_state = {
                "version": 1,
                "deviceId": "local-device",
                "deviceName": "Desktop",
                "workspaceKey": cloud_sync._workspace_key(config),
                "sessions": {},
                "tombstones": {},
                "folders": {},
            }

            def download(_config, key, destination, **_options):
                destination.parent.mkdir(parents=True, exist_ok=True)
                if key.endswith("session.json"):
                    destination.write_bytes(session_bytes)
                elif key.endswith("folders.json"):
                    destination.write_bytes(folder_bytes)
                else:
                    destination.write_bytes(audio_bytes)

            saved_states = []
            with (
                patch.multiple(cloud_sync, **paths),
                patch.object(cloud_sync, "export_static_assets"),
                patch.object(cloud_sync, "load_sync_index", return_value={**files, "sessions/folders.json": folder_digest}),
                patch.object(cloud_sync, "load_json_object", return_value=remote_state),
                patch.object(cloud_sync, "load_local_sync_state", return_value=local_state),
                patch.object(cloud_sync, "save_local_sync_state", side_effect=lambda state: saved_states.append(state)),
                patch.object(cloud_sync, "download_file", side_effect=download),
                patch.object(cloud_sync, "upload_file"),
                patch.object(cloud_sync, "upload_json_object"),
                patch.object(cloud_sync, "upload_sync_index"),
                patch.object(cloud_sync, "delete_object_keys") as delete,
            ):
                result = cloud_sync.sync_cloud_incremental(config)

            self.assertEqual(result["downloaded"], 1)
            self.assertTrue((paths["DATA_RESULTS_DIR"] / "song-1.json").exists())
            self.assertTrue((paths["PUBLIC_AUDIO_DIR"] / "song-1.mp3").exists())
            self.assertEqual(json.loads(paths["FOLDERS_FILE"].read_text(encoding="utf-8"))[0]["id"], "folder-1")
            self.assertIn("song-1", saved_states[-1]["sessions"])
            delete.assert_not_called()

    def test_explicit_local_deletion_removes_remote_assets_and_keeps_tombstone(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            config = self._config()
            files = {
                "sessions/song-1/session.json": sha256(b"result"),
                "sessions/song-1/audio.mp3": sha256(b"audio"),
                "unrelated-object": "must-not-delete",
            }
            folder_digest = sha256(b"[]")
            remote_state = {
                "version": 1,
                "devices": {},
                "folders": {"deviceId": "remote", "updatedAt": 1, "digest": folder_digest, "key": "sessions/folders.json"},
                "sessions": {
                    "song-1": {
                        "deviceId": "remote",
                        "updatedAt": 10,
                        "files": files,
                        "digest": cloud_sync._mapping_digest(files),
                    }
                },
            }
            local_state = {
                "version": 1,
                "deviceId": "local-device",
                "deviceName": "Desktop",
                "workspaceKey": cloud_sync._workspace_key(config),
                "sessions": {},
                "tombstones": {"song-1": {"deletedAt": 20, "deviceId": "local-device"}},
                "folders": {},
            }
            uploaded_states = []
            with (
                patch.multiple(cloud_sync, **paths),
                patch.object(cloud_sync, "export_static_assets"),
                patch.object(cloud_sync, "load_sync_index", return_value={**files, "sessions/folders.json": folder_digest}),
                patch.object(cloud_sync, "load_json_object", return_value=remote_state),
                patch.object(cloud_sync, "load_local_sync_state", return_value=local_state),
                patch.object(cloud_sync, "save_local_sync_state"),
                patch.object(cloud_sync, "upload_file"),
                patch.object(cloud_sync, "upload_json_object", side_effect=lambda _config, _key, state: uploaded_states.append(state)),
                patch.object(cloud_sync, "upload_sync_index"),
                patch.object(cloud_sync, "delete_object_keys") as delete,
            ):
                cloud_sync.sync_cloud_incremental(config)

            delete.assert_called_once_with(config, [
                "sessions/song-1/session.json",
                "sessions/song-1/audio.mp3",
            ])
            self.assertTrue(uploaded_states[-1]["sessions"]["song-1"]["deleted"])

    def test_concurrent_changes_keep_the_newer_remote_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = self._paths(root)
            config = self._config()
            local_bytes = json.dumps({"id": "song-1", "title": "Local", "bpm": 120}).encode("utf-8")
            remote_bytes = json.dumps({"id": "song-1", "title": "Remote", "bpm": 130}).encode("utf-8")
            result_file = paths["DATA_RESULTS_DIR"] / "song-1.json"
            result_file.write_bytes(local_bytes)
            old_time = time.time() - 60
            os.utime(result_file, (old_time, old_time))

            remote_files = {"sessions/song-1/session.json": sha256(remote_bytes)}
            remote_entry = {
                "deviceId": "remote-device",
                "updatedAt": time.time(),
                "entryDate": "2026-08-16",
                "files": remote_files,
                "digest": cloud_sync._mapping_digest(remote_files),
            }
            remote_state = {
                "version": 1,
                "devices": {},
                "folders": {
                    "deviceId": "remote-device",
                    "updatedAt": 1,
                    "digest": sha256(b"[]"),
                    "key": "sessions/folders.json",
                },
                "sessions": {"song-1": remote_entry},
            }
            local_state = {
                "version": 1,
                "deviceId": "local-device",
                "deviceName": "Desktop",
                "workspaceKey": cloud_sync._workspace_key(config),
                "sessions": {
                    "song-1": {
                        "localDigest": "previous-local",
                        "remoteRevision": "previous-remote",
                    }
                },
                "tombstones": {},
                "folders": {},
            }

            def download(_config, key, destination, **_options):
                self.assertEqual(key, "sessions/song-1/session.json")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(remote_bytes)

            with (
                patch.multiple(cloud_sync, **paths),
                patch.object(cloud_sync, "export_static_assets"),
                patch.object(cloud_sync, "load_sync_index", return_value={**remote_files, "sessions/folders.json": sha256(b"[]")}),
                patch.object(cloud_sync, "load_json_object", return_value=remote_state),
                patch.object(cloud_sync, "load_local_sync_state", return_value=local_state),
                patch.object(cloud_sync, "save_local_sync_state"),
                patch.object(cloud_sync, "download_file", side_effect=download),
                patch.object(cloud_sync, "upload_file"),
                patch.object(cloud_sync, "upload_json_object"),
                patch.object(cloud_sync, "upload_sync_index"),
                patch.object(cloud_sync, "delete_object_keys"),
            ):
                result = cloud_sync.sync_cloud_incremental(config)

            self.assertEqual(json.loads(result_file.read_text(encoding="utf-8"))["title"], "Remote")
            self.assertEqual(result["conflicts"], [{"sessionId": "song-1", "kept": "remote"}])


if __name__ == "__main__":
    unittest.main()
