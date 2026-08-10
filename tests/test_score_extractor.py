import json
import tempfile
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from practice_lab.models import ScoreExtractRequest

from practice_lab.score_extractor import (
    clean_score_overlays,
    chord_degree_label,
    crop_leading_shared_barline,
    create_numberless_edge_bridge,
    annotate_extracted_measures,
    annotate_score_harmony,
    build_numbered_measure_rows,
    combine_a4_pages_to_a3,
    crop_to_score_band,
    detect_paired_score_system_bounds,
    extract_vertical_scrolling_score_systems,
    extract_tab_bands_from_paired_systems,
    fit_score_whitespace,
    format_estimated_key_summary,
    is_complete_static_score_sequence,
    preserve_complete_score_systems,
    detect_measure_barlines,
    detect_staff_horizontal_extent,
    detect_tab_staff_anchor,
    group_score_views,
    infer_chord_from_frets,
    infer_key_from_pitch_histogram,
    score_row_layouts,
    estimate_horizontal_scroll,
    estimate_score_edge_overlap,
    measure_signature_difference,
    reconstruct_scrolling_score,
    remove_leading_tab_label,
    remove_spurious_close_barlines,
    resolve_musical_output_options,
    stitch_edge_overlap_runs,
    remove_vertical_playback_cursor,
    resolve_score_time_range,
    score_region_likelihood,
    scan_score_views,
    extract_crops_at_scan_indexes,
    trim_frame_edges,
    trim_vertical_score_whitespace,
    tab_staff_vertical_offsets,
    tab_staff_vertical_layout,
    write_a3_2up_pngs,
    write_a4_pngs,
)


