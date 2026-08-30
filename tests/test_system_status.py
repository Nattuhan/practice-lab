import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from practice_lab import app as app_module
from practice_lab import system_status


def completed(command, returncode=0, stdout=""):
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


class SystemStatusTests(unittest.TestCase):
    def test_healthz_identifies_the_desktop_backend_instance(self):
        with patch.dict(os.environ, {"PRACTICE_LAB_INSTANCE_ID": "desktop-instance"}, clear=False):
            client = TestClient(app_module.create_app())
            response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "instanceId": "desktop-instance"})

    def test_non_windows_is_ready_without_nvidia_setup(self):
        with (
            patch("practice_lab.system_status.platform.system", return_value="Darwin"),
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1"}, clear=True),
        ):
            status = system_status.get_system_status()
        self.assertTrue(status["ready"])
        self.assertFalse(status["setupSupported"])

    def test_packaged_mac_reports_missing_optional_analysis_runtime(self):
        with (
            patch("practice_lab.system_status.platform.system", return_value="Darwin"),
            patch("practice_lab.system_status.importlib.util.find_spec", return_value=None),
            patch("practice_lab.system_status.mac_analysis_runtime_executable", return_value=Path("/missing/runtime")),
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1"}, clear=True),
        ):
            status = system_status.get_system_status()

        self.assertFalse(status["ready"])
        self.assertTrue(status["cpuSetupSupported"])
        self.assertIn("Mac解析機能", status["message"])

    def test_windows_requires_the_complete_cuda_runtime(self):
        def fake_run(command, timeout=12):
            if "--query-gpu=name" in command:
                return completed(command, stdout="NVIDIA GeForce RTX 4080\n")
            return completed(command)

        with (
            patch("practice_lab.system_status.platform.system", return_value="Windows"),
            patch("practice_lab.system_status.shutil.which", side_effect=lambda name: name),
            patch("practice_lab.system_status.os.path.lexists", return_value=True),
            patch("practice_lab.system_status._run", side_effect=fake_run),
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1", "PRACTICE_LAB_ANALYSIS_MODE": "nvidia"}, clear=True),
        ):
            status = system_status.get_system_status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["nvidia"]["name"], "NVIDIA GeForce RTX 4080")
        self.assertTrue(status["wsl"]["cudaAvailable"])
        self.assertTrue(status["runtime"]["available"])

    def test_windows_does_not_report_ready_without_wsl(self):
        def which(name):
            return "nvidia-smi.exe" if name.startswith("nvidia-smi") else None

        with (
            patch("practice_lab.system_status.platform.system", return_value="Windows"),
            patch("practice_lab.system_status.shutil.which", side_effect=which),
            patch("practice_lab.system_status._run", return_value=completed([], stdout="RTX 4090\n")),
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1", "PRACTICE_LAB_ANALYSIS_MODE": "nvidia"}, clear=True),
        ):
            status = system_status.get_system_status()
        self.assertFalse(status["ready"])
        self.assertTrue(status["nvidia"]["available"])
        self.assertFalse(status["wsl"]["available"])

    def test_verified_runtime_does_not_require_windows_to_follow_the_wsl_symlink(self):
        def fake_run(command, timeout=12):
            if "--query-gpu=name" in command:
                return completed(command, stdout="NVIDIA GeForce RTX 3070\n")
            return completed(command)

        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            (runtime / ".verified").touch()
            wsl_python = runtime / ".venv" / "bin" / "python"
            with (
                patch("practice_lab.system_status.platform.system", return_value="Windows"),
                patch("practice_lab.system_status.shutil.which", side_effect=lambda name: name),
                patch("practice_lab.system_status.os.path.lexists", return_value=False),
                patch("practice_lab.system_status.default_wsl_python", return_value=wsl_python),
                patch("practice_lab.system_status._run", side_effect=fake_run),
                patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1", "PRACTICE_LAB_ANALYSIS_MODE": "nvidia"}, clear=True),
            ):
                status = system_status.get_system_status()
        self.assertTrue(status["runtime"]["available"])
        self.assertTrue(status["ready"])

    def test_windows_cpu_mode_does_not_require_nvidia(self):
        with (
            patch("practice_lab.system_status.platform.system", return_value="Windows"),
            patch("practice_lab.system_status.importlib.util.find_spec", return_value=object()),
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1", "PRACTICE_LAB_ANALYSIS_MODE": "cpu"}, clear=True),
        ):
            status = system_status.get_system_status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["analysisMode"], "cpu")
        self.assertFalse(status["setupSupported"])

    def test_windows_cpu_mode_reports_missing_optional_runtime(self):
        with (
            patch("practice_lab.system_status.platform.system", return_value="Windows"),
            patch("practice_lab.system_status.importlib.util.find_spec", return_value=None),
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP": "1", "PRACTICE_LAB_ANALYSIS_MODE": "cpu"}, clear=True),
        ):
            status = system_status.get_system_status()
        self.assertFalse(status["ready"])
        self.assertTrue(status["cpuSetupSupported"])
        self.assertIn("CPU解析機能", status["message"])

    def test_nvidia_setup_endpoint_requires_desktop_token(self):
        with patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP_TOKEN": "secret"}, clear=False):
            client = TestClient(app_module.create_app())
            response = client.post("/system/setup-nvidia")
        self.assertEqual(response.status_code, 403)

    def test_nvidia_setup_endpoint_accepts_desktop_token(self):
        with (
            patch.dict(os.environ, {"PRACTICE_LAB_DESKTOP_TOKEN": "secret"}, clear=False),
            patch("practice_lab.app.launch_nvidia_setup", return_value={"started": True}),
        ):
            client = TestClient(app_module.create_app())
            response = client.post(
                "/system/setup-nvidia",
                headers={"X-Practice-Lab-Desktop-Token": "secret"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"started": True})


if __name__ == "__main__":
    unittest.main()
