from __future__ import annotations

from unittest import mock

from scripts.build_score_feature_pack import pack_distributions


def test_windows_score_pack_uses_headless_opencv() -> None:
    with mock.patch("scripts.build_score_feature_pack.platform.system", return_value="Windows"):
        distributions = pack_distributions()

    assert "opencv-python-headless" in distributions
    assert "opencv-python" not in distributions


def test_macos_score_pack_uses_regular_opencv() -> None:
    with mock.patch("scripts.build_score_feature_pack.platform.system", return_value="Darwin"):
        distributions = pack_distributions()

    assert "opencv-python" in distributions
    assert "opencv-python-headless" not in distributions
