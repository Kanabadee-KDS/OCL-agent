"""Release scope lives in docs/brd/00-overview.md §7 only; docs/plan.md points there."""

from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[3] / "docs"


def test_release_table_is_not_copied_into_the_plan():
    plan = (DOCS / "plan.md").read_text(encoding="utf-8")
    brd = (DOCS / "brd/00-overview.md").read_text(encoding="utf-8")
    assert "| Release |" in brd
    assert "| Release |" not in plan, "release scope belongs in docs/brd/00-overview.md §7"
    assert "docs/brd/00-overview.md` §7" in plan
