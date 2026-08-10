import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from practice_lab.config import ensure_directories
from practice_lab.storage import bootstrap_public_data, export_static_assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Sync JSON results only and clear public/audio for lightweight publishing.",
    )
    args = parser.parse_args()

    ensure_directories()
    bootstrap_public_data()
    export_static_assets(include_audio=not args.metadata_only)
    if args.metadata_only:
        print("Exported results into public/ without audio files.")
    else:
        print("Exported runtime data into public/.")


if __name__ == "__main__":
    main()
