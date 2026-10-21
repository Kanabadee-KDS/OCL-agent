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


def _val(v: Any) -> str:
    if v is None or v == "" or v == []:
        return ""
    if isinstance(v, bool):
        return "ใช่" if v else "ไม่ใช่"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def render_info(data: dict[str, Any]) -> str:
    values = data.get("values") or {}
    metas = data.get("meta") or {}
    fields = data.get("fields") or []
    if not any(values.get(k) not in (None, "", []) for k in ("name_th", "degree_full_th")):
        return (
            "# ข้อมูลหลักสูตร\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "| ฟิลด์ | ค่า |\n| --- | --- |\n| ชื่อหลักสูตร (ไทย) | |\n"
            "| ชื่อหลักสูตร (อังกฤษ) | |\n| ปีการศึกษาที่เริ่มใช้ | |\n| หน่วยกิตตลอดหลักสูตร | |\n"
        )
    year = values.get("edition_year") or values.get("start_year")
    lines = [
        "# ข้อมูลหลักสูตร",
        "",
        f"**{values.get('name_th') or ''}**  ",
        f"{values.get('name_en') or ''}  ",
        f"{values.get('degree_full_th') or ''} · {values.get('degree_abbr_th') or ''}  ",
        f"ฉบับ พ.ศ. {year or '–'} ({values.get('revision_type') or '–'}) · "
        f"หน่วยกิตตลอดหลักสูตร ไม่น้อยกว่า **{values.get('total_credits') or '–'}** หน่วยกิต · "
        f"ระยะเวลา {values.get('duration_years') or '–'} ปี",
        "",
    ]
    group = None
    for f in fields:
        v = values.get(f["key"])
        if v in (None, "", []):
            continue
        if f["group"] != group:
            group = f["group"]
            lines += ["", f"## {group}", "", "| ฟิลด์ | ค่า | ที่มา |", "| --- | --- | --- |"]
        m = metas.get(f["key"]) or {}
        src = ("อนุมาน · " if m.get("inferred") else "") + _conf(m)
        lines.append(f"| {f['label']} | {_val(v)} | {src} |")
    majors = data.get("majors") or []
    lines += ["", "## วิชาเอก/แขนงวิชา", ""]
    lines += [f"- {x['name']}" for x in majors] or ["ไม่มี"]
    collab = data.get("collaborations") or []
    lines += ["", "## ความร่วมมือกับสถาบันอื่น", ""]
    if collab:
        lines += ["| สถาบัน | ประเทศ | ในประเทศ/ต่างประเทศ |", "| --- | --- | --- |"]
        lines += [
            f"| {x['institution']} | {x.get('country') or ''} | "
            f"{'ในประเทศ' if x.get('domestic') else 'ต่างประเทศ'} |"
            for x in collab
        ]
    else:
        lines.append(values.get("collaboration_text") or "ไม่มี")
    careers = data.get("careers") or []
    lines += ["", "## อาชีพที่ประกอบได้หลังสำเร็จการศึกษา", ""]
    if careers:
        lines += ["| กลุ่ม | อาชีพ | หน้า |", "| --- | --- | --- |"]
        lines += [
            f"| {c.get('group') or ''} | {c['name']} | "
            f"{((c.get('meta') or {}).get('source') or {}).get('page') or ''} |"
            for c in careers
        ]
    else:
        lines.append("_[ไม่พบ]_")
    return "\n".join(lines) + "\n"


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


def render_ksec(data: dict[str, Any]) -> str:
    plos = data.get("plos") or []
    if not plos:
        return (
            "# KSEC ตาม PLO\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "| PLO | รหัส | ด้าน | รายละเอียด |\n| --- | --- | --- | --- |\n| PLO1 | K1-1 | K | |\n"
        )
    cat = {"K": "ความรู้ (K)", "S": "ทักษะ (S)", "E": "จริยธรรม (E)", "C": "คุณลักษณะ (C)"}
    lines = ["# ผลลัพธ์การเรียนรู้ 4 ด้าน (KSEC) ตาม PLO", "", f"รวม {data.get('count', 0)} รายการ"]
    plan = object()
    for p in plos:
        if p.get("plan") != plan:
            plan = p.get("plan")
            if plan:
                lines += ["", f"## {plan}"]
        head = f"### {p['code']}" + (f" ({p['group']})" if p.get("group") else "")
        lines += ["", head, "", p.get("text") or "", ""]
        lines += ["| รหัส | ด้าน | ประเภท | รายละเอียด | หน้า |", "| --- | --- | --- | --- | --- |"]
        for it in p.get("items") or []:
            page = ((it.get("meta") or {}).get("source") or {}).get("page") or ""
            lines.append(
                f"| {it['code']} | {cat.get(it['category'], it['category'])} "
                f"| {it.get('subtype') or ''} | {it.get('text') or ''} | {page} |"
            )
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
    krows = data.get("ksec_rows") or []
    kcols = data.get("ksec_columns") or []
    if krows and kcols:
        lines += [
            "",
            "## 4.2 รายวิชา × KSEC",
            "",
            f"รายวิชา {len(krows)} · คอลัมน์ {len(kcols)} · ค่าในช่อง = รหัส KSEC ที่รายวิชารับผิดชอบ",
            "",
            "| รายวิชา | " + " | ".join(kcols) + " |",
            "|" + " --- |" * (len(kcols) + 1),
        ]
        for r in krows:
            cells = " | ".join(", ".join(r.get("by_column", {}).get(c, [])) for c in kcols)
            lines.append(f"| {r['course_code']} {r.get('course_name') or ''} | {cells} |")
    return "\n".join(lines) + "\n"


