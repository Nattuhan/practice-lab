import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from practice_lab.analyzer_backend import analyzer_command, resolve_backend


class AnalyzerBackendTests(unittest.TestCase):
    def test_windows_prefers_existing_wsl_cuda_runtime(self):
        with TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            with patch.dict(os.environ, {}, clear=True):
                backend = resolve_backend(system="Windows", wsl_python=python)
        self.assertEqual((backend.executor, backend.device), ("wsl", "cuda"))

    def test_windows_without_wsl_uses_native_auto(self):
        with patch.dict(os.environ, {}, clear=True):
            backend = resolve_backend(system="Windows", wsl_python=Path("missing"))
        self.assertEqual((backend.executor, backend.device), ("native", "auto"))

    def test_macos_uses_native_auto(self):
        with patch.dict(os.environ, {}, clear=True):
            backend = resolve_backend(system="Darwin", wsl_python=None)
        self.assertEqual((backend.executor, backend.device), ("native", "auto"))

    def test_cpu_override_avoids_wsl(self):
        with TemporaryDirectory() as temp_dir:
            python = Path(temp_dir) / "python"
            python.touch()
            with patch.dict(os.environ, {"ANALYZER_DEVICE": "cpu"}, clear=True):
                backend = resolve_backend(system="Windows", wsl_python=python)
        self.assertEqual((backend.executor, backend.device), ("native", "cpu"))

    def test_native_command_passes_selected_device(self):
        with patch.dict(os.environ, {"ANALYZER_DEVICE": "mps"}, clear=True):
            backend = resolve_backend(system="Darwin")
        command, cwd = analyzer_command(
            backend,
            script=Path("scripts/analyze_audio.py"),
            audio_path=Path("song.wav"),
            work_dir=Path("work"),
            wsl_python=Path("unused"),
        )
        self.assertEqual(command[-4:], ["--device", "mps", "--tempo-mode", "constant"])
        self.assertEqual(cwd, Path("work"))

    def test_variable_tempo_is_passed_to_native_and_wsl(self):
        from practice_lab.analyzer_backend import AnalyzerBackend
        for executor in ('native', 'wsl'):
            with self.subTest(executor=executor):
                command, _ = analyzer_command(
                    AnalyzerBackend(executor, 'cpu', 'CPU'), script=Path('scripts/analyze_audio.py'),
                    audio_path=Path('song.wav'), work_dir=Path('work'), wsl_python=Path('python'),
                    tempo_mode='variable')
                if executor == 'native':
                    self.assertEqual(command[-2:], ['--tempo-mode', 'variable'])
                else:
                    self.assertIn('--tempo-mode variable', command[-1])


if __name__ == "__main__":
    unittest.main()
