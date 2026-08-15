import tempfile
import unittest
from pathlib import Path

from practice_lab.jpop_sections import refine_jpop_section_labels
from scripts.refine_jpop_sections import refine_library


def section(label: str, start: int) -> dict:
    return {
        "label": label,
        "start_bar": start,
        "end_bar": start + 7,
        "bar_count": 8,
        "start_time": float(start),
        "end_time": float(start + 8),
        "start_time_str": "00:00",
    }


class JpopSectionLabelTests(unittest.TestCase):
    def test_last_consecutive_verse_before_chorus_becomes_pre_chorus(self):
        refined, changes = refine_jpop_section_labels(
            [section("intro", 1), section("verse", 9), section("verse", 17), section("chorus", 25)]
        )

        self.assertEqual([item["label"] for item in refined], ["intro", "verse", "pre-chorus", "chorus"])
        self.assertEqual(changes[0]["index"], 2)

    def test_isolated_and_repeated_verses_without_following_chorus_are_untouched(self):
        source = [section("verse", 1), section("verse", 9), section("bridge", 17)]
        refined, changes = refine_jpop_section_labels(source)

        self.assertEqual(refined, source)
        self.assertEqual(changes, [])

    def test_three_verse_run_only_promotes_the_chorus_leading_section(self):
        refined, _ = refine_jpop_section_labels(
            [section("verse", 1), section("verse", 9), section("verse", 17), section("chorus", 25)]
        )

        self.assertEqual([item["label"] for item in refined], ["verse", "verse", "pre-chorus", "chorus"])

    def test_bulk_refinement_preserves_original_sections(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_dir = root / "data" / "results"
            result_dir.mkdir(parents=True)
            payload = {
                "id": "song-1",
                "title": "Song",
                "sections": [section("verse", 1), section("verse", 9), section("chorus", 17)],
            }
            import json

            (result_dir / "song-1.json").write_text(json.dumps(payload), encoding="utf-8")
            summary = refine_library(root)
            updated = json.loads((result_dir / "song-1.json").read_text(encoding="utf-8"))

            self.assertEqual(summary["changed"], 1)
            self.assertEqual(updated["sections"][1]["label"], "pre-chorus")
            self.assertEqual(updated["jpopOriginalSections"][1]["label"], "verse")
            self.assertTrue((root / "public" / "results" / "song-1.json").is_file())


if __name__ == "__main__":
    unittest.main()
