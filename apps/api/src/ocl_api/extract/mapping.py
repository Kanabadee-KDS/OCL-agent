"""Part 9: Curriculum Mapping 4.1 (course × PLO) from the chapter 4 table.

The table carries a two-row header (merged "ผลลัพธ์การเรียนรู้ของหลักสูตร" over PLO1..n) and
Wingdings bullets that ingestion already turned into "●". Deterministic: no LLM.
Part 4.2 (PLO + KSEC codes per cell) is left for R1 once KSEC (part 5) exists.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import PartResult, chapter, meta, subsection, tables
from ocl_api.ingest.model import Document, Table

RE_PLO_COL = re.compile(r"^\s*PLO\s?(\d+)\s*$", re.I)
RE_COURSE = re.compile(r"^\s*([ก-ฮ]{2,4}\s?\d{3}(?:-\d)?)\s*(.*)$")
MARKS = {"●", "✓", "✔", "√", "x", "X", "■", "☑", "◉", "•"}


def _plo_columns(t: Table) -> tuple[int, dict[int, str]] | None:
    """Return (header_row_index, {col: 'PLOn'}) for the first row that names PLO columns."""
    for i, row in enumerate(t.rows[:4]):
        cols = {
            j: f"PLO{RE_PLO_COL.match(c).group(1)}"
            for j, c in enumerate(row)
            if RE_PLO_COL.match(c or "")
        }
        if len(cols) >= 2:
            return i, cols
    return None


def _is_mark(cell: str) -> bool:
    c = (cell or "").strip()
    return bool(c) and (c in MARKS or all(ch in MARKS for ch in c))


def parse_mapping_table(t: Table) -> list[dict[str, Any]]:
    found = _plo_columns(t)
    if not found:
        return []
    header_i, cols = found
    rows: list[dict[str, Any]] = []
    group: str | None = None
    for row in t.rows[header_i + 1 :]:
        first = (row[0] or "").strip()
        if not first:
            continue
        m = RE_COURSE.match(first)
        if not m:
            group = first
            continue
        plos = [name for j, name in cols.items() if j < len(row) and _is_mark(row[j])]
        rows.append(
            {
                "course_code": re.sub(r"\s+", "", m.group(1)),
                "course_name": m.group(2).strip() or None,
                "group": group,
                "plos": plos,
                "meta": meta("high", t.page, " | ".join(c for c in row if c)[:160]),
            }
        )
    return rows


def extract_mapping(doc: Document, gateway=None) -> PartResult:  # noqa: ARG001 - no LLM here
    res = PartResult(key="mapping", data={"plo_codes": [], "rows": [], "meta": {}})
    ch4 = chapter(doc, "4")
    if ch4 is None:
        res.notes.append("chapter 4 not found")
        return res
    candidates = list(tables(subsection(ch4.blocks, "4"))) or list(tables(ch4.blocks))
    # Books split the mapping into one table per group (PhD) or keep one big table
    # (bachelor). Take every PLO-headed table that actually carries marks; tables with
    # PLO columns but no marks are the KSEC-number layout of item 4.2 (R1).
    marked: list[tuple[Table, dict[int, str], list[dict[str, Any]]]] = []
    for t in candidates:
        found = _plo_columns(t)
        if not found:
            continue
        has_marks = any(_is_mark(c) for row in t.rows[found[0] + 1 :] for c in row[1:])
        if not has_marks:
            continue
        marked.append((t, found[1], parse_mapping_table(t)))
    if not marked:
        res.notes.append("no course × PLO table with marks found in chapter 4")
        return res
    # the biggest marked table defines the PLO set (4.1); other tables join only when they
    # share that exact set (split-per-group layouts), which keeps the 4-ด้าน table (4.2) out
    primary = max(marked, key=lambda m: len(m[2]))
    plo_set = set(primary[1].values())
    best: list[dict[str, Any]] = []
    for t, cols, rows in marked:
        if set(cols.values()) == plo_set:
            best.extend(rows)
        else:
            res.notes.append(f"skipped table p.{t.page} with PLO columns {sorted(cols.values())}")
    best_cols = primary[1]
    # merge duplicates (same course listed twice keeps the union of marks)
    merged: dict[str, dict[str, Any]] = {}
    for r in best:
        if r["course_code"] in merged:
            merged[r["course_code"]]["plos"] = sorted(
                set(merged[r["course_code"]]["plos"]) | set(r["plos"]), key=_plo_key
            )
        else:
            merged[r["course_code"]] = r
    res.data["plo_codes"] = sorted(best_cols.values(), key=_plo_key)
    res.data["rows"] = list(merged.values())
    res.data["count"] = len(merged)
    res.data["unmapped_courses"] = [r["course_code"] for r in merged.values() if not r["plos"]]
    return res


def _plo_key(code: str) -> int:
    m = re.search(r"\d+", code)
    return int(m.group()) if m else 0
