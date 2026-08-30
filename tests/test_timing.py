import unittest

from practice_lab.timing import normalize_section_bar_ranges, normalize_tempo_grid


class TempoGridNormalizationTests(unittest.TestCase):
    def test_repairs_overlaps_gaps_and_the_trailing_range_without_changing_times(self):
        sections = [
            {"label": "start", "start_bar": 1, "end_bar": 2, "start_time": 0.0, "end_time": 3.0},
            {"label": "verse", "start_bar": 1, "end_bar": 8, "start_time": 3.0, "end_time": 18.0},
            {"label": "chorus", "start_bar": 10, "end_bar": 11, "start_time": 18.0, "end_time": 24.0},
        ]

        adjusted = normalize_section_bar_ranges(sections, 12)

        self.assertEqual(
            [(section["start_bar"], section["end_bar"], section["bar_count"]) for section in adjusted],
            [(1, 2, 2), (3, 8, 6), (9, 12, 4)],
        )
        self.assertEqual([(section["start_time"], section["end_time"]) for section in adjusted], [(0.0, 3.0), (3.0, 18.0), (18.0, 24.0)])

    def test_promotes_half_time_bpm_when_sustained_double_time_beats_are_present(self):
        beats = [round(index * 0.68, 3) for index in range(12)]
        transition = beats[-1]
        beats.extend(round(transition + 0.34 * index, 3) for index in range(1, 25))
        data = {
            "bpm": 88.0,
            "total_bars": 6,
            "beats": beats,
            "downbeats": [beats[2], beats[6], beats[10], beats[18], beats[22], beats[26], beats[30]],
            "sections": [
                {"label": "verse", "start_time": 0.0, "end_time": beats[12], "start_bar": 1, "end_bar": 3, "bar_count": 3},
                {"label": "chorus", "start_time": beats[12], "end_time": beats[-1], "start_bar": 4, "end_bar": 6, "bar_count": 3},
            ],
        }

        adjusted = normalize_tempo_grid(data)
        intervals = [round(adjusted["beats"][index + 1] - adjusted["beats"][index], 2) for index in range(len(adjusted["beats"]) - 1)]

        self.assertEqual(adjusted["bpm"], 176.0)
        self.assertTrue(all(interval == 0.34 for interval in intervals[1:-1]))
        self.assertGreater(len(adjusted["beats"]), len(beats))
        self.assertGreater(adjusted["total_bars"], data["total_bars"])

    def test_keeps_stable_half_time_grid_unchanged(self):
        data = {
            "bpm": 88.0,
            "total_bars": 3,
            "beats": [round(index * 0.68, 3) for index in range(16)],
            "downbeats": [0.0, 2.72, 5.44],
            "sections": [],
        }

        self.assertIs(normalize_tempo_grid(data), data)

    def test_backfills_sparse_syncopated_intro_from_stable_later_grid(self):
        sparse_intro = [3.54, 4.44, 5.34, 6.24, 7.12, 7.94, 8.84, 9.71, 10.62, 11.53]
        stable = [round(11.53 + 0.61 * index, 2) for index in range(1, 25)]
        beats = sparse_intro + stable
        data = {
            "bpm": 98.0,
            "total_bars": 8,
            "beats": beats,
            "downbeats": [6.24, 9.71, 12.75, 15.19, 17.63, 20.07, 22.51, 24.95],
            "sections": [
                {"label": "start", "start_time": 0.0, "end_time": 3.04},
                {"label": "intro", "start_time": 3.04, "end_time": 20.0},
            ],
        }

        adjusted = normalize_tempo_grid(data)

        self.assertEqual(adjusted["beats"][:5], [2.99, 3.6, 4.21, 4.82, 5.43])
        self.assertEqual(adjusted["downbeats"][:4], [2.99, 5.43, 7.87, 10.31])
        self.assertEqual(adjusted["beats"][14:17], [11.53, 12.14, 12.75])
        self.assertEqual(adjusted["sections"][0]["start_bar"], 1)
        self.assertEqual(adjusted["sections"][1]["start_bar"], adjusted["sections"][0]["end_bar"] + 1)

    def test_backfills_sparse_intro_when_stable_grid_starts_after_24_detected_beats(self):
        sparse_intro = [
            1.10, 1.92, 2.73, 3.52, 4.33, 5.14, 5.95, 6.79,
            7.56, 8.37, 9.18, 9.97, 10.79, 11.49, 12.18, 12.86,
            13.60, 14.42, 15.21, 16.02, 16.82, 17.64, 18.43, 19.25,
            20.05, 20.86, 21.65, 22.47, 23.27, 23.84, 24.38, 24.88,
        ]
        stable = [round(24.88 + 0.4 * index, 2) for index in range(1, 50)]
        beats = sparse_intro + stable
        data = {
            "bpm": 150.0,
            "total_bars": 15,
            "beats": beats,
            "downbeats": [25.28, 26.88, 28.48, 30.08, 31.68, 33.28],
            "sections": [],
        }

        adjusted = normalize_tempo_grid(data)

        self.assertIsNot(adjusted, data)
        self.assertTrue(all(
            round(right - left, 2) == 0.4
            for left, right in zip(adjusted["beats"][:50], adjusted["beats"][1:51])
        ))
        self.assertGreater(len(adjusted["beats"]), len(beats))

    def test_does_not_flatten_a_short_tempo_change_later_in_song(self):
        beats = [round(index * 0.9, 2) for index in range(40)]
        beats.extend(round(beats[-1] + 0.61 * index, 2) for index in range(1, 30))
        data = {
            "bpm": 98.0,
            "beats": beats,
            "downbeats": beats[::4],
            "sections": [],
        }

        self.assertIs(normalize_tempo_grid(data), data)


if __name__ == "__main__":
    unittest.main()