class ScorePageLayoutTests(unittest.TestCase):
    def test_reflow_crop_preserves_thin_marking_above_staff(self):
        image = Image.new("RGB", (320, 140), "white")
        draw = ImageDraw.Draw(image)
        for y in (70, 82, 94, 106):
            draw.line((0, y, 319, y), fill=(150, 150, 150), width=2)
        draw.arc((250, 12, 310, 28), 180, 360, fill="black", width=2)

        cropped = crop_to_score_band(image, margin=0, preserve_all_content=True)

        self.assertLess(cropped.height, image.height)
        self.assertGreater(np.count_nonzero(np.asarray(cropped.convert("L"))[0:20] < 100), 0)

    def test_aligns_measures_with_different_tab_staff_heights(self):
        def measure(staff_top: int) -> Image.Image:
            image = Image.new("RGB", (160, 120), "white")
            draw = ImageDraw.Draw(image)
            for y in (staff_top, staff_top + 12, staff_top + 24, staff_top + 36):
                draw.line((0, y, 159, y), fill=(150, 150, 150), width=2)
            draw.rectangle((70, staff_top + 8, 80, staff_top + 18), fill="black")
            return image

        measures = [measure(30), measure(30), measure(30), measure(55)]
        try:
            self.assertEqual([detect_tab_staff_anchor(image) for image in measures], [30, 30, 30, 55])
            self.assertEqual(tab_staff_vertical_offsets(measures), [0, 0, 0, -25])
            self.assertEqual(tab_staff_vertical_layout(measures), ([25, 25, 25, 0], 145))
        finally:
            for image in measures:
                image.close()

    def test_removes_embedded_tab_label_but_keeps_staff_and_notes(self):
        image = Image.new("RGB", (240, 90), "white")
        draw = ImageDraw.Draw(image)
        for y in (25, 35, 45, 55):
            draw.line((0, y, 239, y), fill=(150, 150, 150), width=2)
        draw.line((1, 24, 1, 57), fill="black", width=2)
        draw.text((8, 17), "T", fill="black")
        draw.text((8, 32), "A", fill="black")
        draw.text((8, 47), "B", fill="black")
        draw.rectangle((34, 48, 41, 56), fill="black")
        draw.rectangle((62, 31, 72, 40), fill="black")

        cleaned = remove_leading_tab_label(image)
        cleaned_gray = np.asarray(cleaned.convert("L"))

        self.assertEqual(np.count_nonzero(cleaned_gray[17:60, 7:43] < 100), 0)
        self.assertGreater(np.count_nonzero(cleaned_gray[24:57, 0:4] < 100), 0)
        self.assertGreater(np.count_nonzero(cleaned_gray[31:41, 62:73] < 100), 0)
        for y in (25, 35, 45, 55):
            self.assertGreater(np.count_nonzero(cleaned_gray[y:y + 2, 7:26] < 220), 0)

    def test_reflow_does_not_clean_circled_fret_at_nonleading_measure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = Image.new("RGB", (400, 100), "white")
            draw = ImageDraw.Draw(image)
            for y in (30, 42, 54, 66):
                draw.line((0, y, 399, y), fill=(150, 150, 150), width=2)
            for x in (0, 100, 200, 300, 399):
                draw.line((x, 28, x, 68), fill="black", width=2)
            draw.ellipse((208, 35, 246, 73), outline="black", width=3)
            draw.text((215, 45), "12", fill="black")
            image.save(source)
            image.close()

            with patch(
                "practice_lab.score_extractor.read_printed_measure_numbers_batch",
                side_effect=lambda paths, barline_sets: [{} for _path in paths],
            ):
                rows, count, _deduplicated = build_numbered_measure_rows(
                    [source], root / "rows", show_measure_numbers=False
                )

            self.assertEqual(count, 4)
            with Image.open(rows[0]).convert("L") as row:
                third_measure = np.asarray(row)[:, 200:300]
                self.assertGreater(np.count_nonzero(third_measure < 100), 80)

    def test_three_logical_pages_make_two_a3_sheets_without_losing_page_three(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pages = []
            for index, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255)), start=1):
                page = root / f"page_{index}.png"
                Image.new("RGB", (100, 140), color).save(page)
                pages.append(page)

            outputs = combine_a4_pages_to_a3(pages, root, "score")

            self.assertEqual(len(outputs), 2)
            with Image.open(outputs[1]).convert("RGB") as second_sheet:
                self.assertEqual(second_sheet.getpixel((50, 70)), (0, 0, 255))
                self.assertEqual(second_sheet.getpixel((150, 70)), (255, 255, 255))

    @staticmethod
    def _draw_paired_system(image, first_line, marker_x):
        draw = ImageDraw.Draw(image)
        for y in [first_line + offset for offset in (0, 10, 20, 30, 40, 70, 80, 90, 100)]:
            draw.line((20, y, image.width - 20, y), fill="black", width=2)
        draw.rectangle((marker_x, first_line + 12, marker_x + 18, first_line + 62), fill="black")

    def test_detects_standard_notation_and_tab_as_one_complete_system(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "frame.png"
            image = Image.new("RGB", (400, 500), "white")
            self._draw_paired_system(image, 60, 80)
            self._draw_paired_system(image, 280, 180)
            image.save(path)
            image.close()

            bounds = detect_paired_score_system_bounds(path)

            self.assertEqual(len(bounds), 2)
            self.assertLess(bounds[0][0], 60)
            self.assertGreater(bounds[0][1], 160)

    def test_score_band_trim_keeps_nearby_notation_and_tab(self):
        image = Image.new("RGB", (300, 260), "white")
        draw = ImageDraw.Draw(image)
        for y in (40, 50, 60, 70, 80):
            draw.line((10, y, 290, y), fill="black")
        for y in (135, 150, 165, 180):
            draw.line((10, y, 290, y), fill="black")
        draw.rectangle((80, 45, 90, 105), fill="black")
        draw.rectangle((160, 140, 170, 205), fill="black")

        cropped = crop_to_score_band(image)

        self.assertGreater(cropped.height, 150)
        image.close()
        cropped.close()

    def test_paired_system_outputs_tab_only_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paired = root / "paired.png"
            image = Image.new("RGB", (400, 260), "white")
            self._draw_paired_system(image, 60, 120)
            image.save(paired)
            image.close()

            outputs = extract_tab_bands_from_paired_systems([paired], root / "tab")

            with Image.open(outputs[0]).convert("L") as tab:
                self.assertLess(tab.height, 150)
                self.assertGreater(np.count_nonzero(np.asarray(tab) < 128), 100)

    def test_tab_only_crop_excludes_notation_tie_from_interstaff_gap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paired = root / "paired.png"
            image = Image.new("RGB", (400, 260), "white")
            self._draw_paired_system(image, 60, 120)
            draw = ImageDraw.Draw(image)
            draw.line((180, 103, 220, 103), fill="black", width=3)
            draw.line((180, 120, 220, 120), fill="black", width=3)
            image.save(paired)
            image.close()

            outputs = extract_tab_bands_from_paired_systems([paired], root / "tab")

            with Image.open(outputs[0]).convert("L") as tab:
                pixels = np.asarray(tab)
                self.assertEqual(np.count_nonzero(pixels[0:4, 180:221] < 128), 0)
                self.assertGreater(np.count_nonzero(pixels[4:12, 180:221] < 128), 0)

    def test_vertical_scroll_reuses_overlapping_complete_system(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.png"
            second = root / "second.png"
            first_image = Image.new("RGB", (400, 500), "white")
            self._draw_paired_system(first_image, 60, 70)
            self._draw_paired_system(first_image, 280, 150)
            first_image.save(first)
            first_image.close()
            second_image = Image.new("RGB", (400, 500), "white")
            self._draw_paired_system(second_image, 60, 150)
            self._draw_paired_system(second_image, 280, 240)
            second_image.save(second)
            second_image.close()

            outputs, usable = extract_vertical_scrolling_score_systems(
                [first, first, first, second, second, second], root / "systems"
            )

            self.assertEqual(usable, 6)
            self.assertEqual(len(outputs), 3)

    def test_whitespace_expansion_preserves_notation_ink(self):
        image = Image.new("RGB", (120, 70), "white")
        draw = ImageDraw.Draw(image)
        for y in (30, 40, 50, 60):
            draw.line((0, y, 119, y), fill=(150, 150, 150), width=1)
        draw.line((0, 27, 0, 63), fill="black", width=2)
        draw.line((119, 27, 119, 63), fill="black", width=2)
        draw.rectangle((52, 34, 58, 47), fill="black")
        before = np.asarray(image.convert("L")) < 100
        before[(30, 40, 50, 60), :] = False

        expanded = fit_score_whitespace(image, 180)
        after = np.asarray(expanded.convert("L")) < 100
        after[(30, 40, 50, 60), :] = False

        self.assertEqual(expanded.width, 180)
        self.assertEqual(np.count_nonzero(after), np.count_nonzero(before))
        image.close()
        expanded.close()

    def test_whitespace_compression_preserves_notation_ink(self):
        image = Image.new("RGB", (180, 70), "white")
        draw = ImageDraw.Draw(image)
        for y in (30, 40, 50, 60):
            draw.line((0, y, 179, y), fill=(150, 150, 150), width=1)
        draw.line((0, 27, 0, 63), fill="black", width=2)
        draw.line((179, 27, 179, 63), fill="black", width=2)
        draw.rectangle((76, 34, 82, 47), fill="black")
        before = np.asarray(image.convert("L")) < 100
        before[(30, 40, 50, 60), :] = False

        compressed = fit_score_whitespace(image, 120)
        after = np.asarray(compressed.convert("L")) < 100
        after[(30, 40, 50, 60), :] = False

        self.assertEqual(compressed.width, 120)
        self.assertEqual(np.count_nonzero(after), np.count_nonzero(before))
        image.close()
        compressed.close()

    def test_whitespace_fitting_keeps_boundary_glyph_halves_at_cell_edges(self):
        image = Image.new("RGB", (200, 70), "white")
        draw = ImageDraw.Draw(image)
        for y in (25, 35, 45, 55):
            draw.line((0, y, 199, y), fill=(150, 150, 150), width=1)
        draw.arc((-12, 24, 16, 52), 270, 90, fill="black", width=3)
        draw.arc((184, 24, 212, 52), 90, 270, fill="black", width=3)

        expanded = fit_score_whitespace(image, 300)
        pixels = np.asarray(expanded.convert("L")) < 100
        for y in (25, 35, 45, 55):
            pixels[y, :] = False
        columns = np.where(np.any(pixels, axis=0))[0]

        self.assertLessEqual(int(columns[0]), 3)
        self.assertGreaterEqual(int(columns[-1]), 296)
        image.close()
        expanded.close()

    def test_score_extraction_defaults_to_auto_tab_mode(self):
        request = ScoreExtractRequest()

        self.assertEqual(request.processingMode, "auto")
        self.assertEqual(request.scoreContent, "tab")
        self.assertEqual(request.verticalScrollMode, "auto")
        self.assertEqual(request.horizontalScrollMode, "auto")
        self.assertEqual(request.measuresPerRow, 4)
        self.assertFalse(request.showMeasureNumbers)
        self.assertTrue(request.showMusicalAnalysis)
        self.assertIsNone(request.showChordSymbols)
        self.assertIsNone(request.showKeyEstimate)
        self.assertIsNone(request.showBpm)
        self.assertIsNone(request.startSec)
        self.assertIsNone(request.endSec)

    def test_musical_print_options_are_independent(self):
        self.assertEqual(
            resolve_musical_output_options({
                "showChordSymbols": True,
                "showKeyEstimate": False,
                "showBpm": True,
            }),
            (True, False, True),
        )
        self.assertEqual(
            resolve_musical_output_options({"showMusicalAnalysis": False}),
            (False, False, False),
        )

    def test_score_time_range_defaults_to_the_full_video(self):
        self.assertEqual(
            resolve_score_time_range({"durationSec": 245.5}, {}),
            (0.0, 245.5),
        )

    def test_score_time_range_clamps_end_to_video_duration(self):
        self.assertEqual(
            resolve_score_time_range(
                {"durationSec": 245.5}, {"startSec": 30, "endSec": 999}
            ),
            (30.0, 245.5),
        )

    def test_score_time_range_rejects_end_before_start(self):
        with self.assertRaisesRegex(ValueError, "終了時間"):
            resolve_score_time_range(
                {"durationSec": 245.5}, {"startSec": 60, "endSec": 30}
            )

    def test_tab_image_harmony_recognizes_d_major_key_and_slash_chord(self):
        key_profile = np.roll(
            np.asarray((6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)),
            2,
        )
        key = infer_key_from_pitch_histogram(key_profile)
        chord, confidence, notes = infer_chord_from_frets(
            {0: 2, 1: 3, 2: 2, 3: 0, 4: 0, 5: 2}
        )

        self.assertEqual(key["key"], "D Major")
        self.assertIn("B Natural Minor", key["scale"])
        self.assertEqual(chord, "D/F#")
        self.assertGreater(confidence, 0.4)
        self.assertEqual(len(notes), 6)

    def test_missing_open_string_does_not_turn_g_major_into_b_augmented(self):
        chord, confidence, _notes = infer_chord_from_frets(
            {0: 3, 1: 0, 2: 0, 4: 2, 5: 3}
        )

        self.assertEqual(chord, "G")
        self.assertGreater(confidence, 0.4)

    def test_estimated_key_summary_is_concise_japanese(self):
        summary = format_estimated_key_summary({"tonic": 7, "mode": "major"})

        self.assertEqual(summary, "推定キー：Gメジャー / Eマイナー")
        self.assertNotIn("Image", summary)
        self.assertNotIn("Scale", summary)
        self.assertNotIn("可能性", summary)

    def test_chord_degrees_use_roman_numerals_in_g_major(self):
        self.assertEqual(chord_degree_label("G", 7), "I")
        self.assertEqual(chord_degree_label("Am", 7), "ii")
        self.assertEqual(chord_degree_label("Bm7", 7), "iii")
        self.assertEqual(chord_degree_label("C", 7), "IV")
        self.assertEqual(chord_degree_label("D/F#", 7), "V")
        self.assertEqual(chord_degree_label("Em", 7), "vi")
        self.assertEqual(chord_degree_label("F#dim", 7), "vii°")

    def test_chord_symbols_are_added_above_score_measures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "row.png"
            image = Image.new("RGB", (400, 100), "white")
            draw = ImageDraw.Draw(image)
            for y in (35, 45, 55, 65):
                draw.line((0, y, 399, y), fill=(140, 140, 140), width=2)
            for x in (0, 100, 200, 300, 399):
                draw.line((x, 33, x, 68), fill="black", width=2)
            image.save(source)

            outputs = annotate_score_harmony(
                [source], root / "annotated", [["D"], ["A"], ["Bm"], ["G"]],
                measures_per_row=4, processing_mode="auto",
            )

            with Image.open(outputs[0]).convert("L") as annotated:
                self.assertEqual(annotated.height, 136)
                self.assertGreater(np.count_nonzero(np.asarray(annotated)[:36] < 200), 0)

    def test_chord_symbols_are_centered_over_their_detected_change_positions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "row.png"
            Image.new("RGB", (400, 100), "white").save(source)

            outputs = annotate_score_harmony(
                [source], root / "annotated", [[
                    {"label": "G", "position": 0.2, "degree": "I"},
                    {"label": "D", "position": 0.8, "degree": "V"},
                ]], measures_per_row=1, processing_mode="auto",
            )

            with Image.open(outputs[0]).convert("L") as annotated:
                band = np.asarray(annotated)[:36]
                self.assertGreater(np.count_nonzero(band[:, 45:115] < 200), 0)
                self.assertGreater(np.count_nonzero(band[:, 285:355] < 200), 0)
                self.assertEqual(np.count_nonzero(band[:, 170:230] < 200), 0)
                self.assertEqual(annotated.height, 136)
                first_ink_x = np.where(band[:, 70:150] < 200)[1].min() + 70
                second_ink_x = np.where(band[:, 310:390] < 200)[1].min() + 310
                self.assertAlmostEqual(first_ink_x, 80, delta=3)
                self.assertAlmostEqual(second_ink_x, 320, delta=3)

    def test_measure_numbers_are_kept_above_chord_symbols(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "row.png"
            image = Image.new("RGB", (400, 100), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((8, 2, 16, 10), fill="black")
            draw.line((0, 20, 399, 20), fill="black", width=2)
            image.save(source)

            outputs = annotate_score_harmony(
                [source], root / "annotated", [[{"label": "G", "position": 0.5}]],
                measures_per_row=1, processing_mode="auto", show_measure_numbers=True,
            )

            with Image.open(outputs[0]).convert("L") as annotated:
                pixels = np.asarray(annotated)
                self.assertGreater(np.count_nonzero(pixels[:20, :30] < 200), 0)
                self.assertGreater(np.count_nonzero(pixels[20:56] < 200), 0)
                self.assertGreater(np.count_nonzero(pixels[56:59] < 200), 0)

    def test_simple_tab_analysis_uses_audited_measure_numbers_and_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = []
            for index in range(2):
                path = root / f"row_{index}.png"
                Image.new("RGB", (400, 100), "white").save(path)
                frames.append(path)
            audit = root / "audit.json"
            audit.write_text(json.dumps({"frames": [
                {"firstMeasure": 1, "boundaries": [10, 80, 160, 240, 320, 390]},
                {"firstMeasure": 6, "boundaries": [10, 200, 390]},
            ]}), encoding="utf-8")

            layouts = score_row_layouts(
                frames, measure_count=7, measures_per_row=4,
                processing_mode="simple", audit_path=audit,
            )

            self.assertEqual(layouts[0], (0, [10, 80, 160, 240, 320, 390]))
            self.assertEqual(layouts[1], (5, [10, 200, 390]))

    def test_inset_staff_onset_is_recognized_without_a_vertical_left_barline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "inset.png"
            image = Image.new("RGB", (320, 90), "white")
            draw = ImageDraw.Draw(image)
            for y in (30, 40, 50, 60):
                draw.line((40, y, 300, y), fill=(140, 140, 140), width=2)
            for x in (120, 220, 300):
                draw.line((x, 28, x, 62), fill="black", width=2)
            image.save(path)

            start, end = detect_staff_horizontal_extent(path)
            self.assertEqual(start, 40)
            self.assertAlmostEqual(end, 300, delta=2)

    def test_jump_scrolling_edge_fragments_are_joined_into_a_closed_measure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def make_frame(path: Path, barlines: tuple[int, ...], marker: int) -> None:
                image = Image.new("RGB", (300, 90), "white")
                draw = ImageDraw.Draw(image)
                for y in (30, 40, 50, 60):
                    draw.line((0, y, 299, y), fill=(140, 140, 140), width=2)
                for x in barlines:
                    draw.line((x, 28, x, 62), fill="black", width=2)
                draw.rectangle((marker, 34, marker + 8, 48), fill="black")
                image.save(path)

            left = root / "left.png"
            right = root / "right.png"
            make_frame(left, (0, 80, 160, 240), 272)
            make_frame(right, (60, 140, 220, 299), 22)

            bridge = create_numberless_edge_bridge(left, right, root / "bridge.png")

            self.assertIsNotNone(bridge)
            barlines = remove_spurious_close_barlines(detect_measure_barlines(bridge), {})
            self.assertEqual(len(barlines), 2)
            self.assertLessEqual(barlines[0], 5)
            self.assertAlmostEqual(barlines[1], 128, delta=4)

    def test_selected_crop_measure_numbers_win_over_unrelated_analysis_imagery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = root / "selected"
            analysis = root / "analysis"
            selected.mkdir()
            analysis.mkdir()

            def make_frame(path: Path, *, noisy_header: bool = False) -> None:
                image = Image.new("RGB", (320, 140 if noisy_header else 90), "white")
                draw = ImageDraw.Draw(image)
                offset = 50 if noisy_header else 0
                if noisy_header:
                    for y in (8, 14, 20, 26):
                        draw.line((0, y, 319, y), fill="black", width=2)
                for y in (30 + offset, 40 + offset, 50 + offset, 60 + offset):
                    draw.line((0, y, 319, y), fill=(140, 140, 140), width=2)
                for x in (0, 80, 160, 240, 319):
                    draw.line((x, 28 + offset, x, 62 + offset), fill="black", width=2)
                image.save(path)

            selected_path = selected / "frame.png"
            analysis_path = analysis / "frame.png"
            make_frame(selected_path)
            make_frame(analysis_path, noisy_header=True)

            def fake_numbers(paths, barline_sets):
                results = []
                for path, barlines in zip(paths, barline_sets):
                    results.append(
                        {x: index + 1 for index, x in enumerate(barlines)}
                        if path.parent.name == "selected"
                        else {}
                    )
                return results

            audit = root / "audit.json"
            with patch("practice_lab.score_extractor.read_printed_measure_numbers_batch", side_effect=fake_numbers):
                _rows, count, _deduplicated = build_numbered_measure_rows(
                    [selected_path], root / "rows", barline_frames=[analysis_path], audit_path=audit
                )

            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            self.assertEqual(audit_data["policy"]["mode"], "printed-measure-number-reconstruction")
            self.assertEqual(count, 4)

    def test_reflow_removes_the_next_measures_duplicate_left_barline(self):
        measure = Image.new("RGB", (100, 80), "white")
        draw = ImageDraw.Draw(measure)
        for y in (28, 38, 48, 58):
            draw.line((0, y, 99, y), fill=(140, 140, 140), width=2)
        draw.line((0, 26, 0, 61), fill="black", width=3)
        draw.rectangle((28, 34, 35, 49), fill="black")

        cropped = crop_leading_shared_barline(measure)

        self.assertLess(cropped.width, measure.width)
        self.assertGreater(cropped.width, 80)
        self.assertGreater(np.count_nonzero(np.asarray(cropped.convert("L"))[:, 15:40] < 180), 0)
        cropped.close()
        measure.close()

    def test_numbered_edge_fragment_is_replaced_by_later_complete_measure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def make_frame(path: Path, marker_offset: int) -> None:
                image = Image.new("RGB", (300, 90), "white")
                draw = ImageDraw.Draw(image)
                for y in (30, 40, 50, 60):
                    draw.line((0, y, 299, y), fill=(140, 140, 140), width=2)
                for x in (0, 100, 200, 299):
                    draw.line((x, 28, x, 62), fill="black", width=2)
                draw.rectangle((20 + marker_offset, 35, 28 + marker_offset, 52), fill="black")
                image.save(path)

            first = root / "first.png"
            second = root / "second.png"
            make_frame(first, 0)
            make_frame(second, 15)
            audit = root / "audit.json"

            def fake_numbers(paths, barline_sets):
                results = []
                for path, barlines in zip(paths, barline_sets):
                    start = 1 if path.name == "first.png" else 3
                    results.append({x: start + index for index, x in enumerate(barlines)})
                return results

            with patch("practice_lab.score_extractor.read_printed_measure_numbers_batch", side_effect=fake_numbers):
                _rows, measure_count, _deduplicated = build_numbered_measure_rows(
                    [first, second], root / "rows", audit_path=audit
                )

            audit_data = json.loads(audit.read_text(encoding="utf-8"))
            source_three = next(item for item in audit_data["measureSources"] if item["measure"] == 3)
            self.assertEqual(measure_count, 5)
            self.assertEqual(source_three["frame"], "second.png")
            self.assertEqual(source_three["localMeasureIndex"], 1)
            self.assertEqual(audit_data["rejectedEdgeFragments"], 2)
            self.assertTrue(audit_data["measureSources"][-1]["edgeFallback"])

    def test_adaptive_scan_keeps_representatives_from_each_score_view(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "source"
            source_dir.mkdir()
            panorama = Image.new("RGB", (460, 100), "white")
            panorama_draw = ImageDraw.Draw(panorama)
            for y in (35, 45, 55, 65):
                panorama_draw.line((0, y, 459, y), fill=(130, 130, 130), width=2)
            for marker_index, marker in enumerate((17, 49, 88, 136, 173, 229, 271, 318, 367, 421)):
                panorama_draw.rectangle(
                    (marker, 23 + marker_index % 11, marker + 5 + marker_index % 9, 76 - marker_index % 13),
                    fill="black",
                )
                panorama_draw.text((marker + 10, 12 + marker_index % 17), chr(65 + marker_index), fill="black")
            for index in range(7):
                left = 0 if index < 3 else (70 if index == 3 else 140)
                image = panorama.crop((left, 0, left + 320, 100))
                image.save(source_dir / f"frame_{index + 1:06d}.png")
            video = root / "source.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-framerate", "2",
                    "-i", str(source_dir / "frame_%06d.png"), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(video), "-y",
                ],
                check=True,
            )
            region = {"x": 0, "y": 0, "width": 320, "height": 100}

            indexes, fps, scanned, rejected = scan_score_views(
                video, root / "scan", region, scan_interval_sec=0.5,
                samples_per_view=2, minimum_stable_samples=3,
            )
            extracted = extract_crops_at_scan_indexes(video, root / "full", region, fps, indexes)

            self.assertEqual(scanned, 7)
            self.assertEqual(len(indexes), 4)
            self.assertEqual(len(extracted), 4)
            self.assertEqual(rejected, 1)
            self.assertNotIn(3, indexes)

    def test_vertical_whitespace_is_trimmed_per_frame_without_following_side_border(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = Image.new("RGB", (400, 180), (250, 249, 245))
            draw = ImageDraw.Draw(image)
            draw.line((0, 0, 0, 179), fill="black", width=3)
            for y in (70, 80, 90, 100):
                draw.line((20, y, 380, y), fill=(100, 100, 100), width=2)
            draw.text((45, 55), "7", fill="black")
            draw.line((70, 90, 70, 120), fill="black", width=2)
            image.save(source)

            outputs, removed = trim_vertical_score_whitespace([source], root / "trimmed", margin=8)

            with Image.open(outputs[0]) as trimmed:
                self.assertLess(trimmed.height, image.height)
                self.assertGreaterEqual(trimmed.height, 80)
                self.assertEqual(trimmed.width, image.width)
            self.assertGreater(removed, 0)

    def test_numbered_rows_trim_source_whitespace_before_the_label_band(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = Image.new("RGB", (320, 180), "white")
            draw = ImageDraw.Draw(image)
            for y in (95, 105, 115, 125):
                draw.line((0, y, 319, y), fill=(140, 140, 140), width=2)
            for x in (0, 80, 160, 240, 319):
                draw.line((x, 93, x, 128), fill="black", width=2)
            draw.text((18, 108), "7", fill="black")
            image.save(source)

            with patch(
                "practice_lab.score_extractor.read_printed_measure_numbers_batch",
                side_effect=lambda paths, barline_sets: [{} for _path in paths],
            ):
                rows, measure_count, _deduplicated = build_numbered_measure_rows(
                    [source], root / "rows"
                )

            self.assertEqual(measure_count, 4)
            with Image.open(rows[0]).convert("L") as numbered:
                pixels = np.asarray(numbered)
                self.assertLess(numbered.height, 90)
                self.assertGreater(np.count_nonzero(pixels[:20] < 200), 0)
                self.assertGreater(np.count_nonzero(pixels[20:40] < 200), 0)

    def test_measures_per_row_is_an_explicit_layout_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = Image.new("RGB", (320, 100), "white")
            draw = ImageDraw.Draw(image)
            for y in (35, 45, 55, 65):
                draw.line((0, y, 319, y), fill=(140, 140, 140), width=2)
            for x in (0, 80, 160, 240, 319):
                draw.line((x, 33, x, 68), fill="black", width=2)
            image.save(source)

            with patch(
                "practice_lab.score_extractor.read_printed_measure_numbers_batch",
                side_effect=lambda paths, barline_sets: [{} for _path in paths],
            ):
                rows, count, _ = build_numbered_measure_rows(
                    [source], root / "rows", measures_per_row=3
                )

            self.assertEqual(count, 4)
            self.assertEqual(len(rows), 2)

    def test_horizontal_scroll_can_be_explicitly_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = Image.new("RGB", (320, 100), "white")
            draw = ImageDraw.Draw(image)
            for y in (35, 45, 55, 65):
                draw.line((0, y, 319, y), fill=(140, 140, 140), width=2)
            for x in (0, 80, 160, 240, 319):
                draw.line((x, 33, x, 68), fill="black", width=2)
            image.save(source)

            with patch(
                "practice_lab.score_extractor.read_printed_measure_numbers_batch",
                side_effect=lambda paths, barline_sets: [{} for _path in paths],
            ), patch("practice_lab.score_extractor.reconstruct_scrolling_score") as reconstruct:
                _rows, count, _ = build_numbered_measure_rows(
                    [source], root / "rows", horizontal_scroll_mode="off"
                )

            self.assertEqual(count, 4)
            reconstruct.assert_not_called()

    def test_measure_numbers_can_be_hidden_without_disabling_measure_reconstruction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = Image.new("RGB", (320, 100), "white")
            draw = ImageDraw.Draw(image)
            for y in (35, 45, 55, 65):
                draw.line((0, y, 319, y), fill=(140, 140, 140), width=2)
            for x in (0, 80, 160, 240, 319):
                draw.line((x, 33, x, 68), fill="black", width=2)
            draw.text((18, 48), "7", fill="black")
            image.save(source)

            with patch(
                "practice_lab.score_extractor.read_printed_measure_numbers_batch",
                side_effect=lambda paths, barline_sets: [{} for _path in paths],
            ):
                shown_rows, shown_count, _ = build_numbered_measure_rows(
                    [source], root / "shown", show_measure_numbers=True
                )
                hidden_rows, hidden_count, _ = build_numbered_measure_rows(
                    [source], root / "hidden", show_measure_numbers=False
                )

            self.assertEqual(shown_count, 4)
            self.assertEqual(hidden_count, shown_count)
            with Image.open(shown_rows[0]) as shown, Image.open(hidden_rows[0]) as hidden:
                self.assertEqual(shown.height, hidden.height + 20)

    def test_complete_margin_bounded_score_rows_are_preserved_without_reflow(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = []
            for frame_index in range(3):
                path = root / f"source_{frame_index}.png"
                image = Image.new("RGB", (400, 100), "white")
                draw = ImageDraw.Draw(image)
                for y in (35, 45, 55, 65):
                    draw.line((40, y, 360, y), fill=(140, 140, 140), width=2)
                for x in (40, 140, 250, 360):
                    draw.line((x, 33, x, 68), fill="black", width=2)
                draw.rectangle((70 + frame_index * 15, 40, 78 + frame_index * 15, 58), fill="black")
                image.save(path)
                frames.append(path)

            self.assertTrue(is_complete_static_score_sequence(frames))
            outputs, measure_count, deduplicated = preserve_complete_score_systems(
                frames,
                root / "preserved",
                audit_path=root / "audit.json",
                show_measure_numbers=False,
            )

            self.assertEqual(len(outputs), len(frames))
            self.assertEqual(measure_count, 9)
            self.assertEqual(deduplicated, 0)
            with Image.open(outputs[0]) as preserved:
                self.assertEqual(preserved.size, (400, 100))
            audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["policy"]["mode"], "complete-static-system-preservation")

    def test_edge_clipped_score_rows_are_not_classified_as_complete_systems(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = []
            for frame_index in range(3):
                path = root / f"scroll_{frame_index}.png"
                image = Image.new("RGB", (400, 100), "white")
                draw = ImageDraw.Draw(image)
                for y in (35, 45, 55, 65):
                    draw.line((0, y, 399, y), fill=(140, 140, 140), width=2)
                for x in (0, 110, 230, 399):
                    draw.line((x, 33, x, 68), fill="black", width=2)
                image.save(path)
                frames.append(path)

            self.assertFalse(is_complete_static_score_sequence(frames))

    def test_complete_system_preservation_removes_edge_video_bars_and_black_cards(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            score = root / "score.png"
            image = Image.new("RGB", (400, 110), "white")
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 399, 7), fill="black")
            for y in (40, 50, 60, 70):
                draw.line((40, y, 360, y), fill=(140, 140, 140), width=2)
            for x in (40, 140, 250, 360):
                draw.line((x, 38, x, 73), fill="black", width=2)
            image.save(score)
            black_card = root / "black.png"
            Image.new("RGB", (400, 110), "black").save(black_card)

            outputs, measure_count, _ = preserve_complete_score_systems(
                [score, black_card],
                root / "preserved",
                audit_path=root / "audit.json",
                show_measure_numbers=False,
            )

            self.assertEqual(len(outputs), 1)
            self.assertEqual(measure_count, 3)
            with Image.open(outputs[0]).convert("L") as preserved:
                self.assertGreater(float(np.mean(np.asarray(preserved)[0])), 240)

    def test_preview_likelihood_prefers_staff_over_title_card(self):
        region = {"x": 0, "y": 0, "width": 400, "height": 120}
        title = Image.new("RGB", (400, 120), "black")
        ImageDraw.Draw(title).text((80, 45), "TITLE", fill="white")
        score = Image.new("RGB", (400, 120), "white")
        draw = ImageDraw.Draw(score)
        for y in (30, 40, 50, 60):
            draw.line((5, y, 395, y), fill=(150, 150, 150), width=2)
        for x in (40, 130, 220, 310):
            draw.line((x, 28, x, 62), fill="black", width=2)
            draw.ellipse((x + 18, 42, x + 27, 50), fill="black")

        self.assertEqual(score_region_likelihood(title, region), 0.0)
        self.assertGreater(score_region_likelihood(score, region), 0.0)

    def test_numberless_score_reconstructs_chronological_measure_overlap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def make_frame(path: Path, values: tuple[int, ...]) -> None:
                image = Image.new("RGB", (300, 90), "white")
                draw = ImageDraw.Draw(image)
                for y in (30, 40, 50, 60):
                    draw.line((0, y, 299, y), fill=(140, 140, 140), width=2)
                for index, value in enumerate(values):
                    left = index * 75
                    draw.line((left, 29, left, 62), fill="black", width=2)
                    marker_x = left + 10 + value * 7
                    draw.rectangle((marker_x, 34, marker_x + 5 + value, 43 + value), fill="black")
                draw.line((299, 29, 299, 62), fill="black", width=2)
                image.save(path)

            first = root / "first.png"
            second = root / "second.png"
            make_frame(first, (1, 2, 3, 4))
            make_frame(second, (3, 4, 5, 6))
            progress_events: list[tuple[str, str]] = []

            rows, measure_count, deduplicated = build_numbered_measure_rows(
                [first, second], root / "rows", progress=lambda stage, message: progress_events.append((stage, message))
            )

            self.assertEqual(measure_count, 6)
            self.assertEqual(deduplicated, 2)
            self.assertGreaterEqual(len(rows), 1)
            self.assertIn("小節線解析", [stage for stage, _message in progress_events])

    def test_a_merely_similar_single_measure_is_not_removed(self):
        left = np.zeros((64, 128), dtype=bool)
        right = np.zeros((64, 128), dtype=bool)
        left[20:35, 30:35] = True
        right[20:35, 36:41] = True

        self.assertGreater(measure_signature_difference(left, right), 0.02)

    def test_only_complete_measures_receive_generated_numbers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = Image.new("RGB", (260, 90), "white")
            draw = ImageDraw.Draw(image)
            for y in (30, 40, 50, 60):
                draw.line((0, y, 259, y), fill=(140, 140, 140), width=2)
            for x in (35, 105, 175, 235):
                draw.line((x, 29, x, 62), fill="black", width=2)
            image.save(source)

            outputs, count = annotate_extracted_measures([source], root / "numbered")

            self.assertEqual(count, 3)
            with Image.open(outputs[0]).convert("L") as numbered:
                label_band = np.asarray(numbered)[0:24]
                self.assertGreater(np.count_nonzero(label_band < 180), 0)

    def test_measure_barlines_are_detected_from_staff_spanning_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "staff.png"
            image = Image.new("RGB", (240, 90), "white")
            draw = ImageDraw.Draw(image)
            for y in (20, 30, 40, 50):
                draw.line((0, y, 239, y), fill=(140, 140, 140), width=2)
            for x in (40, 100, 160, 220):
                draw.line((x, 19, x, 52), fill="black", width=2)
            # A note stem that does not span the whole staff is not a barline.
            draw.line((75, 31, 75, 55), fill="black", width=2)
            image.save(path)

            positions = detect_measure_barlines(path)

            self.assertEqual(len(positions), 4)
            for actual, expected in zip(positions, (40, 100, 160, 220)):
                self.assertAlmostEqual(actual, expected, delta=2)

    def test_short_edge_overlaps_are_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            left = root / "left.png"
            right = root / "right.png"
            panorama = Image.new("RGB", (240, 70), "white")
            draw = ImageDraw.Draw(panorama)
            for index, x in enumerate(range(10, 231, 22)):
                top = 5 + (index * 7) % 25
                bottom = 62 - (index * 5) % 18
                draw.rectangle((x, top, x + 4 + index % 4, bottom), fill="black")
                draw.text((x + 7, 18 + index % 3 * 9), chr(65 + index), fill="black")
            panorama.crop((0, 0, 140, 70)).save(left)
            panorama.crop((100, 0, 240, 70)).save(right)

            overlap = estimate_score_edge_overlap(left, right)
            self.assertIsNotNone(overlap)
            self.assertAlmostEqual(overlap[0], 40, delta=2)
            outputs, stitched = stitch_edge_overlap_runs([left, right], root / "output")
            self.assertEqual(stitched, 1)
            self.assertEqual(len(outputs), 2)
            with Image.open(outputs[1]).convert("L") as second:
                # A safety margin remains, so uncertain edge content is retained.
                self.assertGreater(np.count_nonzero(np.asarray(second) < 180), 0)

    def test_horizontal_scroll_is_stitched_without_duplicate_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            panorama = Image.new("RGB", (260, 70), "white")
            draw = ImageDraw.Draw(panorama)
            for x in (20, 65, 110, 155, 200, 245):
                draw.rectangle((x, 10, x + 8, 60), fill="black")
                draw.text((x + 12, 25), str(x), fill="black")
            frames = []
            for index, x in enumerate((0, 70, 140)):
                path = root / f"scroll_{index}.png"
                panorama.crop((x, 0, x + 120, 70)).save(path)
                frames.append(path)

            estimate = estimate_horizontal_scroll(frames[0], frames[1])
            self.assertIsNotNone(estimate)
            self.assertAlmostEqual(estimate[0], 70, delta=2)

            outputs, collapsed, stitched = reconstruct_scrolling_score(frames, root / "stitched")

            self.assertEqual(stitched, 1)
            self.assertGreaterEqual(collapsed, 0)
            self.assertEqual(len(outputs), 2)
            for path in outputs:
                with Image.open(path) as image:
                    self.assertEqual(image.size, (120, 70))

    def test_vertical_cursor_cleanup_preserves_dark_notation(self):
        gray = np.full((100, 80), 255, dtype=np.uint8)
        gray[:, 30:32] = 185
        gray[20:80, 55:57] = 20
        gray[45:48, :] = 90

        cleaned = remove_vertical_playback_cursor(gray)

        self.assertTrue(np.all(cleaned[:45, 30:32] == 255))
        self.assertTrue(np.all(cleaned[48:, 30:32] == 255))
        self.assertTrue(np.all(cleaned[20:45, 55:57] == 20))
        self.assertTrue(np.all(cleaned[48:80, 55:57] == 20))
        self.assertTrue(np.all(cleaned[45:48, :30] == 90))

    def test_overlay_cleanup_combines_moving_highlights_and_cursor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = []
            for index, highlight_x in enumerate((10, 70, 130)):
                image = Image.new("RGB", (180, 80), "white")
                draw = ImageDraw.Draw(image)
                draw.line((0, 30, 179, 30), fill="black", width=2)
                draw.rectangle((80, 15, 95, 55), fill="black")
                overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
                overlay_draw = ImageDraw.Draw(overlay)
                overlay_draw.rectangle((highlight_x, 0, highlight_x + 45, 79), fill=(255, 230, 0, 80))
                overlay_draw.line((highlight_x + 20, 0, highlight_x + 20, 79), fill=(20, 150, 220, 180), width=2)
                image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
                path = root / f"source_{index}.png"
                image.save(path)
                frames.append(path)

            cleaned, collapsed = clean_score_overlays(frames, root / "cleaned")

            self.assertEqual(len(cleaned), 1)
            self.assertEqual(collapsed, 2)
            with Image.open(cleaned[0]).convert("RGB") as result:
                self.assertEqual(result.getpixel((20, 10)), (255, 255, 255))
                self.assertLess(result.getpixel((85, 25))[0], 20)
                self.assertLess(result.getpixel((30, 30))[0], 20)

    def test_overlay_cleanup_removes_video_showing_through_translucent_score(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = []
            for index in range(6):
                background = Image.new("L", (240, 90), 205)
                background_draw = ImageDraw.Draw(background)
                background_draw.rectangle(
                    (index * 28 - 35, 0, index * 28 + 65, 89),
                    fill=55 + index * 18,
                )
                score = Image.new("L", background.size, 255)
                draw = ImageDraw.Draw(score)
                for y in (32, 38, 44, 50, 56):
                    draw.line((12, y, 225, y), fill=0, width=1)
                draw.ellipse((105, 37, 117, 46), fill=0)
                draw.line((116, 20, 116, 42), fill=0, width=2)
                draw.line((35, 18, 58, 72), fill=90, width=1)
                translucent = Image.blend(background, score, 0.72).convert("RGB")
                path = root / f"source_{index}.png"
                translucent.save(path)
                frames.append(path)

            cleaned, collapsed = clean_score_overlays(frames, root / "cleaned")

            self.assertEqual(len(cleaned), 1)
            self.assertEqual(collapsed, 5)
            with Image.open(cleaned[0]).convert("L") as result:
                self.assertEqual(result.getpixel((70, 12)), 255)
                self.assertEqual(result.getpixel((70, 44)), 0)
                self.assertEqual(result.getpixel((111, 41)), 0)
                self.assertGreater(float(np.mean(np.asarray(result) == 255)), 0.90)
                tones = np.asarray(result)
                self.assertTrue(np.any((tones > 0) & (tones < 255)))

    def test_score_view_grouping_keeps_different_notation_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frames = []
            for index, x in enumerate((15, 135)):
                image = Image.new("RGB", (180, 80), "white")
                draw = ImageDraw.Draw(image)
                draw.rectangle((x, 5, x + 30, 70), fill="black")
                path = root / f"view_{index}.png"
                image.save(path)
                frames.append(path)

            self.assertEqual(len(group_score_views(frames)), 2)

    def test_a4_adds_song_title_to_every_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frame_dir = root / "frames"
            frame_dir.mkdir()
            frames = []
            for index in range(3):
                frame = frame_dir / f"frame_{index}.png"
                Image.new("RGB", (100, 120), "white").save(frame)
                frames.append(frame)

            outputs = write_a4_pngs(frames, root / "a4", "Test Score", "test")

            self.assertGreater(len(outputs), 1)
            with Image.open(outputs[1]) as second_page:
                self.assertGreaterEqual(second_page.width, 200)
                header = second_page.crop((0, 0, second_page.width, 80))
                colors = header.convert("L").getcolors(maxcolors=256)
                non_white_pixels = sum(count for count, value in colors if value < 250)

            self.assertGreater(non_white_pixels, 0)

    def test_a3_2up_places_two_a4_pages_side_by_side(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            frame_dir = root / "frames"
            frame_dir.mkdir()
            frames = []
            for index, color in enumerate(("red", "green", "blue"), start=1):
                frame = frame_dir / f"frame_{index}.png"
                Image.new("RGB", (100, 120), color).save(frame)
                frames.append(frame)

            a4_outputs = write_a4_pngs(frames, root / "a4", "Test Score", "test")
            a3_outputs = write_a3_2up_pngs(frames, root / "a3", "Test Score", "test")

            self.assertEqual(len(a4_outputs), 3)
            self.assertEqual(len(a3_outputs), 2)
            with Image.open(a4_outputs[0]) as a4_page, Image.open(a3_outputs[0]) as a3_page:
                self.assertEqual(a3_page.size, (a4_page.width * 2, a4_page.height))

    def test_trim_frame_edges_removes_start_and_end_frames(self):
        frames = [Path(f"frame_{index}.png") for index in range(5)]

        trimmed = trim_frame_edges(frames, trim_start=1, trim_end=2)

        self.assertEqual(trimmed, frames[1:3])

    def test_trim_frame_edges_requires_at_least_one_frame(self):
        frames = [Path("frame_1.png"), Path("frame_2.png")]

        with self.assertRaises(ValueError):
            trim_frame_edges(frames, trim_start=1, trim_end=1)


if __name__ == "__main__":
    unittest.main()
