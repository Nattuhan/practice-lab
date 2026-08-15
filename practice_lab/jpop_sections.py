from __future__ import annotations

from copy import deepcopy


def _canonical_label(value: object) -> str:
    label = str(value or "").strip().lower().replace("_", "-")
    if label in {"aメロ", "a-melo"}:
        return "verse"
    if label in {"bメロ", "b-melo"}:
        return "pre-chorus"
    if label in {"サビ", "hook"}:
        return "chorus"
    return label


def refine_jpop_section_labels(sections: list[dict]) -> tuple[list[dict], list[dict]]:
    """Interpret model sections using common J-pop A/B/chorus structure.

    All-In-One sometimes emits two distinct adjacent ``verse`` segments before
    a chorus.  The boundary is still valuable: in J-pop, the final one usually
    functions as the B section that leads into the chorus.  Only that narrowly
    defined context is rewritten, leaving isolated verses and verse repetitions
    elsewhere untouched.
    """

    refined = deepcopy(sections)
    changes: list[dict] = []
    index = 0
    while index < len(refined):
        if _canonical_label(refined[index].get("label")) != "verse":
            index += 1
            continue

        run_start = index
        while index + 1 < len(refined) and _canonical_label(refined[index + 1].get("label")) == "verse":
            index += 1
        run_end = index
        next_label = _canonical_label(refined[run_end + 1].get("label")) if run_end + 1 < len(refined) else ""

        if run_end > run_start and next_label == "chorus":
            original = str(refined[run_end].get("label") or "verse")
            refined[run_end]["label"] = "pre-chorus"
            changes.append(
                {
                    "index": run_end,
                    "from": original,
                    "to": "pre-chorus",
                    "reason": "consecutive-verse-before-chorus",
                }
            )
        index += 1

    return refined, changes
