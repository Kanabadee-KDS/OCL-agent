"""The คู่มือหลักสูตร's own data: หมวด 0–5 (BRD 01 §4), one row per section (migration 010).

A section holds the import parts it is made of, keyed by part name, so an imported book
converts without loss and back (`to_parts`): `info` is split between หมวด 0 (master data) and
หมวด 1 (general data), every other part belongs to one section. Import is one way to fill
a draft; a draft can also start blank ("เพิ่มหลักสูตร"). The import job is not read again
after finalize: edits go to these rows, each with a history row (NFR-15).
"""

from __future__ import annotations

from typing import Any

from ocl_api.curriculum_form import SECTION1_LISTS, SECTION1_VALUES
from ocl_api.db import Jsonb

SECTIONS: dict[str, str] = {
    "0": "หมวด 0 ข้อมูลหลัก",
    "1": "หมวด 1 ข้อมูลทั่วไป",
    "2": "หมวด 2 ข้อมูลเฉพาะ",
    "3": "หมวด 3 PLO/KSEC",
    "4": "หมวด 4 โครงสร้าง/Mapping",
    "5": "หมวด 5 สถานภาพ/อนุมัติ",
}
PART_SECTION: dict[str, str] = {
    "teachers": "0",
    "plan": "2",
    "plo": "3",
    "ksec": "3",
    "structure": "4",
    "modules": "4",
    "courses": "4",
    "mapping": "4",
    "appr": "5",
}  # `info` is split, see below
# which `info` keys are หมวด 1 is decided by the form (curriculum_form.py), nowhere else
INFO_SECTION1_VALUES = SECTION1_VALUES
INFO_SECTION1_LISTS = SECTION1_LISTS
# in review the faculty edits หมวด 3–4, and inside หมวด 4 only the Curriculum Mapping
REVIEW_EDITABLE: dict[str, set[str] | None] = {"3": None, "4": {"mapping"}}


def sections_of_part(key: str) -> list[str]:
    return ["0", "1"] if key == "info" else [PART_SECTION[key]] if key in PART_SECTION else []


def _split_info(info: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    s0: dict[str, Any] = {}
    s1: dict[str, Any] = {}
    for k, v in info.items():
        if k in ("values", "meta") and isinstance(v, dict):
            s0[k] = {kk: vv for kk, vv in v.items() if kk not in INFO_SECTION1_VALUES}
            s1[k] = {kk: vv for kk, vv in v.items() if kk in INFO_SECTION1_VALUES}
        elif k in INFO_SECTION1_LISTS:
            s1[k] = v
        else:
            s0[k] = v
    return s0, s1


def from_parts(parts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Import parts ({key: part data}) → {section: {part key: data}}; all six sections present."""
    out: dict[str, dict[str, Any]] = {n: {} for n in SECTIONS}
    for key, data in parts.items():
        if data is None:
            continue
        if key == "info":
            s0, s1 = _split_info(data)
            out["0"]["info"], out["1"]["info"] = s0, s1
        elif key in PART_SECTION:
            out[PART_SECTION[key]][key] = data
    return out


def to_parts(sections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Back to import parts (merging `info`), for counts and anything written per part."""
    parts: dict[str, Any] = {}
    for n in sorted(sections):
        for key, data in (sections[n] or {}).items():
            if key != "info":
                parts[key] = data
    i0 = (sections.get("0") or {}).get("info")
    i1 = (sections.get("1") or {}).get("info")
    if i0 is not None or i1 is not None:
        info = dict(i0 or {})
        for k, v in (i1 or {}).items():
            info[k] = {**(info.get(k) or {}), **v} if k in ("values", "meta") else v
        parts["info"] = info
    return parts


def with_part(section: dict[str, Any], key: str, data: Any, n: str) -> dict[str, Any]:
    """`section` (number `n`) with one part replaced; for `info`, only this section's half."""
    out = dict(section or {})
    if key == "info":
        s0, s1 = _split_info(data or {})
        out["info"] = s0 if n == "0" else s1
    else:
        out[key] = data
    return out


def master_columns(sections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The list's columns (name, code, level, start year, faculty) read from หมวด 0."""
    v = ((sections.get("0") or {}).get("info") or {}).get("values") or {}
    return {k: v.get(k) for k in ("program_code", "name_th", "level", "start_year", "faculty")}


def write_all(conn, draft_id: int, sections: dict[str, dict[str, Any]], by: str, why: str) -> None:
    """Replace all six sections (finalize, backfill) and log each one."""
    for n in SECTIONS:
        data = sections.get(n) or {}
        conn.execute(
            "INSERT INTO curriculum_sections (draft_id, section, data, updated_by) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (draft_id, section) DO UPDATE SET "
            "data = EXCLUDED.data, updated_by = EXCLUDED.updated_by, updated_at = now()",
            (draft_id, n, Jsonb(data), by),
        )
        conn.execute(
            "INSERT INTO curriculum_section_history (draft_id, section, by, why, data) "
            "VALUES (%s, %s, %s, %s, %s)",
            (draft_id, n, by, why, Jsonb(data)),
        )


def write_one(conn, draft_id: int, n: str, data: dict[str, Any], by: str, why: str) -> None:
    """Replace one section and log it (changes made by the system: links, สมอ.08)."""
    conn.execute(
        "UPDATE curriculum_sections SET data = %s, updated_by = %s, updated_at = now() "
        "WHERE draft_id = %s AND section = %s",
        (Jsonb(data), by, draft_id, n),
    )
    conn.execute(
        "INSERT INTO curriculum_section_history (draft_id, section, by, why, data) "
        "VALUES (%s, %s, %s, %s, %s)",
        (draft_id, n, by, why, Jsonb(data)),
    )


def backfill(url: str, schema: str | None) -> int:
    """Drafts made before migration 010 get their sections from the finalize snapshot."""
    from ocl_api.db import connect

    done = 0
    with connect(url, schema) as conn:
        rows = conn.execute(
            "SELECT d.id, d.data FROM curriculum_drafts d WHERE NOT EXISTS "
            "(SELECT 1 FROM curriculum_sections s WHERE s.draft_id = d.id)"
        ).fetchall()
        for r in rows:
            parts = {
                k: (p or {}).get("data") for k, p in ((r["data"] or {}).get("parts") or {}).items()
            }
            with conn.transaction():
                write_all(conn, r["id"], from_parts(parts), "system", "แปลงจากข้อมูลนำเข้า")
            done += 1
    return done


def normalized(sections: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """`info` split again by the current form: data stored under an older split reads right."""
    if "0" not in sections and "1" not in sections:
        return sections
    info = to_parts({n: sections.get(n) or {} for n in ("0", "1")}).get("info")
    if info is None:
        return sections
    s0, s1 = _split_info(info)
    out = dict(sections)
    for n, half in (("0", s0), ("1", s1)):
        if n in out:
            out[n] = {**(out[n] or {}), "info": half}
    return out
