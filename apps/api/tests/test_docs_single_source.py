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
    # the table of categories counts each one (it drifted once: K said 10 with 17 in the CSV)
    from collections import Counter

    per = Counter(r[0].split("-")[0] for r in rows)
    table = dict(re.findall(r"^\| (?:\*\*)?([A-Z]) [^|]*\| [^|]*\| (\d+) \|", manual, re.M))
    assert {k: int(v) for k, v in table.items()} == dict(per)


def test_fs_round_names_exactly_the_cases_of_its_script():
    """fs-round_ocl.md (round R2) lists its cases as ranges and states how many; both must match
    r2-test-script_ocl.csv, which tools/test_round.py builds, instead of drifting."""
    import csv
    import re

    with (DOCS / "testing/r2-test-script_ocl.csv").open(encoding="utf-8-sig", newline="") as f:
        ids = {r[0] for r in list(csv.reader(f))[1:] if r and r[0] != "EX-00"}
    doc = (DOCS / "testing/fs-round_ocl.md").read_text(encoding="utf-8")
    line = re.search(r"^\*\*กรณีในรอบนี้:\*\* (.+)$", doc, re.M)
    assert line, "the round names its cases"
    listed: set[str] = set()
    for cat, a, b in re.findall(r"([A-Z])-(\d{2})(?:–[A-Z]-(\d{2}))?", line.group(1)):
        listed |= {f"{cat}-{n:02d}" for n in range(int(a), int(b or a) + 1)}
    assert listed == ids, f"extra: {sorted(listed - ids)} · missing: {sorted(ids - listed)}"
    m = re.search(r"สคริปต์รอบนี้ (\d+) กรณี", doc)
    assert m and int(m.group(1)) == len(ids)
    groups = re.search(r"^\| กลุ่ม \| กรณี \| จำนวน \|\n\|---\|---\|---\|\n((?:\|.*\n)+)", doc, re.M)
    assert groups, "the round counts its groups"
    assert sum(int(r.rsplit("|", 2)[1]) for r in groups.group(1).splitlines()) == len(ids)
    # the day plan places every case of the round once
    order = doc.split("## 3. ลำดับ", 1)[1].split("\n## 4.", 1)[0]
    days = [r.split("|")[2] for r in order.splitlines() if re.match(r"\| (\d|PM) ", r)]
    placed: list[str] = []
    for cat, a, b in re.findall(r"([A-Z])-(\d{2})(?:–[A-Z]-(\d{2}))?", " · ".join(days)):
        placed += [f"{cat}-{n:02d}" for n in range(int(a), int(b or a) + 1)]
    assert sorted(placed) == sorted(ids), (
        f"twice: {sorted({p for p in placed if placed.count(p) > 1})} · "
        f"missing: {sorted(ids - set(placed))} · extra: {sorted(set(placed) - ids)}"
    )
