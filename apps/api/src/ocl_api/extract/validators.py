"""Deterministic consistency checks over extracted parts (never the LLM's opinion)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ocl_api.extract.base import Check


def _sum_children(nodes: list[dict[str, Any]]) -> int:
    return sum(int(n.get("credits") or 0) for n in nodes)


def run_checks(parts: dict[str, dict[str, Any]]) -> list[Check]:
    checks: list[Check] = []
    st = parts.get("structure") or {}
    plo = parts.get("plo") or {}
    crs = parts.get("courses") or {}

    tree = st.get("tree") or []
    total = st.get("total_credits")
    if tree:
        plans = [n for n in tree if n.get("plan")]
        top = min(int(n.get("credits") or 0) for n in plans) if plans else _sum_children(tree)
        if total is None:
            checks.append(Check("credits_total", "warn", "ไม่พบหน่วยกิตตลอดหลักสูตร", "structure"))
        elif top == total:
            checks.append(
                Check(
                    "credits_total",
                    "pass",
                    f"ผลรวมหมวดวิชา {top} = หน่วยกิตตลอดหลักสูตร {total}",
                    "structure",
                )
            )
        else:
            checks.append(
                Check(
                    "credits_total",
                    "fail",
                    f"ผลรวมหมวดวิชา {top} ≠ หน่วยกิตตลอดหลักสูตร {total} (เล่มอาจระบุ 'ไม่น้อยกว่า')",
                    "structure",
                )
            )
        bad = []
        for n in _walk(tree):
            kids_with_credits = [c for c in n["children"] if c.get("credits") is not None]
            if kids_with_credits and n.get("credits") is not None and not n.get("plan"):
                s = _sum_children(n["children"])
                if s != n["credits"]:
                    bad.append(f"{n['number']} {n['name']}: ลูกรวม {s} ≠ {n['credits']}")
        checks.append(
            Check(
                "credits_sub",
                "warn" if bad else "pass",
                "; ".join(bad) if bad else "หน่วยกิตกลุ่มย่อยรวมตรงกับหมวดทุกหมวด",
                "structure",
            )
        )
    else:
        checks.append(Check("credits_total", "fail", "ไม่พบโครงสร้างหลักสูตร", "structure"))

    plos = plo.get("plos") or []
    checks.append(
        Check(
            "plo_present",
            "pass" if plos else "fail",
            f"พบ PLO {len(plos)} ข้อ" if plos else "ไม่พบ PLO ในหมวดที่ 3",
            "plo",
        )
    )

    courses = crs.get("courses") or []
    mp = parts.get("mapping") or {}
    mrows = mp.get("rows") or []
    if mrows:
        plo_codes = mp.get("plo_codes") or []
        covered = {p for r in mrows for p in r.get("plos", [])}
        missing = [p for p in plo_codes if p not in covered]
        checks.append(
            Check(
                "plo_covered",
                "warn" if missing else "pass",
                f"PLO ที่ไม่มีรายวิชารองรับ: {', '.join(missing)}"
                if missing
                else f"ทุก PLO ({len(plo_codes)}) มีรายวิชารองรับใน Mapping",
                "mapping",
            )
        )
        declared = [p.get("code") for p in (plo.get("plos") or [])]
        absent = [p for p in declared if p and p not in plo_codes]
        if declared:
            checks.append(
                Check(
                    "mapping_has_all_plos",
                    "warn" if absent else "pass",
                    f"PLO ในหมวดที่ 3 ที่ไม่มีคอลัมน์ใน Mapping: {', '.join(absent)}"
                    if absent
                    else "คอลัมน์ Mapping ครบทุก PLO ของหมวดที่ 3",
                    "mapping",
                )
            )
        unmapped = mp.get("unmapped_courses") or []
        checks.append(
            Check(
                "courses_unmapped",
                "warn" if unmapped else "pass",
                f"รายวิชาใน Mapping ที่ไม่มี PLO เลย: {', '.join(unmapped[:8])}"
                if unmapped
                else "ทุกรายวิชาใน Mapping มีอย่างน้อย 1 PLO",
                "mapping",
            )
        )
        if courses:
            listed = {c.get("code_th") for c in courses}
            mapped = {r["course_code"] for r in mrows}
            only_list = sorted(listed - mapped)
            only_map = sorted(mapped - listed)
            checks.append(
                Check(
                    "mapping_vs_courses",
                    "warn" if (only_list or only_map) else "pass",
                    (
                        f"อยู่ในรายวิชาแต่ไม่อยู่ใน Mapping {len(only_list)}: {', '.join(only_list[:6])}"
                        if only_list
                        else ""
                    )
                    + (" · " if only_list and only_map else "")
                    + (
                        f"อยู่ใน Mapping แต่ไม่อยู่ในรายวิชา {len(only_map)}: {', '.join(only_map[:6])}"
                        if only_map
                        else ""
                    )
                    or "รายวิชาใน Mapping ตรงกับรายการรายวิชา",
                    "mapping",
                )
            )
    codes = Counter(c.get("code_th") for c in courses)
    dup = [c for c, n in codes.items() if n > 1]
    checks.append(
        Check(
            "course_code_unique",
            "fail" if dup else "pass",
            f"รหัสซ้ำ: {', '.join(dup)}" if dup else f"รหัสรายวิชาไม่ซ้ำ ({len(courses)} วิชา)",
            "courses",
        )
    )
    no_credit = [c["code_th"] for c in courses if not c.get("credit_text")]
    no_desc = [c["code_th"] for c in courses if not c.get("description_th")]
    low = [c["code_th"] for c in courses if (c.get("meta") or {}).get("confidence") == "low"]
    checks.append(
        Check(
            "course_fields",
            "warn" if (no_credit or no_desc) else "pass",
            f"ไม่มีหน่วยกิต {len(no_credit)} วิชา · ไม่มีคำอธิบาย {len(no_desc)} วิชา"
            + (f" (เช่น {', '.join((no_credit + no_desc)[:5])})" if (no_credit or no_desc) else ""),
            "courses",
        )
    )
    if low:
        checks.append(
            Check(
                "course_conflicts",
                "warn",
                f"parser กับ LLM ไม่ตรงกัน {len(low)} วิชา: {', '.join(low[:8])}",
                "courses",
            )
        )
    if courses and tree:
        total_course_credits = sum(int(c.get("credits") or 0) for c in courses)
        checks.append(
            Check(
                "courses_vs_structure",
                "info",
                f"รายวิชา {len(courses)} วิชา · หน่วยกิตรวมของรายวิชาที่พบ {total_course_credits}",
                "courses",
            )
        )
    return checks


def _walk(nodes: list[dict[str, Any]]):
    for n in nodes:
        yield n
        yield from _walk(n.get("children") or [])
