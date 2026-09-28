import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_timing_result import verify_result


class VerifyTimingResultTests(unittest.TestCase):
    def test_fresh_result_checks_pulse_coverage_and_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "start"
            result = root / "result.json"
            marker.touch()
            beats = [index * .375 for index in range(200)]
            result.write_text(json.dumps({"bpm": 160, "beats": beats}))
            actual = verify_result(result, bpm=160, window=(10, 60),
                                   last_beat_between=(74, 75), fresh_after=marker)
            self.assertEqual(actual["bpm"], 160)
            self.assertEqual(actual["gridCoverage"], 1)

            # A displayed 160 BPM can conceal a substantial half-time span.
            gaps = [.375] * 199
            gaps[75:100] = [.75] * 25
            beats = [0.0]
            for gap in gaps:
                beats.append(beats[-1] + gap)
            result.write_text(json.dumps({"bpm": 160, "beats": beats}))
            with self.assertRaisesRegex(AssertionError, "grid coverage"):
                verify_result(result, bpm=160, window=(10, 80),
                              last_beat_between=(70, 90), fresh_after=marker)

    def test_stale_result_wrong_bpm_and_late_click_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "result.json"
            marker = root / "start"
            beats = [index * .375 for index in range(200)]
            result.write_text(json.dumps({"bpm": 80, "beats": beats}))
            marker.touch()
            with self.assertRaisesRegex(AssertionError, "not regenerated"):
                verify_result(result, bpm=160, window=(10, 60),
                              last_beat_between=(74, 75), fresh_after=marker)
            with self.assertRaisesRegex(AssertionError, "BPM 80"):
                verify_result(result, bpm=160, window=(10, 60),
                              last_beat_between=(74, 75))
            result.write_text(json.dumps({"bpm": 160, "beats": beats}))
            with self.assertRaisesRegex(AssertionError, "last beat"):
                verify_result(result, bpm=160, window=(10, 60),
                              last_beat_between=(70, 73))


if __name__ == "__main__":
    unittest.main()
