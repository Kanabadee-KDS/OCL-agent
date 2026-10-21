"""Markdown views of extracted parts (developer prompt files 2-, 3-, 4-) with fallback
templates when a part is empty so an editor can fill it in by hand."""

from __future__ import annotations

from typing import Any

CONF_TH = {"high": "สูง", "medium": "กลาง", "low": "ต่ำ"}


def _conf(m: dict[str, Any] | None) -> str:
    if not m:
        return ""
    c = CONF_TH.get(m.get("confidence", ""), "?")
    p = (m.get("source") or {}).get("page")
    return f"ความมั่นใจ {c}" + (f" · หน้า {p}" if p else "")


def render_structure(data: dict[str, Any]) -> str:
    tree = data.get("tree") or []
    if not tree:
        return (
            "# โครงสร้างหลักสูตร\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "## จำนวนหน่วยกิตตลอดหลักสูตร\n\n_[ระบุ]_\n\n## โครงสร้าง\n\n"
            "| หมวดวิชา | หน่วยกิต |\n| --- | --- |\n| 1. หมวดวิชาศึกษาทั่วไป | |\n"
            "| 2. หมวดวิชาเฉพาะ | |\n| 3. หมวดวิชาเลือกเสรี | |\n"
        )
    total = data.get("total_credits")
    lines = [
        "# โครงสร้างหลักสูตร",
        "",
        "## จำนวนหน่วยกิตตลอดหลักสูตร",
        "",
        f"ไม่น้อยกว่า **{total}** หน่วยกิต" if total else "_[ไม่พบ]_",
        "",
        "## โครงสร้าง",
        "",
        "| หมวดวิชา / กลุ่มวิชา | หน่วยกิต | หมายเหตุ |",
        "| --- | --- | --- |",
    ]

    def walk(nodes: list[dict[str, Any]], depth: int = 0) -> None:
        for n in nodes:
            indent = "　" * depth
            credits = n.get("credits")
            lines.append(
                f"| {indent}{n['number']} {n['name']} | "
                f"{credits if credits is not None else ''} | {_conf(n.get('meta'))} |"
            )
            walk(n.get("children") or [], depth + 1)

    walk(tree)
    return "\n".join(lines) + "\n"


def render_plo(data: dict[str, Any]) -> str:
    plos = data.get("plos") or []
    if not plos:
        return (
            "# ผลลัพธ์การเรียนรู้ของหลักสูตร (PLO)\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "- **PLO1**: _[ระบุ]_\n- **PLO2**: _[ระบุ]_\n"
        )
    lines = ["# ผลลัพธ์การเรียนรู้ของหลักสูตร (PLO)", ""]
    for p in plos:
        lines.append(f"- **{p['code']}**: {p['text']}  \n  <sub>{_conf(p.get('meta'))}</sub>")
        for s in p.get("sub_plos") or []:
            lines.append(f"  - **{s['code']}**: {s['text']}")
    return "\n".join(lines) + "\n"


def render_courses(data: dict[str, Any]) -> str:
    courses = data.get("courses") or []
    if not courses:
        return (
            "# รายวิชา\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "| รหัส | ชื่อวิชา (ไทย) | ชื่อวิชา (อังกฤษ) | หน่วยกิต |\n"
            "| --- | --- | --- | --- |\n| | | | |\n"
        )
    lines = [
        "# รายวิชา",
        "",
        f"รวม {len(courses)} รายวิชา",
        "",
        "| รหัส | ชื่อวิชา (ไทย) | รหัส/ชื่อ (อังกฤษ) | หน่วยกิต | กลุ่ม | ความมั่นใจ |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in courses:
        en = " ".join(x for x in (c.get("code_en"), c.get("name_en")) if x)
        lines.append(
            f"| {c['code_th']} | {c.get('name_th') or ''} | {en} | {c.get('credit_text') or ''} | "
            f"{c.get('group') or ''} | {_conf(c.get('meta'))} |"
        )
    lines += ["", "## คำอธิบายรายวิชา", ""]
    for c in courses:
        lines.append(f"### {c['code_th']} {c.get('name_th') or ''} {c.get('credit_text') or ''}")
        if c.get("code_en") or c.get("name_en"):
            lines.append(f"{c.get('code_en') or ''} {c.get('name_en') or ''}".strip())
        if c.get("prerequisite"):
            lines.append(f"บุรพวิชา: {c['prerequisite']}")
        lines.append("")
        lines.append(c.get("description_th") or "_[ไม่พบคำอธิบาย]_")
        if c.get("description_en"):
            lines.append("")
            lines.append(c["description_en"])
        lines.append("")
    return "\n".join(lines) + "\n"


def render_mapping(data: dict[str, Any]) -> str:
    plos = data.get("plo_codes") or []
    rows = data.get("rows") or []
    if not rows:
        return (
            "# Curriculum Mapping\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "| รายวิชา | PLO1 | PLO2 | PLO3 |\n| --- | --- | --- | --- |\n| | | | |\n"
        )
    lines = [
        "# Curriculum Mapping (รายวิชา × PLO)",
        "",
        f"รายวิชา {len(rows)} · PLO {len(plos)} · ● = รับผิดชอบ",
        "",
        "| รายวิชา | " + " | ".join(plos) + " | หน้า |",
        "|" + " --- |" * (len(plos) + 2),
    ]
    group = None
    for r in rows:
        if r.get("group") and r["group"] != group:
            group = r["group"]
            lines.append(f"| **{group}** |" + " |" * (len(plos) + 1))
        marks = " | ".join("●" if p in r["plos"] else "" for p in plos)
        page = (r.get("meta") or {}).get("source", {}).get("page") or ""
        lines.append(f"| {r['course_code']} {r.get('course_name') or ''} | {marks} | {page} |")
    return "\n".join(lines) + "\n"


RENDERERS = {
    "structure": ("2-course_structure.md", render_structure),
    "plo": ("4-plos.md", render_plo),
    "courses": ("3-courses_list.md", render_courses),
    "mapping": ("5-curriculum_mapping.md", render_mapping),
}
