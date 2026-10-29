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


def test_manual_states_the_current_number_of_test_cases():
    """test-manual_ocl.md quotes the size of test-script_ocl.csv; a case added to one only fails."""
    import csv
    import re

    with (DOCS / "testing/test-script_ocl.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in list(csv.reader(f))[1:] if r and not r[1].startswith("ตัวอย่าง")]
    manual = (DOCS / "testing/test-manual_ocl.md").read_text(encoding="utf-8")
    m = re.search(r"`test-script_ocl\.csv` \((\d+) กรณีทั้งหมด", manual)
    assert m, "the manual names the case count of test-script_ocl.csv"
    assert int(m.group(1)) == len(rows)
