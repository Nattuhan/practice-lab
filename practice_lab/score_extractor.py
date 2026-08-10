import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import numpy as np
import cv2
from PIL import Image, ImageChops, ImageOps, ImageStat

from .config import DATA_AUDIO_DIR, DATA_RESULTS_DIR, DATA_SCORE_DIR, PUBLIC_SCORE_DIR

MAX_OUTPUT_HEIGHT = 30000
A4_RATIO = 297 / 210
PRINT_PAGE_SCALE = 2
BOLD_FONT_CANDIDATES = [
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
    Path("/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"),
    Path(r"C:\Windows\Fonts\NotoSansJP-VF.ttf"),
    Path(r"C:\Windows\Fonts\YuGothB.ttc"),
    Path(r"C:\Windows\Fonts\BIZ-UDGothicB.ttc"),
    Path(r"C:\Windows\Fonts\meiryob.ttc"),
]
FONT_CANDIDATES = [
    Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
    Path("/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"),
    Path(r"C:\Windows\Fonts\NotoSansJP-VF.ttf"),
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"C:\Windows\Fonts\YuGothR.ttc"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\msgothic.ttc"),
    Path("arial.ttf"),
]
PRINT_TEXT_COLOR = (0, 0, 0)
_OCR_ENGINE = None
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_KEY_PROFILE = np.asarray((6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88))
MINOR_KEY_PROFILE = np.asarray((6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17))


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=True)


def extract_video_id(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        if parsed.hostname == "youtu.be":
            return parsed.path.lstrip("/").split("?")[0]
        if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
            return parse_qs(parsed.query).get("v", [None])[0]
    except Exception:
        return None
    return None


def make_score_id(url: str) -> str:
    return extract_video_id(url) or f"score-{int(time.time())}"


def yt_dlp_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", *args]


def yt_dlp_error(stderr: str, fallback: str) -> str:
    message = (stderr or fallback).strip()
    if "HTTP Error 403" in message or "Forbidden" in message:
        return f"{message}\n\nYouTube returned 403. yt-dlp was updated locally; retry the job. If it still fails, the video may require browser cookies or may be temporarily blocked by YouTube."
    return message


def download_source_video(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            yt_dlp_command(
                "-f",
                "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
                "--merge-output-format",
                "mp4",
                "-o",
                os.path.join(temp_dir, "source.%(ext)s"),
                "--no-playlist",
                "--js-runtimes",
                "node",
                url,
            ),
            capture_output=True,
            text=True,
            timeout=240,
        )
        if result.returncode != 0:
            raise RuntimeError(yt_dlp_error(result.stderr, "yt-dlp video download failed"))
        files = list(Path(temp_dir).glob("*.mp4"))
        if not files:
            raise RuntimeError("mp4 not found")
        shutil.move(str(files[0]), str(destination))


def get_video_title(url: str, fallback: str) -> str:
    result = subprocess.run(
        yt_dlp_command(
            "--encoding", "utf-8", "--print", "title", "--no-playlist", "--js-runtimes", "node", url
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return unicodedata.normalize("NFC", result.stdout.strip()) or fallback


def probe_video(path: Path) -> dict:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "durationSec": float(payload.get("format", {}).get("duration") or 0),
    }


def resolve_score_time_range(video: dict, payload: dict) -> tuple[float, float]:
    """Resolve an optional extraction range, defaulting to the full video."""
    duration = float(video.get("durationSec") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("動画の長さを取得できませんでした")

    raw_start = payload.get("startSec")
    raw_end = payload.get("endSec")
    start = 0.0 if raw_start is None else float(raw_start)
    end = duration if raw_end is None else min(float(raw_end), duration)
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < 0:
        raise ValueError("抽出時間には0以上の数値を指定してください")
    if start >= duration:
        raise ValueError("開始時間は動画の長さより前にしてください")
    if end <= start:
        raise ValueError("終了時間は開始時間より後にしてください")
    return start, end


def resolve_musical_output_options(payload: dict) -> tuple[bool, bool, bool]:
    """Resolve independent print toggles with legacy all-in-one compatibility."""
    legacy = bool(payload.get("showMusicalAnalysis", True))

    def selected(key: str) -> bool:
        value = payload.get(key)
        return legacy if value is None else bool(value)

    return selected("showChordSymbols"), selected("showKeyEstimate"), selected("showBpm")


def infer_key_from_pitch_histogram(pitch_histogram: np.ndarray) -> dict:
    """Infer a key from pitches decoded directly from TAB fret images."""
    energy = np.asarray(pitch_histogram, dtype=np.float64).reshape(12)
    if float(energy.sum()) <= 0:
        return {"key": None, "scale": None, "confidence": 0.0}
    energy = energy / energy.sum()
    candidates: list[tuple[float, int, str]] = []
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_KEY_PROFILE), ("minor", MINOR_KEY_PROFILE)):
            shifted = np.roll(profile, tonic)
            score = float(np.corrcoef(energy, shifted)[0, 1])
            candidates.append((score, tonic, mode))
    candidates.sort(reverse=True)
    best, second = candidates[0], candidates[1]
    _score, tonic, mode = best
    key = f"{NOTE_NAMES[tonic]} {'Major' if mode == 'major' else 'Minor'}"
    if mode == "major":
        relative = f"{NOTE_NAMES[(tonic + 9) % 12]} Natural Minor"
        scale = f"{NOTE_NAMES[tonic]} Major / {relative}"
    else:
        relative = f"{NOTE_NAMES[(tonic + 3) % 12]} Major"
        scale = f"{NOTE_NAMES[tonic]} Natural Minor / {relative}"
    confidence = max(0.0, min(1.0, 0.5 + (best[0] - second[0]) * 1.8))
    return {
        "key": key, "scale": scale, "confidence": round(confidence, 3),
        "tonic": tonic, "mode": mode,
    }


def format_estimated_key_summary(analysis: dict) -> str | None:
    """Format the image-derived key estimate for a Japanese printed score."""
    tonic = analysis.get("tonic")
    mode = analysis.get("mode")
    if not isinstance(tonic, int) or tonic not in range(12) or mode not in {"major", "minor"}:
        return None
    if mode == "major":
        primary = f"{NOTE_NAMES[tonic]}メジャー"
        relative = f"{NOTE_NAMES[(tonic + 9) % 12]}マイナー"
    else:
        primary = f"{NOTE_NAMES[tonic]}マイナー"
        relative = f"{NOTE_NAMES[(tonic + 3) % 12]}メジャー"
    return f"推定キー：{primary} / {relative}"


CHORD_NOTE_PITCH_CLASSES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}
ROMAN_DEGREES = (
    "I", "♭II", "II", "♭III", "III", "IV",
    "♭V", "V", "♭VI", "VI", "♭VII", "VII",
)


def chord_degree_label(chord: str, tonic: int) -> str | None:
    """Return a concise Roman-numeral degree for a printed chord symbol."""
    match = re.fullmatch(r"([A-G](?:#|b)?)([^/]*)?(?:/[A-G](?:#|b)?)?", chord)
    if not match or match.group(1) not in CHORD_NOTE_PITCH_CLASSES:
        return None
    root, suffix = match.group(1), match.group(2) or ""
    degree = ROMAN_DEGREES[(CHORD_NOTE_PITCH_CLASSES[root] - tonic) % 12]
    accidental = degree[:-len(degree.lstrip("♭#"))]
    numeral = degree[len(accidental):]
    is_minor = suffix.startswith("m") and not suffix.startswith("maj")
    if is_minor or suffix.startswith("dim"):
        numeral = numeral.lower()
    if suffix.startswith("dim"):
        numeral += "°"
    elif suffix.startswith("aug"):
        numeral += "+"
    return accidental + numeral


def _load_existing_timing(video_id: str) -> dict:
    result_path = DATA_RESULTS_DIR / f"{video_id}.json"
    if not result_path.exists():
        return {}
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_tab_string_lines(image: Image.Image) -> list[int]:
    """Locate the lowest regular six-line guitar TAB staff in a score row."""
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    density = np.mean(gray < 210, axis=1)
    dense_rows = np.where(density >= 0.32)[0]
    groups: list[list[int]] = []
    for row in dense_rows:
        row = int(row)
        if not groups or row > groups[-1][-1] + 1:
            groups.append([row])
        else:
            groups[-1].append(row)
    centers = [round(sum(group) / len(group)) for group in groups if len(group) <= 5]
    candidates: list[list[int]] = []
    for start in range(len(centers) - 5):
        candidate = centers[start:start + 6]
        gaps = np.diff(candidate)
        if np.all((gaps >= 7) & (gaps <= 36)) and float(gaps.max() / gaps.min()) <= 1.35:
            candidates.append(candidate)
    return candidates[-1] if candidates else []


TAB_CHORD_TEMPLATES = (
    ("", (0, 4, 7)), ("m", (0, 3, 7)), ("5", (0, 7)),
    ("sus2", (0, 2, 7)), ("sus4", (0, 5, 7)),
    ("dim", (0, 3, 6)), ("aug", (0, 4, 8)),
    ("7", (0, 4, 7, 10)), ("maj7", (0, 4, 7, 11)), ("m7", (0, 3, 7, 10)),
)
STANDARD_GUITAR_TUNING_MIDI = (64, 59, 55, 50, 45, 40)


def infer_chord_from_frets(frets: dict[int, int]) -> tuple[str | None, float, list[int]]:
    """Infer one chord from visually read top-to-bottom guitar string frets."""
    if len(frets) < 2:
        return None, 0.0, []
    midi_notes = [STANDARD_GUITAR_TUNING_MIDI[string] + fret for string, fret in frets.items()]
    pitch_classes = {note % 12 for note in midi_notes}
    if len(pitch_classes) < 2:
        return None, 0.0, midi_notes
    candidates: list[tuple[float, int, str]] = []
    bass = min(midi_notes) % 12
    for root in range(12):
        for suffix, intervals in TAB_CHORD_TEMPLATES:
            target = {(root + interval) % 12 for interval in intervals}
            missing = len(target - pitch_classes)
            extra = len(pitch_classes - target)
            root_penalty = 0 if root in pitch_classes else 1
            # A missed open-string digit can leave G major and Baug/G with the
            # same pitch-class score. Prefer the common root-position reading;
            # inversions still win when all of their chord tones are present.
            bass_penalty = 0.0 if root == bass else 0.14
            uncommon_penalty = 0.18 if suffix == "aug" else (0.10 if suffix == "dim" else 0.0)
            score = (
                missing * 1.0 + extra * 0.28 + root_penalty * 0.45
                + max(0, len(target) - 3) * 0.04 + bass_penalty + uncommon_penalty
            )
            candidates.append((score, len(target), f"{NOTE_NAMES[root]}{suffix}"))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    score, _size, label = candidates[0]
    root_name = re.match(r"^[A-G]#?", label)
    root = NOTE_NAMES.index(root_name.group(0)) if root_name else -1
    if bass != root and bass in pitch_classes and not label.endswith("5"):
        label = f"{label}/{NOTE_NAMES[bass]}"
    confidence = max(0.0, min(1.0, 1.0 - score * 0.22))
    return label, confidence, midi_notes


def _tab_digit_columns(gray: np.ndarray, lines: list[int], left: int, right: int) -> list[tuple[int, int]]:
    gap = round(float(np.median(np.diff(lines))))
    radius = max(7, round(gap * 0.42))
    signal = np.zeros(gray.shape[1], dtype=np.int16)
    for y in lines:
        band = gray[max(0, y - radius):min(gray.shape[0], y + radius + 1), :]
        signal = np.maximum(signal, np.count_nonzero(band < 165, axis=0))
    xs = np.where((signal >= 4) & (np.arange(gray.shape[1]) >= left) & (np.arange(gray.shape[1]) <= right))[0]
    groups: list[list[int]] = []
    for x in xs:
        x = int(x)
        if not groups or x > groups[-1][-1] + 5:
            groups.append([x])
        else:
            groups[-1].append(x)
    return [(group[0], group[-1]) for group in groups if group[-1] - group[0] >= 4]


def read_tab_measure_chord_events(
    image: Image.Image, lines: list[int], left: int, right: int
) -> tuple[list[dict[str, str | float]], np.ndarray, float]:
    global _OCR_ENGINE
    from rapidocr_onnxruntime import RapidOCR

    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    rgb = image.convert("RGB")
    gray = np.asarray(rgb.convert("L"), dtype=np.uint8)
    gap = round(float(np.median(np.diff(lines))))
    radius_y = max(8, round(gap * 0.48))
    events: list[dict[str, str | float]] = []
    pitch_histogram = np.zeros(12, dtype=np.float64)
    confidences: list[float] = []
    for column_left, column_right in _tab_digit_columns(gray, lines, left, right):
        frets: dict[int, int] = {}
        ocr_confidences: list[float] = []
        for string_index, y in enumerate(lines):
            crop_left = max(left, column_left - 4)
            crop_right = min(right + 1, column_right + 5)
            crop = rgb.crop((crop_left, max(0, y - radius_y), crop_right, min(rgb.height, y + radius_y + 1)))
            target_height = 126
            target_width = max(48, round(crop.width * target_height / max(1, crop.height)))
            crop = crop.resize((target_width, target_height), Image.Resampling.BICUBIC)
            result, _elapsed = _OCR_ENGINE(
                np.asarray(crop, dtype=np.uint8), use_det=False, use_cls=False, use_rec=True
            )
            crop.close()
            if not result:
                continue
            text = str(result[0][0]).strip()
            confidence = float(result[0][1])
            if confidence >= 0.30 and re.fullmatch(r"\d{1,2}", text):
                fret = int(text)
                if 0 <= fret <= 30:
                    frets[string_index] = fret
                    ocr_confidences.append(confidence)
        label, chord_confidence, midi_notes = infer_chord_from_frets(frets)
        combined_confidence = chord_confidence * (float(np.mean(ocr_confidences)) if ocr_confidences else 0)
        if label and combined_confidence >= 0.42:
            if not events or events[-1]["label"] != label:
                events.append({
                    "label": label,
                    "position": round(
                        max(0.0, min(1.0, (column_left - left) / max(1, right - left))), 4
                    ),
                })
            for note in midi_notes:
                pitch_histogram[note % 12] += 1
            confidences.append(combined_confidence)
    rgb.close()
    return events[:4], pitch_histogram, (float(np.mean(confidences)) if confidences else 0.0)


def read_tab_measure_chords(
    image: Image.Image, lines: list[int], left: int, right: int
) -> tuple[list[str], np.ndarray, float]:
    """Compatibility wrapper returning chord names without their TAB positions."""
    events, histogram, confidence = read_tab_measure_chord_events(image, lines, left, right)
    return [str(event["label"]) for event in events], histogram, confidence


def score_row_layouts(
    score_frames: list[Path], *, measure_count: int, measures_per_row: int,
    processing_mode: str, audit_path: Path | None = None,
) -> list[tuple[int, list[int]]]:
    if processing_mode == "simple" and audit_path and audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            rows = [
                (int(row["firstMeasure"]) - 1, [int(value) for value in row["boundaries"]])
                for row in audit.get("frames", [])
                if row.get("firstMeasure") is not None and len(row.get("boundaries", [])) >= 2
            ]
            if len(rows) == len(score_frames):
                return rows
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    layouts: list[tuple[int, list[int]]] = []
    measure_index = 0
    for frame in score_frames:
        if measure_index >= measure_count:
            break
        with Image.open(frame) as image:
            width = image.width
        if processing_mode == "auto":
            count = min(measures_per_row, measure_count - measure_index)
            boundaries = [round(width * index / count) for index in range(count + 1)]
        else:
            detected = complete_score_system_boundaries(frame)
            boundaries = detected if len(detected) >= 2 else [0, width]
            count = min(len(boundaries) - 1, measure_count - measure_index)
            boundaries = boundaries[:count + 1]
        layouts.append((measure_index, boundaries))
        measure_index += len(boundaries) - 1
    return layouts


