"""Every action the API writes to curriculum_events has a Thai label on the curriculum page, so
the history never shows a raw code (R2 L-03: an approved สมอ.08 showed 'smo08')."""

from __future__ import annotations

import re
from pathlib import Path

from ocl_api.curricula import ACTIONS

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "apps/api/src/ocl_api"
PAGE = ROOT / "apps/web/src/app/(app)/curricula/[id]/curriculum-client.tsx"


def written_actions() -> set[str]:
    """Transitions plus the actions spelled out in an INSERT INTO curriculum_events."""
    found = set(ACTIONS)
    for py in SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for m in re.finditer(
            r"INSERT INTO curriculum_events.{0,200}?VALUES \(([^)]*)\)", text, re.S
        ):
            found |= set(re.findall(r"'([a-z0-9_]+)'", m.group(1)))
    return found - {"import", "review", "verified", "published"}  # statuses, not actions


def test_every_written_action_has_a_thai_label() -> None:
    m = re.search(r"const ACTION_TH: Record<string, string> = \{(.+?)\};", PAGE.read_text("utf-8"))
    assert m, "the page keeps its labels in ACTION_TH"
    labels = set(re.findall(r"(\w+):", m.group(1)))
    acts = written_actions()
    assert {"create", "edit", "smo08"} <= acts, acts  # the scan itself still finds them
    assert acts <= labels, f"no Thai label: {sorted(acts - labels)}"
