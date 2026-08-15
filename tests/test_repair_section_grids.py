import json
import tempfile
import unittest
from pathlib import Path

from scripts.repair_section_grids import repair_library


class RepairSectionGridTests(unittest.TestCase):
    def test_repairs_library_and_preserves_original_sections(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result_dir = root / "data" / "results"
            result_dir.mkdir(parents=True)
            payload = {
                "id": "song-1",
                "title": "Song",
                "total_bars": 8,
                "sections": [
                    {"label": "start", "start_bar": 1, "end_bar": 1, "bar_count": 1},
                    {"label": "verse", "start_bar": 1, "end_bar": 7, "bar_count": 7},
                ],
            }
            (result_dir / "song-1.json").write_text(json.dumps(payload), encoding="utf-8")

            summary = repair_library(root)
            updated = json.loads((result_dir / "song-1.json").read_text(encoding="utf-8"))

            self.assertEqual(summary["changed"], 1)
            self.assertEqual([(item["start_bar"], item["end_bar"]) for item in updated["sections"]], [(1, 1), (2, 8)])
            self.assertEqual(updated["sectionGridOriginalSections"][1]["start_bar"], 1)


if __name__ == "__main__":
    unittest.main()
