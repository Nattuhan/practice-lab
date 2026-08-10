import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.split_stems import main


if __name__ == "__main__":
    raise SystemExit(main())
