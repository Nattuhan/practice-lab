import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR


def number_band_top(gray: np.ndarray) -> int | None:
    dense_rows = np.where(np.mean(gray < 210, axis=1) > 0.25)[0]
    groups: list[list[int]] = []
    for row in dense_rows:
        if not groups or row > groups[-1][-1] + 1:
            groups.append([int(row)])
        else:
            groups[-1].append(int(row))
    centers = [round(sum(group) / len(group)) for group in groups if len(group) <= 4]
    return centers[0] if centers else None


def main() -> None:
    request_path = Path(sys.argv[1])
    response_path = Path(sys.argv[2])
    requests = json.loads(request_path.read_text(encoding="utf-8"))
    engine = RapidOCR()
    results = []
    for request in requests:
        with Image.open(request["path"]) as source:
            rgb = source.convert("RGB")
            gray = np.asarray(source.convert("L"), dtype=np.uint8)
        staff_top = number_band_top(gray)
        values: dict[str, int] = {}
        if staff_top is not None:
            top = max(0, staff_top - 55)
            bottom = max(top + 1, staff_top - 2)
            for x in request["barlines"]:
                left = max(0, x - 45)
                right = min(rgb.width, x + 45)
                crop = rgb.crop((left, top, right, bottom)).resize(
                    ((right - left) * 3, max(48, (bottom - top) * 3)), Image.Resampling.BICUBIC
                )
                result, _elapsed = engine(
                    np.asarray(crop, dtype=np.uint8), use_det=False, use_cls=False, use_rec=True
                )
                crop.close()
                if not result:
                    continue
                text = str(result[0][0]).strip()
                confidence = float(result[0][1])
                if confidence >= 0.80 and re.fullmatch(r"\d{1,4}", text):
                    values[str(x)] = int(text)
        results.append(values)
    response_path.write_text(json.dumps(results), encoding="utf-8")


if __name__ == "__main__":
    main()
