import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from practice_lab import app as app_module


def test_desktop_backend_requires_matching_host_origin_and_token():
    origin = "http://127.0.0.1:50067"
    with patch.dict(os.environ, {
        "PRACTICE_LAB_DESKTOP_TOKEN": "desktop-secret",
        "PRACTICE_LAB_BACKEND_ORIGIN": origin,
    }, clear=False):
        client = TestClient(app_module.create_app())

        assert client.get("/healthz").status_code == 200
        assert client.get("/storage").status_code == 421
        assert client.get("/storage", headers={"host": "127.0.0.1:50067"}).status_code == 403
        assert client.get("/storage", headers={
            "host": "127.0.0.1:50067",
            "origin": "https://evil.example",
            "x-practice-lab-desktop-token": "desktop-secret",
        }).status_code == 403

        response = client.get("/storage", headers={
            "host": "127.0.0.1:50067",
            "origin": origin,
            "x-practice-lab-desktop-token": "desktop-secret",
        })
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cross-origin-resource-policy"] == "same-origin"
