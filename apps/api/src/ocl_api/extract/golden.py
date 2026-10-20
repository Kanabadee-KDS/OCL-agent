"""Golden-sample review sheet: a Markdown checklist the Admin ticks against the book.

Every row carries the source page so the reviewer opens the book at the right place.
The ticked sheet is the evidence behind "หัวข้อครบ 100% · ตาราง ≥ 95%".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ocl_api.extract.render import CONF_TH


def _page(m: dict[str, Any] | None) -> str:
    p = ((m or {}).get("source") or {}).get("page")
    return str(p) if p else "–"


def _conf(m: dict[str, Any] | None) -> str:
    return CONF_TH.get((m or {}).get("confidence", ""), "–")


def render_golden(extract_dir: str | Path, *, book: str, reviewer: str = "") -> str:
    d = Path(extract_dir)
    st = json.loads((d / "structure.json").read_text(encoding="utf-8"))["data"]
    plo = json.loads((d / "plo.json").read_text(encoding="utf-8"))["data"]
    crs = json.loads((d / "courses.json").read_text(encoding="utf-8"))["data"]
    checks = json.loads((d / "checks.json").read_text(encoding="utf-8"))

    L: list[str] = []
    L += [
        f"# Golden sample · {book}",
        "",
        f"ผู้ตรวจ: {reviewer or '________________'} · วันที่: ________ · เล่มต้นฉบับ: เปิดคู่กันแล้วติ๊ก ✓ ถูก / ✗ ผิด / ? ไม่แน่ใจ พร้อมหมายเหตุ",
        "",
        "วิธีนับ: ตารางเชิงตรรกะ = ตารางที่คนเห็นเป็นตารางเดียวแม้ข้ามหน้า · แถวในชีทนี้ที่มาจากตารางของเล่มให้ถือเป็นหน่วยนับของเกณฑ์ ≥ 95%",
        "",
        "## 0. สรุปที่ระบบตรวจเอง (validator)",
        "",
        "| ผล | รายการ | ข้อความ |",
        "| --- | --- | --- |",
    ]
    for c in checks:
        L.append(f"| {c['status'].upper()} | {c['key']} | {c['message']} |")

    L += [
        "",
        "## 1. โครงสร้างหลักสูตร (หมวดที่ 4 ข้อ 1)",
        "",
        f"หน่วยกิตตลอดหลักสูตรที่ระบบอ่านได้: **{st.get('total_credits')}** (หน้า {_page((st.get('meta') or {}).get('total_credits'))}) → ✓ / ✗ : ____",
        "",
        "| # | หมวด / กลุ่มวิชา | หน่วยกิต | หน้า | ความมั่นใจ | ✓/✗ | หมายเหตุ |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    def walk(nodes: list[dict[str, Any]], depth: int = 0) -> None:
        for n in nodes:
            L.append(
                f"| {n['number']} | {'　' * depth}{n['name']} | {n.get('credits') if n.get('credits') is not None else ''} "
                f"| {_page(n.get('meta'))} | {_conf(n.get('meta'))} |  |  |"
            )
            walk(n.get("children") or [], depth + 1)

    walk(st.get("tree") or [])

    L += [
        "",
        "## 2. PLO (หมวดที่ 3 ข้อ 1)",
        "",
        "| รหัส | ข้อความ | หน้า | ความมั่นใจ | ✓/✗ | หมายเหตุ |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for p in plo.get("plos") or []:
        L.append(
            f"| {p['code']} | {p['text']} | {_page(p.get('meta'))} | {_conf(p.get('meta'))} |  |  |"
        )
        for s in p.get("sub_plos") or []:
            L.append(
                f"| {s['code']} | 　{s['text']} | {_page(s.get('meta'))} | {_conf(s.get('meta'))} |  |  |"
            )
    L.append("")
    L.append("PLO ที่เล่มมีแต่ระบบไม่พบ (เขียนเพิ่ม): ______________________")

    courses = crs.get("courses") or []
    L += [
        "",
        f"## 3. รายวิชา (หมวดที่ 4 ข้อ 2–3) · ระบบพบ {len(courses)} วิชา",
        "",
        "ตรวจ 4 ช่อง: รหัส · ชื่อไทย/อังกฤษ · หน่วยกิต · มีคำอธิบาย (ย่อว่า ร/ช/น/ค) เช่น ✓✓✓✓ หรือ ✓✗✓✓",
        "",
        "| # | รหัส | ชื่อ (ไทย) | รหัส/ชื่อ (อังกฤษ) | หน่วยกิต | กลุ่ม/ชุดวิชา | คำอธิบาย | หน้า | ความมั่นใจ | ร/ช/น/ค | หมายเหตุ |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for i, c in enumerate(courses, start=1):
        en = " ".join(x for x in (c.get("code_en"), c.get("name_en")) if x)
        grp = c.get("module") or c.get("group") or ""
        desc = "มี" if c.get("description_th") else "**ไม่มี**"
        L.append(
            f"| {i} | {c['code_th']} | {c.get('name_th') or ''} | {en} | {c.get('credit_text') or ''} | {grp} "
            f"| {desc} | {_page(c.get('meta'))} | {_conf(c.get('meta'))} |  |  |"
        )
    L += [
        "",
        "รายวิชาที่เล่มมีแต่ระบบไม่พบ (เขียนเพิ่ม): ______________________",
        "",
        "## 4. สรุปผลตรวจ",
        "",
        "| เกณฑ์ | นับได้ | ถูก | % | ผ่าน/ไม่ผ่าน |",
        "| --- | --- | --- | --- | --- |",
        "| หัวข้อหลักครบ (หมวด 1–8) | 8 |  |  | ต้อง 100% |",
        f"| โครงสร้างหลักสูตร (แถว) | {st.get('node_count', 0)} |  |  | ≥ 95% |",
        f"| PLO | {plo.get('count', 0)} |  |  | ≥ 95% |",
        f"| รายวิชา (แถว × 4 ช่อง) | {len(courses) * 4} |  |  | ≥ 95% |",
        "",
    ]
    return "\n".join(L)
