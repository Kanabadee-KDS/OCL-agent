"""The คู่มือหลักสูตร form, หมวด 0 1 2 5 (BRD 01 §4 data dictionary · mock cur-edit).

One description that the web renders, the API counts progress from, and sections.py splits
`info` by: every field names its `path` inside the section's data. Fields the import already
reads take label, kind and options from the extractor (extract/info.py FIELDS), so the review
page and this form never disagree; only fields the book does not carry are described here.
หมวด 3–4 have their own editors (FS-2c); their progress is counted from what they hold.

Kinds: text · textarea · int · date · bool · enum · tags (several of the options) · table
(rows of `columns`) · and blocks with their own editor: teachers · teachers_view · plan ·
book (approved PDF) · master (หมวด 1's read-only copy of หมวด 0).
`lookup` options may be extended by the administrators (table `lookups`, migration 011).
"""

from __future__ import annotations

from typing import Any

from ocl_api.extract.info import FIELDS as INFO_FIELDS

_INFO = {f["key"]: f for f in INFO_FIELDS}
_KIND = {"list": "tags"}


def info(key: str, *, required: bool = False, **extra: Any) -> dict[str, Any]:
    """A field the import reads: label, kind and options from the extractor."""
    f = _INFO[key]
    out = {"key": key, "label": f["label"], "kind": _KIND.get(f["kind"], f["kind"])}
    if f.get("options"):
        out["options"] = list(f["options"])
    out.update(path=f"info.values.{key}", required=required, source="เล่ม", **extra)
    return out


def new(key: str, label: str, kind: str, path: str | None = None, **extra: Any) -> dict:
    """A field of the data dictionary that the book does not carry."""
    return {"key": key, "label": label, "kind": kind,
            "path": path or f"info.values.{key}", "required": False, **extra}  # fmt: skip


def col(key: str, label: str, kind: str = "text", **extra: Any) -> dict[str, Any]:
    return {"key": key, "label": label, "kind": kind, **extra}


TEACHING_MODES = ["On-site", "Online", "Hybrid", "WIL"]
APPROVAL_LEVELS = [
    "คณะกรรมการการศึกษาระดับปริญญาตรี",
    "คณะกรรมการการศึกษาระดับบัณฑิตศึกษา",
    "สภาวิชาการ",
    "สภามหาวิทยาลัย",
    "สภาวิชาชีพ",
]