def analyze_tab_harmony(
    score_frames: list[Path], *, measure_count: int, measures_per_row: int,
    processing_mode: str, audit_path: Path | None = None,
) -> dict:
    chords_by_measure: list[list[str]] = [[] for _ in range(measure_count)]
    chord_events_by_measure: list[list[dict[str, str | float]]] = [
        [] for _ in range(measure_count)
    ]
    pitch_histogram = np.zeros(12, dtype=np.float64)
    measure_confidences: list[float] = [0.0 for _ in range(measure_count)]
    layouts = score_row_layouts(
        score_frames, measure_count=measure_count, measures_per_row=measures_per_row,
        processing_mode=processing_mode, audit_path=audit_path,
    )
    for frame, (first_measure, boundaries) in zip(score_frames, layouts):
        with Image.open(frame) as source:
            image = source.convert("RGB")
        lines = detect_tab_string_lines(image)
        if not lines:
            image.close()
            continue
        count = min(len(boundaries) - 1, measure_count - first_measure)
        for index in range(count):
            events, histogram, confidence = read_tab_measure_chord_events(
                image, lines, boundaries[index], boundaries[index + 1]
            )
            labels = [str(event["label"]) for event in events]
            chords_by_measure[first_measure + index] = labels
            chord_events_by_measure[first_measure + index] = events
            pitch_histogram += histogram
            measure_confidences[first_measure + index] = confidence
        image.close()
    key_info = infer_key_from_pitch_histogram(pitch_histogram)
    tonic = key_info.get("tonic")
    if isinstance(tonic, int):
        for events in chord_events_by_measure:
            for event in events:
                degree = chord_degree_label(str(event["label"]), tonic)
                if degree:
                    event["degree"] = degree
    return {
        **key_info,
        "chordsByMeasure": chords_by_measure,
        "chordEventsByMeasure": chord_events_by_measure,
        "analyzedMeasures": sum(bool(labels) for labels in chords_by_measure),
        "averageChordConfidence": round(float(np.mean([v for v in measure_confidences if v > 0])), 3)
        if any(value > 0 for value in measure_confidences) else 0.0,
        "harmonySource": "tab-image",
    }


def resolve_score_bpm(
    video_id: str, video_path: Path, *, start_sec: float, end_sec: float
) -> tuple[float | None, str]:
    timing = _load_existing_timing(video_id)
    if float(timing.get("bpm") or 0) > 0:
        return round(float(timing["bpm"]), 1), "existing-analysis"
    import librosa
    source_audio = DATA_AUDIO_DIR / f"{video_id}.wav"
    offset = start_sec
    if not source_audio.exists():
        source_audio = DATA_SCORE_DIR / video_id / "tempo-audio.wav"
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start_sec:.6f}",
            "-t", f"{end_sec - start_sec:.6f}", "-i", str(video_path), "-vn",
            "-ac", "1", "-ar", "22050", str(source_audio), "-y",
        ])
        offset = 0.0
    y, sample_rate = librosa.load(
        source_audio, sr=22050, mono=True, offset=offset, duration=end_sec - start_sec
    )
    tempo, _beats = librosa.beat.beat_track(y=y, sr=sample_rate)
    return round(float(np.asarray(tempo).reshape(-1)[0]), 1), "audio-tempo-estimate"


def analyze_score_harmony(
    video_id: str, video_path: Path, score_frames: list[Path], *, start_sec: float,
    end_sec: float, measure_count: int, measures_per_row: int, processing_mode: str,
    audit_path: Path | None = None,
) -> dict:
    analysis = analyze_tab_harmony(
        score_frames, measure_count=measure_count, measures_per_row=measures_per_row,
        processing_mode=processing_mode, audit_path=audit_path,
    )
    bpm, bpm_source = resolve_score_bpm(
        video_id, video_path, start_sec=start_sec, end_sec=end_sec
    )
    analysis["bpm"] = bpm
    analysis["bpmSource"] = bpm_source
    return analysis


def resolve_region(video: dict, payload: dict) -> dict:
    width = int(video["width"])
    height = int(video["height"])
    custom = payload.get("region")
    if custom:
        x = max(0, min(width - 1, int(custom["x"])))
        y = max(0, min(height - 1, int(custom["y"])))
        crop_width = max(1, min(width - x, int(custom["width"])))
        crop_height = max(1, min(height - y, int(custom["height"])))
        return {"x": x, "y": y, "width": crop_width, "height": crop_height}

    percent = max(5, min(90, float(payload.get("regionPercent", 30)))) / 100
    crop_height = max(1, round(height * percent))
    preset = str(payload.get("regionPreset", "bottom")).lower()
    y = 0 if preset == "top" else height - crop_height
    return {"x": 0, "y": y, "width": width, "height": crop_height}


def extract_crops(video_path: Path, crop_dir: Path, region: dict, interval_sec: float) -> list[Path]:
    crop_dir.mkdir(parents=True, exist_ok=True)
    fps = 1 / max(0.1, min(10, interval_sec))
    filter_expr = (
        f"fps={fps:.6f},"
        f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']}"
    )
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-vf",
            filter_expr,
            str(crop_dir / "frame_%06d.png"),
            "-y",
        ]
    )
    extracted = sorted(crop_dir.glob("frame_*.png"))
    temporary_names: list[tuple[Path, int]] = []
    for sequence, (path, scan_index) in enumerate(zip(extracted, indexes), start=1):
        temporary = crop_dir / f"selected_{sequence:06d}.png"
        path.rename(temporary)
        temporary_names.append((temporary, scan_index))
    for temporary, scan_index in temporary_names:
        temporary.rename(crop_dir / f"frame_{scan_index + 1:06d}.png")
    return sorted(crop_dir.glob("frame_*.png"))


def scan_score_views(
    video_path: Path, scan_dir: Path, region: dict, *, scan_interval_sec: float = 0.5,
    samples_per_view: int = 3, minimum_stable_samples: int = 3,
    start_sec: float = 0, end_sec: float | None = None,
) -> tuple[list[int], float, int, int]:
    """Return representatives only from views stable across consecutive scans."""
    scan_dir.mkdir(parents=True, exist_ok=True)
    scan_fps = 1.0 / scan_interval_sec
    preview_width = min(384, region["width"])
    filter_expr = (
        f"fps={scan_fps:.6f},"
        f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']},"
        f"scale={preview_width}:-1,format=gray"
    )
    input_args = ["-ss", f"{start_sec:.6f}"] if start_sec > 0 else []
    if end_sec is not None:
        input_args.extend(["-t", f"{end_sec - start_sec:.6f}"])
    _run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", *input_args, "-i", str(video_path),
            "-vf", filter_expr, str(scan_dir / "frame_%06d.pgm"), "-y",
        ]
    )
    scan_frames = sorted(scan_dir.glob("frame_*.pgm"))
    groups = group_score_views(scan_frames)
    selected: list[int] = []
    rejected_transition_frames = 0
    for group_index, group in enumerate(groups):
        if len(group) < minimum_stable_samples:
            previous = groups[group_index - 1][-1] if group_index > 0 else None
            following = groups[group_index + 1][0] if group_index + 1 < len(groups) else None
            incoming_motion = estimate_horizontal_scroll(previous, group[0]) if previous else None
            outgoing_motion = estimate_horizontal_scroll(group[-1], following) if following else None
            # Duration alone cannot distinguish a brief valid score view from an
            # animation frame. Reject it only when it geometrically lies on a
            # continuous horizontal pan between both neighboring views.
            if incoming_motion is not None and outgoing_motion is not None:
                rejected_transition_frames += len(group)
                continue
        for path in evenly_spaced_paths(group, samples_per_view):
            selected.append(int(path.stem.rsplit("_", 1)[-1]) - 1)
    return sorted(set(selected)), scan_fps, len(scan_frames), rejected_transition_frames


def extract_crops_at_scan_indexes(
    video_path: Path, crop_dir: Path, region: dict, scan_fps: float, indexes: list[int], *,
    start_sec: float = 0, end_sec: float | None = None,
) -> list[Path]:
    """Decode the source once and retain only adaptive-scan representative frames."""
    if not indexes:
        return []
    crop_dir.mkdir(parents=True, exist_ok=True)
    selected = "+".join(f"eq(n\\,{index})" for index in indexes)
    filter_expr = (
        f"fps={scan_fps:.6f},select={selected},"
        f"crop={region['width']}:{region['height']}:{region['x']}:{region['y']}"
    )
    input_args = ["-ss", f"{start_sec:.6f}"] if start_sec > 0 else []
    if end_sec is not None:
        input_args.extend(["-t", f"{end_sec - start_sec:.6f}"])
    _run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", *input_args, "-i", str(video_path),
            "-vf", filter_expr, "-vsync", "vfr", str(crop_dir / "frame_%06d.png"), "-y",
        ]
    )
    return sorted(crop_dir.glob("frame_*.png"))


def score_structure_signature(path: Path, *, width: int = 256) -> np.ndarray:
    """Return a color-insensitive mask used to recognize the same score view."""
    with Image.open(path) as source:
        gray = ImageOps.grayscale(source)
        height = max(32, round(gray.height * width / max(1, gray.width)))
        preview = gray.resize((width, height), Image.Resampling.BILINEAR)
        normalized = ImageOps.autocontrast(preview, cutoff=1)
        return np.asarray(normalized, dtype=np.uint8) < 175


def overlay_invariant_score_signature(path: Path, *, width: int = 256) -> np.ndarray:
    """Preserve notation while ignoring colored overlays and moving video beneath it."""
    with Image.open(path) as source:
        rgb = source.convert("RGB")
        height = max(32, round(rgb.height * width / max(1, rgb.width)))
        preview = np.asarray(rgb.resize((width, height), Image.Resampling.BILINEAR), dtype=np.uint8)
    # A bright channel suppresses colored highlights/cursors before local
    # normalization removes the changing video visible through the score.
    brightest_channel = preview.max(axis=2)
    if float(np.mean(brightest_channel < 230)) > 0.25:
        normalized = normalize_translucent_score_background(brightest_channel, sigma=3.0)
        return normalized < 165
    return brightest_channel < 190


def group_score_views(frames: list[Path], *, difference_threshold: float = 0.02) -> list[list[Path]]:
    """Group consecutive frames whose notation is unchanged apart from overlays."""
    if not frames:
        return []

    groups: list[list[Path]] = [[frames[0]]]
    reference = overlay_invariant_score_signature(frames[0])
    for frame in frames[1:]:
        signature = overlay_invariant_score_signature(frame)
        difference = float(np.mean(reference != signature)) if signature.shape == reference.shape else 1.0
        if difference <= difference_threshold:
            groups[-1].append(frame)
        else:
            groups.append([frame])
            reference = signature
    return groups


def evenly_spaced_paths(paths: list[Path], limit: int) -> list[Path]:
    if len(paths) <= limit:
        return paths
    indexes = np.linspace(0, len(paths) - 1, num=limit, dtype=int)
    return [paths[int(index)] for index in indexes]


def remove_vertical_playback_cursor(gray: np.ndarray) -> np.ndarray:
    """Remove tall, faint cursor columns while preserving black score notation."""
    height, width = gray.shape
    if height < 20 or width < 3:
        return gray

    # A playback cursor crosses a large part of the crop. Staff lines and bar
    # lines are either horizontal or much shorter, and true notation is darker.
    midtone = (gray >= 105) & (gray <= 245)
    candidates = np.count_nonzero(midtone, axis=0) >= max(20, round(height * 0.70))
    cleaned = gray.copy()
    start = 0
    while start < width:
        if not candidates[start]:
            start += 1
            continue
        end = start + 1
        while end < width and candidates[end]:
            end += 1
        # Cursors are narrow. A broad gray region is probably real content.
        if end - start <= 8:
            left = max(0, start - 1)
            right = min(width, end + 1)
            region = cleaned[:, left:right]
            region[region >= 105] = 255
        start = end
    return cleaned


def normalize_translucent_score_background(gray: np.ndarray, *, sigma: float) -> np.ndarray:
    """Flatten locally varying video luminance beneath a translucent score layer."""
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma)
    return cv2.divide(gray, np.maximum(background, 1), scale=255)


def compose_overlay_free_frame(frames: list[Path], output_path: Path, *, max_samples: int = 9) -> None:
    """Reconstruct a printable score while suppressing overlays and underlying video."""
    samples = evenly_spaced_paths(frames, max_samples)
    arrays: list[np.ndarray] = []
    expected_size: tuple[int, int] | None = None
    for path in samples:
        with Image.open(path) as source:
            rgb = source.convert("RGB")
            if expected_size is None:
                expected_size = rgb.size
            if rgb.size != expected_size:
                rgb = rgb.resize(expected_size, Image.Resampling.BILINEAR)
            gray = np.asarray(ImageOps.grayscale(rgb), dtype=np.uint8)
            sigma = max(7.0, min(20.0, gray.shape[1] / 85.0))
            arrays.append(normalize_translucent_score_background(gray, sigma=sigma))

    # Real notation remains at the same position, while the video, highlights and
    # playback cursor change between frames. A high temporal percentile therefore
    # keeps the stable ink and rejects the moving material beneath/above the score.
    combined = np.percentile(np.stack(arrays, axis=0), 90, axis=0)
    # Preserve a narrow antialiased edge around the stable notation. A hard
    # black/white threshold makes diagonals, note heads and text visibly jagged
    # once the extracted row is placed on a printable page.
    gray = np.rint(255.0 / (1.0 + np.exp(-(combined - 175.0) / 10.0))).astype(np.uint8)
    gray[combined <= 130] = 0
    gray[combined >= 220] = 255
    gray = remove_vertical_playback_cursor(gray)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(gray, mode="L").convert("RGB").save(output_path)


def clean_score_overlays(frames: list[Path], output_dir: Path) -> tuple[list[Path], int]:
    """Collapse each stable score view into one frame without playback overlays."""
    groups = group_score_views(frames)
    cleaned: list[Path] = []
    for index, group in enumerate(groups, start=1):
        output = output_dir / f"frame_{index:06d}.png"
        compose_overlay_free_frame(group, output)
        cleaned.append(output)
    return cleaned, len(frames) - len(cleaned)


def estimate_horizontal_scroll(left_path: Path, right_path: Path) -> tuple[int, float] | None:
    """Estimate how many source pixels the score viewport moved to the right."""
    with Image.open(left_path) as left_source, Image.open(right_path) as right_source:
        if left_source.size != right_source.size:
            return None
        source_width = left_source.width

    signature_width = min(384, source_width)
    left = score_structure_signature(left_path, width=signature_width)
    right = score_structure_signature(right_path, width=signature_width)
    if left.shape != right.shape:
        return None

    # Long staff/TAB lines match at almost every horizontal offset and can make
    # unrelated measures look identical. Ignore line-dominant rows and align by
    # notes, numbers, stems, and bar lines instead.
    left_row_density = np.mean(left, axis=1)
    right_row_density = np.mean(right, axis=1)
    line_rows = (left_row_density > 0.32) | (right_row_density > 0.32)
    left = left.copy()
    right = right.copy()
    left[line_rows, :] = False
    right[line_rows, :] = False

    def feature_difference(a: np.ndarray, b: np.ndarray) -> float:
        union = np.count_nonzero(a | b)
        if union < max(20, round(a.size * 0.003)):
            return 1.0
        return float(np.count_nonzero(a != b) / union)

    width = left.shape[1]
    min_overlap = max(24, round(width * 0.38))
    max_offset = width - min_overlap
    best_offset = 0
    best_difference = feature_difference(left, right)
    for offset in range(1, max_offset + 1):
        difference = feature_difference(left[:, offset:], right[:, :width - offset])
        if difference < best_difference:
            best_difference = difference
            best_offset = offset

    # True overlap is very close after monochrome normalization. Keeping this
    # strict prevents similar-looking measures on different rows from joining.
    if best_difference > 0.24:
        return None
    source_offset = round(best_offset * source_width / width)
    return source_offset, best_difference


def build_score_panorama(frames: list[Path], offsets: list[int]) -> Image.Image:
    with Image.open(frames[0]) as first:
        frame_width, frame_height = first.size
    positions = [0]
    for offset in offsets:
        positions.append(positions[-1] + offset)
    panorama_width = positions[-1] + frame_width
    canvas = np.full((frame_height, panorama_width, 3), 255, dtype=np.uint8)
    best_chroma = np.full((frame_height, panorama_width), 32767, dtype=np.int16)

    for path, position in zip(frames, positions):
        with Image.open(path) as source:
            rgb = np.asarray(source.convert("RGB"), dtype=np.uint8)
        chroma = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
        target_chroma = best_chroma[:, position:position + frame_width]
        target = canvas[:, position:position + frame_width]
        replace = chroma < target_chroma
        target[replace] = rgb[replace]
        target_chroma[replace] = chroma[replace]

    gray = np.rint(canvas[:, :, 0] * 0.299 + canvas[:, :, 1] * 0.587 + canvas[:, :, 2] * 0.114).astype(np.uint8)
    gray[gray >= 220] = 255
    gray = remove_vertical_playback_cursor(gray)
    return Image.fromarray(gray, mode="L").convert("RGB")


