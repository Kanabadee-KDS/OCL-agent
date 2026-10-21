"""Part 5: KSEC codes per PLO from the chapter 3 table (ผลลัพธ์การเรียนรู้ 4 ด้าน).

The table has one row per PLO and one column per ด้าน (K ความรู้ · S ทักษะ · E จริยธรรม ·
C คุณลักษณะ); each cell lists "K1-1: text" items separated by line breaks (docx) or
spaces (PDF). Codes are normalised to letter + dash-separated numbers ("K1.1" and
"K6.1.1" become "K1-1" and "K6-1-1") so Mapping 4.2 can reference them. A code may be
reused under another PLO (S1-7 under PLO2), which is why items are kept per PLO.
Deterministic: no LLM.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import PartResult, chapter, meta
from ocl_api.ingest.model import Block, Document, Paragraph, Table

RE_CAT_HEADER = re.compile(r"\(\s*([KSEC])\s*\)")
RE_PLO_CELL = re.compile(r"^\s*(PLO\s?\d+(?:\.\d+)?)\s*[:：.)]?\s*(.*)$", re.I | re.S)
RE_CODE = re.compile(r"(?<![A-Za-z])([KSEC])\s?(\d+(?:\s?[-.]\s?\d+)+)\s*[:：]?\s*")
RE_SUBTYPE = re.compile(r"^\s*(?:ทักษะ|คุณลักษณะ)?\s*(ทั่วไป|ลักษณะเฉพาะ|เฉพาะ)\s*$")
RE_PLAN = re.compile(r"(แผน\s*\d+(?:\.\d+)?(?:\s*แบบ\S+)?)")
CATEGORY_TH = {"K": "ความรู้", "S": "ทักษะ", "E": "จริยธรรม", "C": "คุณลักษณะ"}


def normalize_code(letter: str, numbers: str) -> str:
    return letter.upper() + "-".join(re.split(r"\s?[-.]\s?", numbers.strip()))


def _category_columns(t: Table) -> tuple[int, dict[int, str]] | None:
    """(header_row_index, {col: 'K'|'S'|'E'|'C'}) from the row naming the 4 ด้าน."""
    for i, row in enumerate(t.rows[:4]):
        cols = {}
        for j, c in enumerate(row):
            m = RE_CAT_HEADER.search(c or "")
            if m:
                cols[j] = m.group(1)
        if len(cols) >= 3:
            return i, cols
    return None


def parse_cell(cell: str, category: str, page: int | None) -> list[dict[str, Any]]:
    """Split one ด้าน cell into coded items; short lines without a code set the subtype."""
    items: list[dict[str, Any]] = []
    subtype: str | None = None
    for line in cell.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = RE_SUBTYPE.match(line)
        if m:
            subtype = "ลักษณะเฉพาะ" if "เฉพาะ" in m.group(1) else "ทั่วไป"
            continue
        hits = list(RE_CODE.finditer(line))
        if not hits:
            if items:  # wrapped continuation of the previous item
                items[-1]["text"] = (items[-1]["text"] + " " + line).strip()
            continue
        for k, h in enumerate(hits):
            end = hits[k + 1].start() if k + 1 < len(hits) else len(line)
            text = line[h.end() : end].strip(" :：")
            items.append(
                {
                    "code": normalize_code(h.group(1), h.group(2)),
                    "category": h.group(1).upper(),
                    "subtype": subtype,
                    "text": text,
                    "meta": meta("high", page, line[h.start() : end]),
                }
            )
    for it in items:
        if it["category"] != category:
            it["meta"]["confidence"] = "medium"
            it["meta"]["note"] = f"รหัส {it['code']} อยู่ในคอลัมน์ด้าน {category}"
    return items


def _plan_before(blocks: list[Block], index: int) -> str | None:
    """Plan label ("แผน 1 แบบวิชาการ") from the few paragraphs above a table, if any."""
    for b in reversed(blocks[max(0, index - 6) : index]):
        if isinstance(b, Paragraph):
            m = RE_PLAN.search(b.text)
            if m and len(b.text) < 160:
                return m.group(1).strip()
    return None


def parse_ksec_table(t: Table, plan: str | None) -> list[dict[str, Any]]:
    found = _category_columns(t)
    if not found:
        return []
    header_i, cols = found
    plos: list[dict[str, Any]] = []
    group: str | None = None
    for row in t.rows[header_i + 1 :]:
        first = (row[0] or "").strip()
        if _category_columns(Table(rows=[row], page=t.page)):
            continue  # repeated header after a page break
        m = RE_PLO_CELL.match(first)
        has_items = any((row[j] or "").strip() for j in cols if j < len(row))
        if m:
            code = re.sub(r"\s+", "", m.group(1).upper())
            plos.append(
                {
                    "code": code,
                    "plan": plan,
                    "group": group,
                    "text": re.sub(r"\s+", " ", m.group(2)).strip(),
                    "items": [],
                    "meta": meta("high", t.page, first),
                }
            )
        elif first and not has_items:
            group = first  # e.g. "เอกการจัดการภูมิสังคม"
            continue
        elif not plos:
            continue
        for j, cat in cols.items():
            if j < len(row) and (row[j] or "").strip():
                plos[-1]["items"].extend(parse_cell(row[j], cat, t.page))
    return plos


def extract_ksec(doc: Document, gateway=None) -> PartResult:  # noqa: ARG001 - no LLM here
    res = PartResult(key="ksec", data={"plos": [], "codes": [], "meta": {}})
    ch3 = chapter(doc, "3")
    if ch3 is None:
        res.notes.append("chapter 3 not found")
        return res
    plos: list[dict[str, Any]] = []
    for i, b in enumerate(ch3.blocks):
        if isinstance(b, Table) and _category_columns(b):
            plos.extend(parse_ksec_table(b, _plan_before(ch3.blocks, i)))
    if not plos:
        res.notes.append("no PLO × (K/S/E/C) table found in chapter 3")
        return res
    # the same PLO continued in a second table (page break) merges into one entry
    merged: dict[tuple[str | None, str], dict[str, Any]] = {}
    for p in plos:
        key = (p["plan"], p["code"])
        if key in merged:
            merged[key]["items"].extend(p["items"])
            if len(p["text"]) > len(merged[key]["text"]):
                merged[key]["text"] = p["text"]
        else:
            merged[key] = p
    out = list(merged.values())
    codes: set[str] = set()
    for p in out:
        seen: set[str] = set()
        unique = []
        for it in p["items"]:
            if it["code"] in seen:
                continue
            seen.add(it["code"])
            unique.append(it)
        p["items"] = unique
        p["item_count"] = len(unique)
        codes.update(it["code"] for it in unique)
    res.data["plos"] = out
    res.data["codes"] = sorted(codes, key=_code_key)
    res.data["count"] = sum(p["item_count"] for p in out)
    res.data["plans"] = sorted({p["plan"] for p in out if p["plan"]})
    if not any(p["items"] for p in out):
        res.notes.append("PLO rows found but no coded items (K1-1: ...) inside the cells")
    return res


def _code_key(code: str) -> tuple:
    m = re.match(r"([KSEC])-?(.*)", code)
    order = {"K": 0, "S": 1, "E": 2, "C": 3}
    nums = tuple(int(x) for x in re.findall(r"\d+", m.group(2))) if m else ()
    return (order.get(m.group(1), 9) if m else 9, nums)


def category_th(letter: str) -> str:
    return CATEGORY_TH.get(letter, letter)
