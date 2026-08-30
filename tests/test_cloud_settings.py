import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from practice_lab import app as app_module
from practice_lab.cloud_storage import R2Config


class CloudSettingsApiTests(unittest.TestCase):
    def test_desktop_can_enable_cloud_after_local_backend_startup(self):
        with patch.dict(os.environ, {
            "PRACTICE_LAB_DESKTOP_TOKEN": "secret-token",
            "R2_ENABLED": "0",
        }, clear=False):
            client = TestClient(app_module.create_app())
            response = client.post(
                "/desktop/cloud-config",
                headers={"X-Practice-Lab-Desktop-Token": "secret-token"},
                json={
                    "enabled": True,
                    "bucket": "user-bucket",
                    "accountId": "account-id",
                    "accessKeyId": "access",
                    "secretAccessKey": "secret",
                    "publicBaseUrl": "https://assets.example.com/",
                    "prefix": "/sessions/",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"configured": True, "bucket": "user-bucket"})
            self.assertEqual(os.environ["R2_ENABLED"], "1")
            self.assertEqual(os.environ["R2_ENDPOINT_URL"], "https://account-id.r2.cloudflarestorage.com")
            self.assertEqual(os.environ["R2_PUBLIC_BASE_URL"], "https://assets.example.com")
            self.assertEqual(os.environ["R2_PREFIX"], "sessions")

    def test_cloud_status_reports_unconfigured(self):
        with patch("practice_lab.app.get_r2_config", return_value=None):
            client = TestClient(app_module.create_app())
            response = client.get("/cloud/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"configured": False, "bucket": None, "viewerUrl": None})

    def test_cloud_sync_requires_desktop_token(self):
        with patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP_TOKEN": "secret-token"}, clear=False):
            client = TestClient(app_module.create_app())
            response = client.post("/cloud/sync")

        self.assertEqual(response.status_code, 403)

    def test_cloud_connection_uses_current_users_bucket(self):
        config = R2Config(
            bucket="user-bucket",
            endpoint_url="https://example.r2.cloudflarestorage.com",
            access_key_id="access",
            secret_access_key="secret",
            public_base_url="https://assets.example.com",
        )
        with (
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP_TOKEN": "secret-token"}, clear=False),
            patch("practice_lab.app.get_r2_config", return_value=config),
            patch("practice_lab.app.test_r2_connection", return_value={
                "connected": True,
                "bucket": "user-bucket",
                "viewerUrl": "https://assets.example.com/index.html",
            }),
        ):
            client = TestClient(app_module.create_app())
            response = client.post(
                "/cloud/test",
                headers={"X-Practice-Lab-Desktop-Token": "secret-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["bucket"], "user-bucket")


if __name__ == "__main__":
    unittest.main()
