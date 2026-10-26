#!/usr/bin/env python3
"""Expected values for the team's test script, generated from the code instead of typed by hand.

Runs the parser-only extraction (what `ocl extract --no-llm` does) on the sample books and
writes what the *current* code produces into
  docs/testing/test-script_ocl.csv       rows C-xx (counts per part, 'ควรตรวจ' checks) and the
  docs/testing/r1-2-test-script_ocl.csv  "จำนวนรายการ = …" prefix of rows V-xx (both files)
  docs/testing/test-manual_ocl.md        ภาคผนวก ก (counts per book)
so testers compare the screen with this build, not with numbers copied from an older one
(R1 lesson, 26 ต.ค. 2569: 4 of the 5 failures were a stale answer key).

  uv run python tools/expected_values.py            # rewrite both files
  uv run python tools/expected_values.py --check    # exit 1 if a file is stale (run before deploy)

Books come from samples/curriculum (not in git). Each is ingested and extracted once into
<work>/<slug>/ (default data/expected) and reused unless --force.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ocl_api.extract.pipeline import extract
from ocl_api.ingest.pipeline import ingest

ROOT = Path(__file__).resolve().parents[1]
CSVS = [
    ROOT / "docs/testing/test-script_ocl.csv",  # every case
    ROOT / "docs/testing/r1-2-test-script_ocl.csv",  # round R1-2: without cases passed in R1
]
MANUAL = ROOT / "docs/testing/test-manual_ocl.md"
NOTE_PREFIX = "ตัวเลขในตารางสร้างโดย `tools/expected_values.py`"

# file name in samples/curriculum (= the CSV's ข้อมูลทดสอบ column) -> column of ภาคผนวก ก,
# in the table's column order. The scanned PDF has no C/V rows, so it is not here.
BOOKS = [
    ("วท.บ. วิทยาการการเปลี่ยนแปลงสภาพภูมิอากาศ.docx", "ภูมิอากาศ"),
    ("4.1.4 วท.บ.วิทยาศาสตร์การอาหารและโภชนาการ ปรั.pdf", "อาหาร PDF"),
    ("ปร.ด. เศรษฐศาสตร์เพื่อการพัฒนาอย่างยั่งยื.docx", "ปร.ด."),
    ("ศศ.บ. การจัดการภูมิสังคมและวัฒนธรรม (ปป.69).docx", "ศศ.บ."),
    ("ศศ.ม. เศรษฐศาสตร์ธุรกิจและการจัดการ (ปป.69).docx", "ศศ.ม."),
]
# section number -> (label as the review page numbers them, where it sits in the book)
SECTIONS = {
    1: ("1 ข้อมูลหลัก (ฟิลด์ที่มีค่า)", "หมวด 1 ข้อ 1–10, 13"),
    2: ("2 อาจารย์ (คน / ผู้รับผิดชอบ)", "หมวด 1 ข้อ 11–12"),
    3: ("3 แผนรับ (ตาราง / รับปีละ)", "หมวด 2 ข้อ 4"),
    4: ("4 PLO", "หมวด 3 ข้อ 1"),
    5: ("5 KSEC (รายการ)", "หมวด 3 ตาราง"),
    6: ("6 โครงสร้าง (แถว)", "หมวด 4 ข้อ 1–2"),
    7: ("7 ชุดวิชา", "หมวด 4 ข้อ 3"),
    8: ("8 รายวิชา", "หมวด 4 ข้อ 2–3"),
    9: ("9 Mapping (4.1 / 4.2 แถว)", "หมวด 4 ข้อ 4.1–4.2"),
    10: ("10 มติ (อ่านได้ / เล่มเว้นว่าง)", "หมวด 1 ข้อ 13"),
}


def slug(name: str) -> str:
    return re.sub(r"[^0-9A-Za-zก-๙]+", "-", name).strip("-")[:50]


def run_book(book: Path, work: Path, *, force: bool) -> Path:
    """Parser-only extraction of one book; returns the extract dir (holds report.json)."""
    d = work / slug(book.stem)
    out = d / "extract"
    if (out / "report.json").exists() and not force:
        return out
    ingest(book, d / "ingest")
    extract(d / "ingest", gateway=None, out_dir=out)
    return out


def load(out: Path, part: str) -> dict[str, Any]:
    j = json.loads((out / f"{part}.json").read_text(encoding="utf-8"))
    return j.get("data", j)


def expected(out: Path) -> dict[str, Any]:
    """Counts per section in the three spellings the documents use, plus the warn checks."""
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    n = {k: v["count"] or 0 for k, v in rep["parts"].items()}
    teachers, plan, plo, mapping, appr = (
        load(out, p) for p in ("teachers", "plan", "plo", "mapping", "appr")
    )
    plans = sorted({p["plan"] for p in plo.get("plos", []) if p.get("plan")})
    plo_txt = str(n["plo"]) + (f" ({n['plo'] // len(plans)} × {len(plans)} แผน)" if plans else "")
    pending = sum(1 for a in appr.get("approvals", []) if a.get("pending"))
    resp = teachers.get("responsible_count") or 0
    intake = plan.get("intake_per_year") or "–"
    rows41, rows42 = mapping.get("count") or 0, mapping.get("ksec_count") or 0
    # (text of the C row, text after "จำนวนรายการ = " in the V row, cell of ภาคผนวก ก)
    sec = {
        1: (f"1 ข้อมูลหลัก {n['info']} ฟิลด์", f"{n['info']}", f"{n['info']}"),
        2: (
            f"2 อาจารย์ {n['teachers']} คน / ผู้รับผิดชอบ {resp}",
            f"{n['teachers']} คน / ผู้รับผิดชอบ {resp}",
            f"{n['teachers']} / {resp}",
        ),
        3: (
            f"3 แผนรับ {n['plan']} ตาราง / รับปีละ {intake}",
            f"{n['plan']} ตาราง / รับปีละ {intake}",
            f"{n['plan']} / {intake}",
        ),
        4: (f"4 PLO {plo_txt}", plo_txt, plo_txt),
        5: (f"5 KSEC {n['ksec']}", f"{n['ksec']}", f"{n['ksec']}"),
        6: (f"6 โครงสร้าง {n['structure']} แถว", f"{n['structure']} แถว", f"{n['structure']}"),
        7: (f"7 ชุดวิชา {n['modules']}", f"{n['modules']}", f"{n['modules']}"),
        8: (f"8 รายวิชา {n['courses']}", f"{n['courses']}", f"{n['courses']}"),
        9: (
            f"9 Mapping 4.1 {rows41} แถว / 4.2 {rows42} แถว",
            f"4.1 {rows41} แถว / 4.2 {rows42} แถว",
            f"{rows41} / {rows42}",
        ),
        10: (
            f"10 มติ อ่านได้ {n['appr']} / เล่มเว้นว่าง {pending}",
            f"อ่านได้ {n['appr']} / เล่มเว้นว่าง {pending}",
            f"{n['appr']} / {pending}",
        ),
    }
    checks = rep["checks"]
    warns = [i for i in checks["items"] if i["status"] == "warn"]
    fails = [i for i in checks["items"] if i["status"] == "fail"]
    return {"sections": sec, "warns": warns, "fails": fails, "pass": checks["pass"]}


def checks_text(e: dict[str, Any]) -> str:
    head = f"ผ่าน {e['pass']} · ควรตรวจ {len(e['warns'])} · พบปัญหา {len(e['fails'])}"
    items = " ".join(f"({i + 1}) {w['key']}: {w['message']}" for i, w in enumerate(e["warns"]))
    return f"{head} · รายการ 'ควรตรวจ' ครบตามนี้ (ลำดับไม่สำคัญ): {items}"


def update_csv(rows: list[dict[str, str]], exp: dict[str, dict[str, Any]]) -> int:
    changed = 0
    for r in rows:
        e = exp.get(r["ข้อมูลทดสอบ"])
        if e is None:
            continue
        new = None
        if r["TC_ID"].startswith("C-") and r["หัวข้อทดสอบ"].startswith("จำนวนรายการ"):
            new = " · ".join(e["sections"][k][0] for k in range(1, 11))
        elif r["TC_ID"].startswith("C-") and r["หัวข้อทดสอบ"].startswith("ผลตรวจความสอดคล้อง"):
            new = checks_text(e)
        elif r["TC_ID"].startswith("V-"):
            m = re.search(r"ส่วนที่ (\d+)", r["หัวข้อทดสอบ"])
            if m and r["ผลที่คาดหวัง"].startswith("จำนวนรายการ = "):
                v = e["sections"][int(m.group(1))][1]
                new = re.sub(
                    r"^จำนวนรายการ = .*? · ", f"จำนวนรายการ = {v} · ", r["ผลที่คาดหวัง"], count=1
                )
        if new is not None and new != r["ผลที่คาดหวัง"]:
            r["ผลที่คาดหวัง"] = new
            changed += 1
    return changed


def csv_text(rows: list[dict[str, str]], fields: list[str]) -> str:
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return "﻿" + buf.getvalue()


def manual_text(text: str, exp: dict[str, dict[str, Any]], stamp: str) -> str:
    cols = [name for _, name in BOOKS]
    by_col = {name: exp[f] for f, name in BOOKS}
    lines = text.split("\n")
    first = next(i for i, ln in enumerate(lines) if ln.startswith("| 1 ข้อมูลหลัก"))
    last = next(i for i, ln in enumerate(lines) if ln.startswith("| 10 มติ"))
    table = [
        f"| {SECTIONS[k][0]} | {SECTIONS[k][1]} | "
        + " | ".join(by_col[c]["sections"][k][2] for c in cols)
        + " |"
        for k in range(1, 11)
    ]
    note = (
        f"{NOTE_PREFIX} จากโค้ด {stamp} · ส่วนที่ 1 นับเฉพาะฟิลด์ที่มีค่า "
        "(หน้าจอแสดง 'ฟิลด์ 34 · ว่าง N' → ฟิลด์ที่มีค่า = 34 − N) · ถ้าหน้าจอไม่ตรงตารางนี้ "
        "ให้เปิด issue แล้ว PM รันสคริปต์ซ้ำบน build ที่ทดสอบ ห้ามแก้ตัวเลขในตารางเอง"
    )
    tail = lines[last + 1 :]
    tail = [ln for ln in tail if not ln.startswith(NOTE_PREFIX)]
    # keep one blank line after the table, then the note, then whatever followed before
    while tail and tail[0] == "":
        tail.pop(0)
    return "\n".join(lines[:first] + table + ["", note, ""] + tail)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--books", default=str(ROOT / "samples/curriculum"))
    ap.add_argument("--work", default=str(ROOT / "data/expected"), help="ingest/extract output")
    ap.add_argument("--force", action="store_true", help="re-run books that already have output")
    ap.add_argument("--check", action="store_true", help="only report whether the files are stale")
    a = ap.parse_args()

    books = Path(a.books)
    missing = [f for f, _ in BOOKS if not (books / f).exists()]
    if missing:
        print("missing books in", books, *missing, sep="\n  ", file=sys.stderr)
        return 2
    exp: dict[str, dict[str, Any]] = {}
    for f, _ in BOOKS:
        out = run_book(books / f, Path(a.work), force=a.force)
        exp[f] = expected(out)
        print(
            f,
            "·",
            " · ".join(exp[f]["sections"][k][2] for k in range(1, 11)),
            "· warn",
            len(exp[f]["warns"]),
        )

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
    ).stdout.strip()
    stamp = f"commit {commit or '?'} ({dt.date.today().isoformat()})"

    new_csvs, changed = {}, 0
    for path in CSVS:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            fields = list(reader.fieldnames or [])
            rows = list(reader)
        n = update_csv(rows, exp)
        print(f"{path.name}: {n} row(s) differ")
        changed += n
        new_csvs[path] = csv_text(rows, fields)
    old_manual = MANUAL.read_text(encoding="utf-8")
    new_manual = manual_text(old_manual, exp, stamp)

    # the stamp line names the commit and date, so it differs on every run: compare without it
    def body(t: str) -> list[str]:
        return [ln for ln in t.split("\n") if not ln.startswith(NOTE_PREFIX)]

    manual_changed = body(new_manual) != body(old_manual)
    print(f"manual: {'differs' if manual_changed else 'same'}")
    if a.check:
        return 1 if (changed or manual_changed) else 0
    for path, text in new_csvs.items():
        path.write_text(text, encoding="utf-8", newline="")
    MANUAL.write_text(new_manual, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
