from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path


PACK_DISTRIBUTIONS = (
    "rapidocr-onnxruntime",
    "opencv-python",
    "onnxruntime",
    "pyclipper",
    "shapely",
    "pyyaml",
    "tqdm",
    "flatbuffers",
    "protobuf",
    "six",
    "coloredlogs",
    "humanfriendly",
)


def copy_distribution(name: str, destination: Path, *, required: bool = True) -> int:
    try:
        package = distribution(name)
    except PackageNotFoundError:
        if required:
            raise
        return 0
    root = Path(package.locate_file("")).resolve()
    copied = 0
    for entry in package.files or ():
        source = Path(package.locate_file(entry)).resolve()
        try:
            relative = source.relative_to(root)
        except ValueError:
            continue
        if not source.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    return copied


def build_pack(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir) / "score-pack" / "site-packages"
        staging.mkdir(parents=True)
        copied = 0
        for name in PACK_DISTRIBUTIONS:
            copied += copy_distribution(name, staging, required=name not in {"coloredlogs", "humanfriendly"})
        if not (staging / "rapidocr_onnxruntime").is_dir() or not (staging / "cv2").is_dir():
            raise RuntimeError("Score feature dependencies were not collected")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as bundle:
            for file in sorted((Path(temp_dir) / "score-pack").rglob("*")):
                if file.is_file():
                    bundle.write(file, file.relative_to(Path(temp_dir)))
    print(f"Created {output} from {copied} files")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_pack(args.output)


if __name__ == "__main__":
    main()