FORM: dict[str, list[dict[str, Any]]] = {
    "0": [
        {"title": "ก. ทะเบียน", "fields": [
            new("supreme_code", "รหัสหลักสูตร (SUPREME)", "text", source="SUPREME",
                hint="ดึงจาก SUPREME เมื่อเชื่อมระบบ"),
            info("program_code", hint="14 หลัก"),
            info("education_group", required=True),
            info("revision_type", required=True),
            info("edition_year", required=True),  # 1 คู่มือ per program per edition (BRD 01 §1)
            info("previous_program", required_when={"key": "revision_type", "equals": "ปรับปรุง"}),
            info("previous_year"),
            new("book_status", "สถานะเล่มหลักสูตร", "enum", options=["เล่มแม่", "เล่มลูก"],
                required=True),
            info("faculty", required=True),
        ]},
        {"title": "ข. ชื่อหลักสูตรและปริญญา", "fields": [
            info("name_th", required=True),
            info("name_en", required=True),
            info("level", required=True),
            info("field_of_study", required=True, lookup=True),
            new("show_field_of_study", "แสดงสาขาวิชาในชื่อปริญญา", "bool"),
            info("degree_full_th", required=True),
            info("degree_abbr_th", required=True),
            info("degree_full_en", required=True),
            info("degree_abbr_en", required=True),
            new("conferred_by", "ประสาทปริญญาโดย", "text"),
            new("extra_degrees", "กรณีมีปริญญามากกว่า 1 ใบ", "table", columns=[
                col("by", "ประสาทโดย"), col("full_th", "ชื่อเต็ม (ไทย)"),
                col("abbr_th", "ชื่อย่อ (ไทย)"), col("full_en", "ชื่อเต็ม (อังกฤษ)"),
                col("abbr_en", "ชื่อย่อ (อังกฤษ)"),
            ]),
        ]},
        {"title": "ค. เวลาและหน่วยกิต", "fields": [
            info("duration_years", required=True),
            new("plan_code", "รหัสแผน", "text"),
            new("semester_limits", "จำนวนภาคที่ต้องใช้", "table", columns=[
                col("mode", "แบบ", "enum", options=["เต็มเวลา", "บางเวลา"]),
                col("min", "น้อยสุด", "int"), col("max", "มากสุด", "int"),
            ]),
            info("total_credits", required=True),
            new("credits_note", "รายละเอียดกรณีหลายแผน", "textarea"),
            info("start_semester", required=True),
            info("start_year", required=True),
        ]},
        {"title": "ง. การใช้งาน", "fields": [
            info("semesters_counted", required=True),
            info("education_system"),
            info("admission_type", required=True),
            info("is_international"),
            info("admission_text", kind="textarea"),
            info("standard_criteria", required=True),
            new("tqf1_ref", "อ้างอิง มคอ.1", "text", lookup=True),
            new("approved_book", "ไฟล์เล่มหลักสูตรที่อนุมัติแล้ว (PDF ≤ 50 MB)", "book",
                required=True),
            new("active_status", "สถานะการใช้งาน", "enum", options=["ใช้งาน", "ไม่ใช้งาน"],
                required=True),
        ]},
        {"title": "0.2 อาจารย์หลักสูตร", "fields": [
            new("teachers", "อาจารย์ผู้รับผิดชอบ/ประจำหลักสูตร", "teachers",
                path="teachers.teachers", required=True, source="HURIS"),
        ]},
    ],
    "1": [
        {"title": "1.1–1.4 ข้อมูลหลัก (แก้ที่หมวด 0)", "fields": [
            new("master", "รหัส ชื่อ ปริญญา หน่วยกิต", "master", path="-"),
        ]},
        {"title": "1.3 วิชาเอก/แขนงวิชา", "fields": [
            new("majors", "วิชาเอก/แขนงวิชา (ว่าง = ไม่มี)", "table", path="info.majors",
                columns=[col("name", "ชื่อวิชาเอก/แขนง")]),
        ]},
        {"title": "1.5 รูปแบบของหลักสูตร", "fields": [
            info("program_type", required=True, lookup=True),
            info("program_type_text", kind="textarea"),
            info("program_categories"),
            new("prep_type", "ประเภทการจัดทำ", "enum",
                options=["ใหม่", "ปรับปรุง", "ปรับปรุงแบบแยก", "ปรับปรุงแบบรวม"]),
            info("cwie"),
            new("cwie_type", "ประเภท CWIE", "enum", options=["แยก", "คู่ขนาน", "ผสม"],
                lookup=True),
            new("cwie_format", "รูปแบบ CWIE", "enum",
                options=["ฝึกงาน", "สหกิจศึกษา", "ฝึกปฏิบัติวิชาชีพ"], lookup=True),
        ]},
        {"title": "1.6 ระยะเวลาและแผนการศึกษา", "fields": [
            info("study_mode", required=True),
            info("lifelong"),
            new("semesters_open", "ภาคที่เปิดสอน", "tags", options=["1", "2", "ฤดูร้อน"]),
            new("first_open_date", "วันเปิดสอนครั้งแรก", "date"),
        ]},
        {"title": "1.7 ภาษา", "fields": [
            info("language", required=True),
            info("language_text", kind="textarea"),
        ]},
        {"title": "1.8 ความร่วมมือกับสถาบันอื่น", "fields": [
            new("collaborations", "สถาบันที่ร่วมมือ", "table", path="info.collaborations",
                columns=[
                    col("institution", "สถาบัน"),
                    col("location", "ในประเทศ/ต่างประเทศ", "enum",
                        options=["ในประเทศ", "ต่างประเทศ"]),
                    col("form", "รูปแบบ", "enum",
                        options=["วิชาการ", "Dual Degree", "Joint Degree", "อื่น ๆ"]),
                    col("document", "เอกสาร MOU/MOA"),
                ]),
            info("collaboration_text", kind="textarea"),
        ]},
        {"title": "1.9 อาชีพที่สามารถประกอบได้หลังสำเร็จการศึกษา", "fields": [
            new("careers", "อาชีพ", "table", path="info.careers", required=True,
                columns=[col("group", "กลุ่มอาชีพ"), col("name", "อาชีพ")]),
        ]},
        {"title": "1.10–1.11 อาจารย์ผู้รับผิดชอบ/ประจำหลักสูตร (จากหมวด 0.2)", "fields": [
            new("teachers_view", "อาจารย์", "teachers_view", path="-"),
        ]},
    ],
    "2": [
        {"title": "2.1 แผนการรับนิสิต", "fields": [
            new("plan", "แผนการรับนิสิต 5 ปี", "plan", path="plan.plans", required=True),
        ]},
        {"title": "2.2 รูปแบบและวิธีการจัดการเรียนการสอน", "fields": [
            new("teaching_modes", "รูปแบบการเรียนการสอน", "tags", path="plan.teaching_modes",
                options=TEACHING_MODES, required=True, lookup=True),
        ]},
    ],
    "5": [
        {"title": "มติที่ประชุมแต่ละระดับ", "fields": [
            new("approvals", "การอนุมัติ/เห็นชอบ", "table", path="appr.approvals", required=True,
                columns=[
                    col("level", "ระดับ", "enum", options=APPROVAL_LEVELS, lookup=True),
                    col("meeting_no", "ครั้งที่"), col("date", "วันที่", "date"),
                    col("resolution", "มติ"),
                ]),
            new("mhesi_ack_date", "อว. รับทราบเมื่อวันที่", "date", path="appr.mhesi_ack_date"),
        ]},
    ],
}  # fmt: skip

