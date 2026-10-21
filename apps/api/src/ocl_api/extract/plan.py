"""Part 3: แผนการรับนิสิต (chapter 2 item 4) + รูปแบบการสอน.

The admission plan is a ชั้นปี × ปีการศึกษา table with รวม and คาดว่าจะสำเร็จการศึกษา rows.
Graduate books repeat it per plan (แผน 1 / แผน 2) or put both plans side by side under
each year; a book with majors repeats it per major. The teaching mode enum of the
customer's form (On-site / Online / Hybrid / WIL) is never written as such in the
books, so it is inferred from chapter 1 (online delivery, CWIE) and flagged. Teaching
methods per PLO come from the chapter 5 item 1 table when present. Deterministic.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import PartResult, chapter, meta, paragraphs, subsection, to_int
from ocl_api.ingest.model import Block, Document, Paragraph, Table

RE_YEAR = re.compile(r"^\s*(?:ปี(?:การศึกษา)?\s*)?(25\d\d)\s*$")
RE_LEVEL = re.compile(r"^\s*ชั้นปีที่\s*([\d๐-๙]+)")
RE_PLAN_NAME = re.compile(r"^\s*(?:4\.\d\s*)?(แผน\s*\d+(?:\.\d+)?[^\n]*|วิชาเอก[^\n]*|สาขา[^\n]*)$")
RE_METHOD_HEADER = re.compile(r"วิธีการสอน|กลยุทธ์การสอน|กิจกรรมการเรียนรู้|วิธีการจัดการเรียน")


def _cell_int(c: str) -> int:
    c = (c or "").strip()
    if not c or c in {"-", "–", "—"}:
        return 0
    return to_int(c) or 0


def _year_row(t: Table) -> tuple[int, dict[int, str]] | None:
    for i, row in enumerate(t.rows[:4]):
        years = {j: m.group(1) for j, c in enumerate(row) if (m := RE_YEAR.match(c or ""))}
        if len(years) >= 2:
            return i, years
    return None


def parse_plan_table(t: Table, name: str | None) -> list[dict[str, Any]]:
    """One table -> one plan, or several when a sub-header row splits each year into
    แผน 1 / แผน 2 columns."""
    found = _year_row(t)
    if not found:
        return []
    header_i, years = found
    # carry a year across the empty columns of a merged header ("2569 | | 2570 | ...")
    col_year: dict[int, str] = {}
    last = None
    for j in range(len(t.rows[header_i])):
        if j in years:
            last = years[j]
        if last and j > 0:
            col_year[j] = last
    sub = t.rows[header_i + 1] if header_i + 1 < len(t.rows) else []
    sub_labels = {j: c.strip() for j, c in enumerate(sub) if re.match(r"^\s*แผน", c or "")}
    variants: list[tuple[str | None, dict[int, str]]]
    if sub_labels:
        names = sorted({v for v in sub_labels.values()})
        variants = [
            (v, {j: col_year[j] for j, lab in sub_labels.items() if lab == v and j in col_year})
            for v in names
        ]
        data_start = header_i + 2
    else:
        variants = [(name, {j: y for j, y in col_year.items() if j in years})]
        data_start = header_i + 1
    out = []
    for vname, cols in variants:
        ordered = sorted(cols.items())
        ylist = [y for _, y in ordered]
        plan = {
            "name": vname if vname else name,
            "years": ylist,
            "rows": [],
            "total": None,
            "graduates": None,
            "meta": meta("high", t.page, " | ".join(c for c in t.rows[header_i] if c)[:160]),
        }
        for row in t.rows[data_start:]:
            label = re.sub(r"\s+", " ", (row[0] or "")).strip()
            if not label:
                continue
            vals = [_cell_int(row[j]) if j < len(row) else 0 for j, _ in ordered]
            if RE_LEVEL.match(label):
                plan["rows"].append({"label": label, "values": vals})
            elif label.startswith("รวม"):
                plan["total"] = vals
            elif "สำเร็จ" in label or "จบ" in label:
                plan["graduates"] = vals
        if plan["rows"]:
            out.append(plan)
    return out


def _name_before(blocks: list[Block], index: int) -> str | None:
    for b in reversed(blocks[max(0, index - 3) : index]):
        if isinstance(b, Paragraph) and b.text.strip():
            m = RE_PLAN_NAME.match(b.text.strip())
            return re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    return None


def parse_methods(blocks: list[Block]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for b in blocks:
        if not isinstance(b, Table) or not b.rows or len(b.rows[0]) < 2:
            continue
        head = b.rows[0]
        mcol = next((j for j, c in enumerate(head) if RE_METHOD_HEADER.search(c or "")), None)
        if mcol is None:
            continue
        for row in b.rows[1:]:
            outcome = re.sub(r"\s+", " ", row[0] or "").strip()
            methods = re.sub(r"\s+", " ", row[mcol] or "").strip() if mcol < len(row) else ""
            if outcome and methods:
                rows.append(
                    {
                        "outcome": outcome,
                        "methods": methods,
                        "meta": meta("high", b.page, outcome[:80]),
                    }
                )
    return rows


def extract_plan(doc: Document, gateway=None) -> PartResult:  # noqa: ARG001 - no LLM here
    res = PartResult(
        key="plan",
        data={"plans": [], "teaching_modes": [], "teaching_methods": [], "meta": {}},
    )
    ch2 = chapter(doc, "2")
    if ch2 is None:
        res.notes.append("chapter 2 not found")
    else:
        blocks = subsection(ch2.blocks, "4")
        for i, b in enumerate(blocks):
            if isinstance(b, Table):
                res.data["plans"].extend(parse_plan_table(b, _name_before(blocks, i)))
        if not res.data["plans"]:
            res.notes.append("no ชั้นปี × ปีการศึกษา table under chapter 2 item 4")
    plans = res.data["plans"]
    if plans:
        res.data["intake_per_year"] = sum(p["rows"][0]["values"][0] for p in plans if p["rows"])
        res.data["years"] = plans[0]["years"]
        res.data["duration_years"] = max(len(p["rows"]) for p in plans)
    res.data["count"] = len(plans)

    # --- teaching modes (inferred from chapter 1) ---
    ch1 = chapter(doc, "1")
    text1 = " ".join(p.text for p in paragraphs(ch1.blocks)) if ch1 else ""
    ch4 = chapter(doc, "4")
    text4 = " ".join(p.text for p in paragraphs(ch4.blocks)) if ch4 else ""
    online = bool(re.search(r"ออนไลน์|online", text1, re.I)) and "□ หลักสูตรออนไลน์" not in text1
    online = online and bool(
        re.search(r"(ผ่าน|ระบบ)\s*ออนไลน์|☑\s*หลักสูตรออนไลน์|R\s*หลักสูตรออนไลน์", text1)
    )
    wil = bool(re.search(r"CWIE|สหกิจศึกษา|ฝึกปฏิบัติ(?:งาน)?วิชาชีพ|ฝึกงาน", text4))
    modes = ["On-site"] + (["Online", "Hybrid"] if online else []) + (["WIL"] if wil else [])
    res.data["teaching_modes"] = modes
    res.data["meta"]["teaching_modes"] = meta(
        "low",
        ch1.page if ch1 else None,
        ("พบ 'ออนไลน์' ในหมวดที่ 1 · " if online else "")
        + ("พบสหกิจ/ฝึกงานในหมวดที่ 4" if wil else "ไม่พบสหกิจ/ฝึกงานในหมวดที่ 4"),
        inferred=True,
        note="เล่มไม่ได้ระบุรูปแบบการสอนเป็นรายการ ระบบอนุมานจากหมวด 1 และ 4",
    )

    # --- teaching methods per PLO (chapter 5 item 1) ---
    ch5 = chapter(doc, "5")
    if ch5 is not None:
        res.data["teaching_methods"] = parse_methods(subsection(ch5.blocks, "1"))
    return res
