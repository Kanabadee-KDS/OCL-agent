"""Golden-sample review sheet: a Markdown checklist the Admin ticks against the book.

Every row carries the source page so the reviewer opens the book at the right place.
The ticked sheet is the evidence behind "หัวข้อครบ 100% · ตาราง ≥ 95%".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ocl_api.extract.render import CONF_TH, degree_text


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

    info_path = d / "info.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))["data"] if info_path.exists() else {}
    iv = info.get("values") or {}
    im = info.get("meta") or {}
    if iv:
        L += [
            "",
            f"## 1. ข้อมูลหลัก + หมวดที่ 1 ข้อมูลทั่วไป (ข้อ 1–10, 13) · ระบบอ่านได้ {info.get('count', 0)} ฟิลด์",
            "",
            "ฟิลด์ที่ขึ้น 'อนุมาน' เล่มไม่ได้เขียนตรง ๆ ระบบสรุปจากข้อมูลอื่น ให้ตรวจว่าสมเหตุสมผล",
            "",
            "| ฟิลด์ | ค่าที่ระบบอ่านได้ | หน้า | ความมั่นใจ | ✓/✗ | หมายเหตุ |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for f in info.get("fields") or []:
            v = iv.get(f["key"])
            if v in (None, "", []):
                continue
            m = im.get(f["key"]) or {}
            shown = (
                ("ใช่" if v else "ไม่ใช่")
                if isinstance(v, bool)
                else "; ".join(map(str, v))
                if isinstance(v, list)
                else str(v)
            )
            L.append(
                f"| {f['label']} | {shown} | {_page(m)} | {'อนุมาน · ' if m.get('inferred') else ''}{_conf(m)} |  |  |"
            )
        for x in info.get("majors") or []:
            L.append(
                f"| วิชาเอก/แขนง | {x['name']} | {_page(x.get('meta'))} | {_conf(x.get('meta'))} |  |  |"
            )
        for x in info.get("collaborations") or []:
            L.append(
                f"| ความร่วมมือ | {x['institution']} {x.get('country') or ''} | {_page(x.get('meta'))} | {_conf(x.get('meta'))} |  |  |"
            )
        for x in info.get("careers") or []:
            L.append(
                f"| อาชีพ{' (' + x['group'] + ')' if x.get('group') else ''} | {x['name']} | {_page(x.get('meta'))} | {_conf(x.get('meta'))} |  |  |"
            )
        L += ["", "ฟิลด์ที่เล่มมีแต่ระบบไม่พบ (เขียนเพิ่ม): ______________________"]

    tc_path = d / "teachers.json"
    tc = json.loads(tc_path.read_text(encoding="utf-8"))["data"] if tc_path.exists() else {}
    if tc.get("teachers"):
        L += [
            "",
            f"## 1a. อาจารย์หลักสูตร (หมวดที่ 1 ข้อ 11–12) · ระบบพบ {tc.get('count', 0)} คน ผู้รับผิดชอบ {tc.get('responsible_count', 0)} คน",
            "",
            "ตรวจ 4 ช่องต่อคน: ชื่อ · ตำแหน่ง/ผู้รับผิดชอบ · คุณวุฒิ+ปี · สถาบัน (ย่อ ช/ต/ว/ส เช่น ✓✓✓✗)",
            "",
            "| ลำดับ | ชื่อ | ตำแหน่ง | วิชาเอก | คุณวุฒิ (สาขา), ปี – สถาบัน | หน้า | ความมั่นใจ | ช/ต/ว/ส | หมายเหตุ |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for t in tc["teachers"]:
            rank = " ".join(x for x in (t.get("rank"), "ดร." if t.get("doctor") else None) if x)
            degs = " · ".join(degree_text(x) for x in t.get("degrees") or [])
            L.append(
                f"| {t.get('order') or ''}{'*' if t.get('responsible') else ''} | {t['name']} | {rank} | {t.get('group') or ''} | {degs} | {_page(t.get('meta'))} | {_conf(t.get('meta'))} |  |  |"
            )
        L += ["", "อาจารย์ที่เล่มมีแต่ระบบไม่พบ (เขียนเพิ่ม): ______________________"]

    pl_path = d / "plan.json"
    pl = json.loads(pl_path.read_text(encoding="utf-8"))["data"] if pl_path.exists() else {}
    if pl.get("plans"):
        L += [
            "",
            f"## 1c. แผนการรับนิสิต (หมวดที่ 2 ข้อ 4) · {len(pl['plans'])} ตาราง · รูปแบบการสอน (อนุมาน): {' · '.join(pl.get('teaching_modes') or [])}",
            "",
        ]
        for p in pl["plans"]:
            L += [
                f"**{p.get('name') or 'แผนการรับ'}** (หน้า {_page(p.get('meta'))})",
                "",
                "| แถว | " + " | ".join(p["years"]) + " | ✓/✗ | หมายเหตุ |",
                "|" + " --- |" * (len(p["years"]) + 3),
            ]
            for r in p["rows"]:
                L.append(
                    f"| {r['label']} | " + " | ".join(str(v) for v in r["values"]) + " |  |  |"
                )
            if p.get("total"):
                L.append("| รวม | " + " | ".join(str(v) for v in p["total"]) + " |  |  |")
            if p.get("graduates"):
                L.append(
                    "| คาดว่าจะสำเร็จ | " + " | ".join(str(v) for v in p["graduates"]) + " |  |  |"
                )
            L.append("")

    ap_path = d / "appr.json"
    ap = json.loads(ap_path.read_text(encoding="utf-8"))["data"] if ap_path.exists() else {}
    if ap.get("approvals"):
        L += [
            "",
            f"## 1b. สถานภาพและมติอนุมัติ (หมวดที่ 1 ข้อ 13) · สถานภาพ: หลักสูตร{ap.get('status') or '–'} · เริ่มใช้ {ap.get('start_semester') or '–'}/{ap.get('start_year') or '–'}",
            "",
            "| ระดับ | ครั้งที่ | วันที่ประชุม | มติ | หน้า | ✓/✗ | หมายเหตุ |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for a in ap["approvals"]:
            dt = (a.get("date") or {}).get("text") or ("_[เล่มเว้นว่าง]_" if a.get("pending") else "–")
            L.append(
                f"| {a['level']} | {a.get('meeting_no') or '–'} | {dt} | {a.get('resolution') or ''} | {_page(a.get('meta'))} |  |  |"
            )
        if ap.get("missing_levels"):
            L.append("")
            L.append("ยังไม่มีมติ: " + " · ".join(ap["missing_levels"]))

    L += [
        "",
        "## 2. โครงสร้างหลักสูตร (หมวดที่ 4 ข้อ 1)",
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
        "## 3. PLO (หมวดที่ 3 ข้อ 1)",
        "",
        "| รหัส | ข้อความ | หน้า | ความมั่นใจ | ✓/✗ | หมายเหตุ |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for p in plo.get("plos") or []:
        code = p["code"] + (f" ({p['plan']})" if p.get("plan") else "")
        L.append(
            f"| {code} | {p['text']} | {_page(p.get('meta'))} | {_conf(p.get('meta'))} |  |  |"
        )
        for s in p.get("sub_plos") or []:
            L.append(
                f"| {s['code']} | 　{s['text']} | {_page(s.get('meta'))} | {_conf(s.get('meta'))} |  |  |"
            )
    L.append("")
    L.append("PLO ที่เล่มมีแต่ระบบไม่พบ (เขียนเพิ่ม): ______________________")

    ks_path = d / "ksec.json"
    ks = json.loads(ks_path.read_text(encoding="utf-8"))["data"] if ks_path.exists() else {}
    if ks.get("plos"):
        L += [
            "",
            f"## 3b. KSEC ตาม PLO (หมวดที่ 3 ตาราง 4 ด้าน) · ระบบพบ {ks.get('count', 0)} รายการ",
            "",
            "ตรวจว่ารหัสอยู่ใต้ PLO และด้าน (K/S/E/C) ที่ถูกต้อง และข้อความตรงเล่ม",
            "",
            "| PLO | รหัส | ด้าน | รายละเอียด | หน้า | ✓/✗ | หมายเหตุ |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for p in ks["plos"]:
            label = p["code"] + (f" ({p['plan']})" if p.get("plan") else "")
            for it in p.get("items") or []:
                L.append(
                    f"| {label} | {it['code']} | {it['category']} | {it.get('text') or ''} | {_page(it.get('meta'))} |  |  |"
                )
        L += ["", "KSEC ที่เล่มมีแต่ระบบไม่พบ (เขียนเพิ่ม): ______________________"]

    mp_path = d / "mapping.json"
    mp = json.loads(mp_path.read_text(encoding="utf-8"))["data"] if mp_path.exists() else {}
    courses = crs.get("courses") or []
    L += [
        "",
        f"## 4. รายวิชา (หมวดที่ 4 ข้อ 2–3) · ระบบพบ {len(courses)} วิชา",
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
    L += ["", "รายวิชาที่เล่มมีแต่ระบบไม่พบ (เขียนเพิ่ม): ______________________"]
    md_path = d / "modules.json"
    mdd = json.loads(md_path.read_text(encoding="utf-8"))["data"] if md_path.exists() else {}
    if mdd.get("modules"):
        L += [
            "",
            f"## 4a. ชุดวิชา (หมวดที่ 4 ข้อ 3) · ระบบพบ {len(mdd['modules'])} ชุด",
            "",
            "ตรวจ 3 ช่อง: ชื่อ · คำอธิบาย · รายวิชาในชุด (ย่อ ช/ค/ร เช่น ✓✓✗)",
            "",
            "| # | ชุดวิชา | ชื่ออังกฤษ | กลุ่ม | หน่วยกิต | รายวิชา | คำอธิบาย | หน้า | ช/ค/ร | หมายเหตุ |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for m in mdd["modules"]:
            cr = "ไม่นับ" if m.get("counted") is False else (m.get("credits") or "")
            L.append(
                f"| {m['number']} | {m['name_th']} | {m.get('name_en') or ''} | {m.get('group') or ''} | {cr} | {', '.join(m.get('course_codes') or [])} | {'มี' if m.get('description_th') else '**ไม่มี**'} | {_page(m.get('meta'))} |  |  |"
            )
    if mp.get("rows"):
        plos = mp.get("plo_codes") or []
        L += [
            "",
            f"## 4b. Curriculum Mapping (หมวดที่ 4 ข้อ 4.1) · ระบบพบ {len(mp['rows'])} แถว × {len(plos)} PLO",
            "",
            "ตรวจทีละแถวว่าจุด ● ตรงกับเล่ม (ทุกช่องในแถว) ติ๊ก ✓ เมื่อทั้งแถวถูก",
            "",
            "| # | รายวิชา | " + " | ".join(plos) + " | หน้า | ✓/✗ | หมายเหตุ |",
            "|" + " --- |" * (len(plos) + 5),
        ]
        for i, r in enumerate(mp["rows"], start=1):
            marks = " | ".join("●" if p in r["plos"] else "" for p in plos)
            L.append(
                f"| {i} | {r['course_code']} {r.get('course_name') or ''} | {marks} | {_page(r.get('meta'))} |  |  |"
            )
    if mp.get("ksec_rows"):
        kcols = mp.get("ksec_columns") or []
        L += [
            "",
            f"## 4c. Mapping 4.2 รายวิชา × KSEC (หมวดที่ 4 ข้อ 4.2) · ระบบพบ {len(mp['ksec_rows'])} แถว",
            "",
            "ตรวจทีละแถวว่ารหัสในทุกช่องตรงกับเล่ม ติ๊ก ✓ เมื่อทั้งแถวถูก",
            "",
            "| # | รายวิชา | " + " | ".join(kcols) + " | หน้า | ✓/✗ | หมายเหตุ |",
            "|" + " --- |" * (len(kcols) + 5),
        ]
        for i, r in enumerate(mp["ksec_rows"], start=1):
            cells = " | ".join(", ".join(r.get("by_column", {}).get(c, [])) for c in kcols)
            L.append(
                f"| {i} | {r['course_code']} {r.get('course_name') or ''} | {cells} | {_page(r.get('meta'))} |  |  |"
            )

    L += [
        "",
        "## 5. สรุปผลตรวจ",
        "",
        "| เกณฑ์ | นับได้ | ถูก | % | ผ่าน/ไม่ผ่าน |",
        "| --- | --- | --- | --- | --- |",
        "| หัวข้อหลักครบ (หมวด 1–8) | 8 |  |  | ต้อง 100% |",
        f"| ข้อมูลหลัก + หมวด 1 (ฟิลด์) | {info.get('count', 0)} |  |  | ≥ 95% |",
        f"| มติอนุมัติ (แถว) | {len(ap.get('approvals') or [])} |  |  | ≥ 95% |",
        f"| แผนการรับนิสิต (แถว) | {sum(len(p['rows']) + 2 for p in pl.get('plans') or [])} |  |  | ≥ 95% |",
        f"| อาจารย์ (คน × 4 ช่อง) | {len(tc.get('teachers') or []) * 4} |  |  | ≥ 95% |",
        f"| โครงสร้างหลักสูตร (แถว) | {st.get('node_count', 0)} |  |  | ≥ 95% |",
        f"| PLO | {plo.get('count', 0)} |  |  | ≥ 95% |",
        f"| KSEC (รายการ) | {ks.get('count', 0)} |  |  | ≥ 95% |",
        f"| รายวิชา (แถว × 4 ช่อง) | {len(courses) * 4} |  |  | ≥ 95% |",
        f"| ชุดวิชา (ชุด × 3 ช่อง) | {len(mdd.get('modules') or []) * 3} |  |  | ≥ 95% |",
        f"| Curriculum Mapping 4.1 (แถว) | {len(mp.get('rows') or [])} |  |  | ≥ 95% |",
        f"| Curriculum Mapping 4.2 (แถว) | {len(mp.get('ksec_rows') or [])} |  |  | ≥ 95% |",
        "",
    ]
    return "\n".join(L)
