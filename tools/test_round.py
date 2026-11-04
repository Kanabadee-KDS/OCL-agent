#!/usr/bin/env python3
"""Round R2 test script: every case the team has no usable result for, built from the results.

  docs/testing/test-script_ocl.csv  every case (the answer key, kept current by expected_values.py)
  docs/testing/results_ocl.json     the team's last result per case and a fingerprint of the row
                                     they tested (rounds R1 and R1-2)
  -> docs/testing/r2-test-script_ocl.csv

A case is in the round unless the team passed it *and* the row still reads as it did when they
tested it, so a case nobody ran, one that failed, one marked pass with no actual result, and one
whose steps or expected result changed afterwards all come back. A pass whose row is unchanged
but whose code changed since carries "retest" (what changed) and comes back as a regression.
Never edit the output by hand: record results in results_ocl.json (or fix the answer key),
then run this.

  uv run python tools/test_round.py          # write
  uv run python tools/test_round.py --check  # exit 1 when the round file is stale (tests)
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs/testing/test-script_ocl.csv"
RESULTS = ROOT / "docs/testing/results_ocl.json"
OUT = ROOT / "docs/testing/r2-test-script_ocl.csv"
ROUND = "R2"
REASON = f"ที่มาในรอบ {ROUND}"
# what a tester reads to run a case; a change in any of these makes an earlier result stale
FIELDS = {
    "หัวข้อทดสอบ": "หัวข้อ",
    "บัญชี/บทบาท": "บัญชี",
    "เงื่อนไขก่อนทดสอบ": "เงื่อนไขก่อนทดสอบ",
    "ขั้นตอน": "ขั้นตอน",
    "ข้อมูลทดสอบ": "ข้อมูลทดสอบ",
    "ผลที่คาดหวัง": "ผลที่คาดหวัง",
}


def fingerprint(row: dict[str, str]) -> str:
    """Six short hashes, one per field in FIELDS, so a stale result can say what changed."""
    return " ".join(hashlib.sha1(row[f].encode()).hexdigest()[:6] for f in FIELDS)


def changed(row: dict[str, str], tested: str) -> list[str]:
    return [
        FIELDS[f]
        for f, a, b in zip(FIELDS, fingerprint(row).split(), tested.split(), strict=True)
        if a != b
    ]


def load_script() -> tuple[list[str], list[dict[str, str]]]:
    with SCRIPT.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def load_results() -> dict[str, dict[str, str]]:
    return {e["case"]: e for e in json.loads(RESULTS.read_text(encoding="utf-8"))["results"]}


def reason(row: dict[str, str], res: dict[str, str] | None) -> str | None:
    """Why the case is in this round, or None when the team's pass still holds."""
    if res is None:
        return "ใหม่ · ยังไม่เคยทดสอบ"
    rnd, status, note = res["round"], res["status"], res.get("note", "")
    diff = changed(row, res["row"])
    moved = f"{' '.join(diff)}เปลี่ยนหลังทดสอบ" if diff else ""
    if status == "ผ่าน":
        if diff:
            return f"ผ่านในรอบ {rnd} แต่{moved} · ทดสอบกับสคริปต์ใหม่"
        if res.get("retest"):  # same row, but the code behind it changed since the pass
            return f"ผ่านในรอบ {rnd} แต่โค้ดเปลี่ยนหลังทดสอบ: {res['retest']} · ทดสอบซ้ำ"
        return None
    head = {
        "ไม่ผ่าน": f"ไม่ผ่านในรอบ {rnd}",
        "ไม่ได้ทดสอบ": f"รอบ {rnd} ไม่ได้ทดสอบ",
        "ไม่มีในไฟล์ผล": f"อยู่ในรอบ {rnd} แต่ไม่มีในไฟล์ผลที่ทีมส่งกลับ",
        "ผ่านแต่ไม่มีผลจริง": f"รอบ {rnd} บันทึกผ่านแต่ช่องผลจริงว่าง จึงไม่นับเป็นผล",
    }[status]
    return " · ".join(p for p in (head, note, moved) if p)


def round_rows() -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = load_script()
    results = load_results()
    out = []
    for row in rows:
        if row["TC_ID"] == "EX-00":
            why: str | None = "ตัวอย่างการกรอก"
        else:
            why = reason(row, results.get(row["TC_ID"]))
        if why:
            out.append({"TC_ID": row["TC_ID"], REASON: why, **{k: row[k] for k in fields[1:]}})
    return ["TC_ID", REASON, *fields[1:]], out


def round_cases() -> list[str]:
    return [r["TC_ID"] for r in round_rows()[1] if r["TC_ID"] != "EX-00"]


def render() -> str:
    fields, rows = round_rows()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return "﻿" + buf.getvalue()


def summary() -> str:
    _, rows = round_rows()
    rows = [r for r in rows if r["TC_ID"] != "EX-00"]
    why = Counter(r[REASON].split(" · ")[0].split(" แต่")[0] for r in rows)
    who = Counter(r["ผู้ทำ"] for r in rows)
    return f"{len(rows)} cases · " + " · ".join(f"{k} {v}" for k, v in (why | who).items())


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"stale: {OUT.relative_to(ROOT)} · run tools/test_round.py")
            return 1
        print("ok")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} · {summary()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
