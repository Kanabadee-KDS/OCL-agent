"""Part 9: Curriculum Mapping 4.1 (course × PLO) from the chapter 4 table.

The table carries a two-row header (merged "ผลลัพธ์การเรียนรู้ของหลักสูตร" over PLO1..n) and
Wingdings bullets that ingestion already turned into "●". Deterministic: no LLM.
Part 4.2 (course × K/S/E/C per PLO, cells hold item numbers such as "1,2", "1-6" or
"6.1.2") is read from the tables whose PLO header has a second row of K1 S1 E1 C1 ...
and no ● marks; each cell value becomes a KSEC code (letter from the column, numbers
from the cell, a bare number gets the column's PLO number) so it can be checked against
part 5.
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
        res.data.update(extract_ksec_mapping(doc))
        res.data["ksec_count"] = len(res.data["ksec_rows"])
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
    res.data.update(extract_ksec_mapping(doc))
    res.data["ksec_count"] = len(res.data["ksec_rows"])
    return res


RE_KSEC_HEADER = re.compile(r"^\s*([KSEC])\s?(\d+)\*?\s*$")
RE_CELL_TOKEN = re.compile(r"\d+(?:\s?[-.]\s?\d+)*")


def _ksec_columns(t: Table, header_i: int) -> dict[int, tuple[str, str, bool]] | None:
    """{col: (letter, plo_number, inherited)} from the K1 S1 E1 C1 ... row under the PLO
    header; an empty header cell (merged span, PDF phantom column) inherits the header on
    its left and is flagged `inherited`."""
    for row in t.rows[header_i + 1 : header_i + 3]:
        cols: dict[int, tuple[str, str, bool]] = {}
        last: tuple[str, str] | None = None
        hits = 0
        for j, c in enumerate(row):
            m = RE_KSEC_HEADER.match(c or "")
            if m:
                last = (m.group(1).upper(), m.group(2))
                hits += 1
                cols[j] = (*last, False)
            elif last and j > 0:
                cols[j] = (*last, True)
        if hits >= 4:
            return cols
    return None


def cell_codes(value: str, letter: str, plo_number: str) -> list[str]:
    """'1,2' under K1 -> K1-1, K1-2 · '1-7' under S2 -> S1-7 · '6.1.2' under K6 -> K6-1-2."""
    out: list[str] = []
    for tok in RE_CELL_TOKEN.findall(value or ""):
        nums = [n for n in re.split(r"\s?[-.]\s?", tok) if n]
        if not nums:
            continue
        if len(nums) == 1:
            nums = [plo_number, nums[0]]
        code = letter + "-".join(nums)
        if code not in out:
            out.append(code)
    return out


def parse_ksec_mapping_table(t: Table, carry: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Rows of a 4.2 table. `carry` is the last course of the previous table so a row
    whose course cell is empty (page break / wrapped cell) continues it."""
    found = _plo_columns(t)
    if not found:
        return []
    header_i, plo_cols = found
    cols = _ksec_columns(t, header_i)
    if not cols:
        return []
    rows: list[dict[str, Any]] = []
    group: str | None = None
    cur = carry
    for row in t.rows[header_i + 1 :]:
        if any(RE_KSEC_HEADER.match(c or "") for c in row[1:]):
            continue  # header rows
        first = (row[0] or "").strip()
        has_values = any((row[j] or "").strip() for j in cols if j < len(row))
        m = RE_COURSE.match(first)
        if m:
            cur = {
                "course_code": re.sub(r"\s+", "", m.group(1)),
                "course_name": m.group(2).strip() or None,
                "group": group,
                "by_column": {},
                "meta": meta("high", t.page, " | ".join(c for c in row if c)[:160]),
            }
            rows.append(cur)
        elif first and not has_values:
            group = first
            continue
        elif not first and not has_values:
            continue
        if cur is None:
            continue
        for j, (letter, plo_number, inherited) in cols.items():
            if j >= len(row) or not (row[j] or "").strip():
                continue
            # PDF column detection splits one cell into a phantom column plus the real
            # one with the same text; keep only the copy under the real header
            if (
                inherited
                and j + 1 < len(row)
                and (j + 1) in cols
                and (row[j + 1] or "").strip() == row[j].strip()
            ):
                continue
            key = f"{letter}{plo_number}"
            codes = cell_codes(row[j], letter, plo_number)
            lst = cur["by_column"].setdefault(key, [])
            lst.extend(c for c in codes if c not in lst)
    return rows


def extract_ksec_mapping(doc: Document) -> dict[str, Any]:
    """4.2 rows across every KSEC-headed table of chapter 4, in book order."""
    ch4 = chapter(doc, "4")
    if ch4 is None:
        return {"ksec_columns": [], "ksec_rows": []}
    candidates = list(tables(subsection(ch4.blocks, "4"))) or list(tables(ch4.blocks))
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    carry: dict[str, Any] | None = None
    for t in candidates:
        found = _plo_columns(t)
        if not found:
            continue
        cols = _ksec_columns(t, found[0])
        if not cols:
            continue
        for letter, n, _inherited in cols.values():
            key = f"{letter}{n}"
            if key not in columns:
                columns.append(key)
        parsed = parse_ksec_mapping_table(t, carry)
        rows.extend(r for r in parsed if r is not carry)
        if parsed:
            carry = parsed[-1] if parsed[-1] is not carry else carry
    merged: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["course_code"] in merged:
            for k, v in r["by_column"].items():
                lst = merged[r["course_code"]]["by_column"].setdefault(k, [])
                lst.extend(c for c in v if c not in lst)
        else:
            merged[r["course_code"]] = r
    for r in merged.values():
        r["ksec_codes"] = [c for k in columns for c in r["by_column"].get(k, [])]
        r["plos"] = sorted({"PLO" + k[1:] for k, v in r["by_column"].items() if v}, key=_plo_key)
    return {"ksec_columns": columns, "ksec_rows": list(merged.values())}


def _plo_key(code: str) -> int:
    m = re.search(r"\d+", code)
    return int(m.group()) if m else 0
