import json
import os
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
            # Windows can assign equal mtimes to consecutive writes. Make the
            # fixture's ordering explicit instead of depending on clock precision.
            result_time = result.stat().st_mtime_ns
            os.utime(marker, ns=(result_time - 2_000_000_000, result_time - 2_000_000_000))
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
            result_time = result.stat().st_mtime_ns
            os.utime(marker, ns=(result_time + 2_000_000_000, result_time + 2_000_000_000))
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

    def test_missing_head_after_the_checked_window_fails_the_whole_song(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.json"
            beats = [index * .375 for index in range(200)]
            # The pulse and the early repaired passage are perfect. The late
            # missing bar head still produces spoken 5, 6, 7, 8.
            heads = [beats[index] for index in range(0, 200, 4) if index != 164]
            result.write_text(json.dumps({"bpm": 160, "beats": beats, "downbeats": heads}))
            with self.assertRaisesRegex(AssertionError, "bar with 8 beats at 60.000s"):
                verify_result(result, bpm=160, window=(10, 50),
                              last_beat_between=(74, 75), maximum_bar_beats=4)
            # The limit is an investigator's expectation, not a universal
            # runtime rule that rejects real eight-beat music.
            actual = verify_result(result, bpm=160, window=(10, 50),
                                   last_beat_between=(74, 75), maximum_bar_beats=8)
            self.assertEqual(actual["maximumBarBeats"], 8)

    def test_short_bars_survive_but_an_unbounded_last_count_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.json"
            beats = [index * .375 for index in range(200)]
            indexes = list(range(0, 196, 4)) + [195, 198]
            heads = [beats[index] for index in indexes]
            result.write_text(json.dumps({"bpm": 160, "beats": beats, "downbeats": heads}))
            actual = verify_result(result, bpm=160, window=(10, 50),
                                   last_beat_between=(74, 75), maximum_bar_beats=4)
            self.assertEqual(actual["maximumBarBeats"], 4)
            result.write_text(json.dumps({"bpm": 160, "beats": beats, "downbeats": heads[:-3]}))
            with self.assertRaisesRegex(AssertionError, "bar with 12 beats"):
                verify_result(result, bpm=160, window=(10, 50),
                              last_beat_between=(74, 75), maximum_bar_beats=4)


if __name__ == "__main__":
    unittest.main()
