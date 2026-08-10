import unittest
from types import SimpleNamespace

from practice_lab.compute_device import select_torch_device


def fake_torch(*, cuda=False, mps=False):
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
    )


class ComputeDeviceTests(unittest.TestCase):
    def test_auto_prefers_cuda(self):
        self.assertEqual(select_torch_device("auto", fake_torch(cuda=True, mps=True)), "cuda")

    def test_auto_uses_mps_without_cuda(self):
        self.assertEqual(select_torch_device("auto", fake_torch(mps=True)), "mps")

    def test_auto_falls_back_to_cpu(self):
        self.assertEqual(select_torch_device("auto", fake_torch()), "cpu")

    def test_unavailable_explicit_device_fails(self):
        with self.assertRaises(RuntimeError):
            select_torch_device("mps", fake_torch())


if __name__ == "__main__":
    unittest.main()