def find_quiet_cut(gray: np.ndarray, start: int, target_width: int) -> int:
    panorama_width = gray.shape[1]
    ideal = min(panorama_width, start + target_width)
    if ideal >= panorama_width:
        return panorama_width
    search_start = min(ideal, start + max(32, round(target_width * 0.82)))
    search_end = min(panorama_width - 1, start + target_width)
    ink = np.count_nonzero(gray < 180, axis=0).astype(np.float32)
    smoothed = np.convolve(ink, np.ones(7, dtype=np.float32), mode="same")
    return int(search_start + np.argmin(smoothed[search_start:search_end + 1]))


def split_score_panorama(panorama: Image.Image, output_dir: Path, frame_width: int, start_index: int) -> list[Path]:
    gray = np.asarray(panorama.convert("L"), dtype=np.uint8)
    panorama_probe = output_dir / ".panorama-probe.png"
    panorama.save(panorama_probe)
    panorama_barlines = detect_measure_barlines(panorama_probe)
    panorama_probe.unlink(missing_ok=True)
    outputs: list[Path] = []
    start = 0
    index = start_index
    piece_count = max(1, round(panorama.width / frame_width))
    for piece_number in range(piece_count):
        remaining_pieces = piece_count - piece_number
        target_width = round((panorama.width - start) / remaining_pieces)
        if remaining_pieces == 1:
            end = panorama.width
        else:
            ideal = min(panorama.width, start + target_width)
            candidates = [
                x for x in panorama_barlines
                if start + round(target_width * 0.65) <= x <= start + round(target_width * 1.08)
            ]
            # Reflow at a verified barline so no measure is split or lost.
            end = min(candidates, key=lambda x: abs(x - ideal)) if candidates else find_quiet_cut(
                gray, start, target_width
            )
        if end <= start:
            end = min(panorama.width, start + target_width)
        piece = panorama.crop((start, 0, end, panorama.height))
        canvas = Image.new("RGB", (frame_width, panorama.height), "white")
        canvas.paste(piece, (max(0, (frame_width - piece.width) // 2), 0))
        output = output_dir / f"frame_{index:06d}.png"
        canvas.save(output)
        outputs.append(output)
        piece.close()
        canvas.close()
        index += 1
        start = end
    return outputs


def detect_staff_horizontal_extent(path: Path) -> tuple[int, int] | None:
    """Return a consistent horizontal start/end shared by TAB/staff lines."""
    with Image.open(path) as source:
        gray = np.asarray(source.convert("L"), dtype=np.uint8)
    dense_rows = np.where(np.mean(gray < 210, axis=1) > 0.25)[0]
    groups: list[list[int]] = []
    for row in dense_rows:
        if not groups or row > groups[-1][-1] + 1:
            groups.append([int(row)])
        else:
            groups[-1].append(int(row))
    centers = [round(sum(group) / len(group)) for group in groups if len(group) <= 4]
    if len(centers) < 4:
        return None
    starts: list[int] = []
    ends: list[int] = []
    for row in centers:
        columns = np.where(gray[row] < 210)[0]
        if columns.size:
            starts.append(int(columns[0]))
            ends.append(int(columns[-1]))
    if len(starts) < 4 or max(starts) - min(starts) > 8 or max(ends) - min(ends) > 8:
        return None
    return round(float(np.median(starts))), round(float(np.median(ends)))


def prepend_visible_staff_start(path: Path, barlines: list[int]) -> list[int]:
    """Treat an inset horizontal staff onset as a valid left measure boundary."""
    extent = detect_staff_horizontal_extent(path)
    if extent is None:
        return barlines
    start, _end = extent
    if start < 12 or (barlines and barlines[0] - start < 60):
        return barlines
    return [start, *barlines]


def create_numberless_edge_bridge(left_path: Path, right_path: Path, output_path: Path) -> Path | None:
    """Join complementary edge fragments across a jump-scrolling score view."""
    left_barlines = remove_spurious_close_barlines(detect_measure_barlines(left_path), {})
    right_barlines = remove_spurious_close_barlines(detect_measure_barlines(right_path), {})
    if len(left_barlines) < 2 or len(right_barlines) < 2:
        return None
    with Image.open(left_path) as left_source, Image.open(right_path) as right_source:
        if left_source.size != right_source.size:
            return None
        frame_width, frame_height = left_source.size
        boundary_padding = 4
        left_extent = detect_staff_horizontal_extent(left_path)
        right_extent = detect_staff_horizontal_extent(right_path)
        left_start = max(0, left_barlines[-1] - boundary_padding)
        left_end = min(frame_width, (left_extent[1] + 1) if left_extent is not None else frame_width)
        right_start = max(0, right_extent[0] if right_extent is not None else 0)
        right_end = min(frame_width, right_barlines[0] + boundary_padding + 1)
        left_tail_width = left_end - left_start
        right_head_width = right_end - right_start
        combined_width = left_tail_width + right_head_width
        if left_tail_width <= boundary_padding or right_head_width <= boundary_padding:
            return None
        internal_widths = [
            right - left
            for barlines in (left_barlines, right_barlines)
            for left, right in zip(barlines, barlines[1:])
            if right - left >= 60
        ]
        if not internal_widths:
            return None
        median_width = float(np.median(internal_widths))
        # A bridge that is implausibly tiny or wider than two neighboring
        # measures signals a hard section cut rather than one clipped measure.
        if not (median_width * 0.35 <= combined_width <= median_width * 2.2):
            return None
        if combined_width > frame_width:
            return None
        left_rgb = left_source.convert("RGB")
        right_rgb = right_source.convert("RGB")
        # Keep pixels on both sides of each detected boundary. Cropping exactly
        # at a one-pixel barline can retain only half of an antialiased line,
        # causing the completed bridge to be rejected as open-ended later.
        left_piece = left_rgb.crop((left_start, 0, left_end, frame_height))
        right_piece = right_rgb.crop((right_start, 0, right_end, frame_height))
        # Keep the bridge at its natural width. Padding it back to a full video
        # frame makes short fragments occupy less than the staff detector's row
        # density threshold, so otherwise-valid closing barlines disappear.
        canvas = Image.new("RGB", (combined_width, frame_height), "white")
        canvas.paste(left_piece, (0, 0))
        canvas.paste(right_piece, (left_piece.width, 0))
        left_piece.close()
        right_piece.close()
        left_rgb.close()
        right_rgb.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    canvas.close()
    return output_path


def reconstruct_scrolling_score(
    frames: list[Path], output_dir: Path, *, force: bool = False
) -> tuple[list[Path], int, int]:
    """Stitch horizontally scrolling runs and clean stationary score views."""
    if not frames:
        return [], 0, 0
    with Image.open(frames[0]) as first:
        frame_width = first.width

    output_dir.mkdir(parents=True, exist_ok=True)
    bridge_dir = output_dir / "edge-bridges"
    runs: list[tuple[list[Path], list[int]]] = []
    edge_bridge_count = 0
    run_frames = [frames[0]]
    run_offsets: list[int] = []
    for left, right in zip(frames, frames[1:]):
        estimate = estimate_horizontal_scroll(left, right)
        if estimate is None:
            runs.append((run_frames, run_offsets))
            bridge = create_numberless_edge_bridge(
                left, right, bridge_dir / f"bridge_{edge_bridge_count + 1:06d}.png"
            )
            if bridge is not None:
                runs.append(([bridge], []))
                edge_bridge_count += 1
            run_frames = [right]
            run_offsets = []
            continue
        offset, _difference = estimate
        run_frames.append(right)
        run_offsets.append(offset)
    runs.append((run_frames, run_offsets))

    outputs: list[Path] = []
    stitched_runs = edge_bridge_count
    collapsed = 0
    for run_frames, offsets in runs:
        total_scroll = sum(offsets)
        positive_offsets = sum(offset > 0 for offset in offsets)
        scroll_threshold = 0.12 if force else 0.65
        required_offsets = 1 if force else 2
        if total_scroll >= round(frame_width * scroll_threshold) and positive_offsets >= required_offsets:
            panorama = build_score_panorama(run_frames, offsets)
            pieces = split_score_panorama(panorama, output_dir, frame_width, len(outputs) + 1)
            panorama.close()
            outputs.extend(pieces)
            stitched_runs += 1
            collapsed += max(0, len(run_frames) - len(pieces))
        else:
            stationary_dir = output_dir / f"stationary_{len(outputs):06d}"
            cleaned, group_collapsed = clean_score_overlays(run_frames, stationary_dir)
            for source in cleaned:
                destination = output_dir / f"frame_{len(outputs) + 1:06d}.png"
                shutil.move(str(source), str(destination))
                outputs.append(destination)
            collapsed += group_collapsed
    return outputs, collapsed, stitched_runs


def dilate_mask(mask: np.ndarray) -> np.ndarray:
    padded = np.pad(mask, 1, mode="constant")
    dilated = np.zeros_like(mask)
    for y in range(3):
        for x in range(3):
            dilated |= padded[y:y + mask.shape[0], x:x + mask.shape[1]]
    return dilated


def estimate_score_edge_overlap(left_path: Path, right_path: Path) -> tuple[int, float] | None:
    """Match the right edge of one score view with the left edge of the next."""
    with Image.open(left_path) as left_source, Image.open(right_path) as right_source:
        if left_source.size != right_source.size:
            return None
        source_width = left_source.width
    signature_width = min(512, source_width)
    left = score_structure_signature(left_path, width=signature_width)
    right = score_structure_signature(right_path, width=signature_width)
    line_rows = (np.mean(left, axis=1) > 0.32) | (np.mean(right, axis=1) > 0.32)
    left[line_rows, :] = False
    right[line_rows, :] = False

    minimum = max(16, round(signature_width * 0.04))
    maximum = max(minimum, round(signature_width * 0.35))
    best_width = 0
    best_difference = 1.0
    candidates: list[tuple[int, float]] = []
    for overlap_width in range(minimum, maximum + 1):
        left_edge = left[:, -overlap_width:]
        right_edge = right[:, :overlap_width]
        feature_count = np.count_nonzero(left_edge) + np.count_nonzero(right_edge)
        if feature_count < 30:
            continue
        left_dilated = dilate_mask(left_edge)
        right_dilated = dilate_mask(right_edge)
        difference = (
            np.count_nonzero(left_edge & ~right_dilated)
            + np.count_nonzero(right_edge & ~left_dilated)
        ) / feature_count
        if difference < best_difference:
            best_width = overlap_width
            best_difference = float(difference)
        candidates.append((overlap_width, float(difference)))

    if best_width == 0 or best_difference > 0.22:
        return None
    # Repetitive rhythms can produce several plausible widths. Prefer the
    # smallest near-best match so uncertain pixels are retained, never deleted.
    near_best_limit = min(0.22, best_difference + 0.025)
    best_width = min(width for width, difference in candidates if difference <= near_best_limit)
    source_overlap = round(best_width * source_width / signature_width)
    return source_overlap, best_difference


def detect_measure_barlines(path: Path) -> list[int]:
    """Detect vertical lines spanning an entire staff/TAB system."""
    with Image.open(path) as source:
        gray = np.asarray(source.convert("L"), dtype=np.uint8)
    dark = gray < 180
    row_density = np.mean(gray < 210, axis=1)
    dense_rows = np.where(row_density > 0.25)[0]
    row_groups: list[list[int]] = []
    for row in dense_rows:
        if not row_groups or row > row_groups[-1][-1] + 1:
            row_groups.append([int(row)])
        else:
            row_groups[-1].append(int(row))
    centers = [round(sum(group) / len(group)) for group in row_groups if len(group) <= 4]

    staff_systems: list[list[int]] = []
    used_centers: set[int] = set()
    for count in range(min(6, len(centers)), 3, -1):
        for start in range(len(centers) - count + 1):
            candidate = centers[start:start + count]
            if any(row in used_centers for row in candidate):
                continue
            gaps = np.diff(candidate)
            if np.all((gaps >= 5) & (gaps <= 40)) and float(gaps.max() / gaps.min()) <= 1.6:
                staff_systems.append(candidate)
                used_centers.update(candidate)
    if not staff_systems:
        return []

    system_positions: list[list[int]] = []
    for staff_rows in staff_systems:
        top = max(0, staff_rows[0] - 2)
        bottom = min(gray.shape[0], staff_rows[-1] + 3)
        required_run = max(8, round((staff_rows[-1] - staff_rows[0]) * 0.85))
        candidates: list[int] = []
        for x in range(gray.shape[1]):
            if not all(np.any(dark[max(0, row - 1):row + 2, x]) for row in staff_rows):
                continue
            column = dark[top:bottom, x]
            light_indexes = np.where(~column)[0]
            longest_run = int(np.diff(np.r_[-1, light_indexes, len(column)]).max() - 1)
            if longest_run >= required_run:
                candidates.append(x)

        merged: list[list[int]] = []
        for x in candidates:
            if not merged or x > merged[-1][-1] + 2:
                merged.append([x])
            else:
                merged[-1].append(x)
        system_positions.append([round(sum(group) / len(group)) for group in merged])

    if len(system_positions) == 1:
        return system_positions[0]
    consensus = []
    for x in system_positions[0]:
        matches = [x]
        for positions in system_positions[1:]:
            nearest = min(positions, key=lambda value: abs(value - x), default=None)
            if nearest is not None and abs(nearest - x) <= 4:
                matches.append(nearest)
        if len(matches) >= 2:
            consensus.append(round(sum(matches) / len(matches)))
    return consensus


def clean_score_overlays_with_analysis(
    frames: list[Path], analysis_frames: list[Path], output_dir: Path, analysis_output_dir: Path
) -> tuple[list[Path], list[Path], int]:
    """Clean selected crops and wider analysis crops using identical time groups."""
    analysis_by_name = {path.name: path for path in analysis_frames}
    groups = group_score_views(frames)
    cleaned: list[Path] = []
    cleaned_analysis: list[Path] = []
    for group in groups:
        # Preserve the first scan-frame name so audit provenance maps back to
        # source time via adaptiveScanIntervalSec.
        selected_output = output_dir / group[0].name
        analysis_output = analysis_output_dir / group[0].name
        compose_overlay_free_frame(group, selected_output)
        corresponding = [analysis_by_name[path.name] for path in group if path.name in analysis_by_name]
        compose_overlay_free_frame(corresponding, analysis_output)
        cleaned.append(selected_output)
        cleaned_analysis.append(analysis_output)
    return cleaned, cleaned_analysis, len(frames) - len(cleaned)


def _paired_score_system_geometry(gray: np.ndarray) -> list[tuple[int, int, int]]:
    """Return (system top, system bottom, TAB top) for paired score rows."""
    gray = gray.astype(np.float32, copy=False)
    nearby = (np.roll(gray, 3, axis=0) + np.roll(gray, -3, axis=0)) / 2
    ridge_strength = np.mean(np.maximum(0, nearby - gray), axis=1)
    dense_rows = np.where(ridge_strength >= 34)[0]
    groups: list[list[int]] = []
    for row in dense_rows:
        if not groups or row > groups[-1][-1] + 1:
            groups.append([int(row)])
        else:
            groups[-1].append(int(row))
    centers = [max(group, key=lambda row: float(ridge_strength[row])) for group in groups]

    height = gray.shape[0]
    geometry: list[tuple[int, int, int]] = []
    index = 0
    while index + 8 < len(centers):
        candidate = centers[index:index + 9]
        notation_gaps = np.diff(candidate[:5])
        staff_to_tab = candidate[5] - candidate[4]
        tab_gaps = np.diff(candidate[5:])
        valid = (
            np.all((notation_gaps >= 7) & (notation_gaps <= 24))
            and 18 <= staff_to_tab <= 72
            and np.all((tab_gaps >= 9) & (tab_gaps <= 32))
        )
        if not valid:
            index += 1
            continue
        top = candidate[0] - 46
        bottom = candidate[-1] + 64
        # Keep TAB articulations above its first line, but do not admit ties and
        # note heads from the five-line staff in the inter-staff gap.
        tab_top = candidate[5] - 16
        if top >= 0 and bottom <= height:
            geometry.append((top, bottom, max(top, tab_top)))
        index += 9
    return geometry


def detect_paired_score_system_bounds(path: Path) -> list[tuple[int, int]]:
    """Locate complete standard-notation + TAB rows in a tall video crop.

    The two staves are treated as one authored score system.  This is used for
    videos that scroll a page vertically: following a fixed y coordinate would
    otherwise mix the bottom of one system with the top of the next.
    """
    with Image.open(path) as source:
        gray = np.asarray(source.convert("L"), dtype=np.uint8)
    return [(top, bottom) for top, bottom, _tab_top in _paired_score_system_geometry(gray)]


def extract_tab_bands_from_paired_systems(frames: list[Path], output_dir: Path) -> list[Path]:
    """Keep only TAB from paired notation+TAB systems for the default output."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, path in enumerate(frames, start=1):
        with Image.open(path) as source:
            rgb = source.convert("RGB")
            gray = np.asarray(source.convert("L"), dtype=np.uint8)
            geometry = _paired_score_system_geometry(gray)
            if geometry:
                _top, bottom, tab_top = geometry[0]
            else:
                # The pair was already validated before being saved. This is a
                # conservative fallback for compression-altered intermediate PNGs.
                tab_top = round(rgb.height * 0.42)
                bottom = rgb.height
            tab = rgb.crop((0, tab_top, rgb.width, bottom))
        destination = output_dir / f"frame_{index:06d}.png"
        tab.save(destination)
        tab.close()
        outputs.append(destination)
    return outputs


def extract_vertical_scrolling_score_systems(
    frames: list[Path], output_dir: Path
) -> tuple[list[Path], int]:
    """Reconstruct chronological score rows from vertically scrolling pages.

    Each frame can contain multiple complete notation+TAB systems.  Consecutive
    views usually overlap by one or more systems, so the longest matching
    suffix/prefix is removed before the new systems are appended.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    accumulated: list[tuple[Image.Image, np.ndarray]] = []
    usable_frames = 0

    for path in frames:
        bounds = detect_paired_score_system_bounds(path)
        if not bounds:
            continue
        usable_frames += 1
        with Image.open(path) as source:
            rgb = source.convert("RGB")
            current = []
            for top, bottom in bounds:
                crop = rgb.crop((0, top, rgb.width, bottom))
                current.append((crop, measure_image_signature(crop)))
        if not accumulated:
            accumulated.extend(current)
            continue

        maximum_overlap = min(len(accumulated), len(current), 4)
        overlap = 0
        for count in range(maximum_overlap, 0, -1):
            differences = [
                measure_signature_difference(left[1], right[1])
                for left, right in zip(accumulated[-count:], current[:count])
            ]
            if differences and max(differences) <= 0.18:
                overlap = count
                break
        for image, _signature in current[:overlap]:
            image.close()
        accumulated.extend(current[overlap:])

    # Pair detection itself prevents this specialised path from taking over
    # TAB-only videos. Require several observations so isolated false patterns
    # in a title/end card cannot change the extraction mode.
    if usable_frames < 5 or len(accumulated) < 3:
        for image, _signature in accumulated:
            image.close()
        return [], usable_frames

    outputs: list[Path] = []
    for index, (image, _signature) in enumerate(accumulated, start=1):
        destination = output_dir / f"frame_{index:06d}.png"
        image.save(destination)
        image.close()
        outputs.append(destination)
    return outputs, usable_frames


def stitch_edge_overlap_runs(frames: list[Path], output_dir: Path) -> tuple[list[Path], int]:
    if not frames:
        return [], 0
    with Image.open(frames[0]) as first:
        frame_width = first.width

    runs: list[tuple[list[Path], list[int]]] = []
    run_frames = [frames[0]]
    overlaps: list[int] = []
    for left, right in zip(frames, frames[1:]):
        match = estimate_score_edge_overlap(left, right)
        if match is None:
            runs.append((run_frames, overlaps))
            run_frames = [right]
            overlaps = []
        else:
            run_frames.append(right)
            overlaps.append(match[0])
    runs.append((run_frames, overlaps))

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    stitched_runs = 0
    for run_frames, overlaps in runs:
        if not overlaps:
            destination = output_dir / f"frame_{len(outputs) + 1:06d}.png"
            shutil.copy2(run_frames[0], destination)
            outputs.append(destination)
            continue

        first_destination = output_dir / f"frame_{len(outputs) + 1:06d}.png"
        shutil.copy2(run_frames[0], first_destination)
        outputs.append(first_destination)
        safety_margin = round(frame_width * 0.03)
        for path, overlap in zip(run_frames[1:], overlaps):
            with Image.open(path) as source:
                safe_limit = max(0, min(source.width - 1, overlap - safety_margin))
                barlines = [x for x in detect_measure_barlines(path) if safety_margin <= x <= safe_limit]
                # Never cut inside a measure. If no barline is confidently found,
                # retain the entire frame even when an image overlap was detected.
                trim = max(barlines) if barlines else 0
                piece = source.convert("RGB").crop((trim, 0, source.width, source.height))
                canvas = Image.new("RGB", source.size, "white")
                canvas.paste(piece, (0, 0))
            destination = output_dir / f"frame_{len(outputs) + 1:06d}.png"
            canvas.save(destination)
            piece.close()
            canvas.close()
            outputs.append(destination)
        stitched_runs += 1
    return outputs, stitched_runs


def annotate_extracted_measures(frames: list[Path], output_dir: Path) -> tuple[list[Path], int]:
    """Add extraction-order labels only to measures bounded by detected barlines."""
    from PIL import ImageDraw

    output_dir.mkdir(parents=True, exist_ok=True)
    _title_font, label_font = load_title_fonts()
    outputs: list[Path] = []
    measure_number = 1
    for frame_index, path in enumerate(frames, start=1):
        barlines = detect_measure_barlines(path)
        with Image.open(path) as source:
            original = source.convert("RGB")
        label_height = 24
        image = Image.new("RGB", (original.width, original.height + label_height), "white")
        image.paste(original, (0, label_height))
        original.close()
        draw = ImageDraw.Draw(image)
        for left, right in zip(barlines, barlines[1:]):
            if right - left < 24:
                continue
            label = str(measure_number)
            x = min(image.width - 45, left + 6)
            draw.text((x, 3), label, fill=PRINT_TEXT_COLOR, font=label_font)
            measure_number += 1
        output = output_dir / f"frame_{frame_index:06d}.png"
        image.save(output)
        image.close()
        outputs.append(output)
    return outputs, measure_number - 1


def complete_score_system_boundaries(
    path: Path, expected_extent: tuple[int, int] | None = None
) -> list[int]:
    """Return measure boundaries for a fully visible, margin-bounded score row."""
    extent = detect_staff_horizontal_extent(path) or expected_extent
    if extent is None:
        return remove_spurious_close_barlines(detect_measure_barlines(path), {})
    start, end = extent
    barlines = remove_spurious_close_barlines(
        [x for x in detect_measure_barlines(path) if start <= x <= end], {}
    )
    if not barlines or barlines[0] - start >= 12:
        barlines.insert(0, start)
    if not barlines or end - barlines[-1] >= 12:
        barlines.append(end)
    # The consensus staff edges are authoritative. A legitimately narrow final
    # measure must not be discarded as a pair of suspiciously close barlines.
    return sorted(set(barlines))


def is_complete_static_score_sequence(
    frames: list[Path], *, minimum_margin_ratio: float = 0.038
) -> bool:
    """Recognize videos that replace complete score rows instead of scrolling them.

    A complete row has a stable staff onset and ending inside both viewport
    edges. Reflowing this presentation destroys annotations and intentionally
    uneven measure widths, so those rows must be preserved as authored.
    """
    if len(frames) < 2:
        return False
    samples = evenly_spaced_paths(frames, min(24, len(frames)))
    valid = 0
    complete = 0
    for path in samples:
        extent = detect_staff_horizontal_extent(path)
        if extent is None:
            continue
        valid += 1
        with Image.open(path) as source:
            width = source.width
        start, end = extent
        margin = round(width * minimum_margin_ratio)
        if start >= margin and width - 1 - end >= margin:
            complete += 1
    required_valid = max(2, round(len(samples) * 0.45))
    return valid >= required_valid and complete >= max(2, round(valid * 0.75))


def preserve_complete_score_systems(
    frames: list[Path], output_dir: Path, *, audit_path: Path,
    show_measure_numbers: bool = False,
) -> tuple[list[Path], int, int]:
    """Keep complete authored score rows intact and optionally label measures."""
    from PIL import ImageDraw

    output_dir.mkdir(parents=True, exist_ok=True)
    _title_font, label_font = load_title_fonts()
    outputs: list[Path] = []
    measure_number = 1
    row_audit: list[dict] = []
    extents = [extent for path in frames if (extent := detect_staff_horizontal_extent(path)) is not None]
    expected_extent = (
        (round(float(np.median([extent[0] for extent in extents]))),
         round(float(np.median([extent[1] for extent in extents]))))
        if extents else None
    )
    for frame_index, path in enumerate(frames, start=1):
        boundaries = complete_score_system_boundaries(path, expected_extent)
        # Title/end cards can share the selected video band but have no usable
        # score system. They must never become a printable row.
        with Image.open(path) as preview_source:
            preview_region = {
                "x": 0, "y": 0, "width": preview_source.width, "height": preview_source.height,
            }
            if score_region_likelihood(preview_source, preview_region) <= 0:
                continue
        measure_positions = [
            (left, right) for left, right in zip(boundaries, boundaries[1:])
            if right - left >= 24
        ]
        with Image.open(path) as source:
            original = source.convert("RGB")
        # Remove only near-solid dark bands connected to the video crop's top or
        # bottom edge. Internal beams, staff lines and notation are untouched.
        gray = np.asarray(original.convert("L"), dtype=np.uint8)
        edge_dark = np.mean(gray < 80, axis=1) >= 0.80
        top = 0
        while top < original.height and edge_dark[top]:
            top += 1
        bottom = original.height
        while bottom > top and edge_dark[bottom - 1]:
            bottom -= 1
        if top or bottom < original.height:
            cropped = original.crop((0, top, original.width, bottom))
            original.close()
            original = cropped
        label_height = 20 if show_measure_numbers else 0
        canvas = Image.new("RGB", (original.width, original.height + label_height), "white")
        canvas.paste(original, (0, label_height))
        original.close()
        first_measure = measure_number
        if show_measure_numbers:
            draw = ImageDraw.Draw(canvas)
            for left, _right in measure_positions:
                draw.text(
                    (min(canvas.width - 45, left + 6), 1), str(measure_number),
                    fill=PRINT_TEXT_COLOR, font=label_font,
                )
                measure_number += 1
        else:
            measure_number += len(measure_positions)
        output = output_dir / f"frame_{frame_index:06d}.png"
        canvas.save(output)
        canvas.close()
        outputs.append(output)
        row_audit.append({
            "frame": path.name,
            "boundaries": boundaries,
            "firstMeasure": first_measure if measure_positions else None,
            "measureCount": len(measure_positions),
        })
    measure_count = measure_number - 1
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "policy": {
                    "mode": "complete-static-system-preservation",
                    "reflow": False,
                    "reason": "staff begins and ends inside both viewport margins",
                },
                "inputFrames": len(frames),
                "outputFrames": len(outputs),
                "outputMeasures": measure_count,
                "deduplicatedMeasures": 0,
                "rejectedEdgeFragments": 0,
                "unresolvedMeasures": 0,
                "frames": row_audit,
                "measureSources": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return outputs, measure_count, 0


def measure_image_signature(image: Image.Image) -> np.ndarray:
    gray = ImageOps.grayscale(image).resize((128, 64), Image.Resampling.BILINEAR)
    mask = np.asarray(ImageOps.autocontrast(gray, cutoff=1), dtype=np.uint8) < 175
    line_rows = np.mean(mask, axis=1) > 0.38
    mask[line_rows, :] = False
    return mask


def measure_signature_difference(left: np.ndarray, right: np.ndarray) -> float:
    left_dilated = dilate_mask(left)
    right_dilated = dilate_mask(right)
    feature_count = np.count_nonzero(left) + np.count_nonzero(right)
    if feature_count < 20:
        return 1.0
    return float(
        (np.count_nonzero(left & ~right_dilated) + np.count_nonzero(right & ~left_dilated))
        / feature_count
    )


def measure_number_signature(image: Image.Image) -> np.ndarray:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    row_density = np.mean(gray < 210, axis=1)
    dense_rows = np.where(row_density > 0.25)[0]
    if dense_rows.size == 0:
        return np.zeros((32, 96), dtype=bool)
    staff_top = int(dense_rows[0])
    top = max(0, staff_top - 44)
    bottom = max(top + 1, staff_top - 3)
    band = Image.fromarray(gray[top:bottom], mode="L").resize((96, 32), Image.Resampling.BILINEAR)
    return np.asarray(band, dtype=np.uint8) < 190


def number_signature_difference(left: np.ndarray, right: np.ndarray) -> float:
    feature_count = np.count_nonzero(left) + np.count_nonzero(right)
    if feature_count < 8:
        return 1.0
    return float(
        (np.count_nonzero(left & ~dilate_mask(right)) + np.count_nonzero(right & ~dilate_mask(left)))
        / feature_count
    )


def read_printed_measure_numbers(path: Path, barlines: list[int]) -> dict[int, int]:
    """Read printed measure numbers and associate them with detected barlines."""
    global _OCR_ENGINE
    try:
        if _OCR_ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR

            _OCR_ENGINE = RapidOCR()
        with Image.open(path) as source:
            gray = np.asarray(source.convert("L"), dtype=np.uint8)
        row_density = np.mean(gray < 210, axis=1)
        dense_rows = np.where(row_density > 0.25)[0]
        row_groups: list[list[int]] = []
        for row in dense_rows:
            if not row_groups or row > row_groups[-1][-1] + 1:
                row_groups.append([int(row)])
            else:
                row_groups[-1].append(int(row))
        centers = [round(sum(group) / len(group)) for group in row_groups if len(group) <= 4]
        staff_top = centers[0] if centers else None
        if staff_top is None:
            return {}
        top = max(0, staff_top - 55)
        bottom = max(top + 1, staff_top - 2)
        number_band = Image.fromarray(gray[top:bottom], mode="L").resize(
            (gray.shape[1] * 2, (bottom - top) * 2), Image.Resampling.BICUBIC
        )
        result, _elapsed = _OCR_ENGINE(np.asarray(number_band, dtype=np.uint8))
    except (ImportError, OSError, RuntimeError):
        return {}
    if not result:
        return {}

    numbers: dict[int, int] = {}
    for box, text, confidence in result:
        value = str(text).strip()
        if float(confidence) < 0.85 or not re.fullmatch(r"\d{1,4}", value):
            continue
        center_x = round(sum(float(point[0]) for point in box) / len(box) / 2)
        nearest = min(barlines, key=lambda x: abs(x - center_x), default=None)
        if nearest is not None and abs(nearest - center_x) <= 28:
            numbers[nearest] = int(value)
    return numbers


def read_printed_measure_numbers_batch(
    paths: list[Path], barline_sets: list[list[int]], *, batch_size: int = 2
) -> list[dict[int, int]]:
    """Recognize tiny number crops at known barline positions without text detection."""
    global _OCR_ENGINE
    results: list[dict[int, int]] = [{} for _ in paths]
    worker = Path(__file__).resolve().parent.parent / "scripts" / "ocr_measure_numbers.py"
    if worker.exists():
        worker_batch_size = 2
        for batch_start in range(0, len(paths), worker_batch_size):
            payload = [
                {"path": str(path.resolve()), "barlines": barlines}
                for path, barlines in zip(
                    paths[batch_start:batch_start + worker_batch_size],
                    barline_sets[batch_start:batch_start + worker_batch_size],
                )
            ]
            with tempfile.TemporaryDirectory() as temp_dir:
                request_path = Path(temp_dir) / "request.json"
                response_path = Path(temp_dir) / "response.json"
                request_path.write_text(json.dumps(payload), encoding="utf-8")
                process = subprocess.run(
                    [sys.executable, str(worker), str(request_path), str(response_path)],
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                if process.returncode != 0 or not response_path.exists():
                    continue
                batch_results = json.loads(response_path.read_text(encoding="utf-8"))
            for offset, values in enumerate(batch_results):
                results[batch_start + offset] = {int(x): int(number) for x, number in values.items()}
        return results
    try:
        if _OCR_ENGINE is None:
            from rapidocr_onnxruntime import RapidOCR

            _OCR_ENGINE = RapidOCR()
    except (ImportError, OSError, RuntimeError):
        return results

    for frame_index, (path, barlines) in enumerate(zip(paths, barline_sets)):
        with Image.open(path) as source:
            rgb = source.convert("RGB")
            gray = np.asarray(source.convert("L"), dtype=np.uint8)
        row_density = np.mean(gray < 210, axis=1)
        dense_rows = np.where(row_density > 0.25)[0]
        row_groups: list[list[int]] = []
        for row in dense_rows:
            if not row_groups or row > row_groups[-1][-1] + 1:
                row_groups.append([int(row)])
            else:
                row_groups[-1].append(int(row))
        centers = [round(sum(group) / len(group)) for group in row_groups if len(group) <= 4]
        if not centers:
            continue
        staff_top = centers[0]
        top = max(0, staff_top - 55)
        bottom = max(top + 1, staff_top - 2)
        for x in barlines:
            left = max(0, x - 45)
            right = min(rgb.width, x + 45)
            crop = rgb.crop((left, top, right, bottom)).resize(
                ((right - left) * 3, max(48, (bottom - top) * 3)), Image.Resampling.BICUBIC
            )
            try:
                ocr_result, _elapsed = _OCR_ENGINE(
                    np.asarray(crop, dtype=np.uint8), use_det=False, use_cls=False, use_rec=True
                )
            except (OSError, RuntimeError):
                ocr_result = None
            crop.close()
            if not ocr_result:
                continue
            value = str(ocr_result[0][0]).strip()
            confidence = float(ocr_result[0][1])
            if confidence >= 0.80 and re.fullmatch(r"\d{1,4}", value):
                results[frame_index][x] = int(value)
    return results


def infer_barline_numbers(barlines: list[int], recognized: dict[int, int]) -> list[int | None]:
    """Fill missed OCR labels from their position in the ordered barline sequence."""
    if not recognized:
        return [None] * len(barlines)
    anchors = [(index, recognized[x]) for index, x in enumerate(barlines) if x in recognized]
    offsets = [number - index for index, number in anchors]
    offset = round(float(np.median(offsets)))
    # Individual digits can be misread, but positions inside one frame must be
    # consecutive. The median offset makes isolated OCR errors harmless.
    return [offset + index for index in range(len(barlines))]


def remove_spurious_close_barlines(
    barlines: list[int], recognized: dict[int, int], *, minimum_width: int = 60
) -> list[int]:
    cleaned = list(barlines)
    changed = True
    while changed and len(cleaned) > 1:
        changed = False
        for index, (left, right) in enumerate(zip(cleaned, cleaned[1:])):
            if right - left >= minimum_width:
                continue
            left_known = left in recognized
            right_known = right in recognized
            if left_known and not right_known:
                del cleaned[index + 1]
            elif right_known and not left_known:
                del cleaned[index]
            else:
                del cleaned[index + 1]
            changed = True
            break
    return cleaned


def append_visible_right_edge_barline(path: Path, barlines: list[int]) -> list[int]:
    with Image.open(path) as source:
        gray = np.asarray(source.convert("L"), dtype=np.uint8)
    if barlines and gray.shape[1] - 1 - barlines[-1] < 60:
        return barlines
    dark = gray < 180
    longest = 0
    for x in range(max(0, gray.shape[1] - 4), gray.shape[1]):
        column = dark[:, x]
        light_indexes = np.where(~column)[0]
        longest = max(longest, int(np.diff(np.r_[-1, light_indexes, len(column)]).max() - 1))
    if longest >= 25:
        return [*barlines, gray.shape[1] - 1]
    return barlines


def extract_complete_measure_images(path: Path) -> list[Image.Image]:
    barlines = detect_measure_barlines(path)
    measures: list[Image.Image] = []
    with Image.open(path) as source:
        rgb = source.convert("RGB")
        for left, right in zip(barlines, barlines[1:]):
            if right - left >= 24:
                measures.append(rgb.crop((left, 0, right + 1, rgb.height)))
    return measures


def crop_leading_shared_barline(image: Image.Image) -> Image.Image:
    """Remove a measure's duplicated left boundary before horizontal reflow.

    Every extracted measure contains both its left and right barline. When two
    measures are placed next to each other, retaining both copies can turn a
    legitimate double barline into three lines. The previous measure's right
    boundary is authoritative, so only the leading boundary cluster is removed
    from subsequent measures.
    """
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    if gray.shape[1] < 8:
        return image.copy()
    search_width = min(gray.shape[1], 18)
    dark = gray[:, :search_width] < 180
    strong_columns = np.where(np.count_nonzero(dark, axis=0) >= max(6, round(gray.shape[0] * 0.12)))[0]
    if not strong_columns.size or int(strong_columns[0]) > 3:
        return image.copy()
    boundary_columns = strong_columns[strong_columns <= int(strong_columns[0]) + 14]
    cut = min(image.width - 1, int(boundary_columns[-1]) + 1)
    return image.crop((cut, 0, image.width, image.height))


def remove_leading_tab_label(image: Image.Image) -> Image.Image:
    """Remove a source-system TAB glyph without erasing the staff lines.

    Reflowed measures can carry the original system label into the middle of a
    generated row.  The glyph lives in the small gutter immediately after the
    left barline and spans several staff gaps; ordinary fret numbers do not.
    Only that label-like pattern is cleared, then the horizontal lines are
    restored from nearby clean pixels.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8).copy()
    height, width = rgb.shape[:2]
    if width < 48 or height < 24:
        return Image.fromarray(rgb, mode="RGB")

    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    dark = gray < 205
    line_rows = np.mean(dark, axis=1) >= 0.34
    line_indexes = np.where(line_rows)[0]
    if line_indexes.size < 4:
        return Image.fromarray(rgb, mode="RGB")

    groups: list[list[int]] = []
    for row in line_indexes:
        row = int(row)
        if not groups or row > groups[-1][-1] + 1:
            groups.append([row])
        else:
            groups[-1].append(row)
    groups = [group for group in groups if len(group) <= 4]
    if len(groups) < 4:
        return Image.fromarray(rgb, mode="RGB")

    staff_top = groups[0][0]
    staff_bottom = groups[-1][-1]
    # Source TAB glyphs are roughly 35-50 px wide at 1080p.  The prior narrow
    # gutter removed T/A but could leave the right bowl of B as black debris.
    gutter_right = min(width - 8, max(44, min(64, round(width * 0.14))))
    top = max(0, staff_top - 8)
    bottom = min(height, staff_bottom + 9)
    non_staff = dark.copy()
    for group in groups:
        group_top = max(0, group[0] - 1)
        group_bottom = min(height, group[-1] + 2)
        non_staff[group_top:group_bottom, :] = False
    label_probe = non_staff[top:bottom, 4:gutter_right]
    if label_probe.size == 0 or np.count_nonzero(label_probe) < 18:
        return Image.fromarray(rgb, mode="RGB")
    zone_counts = [
        np.count_nonzero(zone)
        for zone in np.array_split(label_probe, 3, axis=0)
    ]
    if sum(count >= 3 for count in zone_counts) < 3:
        return Image.fromarray(rgb, mode="RGB")

    sample_left = min(width - 1, gutter_right + 5)
    sample_right = min(width, sample_left + 28)
    rgb[top:bottom, 4:gutter_right, :] = 255
    for group in groups:
        for row in group:
            sample = rgb[row, sample_left:sample_right, :]
            color = np.median(sample, axis=0).astype(np.uint8) if sample.size else np.array([160] * 3, dtype=np.uint8)
            rgb[row, 4:gutter_right, :] = color
    return Image.fromarray(rgb, mode="RGB")


def detect_tab_staff_anchor(image: Image.Image) -> int | None:
    """Return the top line of the lowest regular four-line TAB staff."""
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    row_density = np.mean(gray < 215, axis=1)
    dense_rows = np.where(row_density >= 0.32)[0]
    groups: list[list[int]] = []
    for row in dense_rows:
        row = int(row)
        if not groups or row > groups[-1][-1] + 1:
            groups.append([row])
        else:
            groups[-1].append(row)
    centers = [group[0] for group in groups if len(group) <= 5]
    candidates: list[list[int]] = []
    for start in range(max(0, len(centers) - 8), len(centers) - 3):
        candidate = centers[start:start + 4]
        gaps = np.diff(candidate)
        if np.all((gaps >= 6) & (gaps <= 36)) and float(gaps.max() / gaps.min()) <= 1.6:
            candidates.append(candidate)
    return candidates[-1][0] if candidates else None


def tab_staff_vertical_offsets(images: list[Image.Image]) -> list[int]:
    """Align independently cropped measures to the median TAB staff height."""
    anchors = [detect_tab_staff_anchor(image) for image in images]
    detected = [anchor for anchor in anchors if anchor is not None]
    if len(detected) < 2:
        return [0] * len(images)
    target = round(float(np.median(detected)))
    return [target - anchor if anchor is not None else 0 for anchor in anchors]


def tab_staff_vertical_layout(images: list[Image.Image]) -> tuple[list[int], int]:
    """Return non-negative paste positions and a height that clips no measure."""
    offsets = tab_staff_vertical_offsets(images)
    top_padding = max(0, -min(offsets, default=0))
    positions = [top_padding + offset for offset in offsets]
    height = max(
        (position + image.height for position, image in zip(positions, images)),
        default=1,
    )
    return positions, height


def fit_score_whitespace(image: Image.Image, target_width: int) -> Image.Image:
    """Adjust staff-only columns while preserving notation at its original width.

    Horizontal staff/TAB rows are ignored when locating quiet columns. Repeating
    or removing those columns changes only empty ruled space, so digits, note
    heads, bends, and barlines are never horizontally scaled.
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    if target_width == width:
        return Image.fromarray(rgb.copy(), mode="RGB")

    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    dark = gray < 225
    line_rows = np.mean(dark, axis=1) >= 0.42
    protected_rows = line_rows.copy()
    for offset in (-2, -1, 1, 2):
        if offset < 0:
            protected_rows[:offset] |= line_rows[-offset:]
        else:
            protected_rows[offset:] |= line_rows[:-offset]
    notation = dark.copy()
    notation[protected_rows, :] = False
    notation_per_column = np.count_nonzero(notation, axis=0)
    staff_per_column = (
        np.count_nonzero(dark[protected_rows, :], axis=0)
        if np.any(protected_rows)
        else np.zeros(width, dtype=int)
    )

    # Never distribute whitespace close to a barline. Circled fret numbers and
    # other glyphs can legitimately straddle that boundary; moving each half
    # independently turns a complete glyph into two clipped fragments.
    margin = min(max(12, round(width * 0.14)), max(12, width // 4))
    candidates = np.arange(margin, max(margin + 1, width - margin))
    if candidates.size:
        local_ink = notation_per_column.copy()
        for offset in (1, 2, 3):
            local_ink[offset:] = np.maximum(local_ink[offset:], notation_per_column[:-offset])
            local_ink[:-offset] = np.maximum(local_ink[:-offset], notation_per_column[offset:])
        quiet = candidates[(local_ink[candidates] == 0) & (staff_per_column[candidates] > 0)]
        if quiet.size:
            candidates = quiet
        else:
            minimum = int(np.min(local_ink[candidates]))
            candidates = candidates[local_ink[candidates] == minimum]
    if not candidates.size:
        candidates = np.array([max(0, width // 2)], dtype=int)

    difference = target_width - width
    if difference > 0:
        repeats = np.ones(width, dtype=int)
        each, remainder = divmod(difference, len(candidates))
        if each:
            repeats[candidates] += each
        if remainder:
            selected = np.linspace(0, len(candidates) - 1, num=remainder, dtype=int)
            repeats[candidates[selected]] += 1
        fitted = np.repeat(rgb, repeats, axis=1)
        return Image.fromarray(fitted, mode="RGB")

    remove_count = min(width - 1, -difference)
    if len(candidates) < remove_count:
        interior = np.arange(margin, max(margin + 1, width - margin))
        ranked = sorted(
            (int(x) for x in interior),
            key=lambda x: (int(notation_per_column[x]), int(staff_per_column[x] == 0)),
        )
        candidates = np.array(ranked, dtype=int)
    selected_indexes = np.linspace(
        0, len(candidates) - 1, num=min(remove_count, len(candidates)), dtype=int
    )
    selected = set(int(candidates[index]) for index in selected_indexes)
    if len(selected) < remove_count:
        for x in candidates:
            selected.add(int(x))
            if len(selected) >= remove_count:
                break
    keep = np.ones(width, dtype=bool)
    keep[list(selected)] = False
    fitted = rgb[:, keep, :]
    if fitted.shape[1] > target_width:
        # This fallback is reachable only for an exceptionally ink-dense measure.
        # Prefer removing the remaining lowest-ink interior columns over scaling.
        remaining = fitted.shape[1] - target_width
        interior = np.arange(margin, max(margin + 1, fitted.shape[1] - margin))
        drop = interior[np.linspace(0, len(interior) - 1, num=remaining, dtype=int)]
        fitted = np.delete(fitted, drop, axis=1)
    return Image.fromarray(fitted[:, :target_width, :], mode="RGB")


def crop_to_score_band(
    image: Image.Image, *, margin: int = 4, preserve_all_content: bool = False
) -> Image.Image:
    """Trim outer whitespace while preserving a nearby notation + TAB pair."""
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    side = min(max(2, round(gray.shape[1] * 0.02)), max(2, gray.shape[1] // 4))
    center = gray[:, side:gray.shape[1] - side] if gray.shape[1] > side * 2 else gray
    ink_per_row = np.count_nonzero(center < 235, axis=1)
    required_ink = max(2, round(center.shape[1] * 0.0008))
    content_rows = np.where(ink_per_row >= required_ink)[0]
    if not content_rows.size:
        return image.copy()
    if preserve_all_content:
        top = max(0, int(content_rows[0]) - margin)
        bottom = min(image.height, int(content_rows[-1]) + margin + 1)
        return image.crop((0, top, image.width, bottom))

    clusters: list[list[int]] = [[int(content_rows[0])]]
    for row in content_rows[1:]:
        row = int(row)
        if row - clusters[-1][-1] > 12:
            clusters.append([row])
        else:
            clusters[-1].append(row)
    cluster_ink = [int(np.sum(ink_per_row[rows[0]:rows[-1] + 1])) for rows in clusters]
    dominant_index = max(
        range(len(clusters)),
        key=lambda index: (cluster_ink[index], clusters[index][-1] - clusters[index][0]),
    )
    selected = [dominant_index]
    dominant = clusters[dominant_index]
    for index, rows in enumerate(clusters):
        if index == dominant_index or cluster_ink[index] < cluster_ink[dominant_index] * 0.18:
            continue
        gap = (
            dominant[0] - rows[-1]
            if rows[-1] < dominant[0]
            else rows[0] - dominant[-1]
        )
        if 0 <= gap <= 105:
            selected.append(index)
    top = max(0, min(clusters[index][0] for index in selected) - margin)
    bottom = min(image.height, max(clusters[index][-1] for index in selected) + margin + 1)
    if bottom - top < 24:
        return image.copy()
    return image.crop((0, top, image.width, bottom))


def build_numbered_measure_rows(
    frames: list[Path], output_dir: Path, *, barline_frames: list[Path] | None = None,
    audit_path: Path | None = None,
    progress: Callable[[str, str], None] | None = None,
    show_measure_numbers: bool = True,
    horizontal_scroll_mode: str = "auto",
    measures_per_row: int = 4,
) -> tuple[list[Path], int, int]:
    """Deduplicate complete measures and reflow only at barlines.

    Measure labels are always reconstructed for auditing, but their visual label
    band is optional so hiding numbers cannot weaken dropout detection.
    """
    from PIL import ImageDraw

    if not frames:
        return [], 0, 0
    with Image.open(frames[0]) as first:
        frame_width, frame_height = first.size

    measures: list[Image.Image] = []
    measure_labels: list[int | None] = []
    signatures: list[np.ndarray] = []
    number_signatures: list[np.ndarray] = []
    deduplicated = 0
    seen_official_numbers: set[int] = set()
    terminal_edge_candidate: dict | None = None
    rejected_edge_fragments = 0
    audit_frames: list[dict] = []
    kept_sources: list[dict] = []
    if barline_frames is None:
        barline_frames = frames
    barline_sets: list[list[int]] = []
    for selected_path, analysis_path in zip(frames, barline_frames):
        # The user-selected crop is the most reliable coordinate space for TAB
        # lines and printed measure numbers. The taller analysis crop can contain
        # unrelated video imagery above the score; use it only when the selected
        # crop genuinely has no usable barline sequence.
        selected_barlines = append_visible_right_edge_barline(
            selected_path, detect_measure_barlines(selected_path)
        )
        analysis_barlines = append_visible_right_edge_barline(
            analysis_path, detect_measure_barlines(analysis_path)
        )
        barline_sets.append(selected_barlines if len(selected_barlines) >= 2 else analysis_barlines)
    sample_indexes = sorted(set(np.linspace(0, len(barline_frames) - 1, num=min(12, len(barline_frames)), dtype=int)))
    if progress:
        progress("小節番号確認", f"代表フレーム {len(sample_indexes)} 枚をOCRしています")
    sample_barlines = [barline_sets[index] for index in sample_indexes]
    sample_selected_recognized = read_printed_measure_numbers_batch(
        [frames[index] for index in sample_indexes], sample_barlines
    )
    sample_analysis_recognized = read_printed_measure_numbers_batch(
        [barline_frames[index] for index in sample_indexes], sample_barlines
    )
    sample_recognized = [
        {**analysis_values, **selected_values}
        for selected_values, analysis_values in zip(sample_selected_recognized, sample_analysis_recognized)
    ]
    printed_numbers_available = any(sample_recognized)
    numberless_scroll_runs = 0
    numberless_collapsed_frames = 0
    if not printed_numbers_available:
        if progress:
            progress("スクロール復元", "番号なし譜面を時系列と小節線から接続しています")
        # Recovery frames are deliberately sampled again from the beginning and
        # end of a video. They are useful when printed numbers identify measures,
        # but would break the chronology used to reconstruct a numberless score.
        chronological = [
            index for index, frame in enumerate(frames)
            if not frame.name.startswith("recovery_") and len(barline_sets[index]) >= 2
        ]
        frames = [frames[index] for index in chronological]
        if horizontal_scroll_mode == "off":
            reconstructed = frames
            numberless_collapsed_frames = 0
            numberless_scroll_runs = 0
        else:
            reconstructed, numberless_collapsed_frames, numberless_scroll_runs = reconstruct_scrolling_score(
                frames,
                output_dir.parent / "scroll-reconstructed",
                force=horizontal_scroll_mode == "on",
            )
        frames = reconstructed
        # Printed-number analysis is irrelevant in this branch; using the same
        # reconstructed crop keeps barline coordinates and pixels in one space.
        barline_frames = reconstructed
        barline_sets = [
            append_visible_right_edge_barline(path, detect_measure_barlines(path))
            for path in reconstructed
        ]
        # Only the first usable view may promote an inset horizontal staff onset
        # to a boundary (for example the opening count measure). On later views
        # the same inset is the viewport's clipped left edge and is recovered by
        # the bridge assembled from the preceding right fragment.
        first_usable = next((i for i, values in enumerate(barline_sets) if len(values) >= 2), None)
        if first_usable is not None:
            barline_sets[first_usable] = prepend_visible_staff_start(
                reconstructed[first_usable], barline_sets[first_usable]
            )
    if progress:
        if printed_numbers_available:
            progress("小節番号OCR", f"譜面フレーム {len(barline_frames)} 枚の番号を読み取っています")
        else:
            progress("小節線解析", f"譜面フレーム {len(barline_frames)} 枚を小節単位に分割しています")
    selected_recognized_sets = read_printed_measure_numbers_batch(frames, barline_sets)
    analysis_recognized_sets = read_printed_measure_numbers_batch(barline_frames, barline_sets)
    recognized_sets = [
        {**analysis_values, **selected_values}
        for selected_values, analysis_values in zip(selected_recognized_sets, analysis_recognized_sets)
    ]
    for frame_index, (frame, barline_frame, barlines, recognized_numbers) in enumerate(
        zip(frames, barline_frames, barline_sets, recognized_sets), start=1
    ):
        if progress and (frame_index == 1 or frame_index % 10 == 0 or frame_index == len(frames)):
            progress("小節復元", f"{frame_index} / {len(frames)} フレームを照合しています")
        barlines = remove_spurious_close_barlines(barlines, recognized_numbers)
        recognized_numbers = {x: number for x, number in recognized_numbers.items() if x in barlines}
        inferred_numbers = infer_barline_numbers(barlines, recognized_numbers)
        incoming: list[Image.Image] = []
        incoming_labels: list[int | None] = []
        incoming_edge_fragments: list[bool] = []
        with Image.open(frame) as source:
            rgb = source.convert("RGB")
            for bar_index, (left, right) in enumerate(zip(barlines, barlines[1:])):
                if right - left >= 24:
                    measure = rgb.crop((left, 0, right + 1, rgb.height))
                    # The source-system TAB label can only belong to the first
                    # measure. Cleaning every reflowed measure corrupts circled
                    # fret numbers such as (12) when they sit near a barline.
                    if bar_index == 0:
                        cleaned_measure = remove_leading_tab_label(measure)
                        measure.close()
                        measure = cleaned_measure
                    incoming.append(measure)
                    incoming_labels.append(inferred_numbers[bar_index])
                    incoming_edge_fragments.append(
                        printed_numbers_available and right >= rgb.width - 1
                    )
        analysis_measures: list[Image.Image] = []
        with Image.open(barline_frame) as analysis_source:
            analysis_rgb = analysis_source.convert("RGB")
            for left, right in zip(barlines, barlines[1:]):
                if right - left >= 24:
                    analysis_measures.append(analysis_rgb.crop((left, 0, right + 1, analysis_rgb.height)))
        # Musical-content matching must use only the user-selected score crop.
        # The taller analysis crop may contain a player's hands or other video
        # imagery which changes while the displayed measure stays identical.
        incoming_signatures = [measure_image_signature(image) for image in incoming]
        incoming_number_signatures = [measure_number_signature(image) for image in analysis_measures]
        for image in analysis_measures:
            image.close()
        if any(incoming_edge_fragments):
            retained_incoming: list[Image.Image] = []
            retained_labels: list[int | None] = []
            retained_signatures: list[np.ndarray] = []
            retained_number_signatures: list[np.ndarray] = []
            for local_index, (image, label, signature, number_signature, edge_fragment) in enumerate(
                zip(
                    incoming,
                    incoming_labels,
                    incoming_signatures,
                    incoming_number_signatures,
                    incoming_edge_fragments,
                ),
                start=1,
            ):
                if not edge_fragment:
                    retained_incoming.append(image)
                    retained_labels.append(label)
                    retained_signatures.append(signature)
                    retained_number_signatures.append(number_signature)
                    continue
                rejected_edge_fragments += 1
                # Keep only the furthest official-numbered edge candidate. It is
                # eligible solely as a terminal fallback after all complete
                # measures have been examined (normally the final measure).
                if printed_numbers_available and label is not None and (
                    terminal_edge_candidate is None or label > terminal_edge_candidate["measure"]
                ):
                    if terminal_edge_candidate is not None:
                        terminal_edge_candidate["image"].close()
                    terminal_edge_candidate = {
                        "measure": label,
                        "image": image,
                        "signature": signature,
                        "numberSignature": number_signature,
                        "frame": frame.name,
                        "frameIndex": frame_index,
                        "localMeasureIndex": local_index,
                    }
                else:
                    image.close()
            incoming = retained_incoming
            incoming_labels = retained_labels
            incoming_signatures = retained_signatures
            incoming_number_signatures = retained_number_signatures
        overlap = 0
        differences: list[float] = []
        number_differences: list[float] = []
        has_official_numbers = sum(label is not None for label in incoming_labels) >= 2
        # With printed numbers, number-only signatures help bridge an occasional
        # OCR miss. They are intentionally disabled for numberless videos: staff
        # lines alone otherwise make unrelated measures appear deceptively close.
        if printed_numbers_available:
            best_number_match: tuple[int, int, list[float]] | None = None
            search_start = max(0, len(number_signatures) - 12)
            for output_start in range(search_start, len(number_signatures)):
                comparable = min(len(number_signatures) - output_start, len(incoming_number_signatures))
                candidate_differences: list[float] = []
                for offset in range(comparable):
                    difference = number_signature_difference(
                        number_signatures[output_start + offset], incoming_number_signatures[offset]
                    )
                    if difference > 0.22:
                        break
                    candidate_differences.append(difference)
                count = len(candidate_differences)
                if count < 2:
                    continue
                if best_number_match is None or count > best_number_match[1]:
                    best_number_match = (output_start, count, candidate_differences)
            if not has_official_numbers and best_number_match is not None:
                _output_start, matched_count, number_differences = best_number_match
                overlap = matched_count
        # Only a suffix-prefix match can be caused by viewport scrolling. Three
        # matching measures are sufficient; two require a much tighter match.
        # A single match is never removed because musical repetition is common.
        if not has_official_numbers and overlap == 0:
            for count in range(min(6, len(measures), len(incoming)), 1, -1):
                differences = [
                    measure_signature_difference(left, right)
                    for left, right in zip(signatures[-count:], incoming_signatures[:count])
                ]
                maximum = 0.075 if count == 2 else 0.12
                if max(differences) <= maximum and float(np.mean(differences)) <= maximum * 0.8:
                    overlap = count
                    break
        first_kept_number = len(measures) + 1
        frame_audit = {
            "frame": frame.name,
            "barlineFrame": barline_frame.name,
            "frameIndex": frame_index,
            "barlines": barlines,
            "recognizedMeasureNumbers": recognized_numbers,
            "inferredMeasureNumbers": inferred_numbers,
            "completeMeasures": len(incoming),
            "deduplicatedPrefixMeasures": overlap,
            "overlapDifferences": [round(value, 6) for value in differences],
            "numberOverlapDifferences": [round(value, 6) for value in number_differences],
            "firstKeptMeasure": first_kept_number if len(incoming) > overlap else None,
        }
        audit_frames.append(frame_audit)
        if has_official_numbers:
            for local_index, (image, label) in enumerate(zip(incoming, incoming_labels), start=1):
                if label is not None and label in seen_official_numbers:
                    image.close()
                    deduplicated += 1
                    continue
                if label is not None:
                    seen_official_numbers.add(label)
                measures.append(image)
                measure_labels.append(label)
                kept_sources.append({
                    "measure": label,
                    "officialNumber": True,
                    "frame": frame.name,
                    "frameIndex": frame_index,
                    "localMeasureIndex": local_index,
                })
                signature_index = local_index - 1
                signatures.append(incoming_signatures[signature_index])
                number_signatures.append(incoming_number_signatures[signature_index])
        else:
            for image in incoming[:overlap]:
                image.close()
            for local_index in range(overlap, len(incoming)):
                kept_sources.append({
                    "measure": len(measures) + (local_index - overlap) + 1,
                    "officialNumber": False,
                    "frame": frame.name,
                    "frameIndex": frame_index,
                    "localMeasureIndex": local_index + 1,
                })
            measures.extend(incoming[overlap:])
            measure_labels.extend([None] * (len(incoming) - overlap))
            signatures.extend(incoming_signatures[overlap:])
            number_signatures.extend(incoming_number_signatures[overlap:])
            deduplicated += overlap

    if terminal_edge_candidate is not None:
        terminal_number = terminal_edge_candidate["measure"]
        if terminal_number > max(seen_official_numbers, default=0):
            measures.append(terminal_edge_candidate["image"])
            measure_labels.append(terminal_number)
            signatures.append(terminal_edge_candidate["signature"])
            number_signatures.append(terminal_edge_candidate["numberSignature"])
            seen_official_numbers.add(terminal_number)
            kept_sources.append({
                "measure": terminal_number,
                "officialNumber": True,
                "edgeFallback": True,
                "frame": terminal_edge_candidate["frame"],
                "frameIndex": terminal_edge_candidate["frameIndex"],
                "localMeasureIndex": terminal_edge_candidate["localMeasureIndex"],
            })
        else:
            terminal_edge_candidate["image"].close()

    index = 0
    while index < len(measure_labels):
        if measure_labels[index] is not None:
            index += 1
            continue
        run_start = index
        while index < len(measure_labels) and measure_labels[index] is None:
            index += 1
        run_end = index
        previous = measure_labels[run_start - 1] if run_start > 0 else None
        following = measure_labels[run_end] if run_end < len(measure_labels) else None
        run_length = run_end - run_start
        if previous is not None and following is not None and following - previous == run_length + 1:
            for offset in range(run_length):
                measure_labels[run_start + offset] = previous + offset + 1
        elif previous is None and following is not None and following == run_length + 1:
            for offset in range(run_length):
                measure_labels[run_start + offset] = offset + 1

    if not printed_numbers_available:
        # These are generated conventional measure numbers, not OCR claims. The
        # audit file retains frame/barline provenance for every assigned number.
        measure_labels = list(range(1, len(measure_labels) + 1))

    output_dir.mkdir(parents=True, exist_ok=True)
    _title_font, label_font = load_title_fonts()
    rows: list[Path] = []

    measures_per_row = max(1, min(8, int(measures_per_row)))
    base_cell_width, wider_cells = divmod(frame_width, measures_per_row)
    cell_widths = [
        base_cell_width + (1 if index < wider_cells else 0)
        for index in range(measures_per_row)
    ]

    def render_row(start: int, end: int) -> None:
        row_measures = [
            (label if label is not None else "?", measure)
            for label, measure in zip(measure_labels[start:end], measures[start:end])
        ]
        if not row_measures:
            return
        pieces: list[Image.Image] = []
        for measure_index, (_number, measure) in enumerate(row_measures):
            if measure_index == 0:
                pieces.append(measure.copy())
            else:
                pieces.append(crop_leading_shared_barline(measure))
        expanded_pieces: list[Image.Image] = []
        for cell_index, piece in enumerate(pieces):
            expanded_pieces.append(fit_score_whitespace(piece, cell_widths[cell_index]))
            piece.close()
        # Width fitting makes faint staff lines continuous enough for reliable
        # detection, so align only after every cell has its final pixel width.
        vertical_positions, aligned_height = tab_staff_vertical_layout(expanded_pieces)
        score_canvas = Image.new("RGB", (frame_width, aligned_height), "white")
        x = 0
        label_positions: list[tuple[int | str, int]] = []
        for cell_index, ((number, _measure), piece, vertical_position) in enumerate(
            zip(row_measures, expanded_pieces, vertical_positions)
        ):
            label_positions.append((number, min(frame_width - 45, x + 6)))
            output_width = cell_widths[cell_index]
            score_canvas.paste(piece, (x, vertical_position))
            x += output_width
            piece.close()
        cropped_score = crop_to_score_band(score_canvas)
        score_canvas.close()
        label_height = 20 if show_measure_numbers else 0
        canvas = Image.new("RGB", (frame_width, cropped_score.height + label_height), "white")
        canvas.paste(cropped_score, (0, label_height))
        cropped_score.close()
        if show_measure_numbers:
            draw = ImageDraw.Draw(canvas)
            for number, label_x in label_positions:
                draw.text((label_x, 1), str(number), fill=PRINT_TEXT_COLOR, font=label_font)
        output = output_dir / f"frame_{len(rows) + 1:06d}.png"
        canvas.save(output)
        canvas.close()
        rows.append(output)

    for start in range(0, len(measures), measures_per_row):
        render_row(start, min(len(measures), start + measures_per_row))
    for measure in measures:
        measure.close()
    if audit_path is not None:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(
                {
                    "policy": {
                        "mode": (
                            "printed-measure-number-reconstruction"
                            if printed_numbers_available
                            else "chronological-multi-measure-overlap-reconstruction"
                        ),
                        "stitchedScrollRuns": numberless_scroll_runs,
                        "collapsedScrollFrames": numberless_collapsed_frames,
                        "minimumConsecutiveMeasuresForDeduplication": 2,
                        "maximumMeasureDifference": {"twoMeasures": 0.075, "threeOrMore": 0.12},
                        "singleMeasureDeduplication": False,
                        "edgeFragments": "not included in numbered score; barline coordinates retained for audit",
                        "rowLayout": "fixed-measure-count-with-whitespace-expansion",
                        "measuresPerRow": measures_per_row,
                    },
                    "inputFrames": len(frames),
                    "outputMeasures": len(measures),
                    "deduplicatedMeasures": deduplicated,
                    "rejectedEdgeFragments": rejected_edge_fragments,
                    "unresolvedMeasures": sum(label is None for label in measure_labels),
                    "frames": audit_frames,
                    "measureSources": kept_sources,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return rows, len(measures), deduplicated


def image_diff(left: Path, right: Path) -> float:
    with Image.open(left) as left_image, Image.open(right) as right_image:
        a = left_image.convert("L").resize((128, 32))
        b = right_image.convert("L").resize((128, 32))
        diff = ImageChops.difference(a, b)
        return float(ImageStat.Stat(diff).mean[0])


def keep_distinct_frames(frames: list[Path], *, threshold: float) -> tuple[list[Path], int]:
    kept: list[Path] = []
    skipped = 0
    last_keep_path: Path | None = None

    for frame in frames:
        if last_keep_path is None:
            kept.append(frame)
            last_keep_path = frame
            continue
        diff = image_diff(last_keep_path, frame)
        if diff > threshold:
            kept.append(frame)
            last_keep_path = frame
        else:
            skipped += 1
    return kept, skipped


def trim_frame_edges(frames: list[Path], *, trim_start: int = 0, trim_end: int = 0) -> list[Path]:
    start = max(0, trim_start)
    end = max(0, trim_end)
    if start + end >= len(frames):
        raise ValueError("トリム枚数が多すぎます。少なくとも1枚は残してください")
    right = len(frames) - end if end else len(frames)
    return frames[start:right]


def load_title_fonts() -> tuple:
    from PIL import ImageFont

    title_font = None
    sub_font = None
    for font_path in [*BOLD_FONT_CANDIDATES, *FONT_CANDIDATES]:
        try:
            title_font = ImageFont.truetype(str(font_path), 34)
            sub_font = ImageFont.truetype(str(font_path), 16)
            break
        except OSError:
            continue
    if title_font is None or sub_font is None:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    return title_font, sub_font


def load_bold_print_font(size: int):
    from PIL import ImageFont

    for font_path in [*BOLD_FONT_CANDIDATES, *FONT_CANDIDATES]:
        try:
            return ImageFont.truetype(str(font_path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_text_to_width(draw, text: str, font, max_width: int) -> str:
    bbox = draw.textbbox((0, 0), text, font=font)
    if bbox[2] - bbox[0] <= max_width:
        return text
    ellipsis = "..."
    trimmed = text
    while trimmed:
        candidate = f"{trimmed.rstrip()}{ellipsis}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return candidate
        trimmed = trimmed[:-1]
    return ellipsis


def paste_title(
    canvas: Image.Image, title: str, margin: int, musical_summary: str | None = None
) -> int:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(canvas)
    font, sub_font = load_title_fonts()
    summary_font = load_bold_print_font(20) if musical_summary else sub_font
    max_width = canvas.width - margin * 2
    y = margin
    title_text = fit_text_to_width(draw, title, font, max_width)
    draw.text(
        (margin, y),
        title_text,
        fill=PRINT_TEXT_COLOR,
        font=font,
        stroke_width=1,
        stroke_fill=PRINT_TEXT_COLOR,
    )
    y += 46
    if musical_summary:
        subtitle = fit_text_to_width(draw, musical_summary, summary_font, max_width)
        draw.text(
            (margin, y),
            subtitle,
            fill=PRINT_TEXT_COLOR,
            font=summary_font,
            stroke_width=1,
            stroke_fill=PRINT_TEXT_COLOR,
        )
        return y + 34
    return y + 12


def paste_page_number(canvas: Image.Image, page_index: int, page_count: int, margin: int) -> None:
    from PIL import ImageDraw

    draw = ImageDraw.Draw(canvas)
    _font, sub_font = load_title_fonts()
    text = f"Page {page_index} / {page_count}"
    bbox = draw.textbbox((0, 0), text, font=sub_font)
    x = (canvas.width - (bbox[2] - bbox[0])) // 2
    y = canvas.height - margin + 6
    draw.text(
        (x, y),
        text,
        fill=PRINT_TEXT_COLOR,
        font=sub_font,
        stroke_width=1,
        stroke_fill=PRINT_TEXT_COLOR,
    )


def safe_filename(value: str, fallback: str) -> str:
    normalized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" ._")
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return (normalized or fallback)[:80]


def fit_image_to_width(image: Image.Image, width: int) -> Image.Image:
    if image.width == width:
        return image.convert("RGB")
    height = max(1, round(image.height * (width / image.width)))
    return image.convert("RGB").resize((width, height))


def trim_vertical_score_whitespace(
    frames: list[Path], output_dir: Path, *, margin: int = 10
) -> tuple[list[Path], int]:
    """Trim top/bottom whitespace independently while retaining notation labels."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    removed_pixels = 0
    for index, frame in enumerate(frames, start=1):
        with Image.open(frame) as source:
            rgb = source.convert("RGB")
            gray = np.asarray(rgb.convert("L"), dtype=np.uint8)
            # Ignore narrow side borders: selection handles and video borders can
            # span the full height even though the score itself does not.
            side = min(max(2, round(gray.shape[1] * 0.02)), max(2, gray.shape[1] // 4))
            center = gray[:, side:gray.shape[1] - side] if gray.shape[1] > side * 2 else gray
            ink_per_row = np.count_nonzero(center < 235, axis=1)
            required_ink = max(2, round(center.shape[1] * 0.0008))
            content_rows = np.where(ink_per_row >= required_ink)[0]
            if content_rows.size:
                top = max(0, int(content_rows[0]) - margin)
                bottom = min(rgb.height, int(content_rows[-1]) + margin + 1)
            else:
                top, bottom = 0, rgb.height
            # Never turn a noisy/blank input into an implausibly thin strip.
            if bottom - top < 24:
                top, bottom = 0, rgb.height
            cropped = rgb.crop((0, top, rgb.width, bottom))
            removed_pixels += rgb.height - cropped.height
        output = output_dir / f"frame_{index:06d}.png"
        cropped.save(output)
        cropped.close()
        rgb.close()
        outputs.append(output)
    return outputs, removed_pixels


def annotate_score_harmony(
    frames: list[Path], output_dir: Path,
    chords_by_measure: list[list[str | dict[str, str | float]]], *,
    measures_per_row: int, processing_mode: str, audit_path: Path | None = None,
    show_measure_numbers: bool = False,
) -> list[Path]:
    """Add measure numbers first, then chord symbols, above the score staff."""
    from PIL import ImageDraw

    output_dir.mkdir(parents=True, exist_ok=True)
    label_font = load_bold_print_font(24)
    degree_font = load_bold_print_font(18)
    outputs: list[Path] = []
    band_height = 36
    measure_number_band_height = 20 if show_measure_numbers else 0
    layouts = score_row_layouts(
        frames, measure_count=len(chords_by_measure), measures_per_row=measures_per_row,
        processing_mode=processing_mode, audit_path=audit_path,
    )
    for frame_index, (frame, (first_measure, boundaries)) in enumerate(
        zip(frames, layouts), start=1
    ):
        with Image.open(frame) as source:
            score = source.convert("RGB")
        count = min(len(boundaries) - 1, len(chords_by_measure) - first_measure)
        if count <= 0:
            score.close()
            break
        canvas = Image.new("RGB", (score.width, score.height + band_height), "white")
        if measure_number_band_height:
            number_band = score.crop((0, 0, score.width, measure_number_band_height))
            score_body = score.crop((0, measure_number_band_height, score.width, score.height))
            canvas.paste(number_band, (0, 0))
            canvas.paste(score_body, (0, measure_number_band_height + band_height))
            number_band.close()
            score_body.close()
        else:
            canvas.paste(score, (0, band_height))
        score.close()
        draw = ImageDraw.Draw(canvas)
        for local_index in range(count):
            chord_items = chords_by_measure[first_measure + local_index]
            if not chord_items:
                continue
            left = boundaries[local_index]
            right = boundaries[local_index + 1]
            for item_index, item in enumerate(chord_items):
                if isinstance(item, dict):
                    label = str(item.get("label") or "")
                    position = float(item.get("position") or 0.0)
                    degree = str(item.get("degree") or "")
                else:
                    label = str(item)
                    position = item_index / max(1, len(chord_items))
                    degree = ""
                if not label:
                    continue
                fitted = fit_text_to_width(draw, label, label_font, max(20, right - left - 12))
                chord_width = round(draw.textlength(fitted, font=label_font))
                degree_text = f"({degree})" if degree else ""
                degree_width = round(draw.textlength(degree_text, font=degree_font)) if degree_text else 0
                text_width = chord_width + degree_width
                onset_x = left + round(max(0.0, min(1.0, position)) * (right - left))
                # A chord symbol is left-aligned to the detected TAB onset, as
                # in conventional score engraving. Clamp only at the page edge.
                text_x = max(0, min(canvas.width - text_width - 2, onset_x))
                draw.text(
                    (text_x, measure_number_band_height + 3), fitted,
                    fill=PRINT_TEXT_COLOR, font=label_font,
                    stroke_width=1, stroke_fill=PRINT_TEXT_COLOR,
                )
                if degree_text:
                    draw.text(
                        (text_x + chord_width, measure_number_band_height + 8),
                        degree_text, fill=PRINT_TEXT_COLOR, font=degree_font,
                        stroke_width=1, stroke_fill=PRINT_TEXT_COLOR,
                    )
        output = output_dir / f"frame_{frame_index:06d}.png"
        canvas.save(output)
        canvas.close()
        outputs.append(output)
    return outputs or frames


def write_a4_pngs(
    frames: list[Path], output_dir: Path, title: str, file_prefix: str,
    musical_summary: str | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    first_frame = Image.open(frames[0])
    content_width = first_frame.width
    first_frame.close()
    margin = max(24, round(content_width * 0.06))
    page_width = content_width + margin * 2
    page_height = round(page_width * A4_RATIO)
    footer_height = margin + 24

    pages: list[list[Image.Image]] = []
    current_page: list[Image.Image] = []
    y = margin + 80

    def flush_page() -> None:
        nonlocal current_page, y
        if not current_page:
            return
        pages.append(current_page)
        current_page = []
        y = margin + 80

    for frame in frames:
        with Image.open(frame) as source:
            image = fit_image_to_width(source, content_width)
        if current_page and y + image.height > page_height - footer_height:
            flush_page()
        current_page.append(image)
        y += image.height
    flush_page()

    page_count = len(pages)
    for output_index, page_images in enumerate(pages, start=1):
        canvas = Image.new("RGB", (page_width, page_height), "white")
        y = paste_title(canvas, title, margin, musical_summary)
        for image in page_images:
            canvas.paste(image, (margin, y))
            y += image.height
            image.close()
        paste_page_number(canvas, output_index, page_count, margin)
        output = output_dir / f"{file_prefix}_{output_index:03d}.png"
        rendered = canvas.resize(
            (canvas.width * PRINT_PAGE_SCALE, canvas.height * PRINT_PAGE_SCALE),
            Image.Resampling.LANCZOS,
        )
        rendered.save(output)
        rendered.close()
        outputs.append(output)
        canvas.close()
    return outputs


def write_a3_2up_pngs(
    frames: list[Path], output_dir: Path, title: str, file_prefix: str,
    musical_summary: str | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    with tempfile.TemporaryDirectory(dir=output_dir.parent) as temp_dir:
        a4_outputs = write_a4_pngs(frames, Path(temp_dir), title, file_prefix, musical_summary)
        if not a4_outputs:
            return outputs

        with Image.open(a4_outputs[0]) as first_page:
            a4_width, a4_height = first_page.size

        for pair_index in range(0, len(a4_outputs), 2):
            output_index = pair_index // 2 + 1
            canvas = Image.new("RGB", (a4_width * 2, a4_height), "white")
            for side, page_path in enumerate(a4_outputs[pair_index:pair_index + 2]):
                with Image.open(page_path) as page:
                    canvas.paste(page.convert("RGB"), (a4_width * side, 0))
            output = output_dir / f"{file_prefix}_a3_{output_index:03d}.png"
            canvas.save(output)
            outputs.append(output)
            canvas.close()

    return outputs


def combine_a4_pages_to_a3(
    a4_outputs: list[Path], output_dir: Path, file_prefix: str
) -> list[Path]:
    """Combine rendered logical pages while retaining them for UI preview."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    if not a4_outputs:
        return outputs
    with Image.open(a4_outputs[0]) as first_page:
        a4_width, a4_height = first_page.size
    for pair_index in range(0, len(a4_outputs), 2):
        output_index = pair_index // 2 + 1
        canvas = Image.new("RGB", (a4_width * 2, a4_height), "white")
        for side, page_path in enumerate(a4_outputs[pair_index:pair_index + 2]):
            with Image.open(page_path) as page:
                canvas.paste(page.convert("RGB"), (a4_width * side, 0))
        output = output_dir / f"{file_prefix}_a3_{output_index:03d}.png"
        canvas.save(output)
        outputs.append(output)
        canvas.close()
    return outputs


def write_vertical_pngs(
    frames: list[Path], output_dir: Path, title: str, file_prefix: str,
    musical_summary: str | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    batch: list[Image.Image] = []
    batch_height = 0
    output_index = 1
    title_height = 110

    def flush() -> None:
        nonlocal batch, batch_height, output_index
        if not batch:
            return
        width = max(image.width for image in batch)
        canvas = Image.new("RGB", (width, batch_height + title_height), "white")
        y = paste_title(canvas, title, 24, musical_summary)
        for image in batch:
            canvas.paste(image.convert("RGB"), (0, y))
            y += image.height
        output = output_dir / f"{file_prefix}_{output_index:03d}.png"
        canvas.save(output)
        outputs.append(output)
        for image in batch:
            image.close()
        canvas.close()
        batch = []
        batch_height = 0
        output_index += 1

    for frame in frames:
        image = Image.open(frame)
        extra = title_height
        if batch and batch_height + image.height + extra > MAX_OUTPUT_HEIGHT:
            flush()
        batch.append(image.copy())
        batch_height += image.height
        image.close()
    flush()
    return outputs


def publish_outputs(video_id: str, outputs: list[Path]) -> list[str]:
    public_dir = PUBLIC_SCORE_DIR / video_id
    if public_dir.exists():
        shutil.rmtree(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    for output in outputs:
        destination = public_dir / output.name
        shutil.copy2(output, destination)
        urls.append(f"/score/{video_id}/{destination.name}")
    return urls


def publish_additional_outputs(video_id: str, outputs: list[Path]) -> list[str]:
    public_dir = PUBLIC_SCORE_DIR / video_id
    public_dir.mkdir(parents=True, exist_ok=True)
    urls = []
    for output in outputs:
        destination = public_dir / output.name
        shutil.copy2(output, destination)
        urls.append(f"/score/{video_id}/{destination.name}")
    return urls


def write_output_zip(video_id: str, outputs: list[Path], file_prefix: str) -> str:
    public_dir = PUBLIC_SCORE_DIR / video_id
    zip_path = public_dir / f"{file_prefix}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for output in outputs:
            archive.write(output, arcname=output.name)
    return f"/score/{video_id}/{zip_path.name}"


def resolve_source(payload: dict) -> tuple[str, Path, str]:
    source_url = (payload.get("url") or "").strip()
    if not source_url:
        raise ValueError("URLを入力してください")
    video_id = make_score_id(source_url)
    video_path = DATA_SCORE_DIR / video_id / "source.mp4"
    if not video_path.exists():
        download_source_video(source_url, video_path)
    metadata_path = DATA_SCORE_DIR / video_id / "source.json"
    if metadata_path.exists():
        title = json.loads(metadata_path.read_text(encoding="utf-8")).get("title") or video_id
    else:
        title = get_video_title(source_url, video_id)
        metadata_path.write_text(json.dumps({"title": title, "url": source_url}, ensure_ascii=False, indent=2), encoding="utf-8")
    return video_id, video_path, title


def score_region_likelihood(image: Image.Image, region: dict) -> float:
    """Estimate whether a crop contains staff/TAB systems rather than a title card."""
    crop = image.convert("L").crop(
        (
            region["x"],
            region["y"],
            region["x"] + region["width"],
            region["y"] + region["height"],
        )
    )
    preview_width = min(960, crop.width)
    preview_height = max(1, round(crop.height * preview_width / max(1, crop.width)))
    gray = np.asarray(crop.resize((preview_width, preview_height), Image.Resampling.BILINEAR), dtype=np.uint8)
    crop.close()
    dark = gray < 210
    row_density = np.mean(dark, axis=1)
    line_rows = np.where((row_density >= 0.28) & (row_density <= 0.98))[0]
    groups: list[list[int]] = []
    for row in line_rows:
        if not groups or row > groups[-1][-1] + 2:
            groups.append([int(row)])
        else:
            groups[-1].append(int(row))
    centers = [round(sum(group) / len(group)) for group in groups if len(group) <= 5]
    regular_lines = 0
    for start in range(len(centers)):
        for count in range(6, 3, -1):
            candidate = centers[start:start + count]
            if len(candidate) != count:
                continue
            gaps = np.diff(candidate)
            if np.all((gaps >= 3) & (gaps <= 35)) and float(gaps.max() / gaps.min()) <= 1.8:
                regular_lines = max(regular_lines, count)
    if regular_lines < 4:
        return 0.0
    # Notes/numbers add local ink while a blank ruled background does not.
    local_ink = float(np.mean((row_density > 0.01) & (row_density < 0.28)))
    return regular_lines * 10.0 + local_ink


def extract_preview_frame(
    video_path: Path, output_path: Path, duration_sec: float, region: dict, *,
    start_sec: float = 0, end_sec: float | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_path.parent) as temp_dir:
        candidate_dir = Path(temp_dir)
        sample_count = 18
        range_end = duration_sec if end_sec is None else end_sec
        range_duration = range_end - start_sec
        fps = sample_count / max(1.0, range_duration)
        input_args = ["-ss", f"{start_sec:.6f}"] if start_sec > 0 else []
        input_args.extend(["-t", f"{range_duration:.6f}"])
        _run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", *input_args, "-i", str(video_path),
                "-vf", f"fps={fps:.8f}", "-frames:v", str(sample_count),
                str(candidate_dir / "candidate_%03d.png"), "-y",
            ]
        )
        candidates = sorted(candidate_dir.glob("candidate_*.png"))
        if not candidates:
            raise RuntimeError("プレビュー画像を抽出できませんでした")
        scored: list[tuple[float, Path]] = []
        for candidate in candidates:
            with Image.open(candidate) as image:
                scored.append((score_region_likelihood(image, region), candidate))
        # Prefer a later candidate on ties so opening title cards are avoided.
        _score, best = max(scored, key=lambda item: (item[0], candidates.index(item[1])))
        shutil.copy2(best, output_path)


def publish_preview(video_id: str, preview_path: Path) -> str:
    public_dir = PUBLIC_SCORE_DIR / video_id
    public_dir.mkdir(parents=True, exist_ok=True)
    destination = public_dir / "preview.png"
    shutil.copy2(preview_path, destination)
    return f"/score/{video_id}/preview.png"


def cleanup_canceled_score_job(video_id: str) -> None:
    work_dir = DATA_SCORE_DIR / video_id
    if not work_dir.exists():
        return
    for child in work_dir.iterdir():
        if child.name in ("source.mp4", "source.json"):
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def prepare_score_preview(
    payload: dict, progress: Callable[[str, str], None] | None = None
) -> dict:
    if progress:
        progress("動画準備", "動画とタイトルを確認しています")
    video_id, video_path, _title = resolve_source(payload)
    video = probe_video(video_path)
    start_sec, end_sec = resolve_score_time_range(video, payload)
    region = resolve_region(video, payload)
    preview_path = DATA_SCORE_DIR / video_id / "preview.png"
    if progress:
        progress("プレビュー探索", "指定時間から譜面が明瞭なフレームを探しています")
    extract_preview_frame(
        video_path, preview_path, float(video["durationSec"]), region,
        start_sec=start_sec, end_sec=end_sec,
    )
    if progress:
        progress("プレビュー出力", "選択領域付きプレビューを準備しています")
    return {
        "videoId": video_id,
        "video": video,
        "region": region,
        "startSec": start_sec,
        "endSec": end_sec,
        "previewFrameUrl": publish_preview(video_id, preview_path),
    }


def extract_score(
    payload: dict, progress: Callable[[str, str], None] | None = None
) -> dict:
    if progress:
        progress("動画準備", "動画とタイトルを確認しています")
    video_id, video_path, source_title = resolve_source(payload)
    requested_title = str(payload.get("title") or "").strip()
    title = requested_title or source_title

    video = probe_video(video_path)
    start_sec, end_sec = resolve_score_time_range(video, payload)
    region = resolve_region(video, payload)
    trim_start = int(payload.get("trimStartFrames", 0) or 0)
    trim_end = int(payload.get("trimEndFrames", 0) or 0)
    requested_processing_mode = str(payload.get("processingMode", "auto") or "auto").lower()
    processing_mode = "simple" if requested_processing_mode == "simple" else "auto"
    score_content = str(payload.get("scoreContent", "tab") or "tab").lower()
    if score_content not in {"tab", "paired"}:
        score_content = "tab"
    vertical_scroll_mode = str(payload.get("verticalScrollMode", "auto") or "auto").lower()
    if vertical_scroll_mode not in {"auto", "on", "off"}:
        vertical_scroll_mode = "auto"
    horizontal_scroll_mode = str(payload.get("horizontalScrollMode", "auto") or "auto").lower()
    if horizontal_scroll_mode not in {"auto", "on", "off"}:
        horizontal_scroll_mode = "auto"
    measures_per_row = max(1, min(8, int(payload.get("measuresPerRow", 4) or 4)))
    if processing_mode not in {"simple", "auto"}:
        processing_mode = "auto"
    show_measure_numbers = bool(payload.get("showMeasureNumbers", False))
    show_chord_symbols, show_key_estimate, show_bpm = resolve_musical_output_options(payload)
    show_musical_analysis = show_chord_symbols or show_key_estimate or show_bpm
    work_dir = DATA_SCORE_DIR / video_id
    source_file = work_dir / "source.mp4"
    preserved_source: Path | None = None
    preserved_metadata = work_dir / "source.json"
    if source_file.exists():
        preserved_source = source_file
    for child in work_dir.iterdir() if work_dir.exists() else []:
        if (preserved_source is not None and child == preserved_source) or child == preserved_metadata:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    crop_dir = work_dir / "crops"
    output_dir = work_dir / "output"

    with tempfile.TemporaryDirectory(dir=DATA_SCORE_DIR) as temp_dir:
        temp_crop_dir = Path(temp_dir) / "crops"
        # Scan at low resolution so short-lived score views are discovered
        # without running the expensive OCR/layout pipeline on every frame.
        scan_interval_sec = 0.5
        if progress:
            progress("譜面変化スキャン", f"{scan_interval_sec:g} 秒刻みの低解像度映像を解析しています")
        representative_indexes, scan_fps, scanned_frame_count, rejected_transition_frames = scan_score_views(
            video_path,
            Path(temp_dir) / "view_scan",
            region,
            scan_interval_sec=scan_interval_sec,
            start_sec=start_sec,
            end_sec=end_sec,
        )
        if progress:
            progress(
                "代表フレーム抽出",
                f"{scanned_frame_count} 候補から {len(representative_indexes)} 枚を元解像度で取得しています",
            )
        frames = extract_crops_at_scan_indexes(
            video_path, temp_crop_dir, region, scan_fps, representative_indexes,
            start_sec=start_sec, end_sec=end_sec,
        )
        if not frames:
            raise RuntimeError("譜面画像を抽出できませんでした")
        analysis_y = max(0, region["y"] - max(240, region["height"] * 3))
        analysis_bottom = region["y"] + region["height"]
        analysis_region = {
            "x": region["x"],
            "y": analysis_y,
            "width": region["width"],
            "height": analysis_bottom - analysis_y,
        }
        analysis_frames = extract_crops_at_scan_indexes(
            video_path,
            Path(temp_dir) / "analysis_crops",
            analysis_region,
            scan_fps,
            representative_indexes,
            start_sec=start_sec,
            end_sec=end_sec,
        )
        if progress:
            progress("ハイライト除去", f"{len(frames)} フレームから色と再生線を除去しています")
        overlay_cleaned, analysis_cleaned, overlay_collapsed = clean_score_overlays_with_analysis(
            frames,
            analysis_frames,
            Path(temp_dir) / "overlay_cleaned",
            Path(temp_dir) / "analysis_cleaned",
        )
        vertical_systems: list[Path] = []
        vertical_system_frames = 0
        if processing_mode != "simple" and vertical_scroll_mode != "off":
            vertical_systems, vertical_system_frames = extract_vertical_scrolling_score_systems(
                analysis_cleaned, Path(temp_dir) / "vertical-systems"
            )
            if vertical_systems:
                overlay_cleaned = (
                    extract_tab_bands_from_paired_systems(
                        vertical_systems, Path(temp_dir) / "vertical-tab-systems"
                    )
                    if score_content == "tab"
                    else vertical_systems
                )
                analysis_cleaned = vertical_systems
            elif vertical_scroll_mode == "on":
                raise RuntimeError(
                    "縦スクロールを強制しましたが、完全な五線譜＋TAB段を検出できませんでした"
                )
        complete_static_systems = is_complete_static_score_sequence(overlay_cleaned)
        if processing_mode == "simple":
            if progress:
                progress("元の段組みを処理", "元の譜面画像を分解せず、1段ずつそのまま配置しています")
            numbered_frames, labeled_measures, deduplicated_measures = preserve_complete_score_systems(
                overlay_cleaned,
                Path(temp_dir) / "simple-rows",
                audit_path=work_dir / "measure-audit.json",
                show_measure_numbers=show_measure_numbers,
            )
        else:
            if progress:
                progress("自動再構成", "小節線・重複・スクロール断片を解析して再構成しています")
            recovery_indexes = sorted(
                set(range(min(8, len(frames))))
                | set(range(max(0, len(frames) - 12), len(frames)))
            )
            recovery_selected_dir = Path(temp_dir) / "recovery_selected"
            recovery_analysis_dir = Path(temp_dir) / "recovery_analysis"
            for recovery_index in recovery_indexes:
                selected_output = recovery_selected_dir / f"recovery_{recovery_index:06d}.png"
                analysis_output = recovery_analysis_dir / f"recovery_{recovery_index:06d}.png"
                compose_overlay_free_frame([frames[recovery_index]], selected_output)
                compose_overlay_free_frame([analysis_frames[recovery_index]], analysis_output)
                overlay_cleaned.append(selected_output)
                analysis_cleaned.append(analysis_output)
            numbered_frames, labeled_measures, deduplicated_measures = build_numbered_measure_rows(
                overlay_cleaned,
                Path(temp_dir) / "numbered",
                barline_frames=analysis_cleaned,
                audit_path=work_dir / "measure-audit.json",
                progress=progress,
                show_measure_numbers=show_measure_numbers,
                horizontal_scroll_mode=horizontal_scroll_mode,
                measures_per_row=measures_per_row,
            )
        numbered_frames = trim_frame_edges(numbered_frames, trim_start=trim_start, trim_end=trim_end)
        if progress:
            progress("余白トリム", f"{len(numbered_frames)} 段の上下余白を個別に調整しています")
        numbered_frames, vertically_trimmed_pixels = trim_vertical_score_whitespace(
            numbered_frames, Path(temp_dir) / "vertical-trimmed"
        )
        musical_analysis: dict | None = None
        musical_analysis_error: str | None = None
        musical_summary: str | None = None
        if show_musical_analysis:
            try:
                if show_chord_symbols or show_key_estimate:
                    if progress:
                        progress("TAB画像解析", "各弦のフレット数字からコードとキーを判定しています")
                    musical_analysis = analyze_score_harmony(
                        video_id, video_path, numbered_frames, start_sec=start_sec,
                        end_sec=end_sec, measure_count=labeled_measures,
                        measures_per_row=measures_per_row, processing_mode=processing_mode,
                        audit_path=work_dir / "measure-audit.json",
                    )
                else:
                    bpm, bpm_source = resolve_score_bpm(
                        video_id, video_path, start_sec=start_sec, end_sec=end_sec
                    )
                    musical_analysis = {"bpm": bpm, "bpmSource": bpm_source}
                if show_chord_symbols:
                    numbered_frames = annotate_score_harmony(
                        numbered_frames, Path(temp_dir) / "harmony-annotated",
                        musical_analysis.get("chordEventsByMeasure")
                        or musical_analysis["chordsByMeasure"], measures_per_row=measures_per_row,
                        processing_mode=processing_mode,
                        audit_path=work_dir / "measure-audit.json",
                        show_measure_numbers=show_measure_numbers,
                    )
                summary_parts = [
                    f"BPM {musical_analysis['bpm']:g}"
                    if show_bpm and musical_analysis.get("bpm") else None,
                    format_estimated_key_summary(musical_analysis) if show_key_estimate else None,
                ]
                musical_summary = "  ·  ".join(part for part in summary_parts if part)
            except Exception as exc:
                musical_analysis_error = str(exc)
                if progress:
                    progress("コード・キー解析", f"推定を省略しました: {exc}")
        skipped = deduplicated_measures
        stitched_runs = 0
        output_dir.mkdir(parents=True, exist_ok=True)
        crop_dir.mkdir(parents=True, exist_ok=True)
        for frame in numbered_frames[:100]:
            shutil.copy2(frame, crop_dir / frame.name)
        layout = str(payload.get("layout", "a3_2up")).lower()
        file_prefix = safe_filename(title, video_id)
        if progress:
            progress("ページ作成", f"{len(numbered_frames)} 段を印刷用レイアウトへ配置しています")
        page_outputs: list[Path] = []
        if layout == "vertical":
            outputs = write_vertical_pngs(
                numbered_frames, output_dir, title, file_prefix, musical_summary
            )
        elif layout == "a3_2up":
            page_outputs = write_a4_pngs(
                numbered_frames, output_dir, title, f"{file_prefix}_page", musical_summary
            )
            outputs = combine_a4_pages_to_a3(page_outputs, output_dir, file_prefix)
        else:
            outputs = write_a4_pngs(
                numbered_frames, output_dir, title, file_prefix, musical_summary
            )
            page_outputs = outputs

    if progress:
        progress("ファイル出力", "PNG・監査情報・ZIPを保存しています")
    urls = publish_outputs(video_id, outputs)
    page_urls = publish_additional_outputs(video_id, page_outputs)
    audit_destination = PUBLIC_SCORE_DIR / video_id / "measure-audit.json"
    shutil.copy2(work_dir / "measure-audit.json", audit_destination)
    audit_url = f"/score/{video_id}/measure-audit.json"
    zip_url = write_output_zip(video_id, outputs, safe_filename(title, video_id))
    metadata = {
        "videoId": video_id,
        "keptFrames": len(numbered_frames),
        "skippedFrames": skipped,
        "overlayCollapsedFrames": overlay_collapsed,
        "stitchedScrollRuns": stitched_runs,
        "labeledMeasures": labeled_measures,
        "showMeasureNumbers": show_measure_numbers,
        "showMusicalAnalysis": show_musical_analysis,
        "showChordSymbols": show_chord_symbols,
        "showKeyEstimate": show_key_estimate,
        "showBpm": show_bpm,
        "musicalAnalysis": musical_analysis,
        "musicalAnalysisError": musical_analysis_error,
        "processingMode": processing_mode,
        "scoreContent": score_content,
        "verticalScrollMode": vertical_scroll_mode,
        "horizontalScrollMode": horizontal_scroll_mode,
        "measuresPerRow": measures_per_row,
        "completeStaticSystems": complete_static_systems,
        "deduplicatedMeasures": deduplicated_measures,
        "verticallyTrimmedPixels": vertically_trimmed_pixels,
        "verticalScrollSystems": len(vertical_systems),
        "verticalScrollSourceFrames": vertical_system_frames,
        "adaptiveScanIntervalSec": scan_interval_sec,
        "adaptiveScannedFrames": scanned_frame_count,
        "adaptiveRepresentativeFrames": len(representative_indexes),
        "adaptiveRejectedTransitionFrames": rejected_transition_frames,
        "measureAuditUrl": audit_url,
        "trimStartFrames": max(0, trim_start),
        "trimEndFrames": max(0, trim_end),
        "startSec": start_sec,
        "endSec": end_sec,
        "videoDurationSec": float(video["durationSec"]),
        "region": region,
        "title": title,
        "layout": layout,
        "outputs": urls,
        "pageOutputs": page_urls,
        "pageCount": len(page_urls),
        "zipUrl": zip_url,
    }
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
    (work_dir / "metadata.json").write_text(metadata_json, encoding="utf-8")
    (PUBLIC_SCORE_DIR / video_id / "metadata.json").write_text(metadata_json, encoding="utf-8")
    return metadata
