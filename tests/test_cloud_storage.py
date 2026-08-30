import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from practice_lab import cloud_storage


class CloudStorageUploadTests(unittest.TestCase):
    def test_json_and_static_app_are_revalidated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "manifest.json"
            source.write_text("[]", encoding="utf-8")
            config = MagicMock(bucket="practice-lab")
            client = MagicMock()

            with patch.object(cloud_storage, "_client", return_value=client):
                cloud_storage.upload_file(config, source, "sessions/manifest.json")

            self.assertEqual(
                client.upload_file.call_args.kwargs["ExtraArgs"],
                {
                    "ContentType": "application/json",
                    "CacheControl": "no-cache, max-age=0, must-revalidate",
                },
            )
            self.assertEqual(
                cloud_storage._cache_control("app.js"),
                "no-cache, max-age=0, must-revalidate",
            )


if __name__ == "__main__":
    unittest.main()
