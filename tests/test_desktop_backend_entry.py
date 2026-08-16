import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from desktop import backend_entry


class DesktopBackendEntryTests(unittest.TestCase):
    def test_runtime_check_imports_all_macos_analysis_modules(self):
        with patch("desktop.backend_entry.importlib.import_module") as import_module:
            backend_entry.check_frozen_runtime("macos-analysis")

        imported = [call.args[0] for call in import_module.call_args_list]
        self.assertEqual(
            imported,
            [
                *backend_entry.COMMON_FROZEN_RUNTIME_MODULES,
                *backend_entry.MACOS_ANALYSIS_RUNTIME_MODULES,
            ],
        )

    def test_frozen_runtime_check_is_dispatched(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(
                sys,
                "argv",
                ["practice-lab-backend", "--check-runtime", "macos-analysis"],
            ),
            patch("desktop.backend_entry.check_frozen_runtime") as check_runtime,
        ):
            handled = backend_entry.run_frozen_python_command()

        self.assertTrue(handled)
        check_runtime.assert_called_once_with("macos-analysis")

    def test_frozen_module_command_is_dispatched_instead_of_starting_uvicorn(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "argv", ["practice-lab-backend.exe", "-m", "yt_dlp", "--version"]),
            patch("desktop.backend_entry.runpy.run_module") as run_module,
        ):
            handled = backend_entry.run_frozen_python_command()

        self.assertTrue(handled)
        run_module.assert_called_once_with("yt_dlp", run_name="__main__")

    def test_frozen_script_command_is_dispatched_instead_of_starting_uvicorn(self):
        with TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "worker.py"
            script.write_text("", encoding="utf-8")
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "argv", ["practice-lab-backend.exe", str(script), "request.json"]),
                patch("desktop.backend_entry.runpy.run_path") as run_path,
            ):
                handled = backend_entry.run_frozen_python_command()

        self.assertTrue(handled)
        run_path.assert_called_once_with(str(script), run_name="__main__")


if __name__ == "__main__":
    unittest.main()