def render_approval(data: dict[str, Any]) -> str:
    rows = data.get("approvals") or []
    lines = ["# สถานภาพของหลักสูตรและมติอนุมัติ", ""]
    if not rows and not data.get("status"):
        return (
            "# สถานภาพของหลักสูตรและมติอนุมัติ\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "| ระดับ | ครั้งที่ | วันที่ประชุม | มติ |\n| --- | --- | --- | --- |\n"
            "| คณะกรรมการการศึกษา | | | |\n| สภาวิชาการ | | | |\n| สภามหาวิทยาลัย | | | |\n"
        )
    st = data.get("status")
    prev = data.get("previous_program")
    lines.append(
        f"- สถานภาพ: **หลักสูตร{st}**"
        + (f" จาก{prev} (พ.ศ. {data.get('previous_year') or '–'})" if prev else "")
        if st
        else "- สถานภาพ: _[ไม่พบ]_"
    )
    if data.get("start_year"):
        lines.append(
            f"- เริ่มใช้: ภาคการศึกษา {data.get('start_semester') or '–'} ปีการศึกษา {data['start_year']}"
        )
    lines += ["", "| ระดับ | ครั้งที่ | วันที่ประชุม | มติ | หน้า |", "| --- | --- | --- | --- | --- |"]
    for a in rows:
        d = a.get("date") or {}
        page = ((a.get("meta") or {}).get("source") or {}).get("page") or ""
        res = "_[เล่มเว้นว่าง]_" if a.get("pending") else a.get("resolution") or ""
        lines.append(
            f"| {a['level']} | {a.get('meeting_no') or '–'} | {d.get('text') or '–'} "
            f"| {res} | {page} |"
        )
    missing = data.get("missing_levels") or []
    if missing:
        lines += ["", "ยังไม่มีมติ/ยังไม่มีในเล่ม: " + " · ".join(missing)]
    return "\n".join(lines) + "\n"


def degree_text(d: dict[str, Any]) -> str:
    s = d.get("degree") or ""
    if d.get("field"):
        s += f" ({d['field']})"
    if d.get("year"):
        s += f", {d['year']}"
    if d.get("institution"):
        s += f" – {d['institution']}"
    return s


def render_teachers(data: dict[str, Any]) -> str:
    rows = data.get("teachers") or []
    if not rows:
        return (
            "# อาจารย์หลักสูตร\n\n> AI สกัดไม่ได้ กรอกด้วยมือ\n\n"
            "| ลำดับ | ชื่อ | ตำแหน่ง | ผู้รับผิดชอบ | คุณวุฒิ ตรี-โท-เอก (สาขา) ปี – สถาบัน |\n"
            "| --- | --- | --- | --- | --- |\n| 1 | | | | |\n"
        )
    lines = [
        "# อาจารย์ผู้รับผิดชอบหลักสูตรและอาจารย์ประจำหลักสูตร",
        "",
        f"อาจารย์ประจำ {len(rows)} คน · ผู้รับผิดชอบ {data.get('responsible_count', 0)} คน (*)",
        "",
        "| ลำดับ | ชื่อ | ตำแหน่ง | วิชาเอก | คุณวุฒิ ตรี-โท-เอก (สาขา), ปี – สถาบัน | หน้า |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for t in rows:
        rank = " ".join(x for x in (t.get("rank"), "ดร." if t.get("doctor") else None) if x)
        page = ((t.get("meta") or {}).get("source") or {}).get("page") or ""
        degs = " · ".join(degree_text(d) for d in t.get("degrees") or [])
        lines.append(
            f"| {t.get('order') or ''}{'*' if t.get('responsible') else ''} | {t['name']} | {rank} "
            f"| {t.get('group') or ''} | {degs} | {page} |"
        )
    return "\n".join(lines) + "\n"


RENDERERS = {
    "info": ("1-program_info.md", render_info),
    "teachers": ("8-teachers.md", render_teachers),
    "structure": ("2-course_structure.md", render_structure),
    "plo": ("4-plos.md", render_plo),
    "ksec": ("4b-ksec.md", render_ksec),
    "courses": ("3-courses_list.md", render_courses),
    "mapping": ("5-curriculum_mapping.md", render_mapping),
    "appr": ("7-approval.md", render_approval),
}
