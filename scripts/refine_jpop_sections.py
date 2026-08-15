from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from practice_lab.jpop_sections import refine_jpop_section_labels


EXCLUDED_RESULT_FILES = {"manifest.json", "folders.json"}


def refine_library(root: Path, *, dry_run: bool = False) -> dict:
    result_dir = root / "data" / "results"
    public_result_dir = root / "public" / "results"
    changed_sessions: list[dict] = []
    scanned = 0

    for result_file in sorted(result_dir.glob("*.json")):
        if result_file.name in EXCLUDED_RESULT_FILES:
            continue
        scanned += 1
        data = json.loads(result_file.read_text(encoding="utf-8"))
        sections = list(data.get("sections") or [])
        refined, changes = refine_jpop_section_labels(sections)
        if not changes:
            continue

        if "jpopOriginalSections" not in data:
            data["jpopOriginalSections"] = deepcopy(sections)
        data["sections"] = refined
        data["jpopLabeling"] = {
            "version": 1,
            "appliedAt": datetime.now(timezone.utc).isoformat(),
            "changes": changes,
        }
        changed_sessions.append(
            {
                "id": data.get("id") or result_file.stem,
                "title": data.get("title") or result_file.stem,
                "changes": len(changes),
            }
        )
        if dry_run:
            continue

        rendered = json.dumps(data, ensure_ascii=False, indent=2)
        result_file.write_text(rendered, encoding="utf-8")
        public_result_dir.mkdir(parents=True, exist_ok=True)
        (public_result_dir / result_file.name).write_text(rendered, encoding="utf-8")

    return {
        "root": str(root.resolve()),
        "scanned": scanned,
        "changed": len(changed_sessions),
        "labelChanges": sum(item["changes"] for item in changed_sessions),
        "sessions": changed_sessions,
        "dryRun": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Refine section labels for common J-pop structures")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refine_library(args.root, dry_run=args.dry_run), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