# info.values keys and info lists that belong to หมวด 1 (sections.py splits `info` by these)
SECTION1_VALUES = {
    f["path"].split(".", 2)[2]
    for g in FORM["1"]
    for f in g["fields"]
    if f["path"].startswith("info.values.")
}
SECTION1_LISTS = {
    f["path"].split(".", 1)[1]
    for g in FORM["1"]
    for f in g["fields"]
    if f["path"].startswith("info.") and not f["path"].startswith("info.values.")
}


def fields(n: str) -> list[dict[str, Any]]:
    return [f for g in FORM.get(n, []) for f in g["fields"]]


def get_path(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for p in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and p.isdigit() and int(p) < len(cur):
            cur = cur[int(p)]
        else:
            return None
    return cur


def _filled(f: dict[str, Any], v: Any) -> bool:
    if f["kind"] == "plan":  # some intake in some year
        rows = [r for p in (v or []) for r in (p.get("rows") or [])]
        return any(x for r in rows for x in (r.get("values") or []))
    if f["kind"] == "book":
        return bool(v and v.get("file"))
    if isinstance(v, (list, dict, str)):
        return bool(v)
    return v is not None


def progress(sections: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per หมวด: required items done/total and the labels still missing (the sidebar ✓)."""
    out: dict[str, dict[str, Any]] = {}
    for n in ("0", "1", "2", "5"):
        data = sections.get(n) or {}
        values0 = get_path(sections.get("0") or {}, "info.values") or {}
        values = {**values0, **(get_path(data, "info.values") or {})}
        missing = []
        total = 0
        for f in fields(n):
            when = f.get("required_when")
            needed = f["required"] or (when and values.get(when["key"]) == when["equals"])
            if not needed:
                continue
            total += 1
            if not _filled(f, get_path(data, f["path"])):
                missing.append(f["label"])
        out[n] = {"done": total - len(missing), "total": total, "missing": missing}
    s3, s4 = sections.get("3") or {}, sections.get("4") or {}
    checks = {
        "3": [("PLO", get_path(s3, "plo.plos")), ("KSEC", get_path(s3, "ksec.codes"))],
        "4": [("โครงสร้าง", get_path(s4, "structure.tree")),
              ("รายวิชา", get_path(s4, "courses.courses")),
              ("Curriculum Mapping", get_path(s4, "mapping.rows"))],
    }  # fmt: skip
    for n, items in checks.items():
        missing = [label for label, v in items if not v]
        out[n] = {"done": len(items) - len(missing), "total": len(items), "missing": missing}
    return dict(sorted(out.items()))


def spec(extra_options: dict[str, list[str]]) -> dict[str, Any]:
    """The form for the web, with the administrators' added options merged in."""

    def merge(f: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        f = dict(f)
        f["lookup_key"] = prefix + f["key"]  # a table column: "<table>.<column>"
        added = extra_options.get(f["lookup_key"], []) if f.get("lookup") else []
        if added:
            have = f.get("options", [])
            f["options"] = [*have, *[o for o in added if o not in have]]
        if f.get("columns"):
            f["columns"] = [merge(c, f["key"] + ".") for c in f["columns"]]
        return f

    return {n: [{**g, "fields": [merge(f) for f in g["fields"]]} for g in groups]
            for n, groups in FORM.items()}  # fmt: skip


def lookup_keys() -> set[str]:
    """Fields and table columns whose options the administrators may extend."""
    out = set()
    for groups in FORM.values():
        for f in (f for g in groups for f in g["fields"]):
            if f.get("lookup"):
                out.add(f["key"])
            out |= {f"{f['key']}.{c['key']}" for c in f.get("columns", []) if c.get("lookup")}
    return out
