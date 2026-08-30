import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from practice_lab import cloud_storage


class CloudStorageUploadTests(unittest.TestCase):
    def test_r2_client_has_bounded_connection_and_read_timeouts(self):
        config = cloud_storage.R2Config(
            bucket="bucket",
            endpoint_url="https://example.invalid",
            access_key_id="access",
            secret_access_key="secret",
        )
        cloud_storage._client.cache_clear()
        with patch("boto3.client", return_value=MagicMock()) as client:
            cloud_storage._client(config)

        client_config = client.call_args.kwargs["config"]
        self.assertEqual(client_config.connect_timeout, 10)
        self.assertEqual(client_config.read_timeout, 60)

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
