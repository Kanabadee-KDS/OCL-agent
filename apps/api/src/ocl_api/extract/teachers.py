"""Part 2: อาจารย์ผู้รับผิดชอบหลักสูตร / อาจารย์ประจำหลักสูตร (chapter 1 items 11–12).

Both items are the same 4-column table (ลำดับ · ชื่อ · คุณวุฒิ ตรี-โท-เอก (สาขา) ปีที่จบ ·
สถาบัน). Item 12 lists everyone and marks the responsible ones with "*"; item 11 lists the
responsible ones only. One teacher's degrees sit in a single cell, one per line in
.docx (some wrapped) and space-separated in PDF, so degrees are cut at their graduation
year and institutions are aligned to them by count. The HURIS match itself belongs to
the main system; this part only produces the names and qualifications to match on.
Deterministic: no LLM.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import PartResult, chapter, meta, subsection, tables
from ocl_api.ingest.model import Document, Table

RANKS = [
    ("ศาสตราจารย์", "ศ."),
    ("รองศาสตราจารย์", "รศ."),
    ("ผู้ช่วยศาสตราจารย์", "ผศ."),
    ("อาจารย์", "อาจารย์"),
]
RE_RANK = re.compile(r"^\s*(ศาสตราจารย์|รองศาสตราจารย์|ผู้ช่วยศาสตราจารย์|ศ\.|รศ\.|ผศ\.|อาจารย์|อ\.)\s*")
RE_DR = re.compile(r"^\s*(ดร\.|Dr\.)\s*")
RE_ORDER = re.compile(r"^\s*(\d+)\s*(\*?)\s*$")
RE_YEAR = re.compile(r",?\s*(25\d\d|19\d\d|20\d\d)\b")
RE_THAI_INST = re.compile(r"(?=มหาวิทยาลัย|สถาบัน|จุฬาลงกรณ์|วิทยาลัย|โรงเรียน|โรงพยาบาล)")
LEVEL_RULES = [
    (
        re.compile(
            r"(ด\.$|^Ph\.?D|^D\.|^Dr\.|^Doctor|^Ed\.D|^D\.?Eng|^Sc\.?D|^DBA|^DEc|^DSc)", re.I
        ),
        "เอก",
    ),
    (re.compile(r"(ม\.$|^M\.|^MA\b|^MS\b|^MBA|^MSc|^Master|^PDSC|^Grad)", re.I), "โท"),
    (re.compile(r"(บ\.$|^B\.|^BA\b|^BS\b|^Bachelor|^LL\.?B)", re.I), "ตรี"),
]


def split_name(raw: str) -> dict[str, Any]:
    """'ผู้ช่วยศาสตราจารย์\\nดร.ภัทรพงษ์ เกริกสกุล' -> rank ผศ., doctor True, name."""
    text = re.sub(r"\s+", " ", raw).strip()
    rank = None
    m = RE_RANK.match(text)
    if m:
        token = m.group(1)
        rank = next((abbr for full, abbr in RANKS if token in (full, abbr)), "อาจารย์")
        text = text[m.end() :]
    doctor = False
    m = RE_DR.match(text)
    if m:
        doctor = True
        text = text[m.end() :]
    return {"rank": rank, "doctor": doctor, "name": text.strip()}


def degree_level(degree: str) -> str | None:
    d = degree.strip()
    for rx, level in LEVEL_RULES:
        if rx.search(d):
            return level
    return None


def split_degrees(cell: str) -> list[dict[str, Any]]:
    """Cut the qualification cell at each graduation year; a trailing piece without a
    year becomes its own item so nothing is lost."""
    text = re.sub(r"\s+", " ", cell.replace("\n", " ")).strip()
    items: list[dict[str, Any]] = []
    pos = 0
    for m in RE_YEAR.finditer(text):
        chunk = text[pos : m.start()].strip(" ,")
        if chunk:
            items.append(_degree_item(chunk, int(m.group(1))))
        pos = m.end()
    tail = text[pos:].strip(" ,")
    if tail:
        items.append(_degree_item(tail, None))
    return items


def _degree_item(chunk: str, year: int | None) -> dict[str, Any]:
    field = None
    m = re.search(r"\((.+?)\)\s*$", chunk) or re.search(r"\((.+)\)", chunk)
    if m:
        field = re.sub(r"\s+", " ", m.group(1)).strip()
        degree = chunk[: m.start()].strip(" ,")
    elif "," in chunk:
        degree, field = (x.strip() for x in chunk.split(",", 1))
    else:
        degree = chunk
    return {
        "degree": degree.strip(),
        "field": field or None,
        "year": year,
        "level": degree_level(degree),
        "institution": None,
    }


COUNTRIES = (
    "USA|U\\.S\\.A\\.|UK|U\\.K\\.|England|France|Germany|Japan|Canada|Australia|Vietnam|Norway|"
    "Netherlands|Thailand|China|Taiwan|Korea|India|Belgium|Sweden|Switzerland|Italy|Spain|"
    "New Zealand|Hungary|Austria|Finland|Denmark|Malaysia|Singapore|Philippines|Indonesia"
)
RE_COUNTRY_END = re.compile(r"\b(?:" + COUNTRIES + r")\s+(?=[A-Zก-๙])")
RE_THAI_TO_LATIN = re.compile(r"(?<=[ก-๙])\s+(?=[A-Z])")
RE_THAI_INST_WORD = re.compile(r"มหาวิทยาลัย|สถาบัน|จุฬาลงกรณ์")
RE_NEXT_THAI = re.compile(r"\s+(?=มหาวิทยาลัย|สถาบัน|จุฬาลงกรณ์|วิทยาลัย|โรงเรียน|โรงพยาบาล)")


def _cut_institutions(flat: str) -> list[str]:
    """Cut one line of institutions after a country name, at a Thai→Latin change and
    before the next Thai institution word."""
    cuts = {m.end() for m in RE_COUNTRY_END.finditer(flat)}
    cuts |= {m.start() for m in RE_THAI_TO_LATIN.finditer(flat)}
    cuts |= {m.start() for m in RE_NEXT_THAI.finditer(flat)}
    # two Thai institutions glued without a space ("จุฬาลงกรณ์มหาวิทยาลัยมหาวิทยาลัยธรรมศาสตร์")
    last = 0
    for m in RE_THAI_INST_WORD.finditer(flat):
        if flat[: m.start()].endswith("จุฬาลงกรณ์"):
            continue  # "จุฬาลงกรณ์มหาวิทยาลัย" is one name
        if m.start() > 0 and RE_THAI_INST_WORD.search(flat[last : m.start()]):
            cuts.add(m.start())
            last = m.start()
    parts, pos = [], 0
    for c in sorted(cuts):
        parts.append(flat[pos:c])
        pos = c
    parts.append(flat[pos:])
    return [p.strip(" ,") for p in parts if p.strip(" ,")]


RE_LATIN = re.compile(r"^[A-Za-z(]")


def split_institutions(cell: str, expected: int) -> list[str] | None:
    """Institutions in the same order as the degrees, or None when the text cannot be
    aligned with the degree count (wrapped names, PDF without line breaks)."""
    lines = [re.sub(r"\s+", " ", x).strip() for x in cell.split("\n") if x.strip()]
    if not lines or expected == 0:
        return None
    if len(lines) == expected:
        return lines
    if len(lines) < expected:
        parts = _cut_institutions(" ".join(lines))
        return parts if len(parts) == expected else None
    # more lines than degrees: Latin names wrap; merge a wrapped line into the one above
    merged = list(lines)
    while len(merged) > expected:
        cands = [
            i
            for i in range(1, len(merged))
            if RE_LATIN.match(merged[i]) and RE_LATIN.match(merged[i - 1])
        ]
        if not cands:
            break
        # prefer a line whose predecessor is obviously unfinished
        idx = next(
            (
                i
                for i in cands
                if re.search(r"(\bof|\band|&|,|-|\bfor|\bthe)$", merged[i - 1], re.I)
            ),
            cands[0],
        )
        merged[idx - 1] = merged[idx - 1] + " " + merged.pop(idx)
    return merged if len(merged) == expected else None


def _is_header(row: list[str]) -> bool:
    return any("ลำดับ" in (c or "") for c in row[:1]) or any("คุณวุฒิ" in (c or "") for c in row)


def parse_teacher_table(t: Table) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    group: str | None = None
    for row in t.rows:
        if _is_header(row) or len(row) < 3:
            continue
        first = (row[0] or "").strip()
        rest = [(c or "").strip() for c in row[1:]]
        if first and not any(rest):
            group = first  # "วิชาเอกการจัดการภูมิสังคม"
            continue
        m = RE_ORDER.match(first)
        name_cell = row[1] if len(row) > 1 else ""
        if not m and not name_cell.strip():
            continue
        person = split_name(name_cell)
        if not person["name"]:
            continue
        degrees = split_degrees(row[2] if len(row) > 2 else "")
        insts = (
            split_institutions(row[3] if len(row) > 3 else "", len(degrees))
            if len(row) > 3
            else None
        )
        notes = []
        if insts:
            for d, inst in zip(degrees, insts, strict=False):
                d["institution"] = inst
        elif degrees and len(row) > 3 and row[3].strip():
            notes.append("แยกสถาบันต่อวุฒิไม่ได้")
        if any(d["year"] is None for d in degrees):
            notes.append("บางวุฒิไม่มีปีที่จบ")
        conf = "high" if not notes else "medium"
        rows.append(
            {
                "order": int(m.group(1)) if m else None,
                "responsible": bool(m and m.group(2)),
                "rank": person["rank"],
                "doctor": person["doctor"],
                "name": person["name"],
                "group": group,
                "degrees": degrees,
                "institutions_text": re.sub(r"\s+", " ", row[3]).strip() if len(row) > 3 else None,
                "highest_level": _highest(degrees),
                "meta": meta(
                    conf,
                    t.page,
                    " | ".join(c for c in row if c)[:160],
                    note="; ".join(notes) or None,
                ),
            }
        )
    return rows


def _highest(degrees: list[dict[str, Any]]) -> str | None:
    order = {"เอก": 3, "โท": 2, "ตรี": 1}
    best = max((order.get(d.get("level") or "", 0) for d in degrees), default=0)
    return next((k for k, v in order.items() if v == best), None)


def _key(name: str) -> str:
    return re.sub(r"\s+", "", name)


def extract_teachers(doc: Document, gateway=None) -> PartResult:  # noqa: ARG001 - no LLM here
    res = PartResult(key="teachers", data={"teachers": [], "responsible_count": 0, "meta": {}})
    ch1 = chapter(doc, "1")
    if ch1 is None:
        res.notes.append("chapter 1 not found")
        return res
    resp = [r for t in tables(subsection(ch1.blocks, "11")) for r in parse_teacher_table(t)]
    allt = [r for t in tables(subsection(ch1.blocks, "12")) for r in parse_teacher_table(t)]
    resp_keys = {_key(r["name"]) for r in resp}
    if allt:
        teachers = allt
        for r in teachers:
            if _key(r["name"]) in resp_keys:
                r["responsible"] = True
        for r in resp:
            r["responsible"] = True
    else:
        teachers = resp
        for r in teachers:
            r["responsible"] = True
        if resp:
            res.notes.append("item 12 (อาจารย์ประจำหลักสูตร) not found; using item 11 only")
    if not teachers:
        res.notes.append("no teacher table in items 11–12")
        return res
    all_keys = {_key(r["name"]) for r in teachers}
    missing = [r["name"] for r in resp if _key(r["name"]) not in all_keys]
    res.data["teachers"] = teachers
    res.data["count"] = len(teachers)
    res.data["responsible_count"] = sum(1 for r in teachers if r["responsible"])
    res.data["responsible_only_in_11"] = missing
    res.data["groups"] = sorted({r["group"] for r in teachers if r["group"]})
    return res
