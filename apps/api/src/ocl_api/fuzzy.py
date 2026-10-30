"""Small string distances for spotting the same name spelled two ways (OCR-2a2): an OCR model
that "corrects" a name, or a book that spells a person differently in two tables."""

from __future__ import annotations


def edit_distance(a: str, b: str, limit: int | None = None) -> int:
    """Levenshtein distance; stops early (returns limit + 1) once it must exceed `limit`."""
    if len(a) < len(b):
        a, b = b, a
    if limit is not None and len(a) - len(b) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if limit is not None and min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def near(a: str, b: str, max_edits: int = 2) -> bool:
    """Different but within `max_edits` (a name of 4+ letters, so short words never match)."""
    return a != b and min(len(a), len(b)) >= 4 and edit_distance(a, b, max_edits) <= max_edits
