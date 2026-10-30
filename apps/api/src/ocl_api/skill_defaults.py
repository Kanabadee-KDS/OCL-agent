"""Skill Transcript defaults (BRD 03 · the mock's D.skills): the seed of migration 017.

No imports beyond json, so db.py can build the seed from it (skills.py uses the database).
The skills are the mock's sample list until the university's skill database arrives (A7).
"""

from __future__ import annotations

import json
from typing import Any

# the four sides (BRD 03 §1)
CATS: dict[str, dict[str, str]] = {
    "GS": {"name": "Generic skills", "th": "ทักษะทั่วไป"},
    "SS": {"name": "Specific skills", "th": "ทักษะเฉพาะ"},
    "E": {"name": "Ethics", "th": "จริยธรรม"},
    "C": {"name": "Characters", "th": "คุณลักษณะ"},
}
SCOPES = {"central": "ส่วนกลาง มศว", "program": "หลักสูตรกำหนด"}
TOOLS = {"rubric": "Scoring rubrics", "self": "Self-Assessment (5 ระดับ)"}
SOURCES = {"course": "รายวิชา", "coop": "สหกิจศึกษา/ฝึกงาน", "activity": "กิจกรรมเสริมหลักสูตร"}

# BR-M3-02: five levels of proficiency from the average score (BRD 03 §1)
LEVELS: list[dict[str, Any]] = [
    {"level": 1, "min": 0.0, "max": 1.49, "en": "Novice", "th": "ผู้เริ่มต้น"},
    {"level": 2, "min": 1.5, "max": 2.49, "en": "Advanced Beginner", "th": "ผู้มีประสบการณ์"},
    {"level": 3, "min": 2.5, "max": 3.49, "en": "Competent", "th": "ผู้มีความสามารถ"},
    {"level": 4, "min": 3.5, "max": 4.49, "en": "Proficient", "th": "ผู้มีความชำนาญ"},
    {"level": 5, "min": 4.5, "max": 5.0, "en": "Expert", "th": "ผู้เชี่ยวชาญ"},
]
# BR-M3-04 [สมมติ · FS-5 Q4 ก]: an Ethics score from this up is S, below is U
ETHICS_PASS = 2.5
FRAMEWORKS: list[dict[str, Any]] = [
    {"level": "ปริญญาตรี", "cohorts": "67 ขึ้นไป", "frame": "GS 5 · SS ตามหลักสูตร · E 4 · C 5",
     "status": "ใช้งาน"},
    {"level": "ปริญญาตรี", "cohorts": "64–66", "frame": "GS 3 · E 2 · C 2 (กรอบเดิม)",
     "status": "กรอบเดิม"},
    {"level": "บัณฑิตศึกษา", "cohorts": "68 ขึ้นไป", "frame": "ยังไม่กำหนด", "status": "ยังไม่กำหนด"},
]  # fmt: skip

# the rights of a person who sets the skills of a curriculum (the mock's SKP) and the
# starting rights of each role (SKROLE)
ASSIGN_PERMS: dict[str, str] = {
    "add": "เพิ่ม Skill ของหลักสูตร (SS/E/C)",
    "map": "กำหนดรายวิชาประเมิน Skill (Mapping)",
    "send": "ส่งเข้าสู่การอนุมัติ",
    "appr": "อนุมัติ Skill/Mapping ของหลักสูตร",
}
ASSIGN_ROLES: dict[str, dict[str, Any]] = {
    "chair": {"label": "ประธานหลักสูตร", "perms": ["add", "map", "send", "appr"], "scope": "all"},
    "cur": {"label": "อาจารย์ผู้รับผิดชอบหลักสูตร", "perms": ["add", "map", "send"],
            "scope": "all"},
    "tch": {"label": "อาจารย์ผู้สอน", "perms": ["map"], "scope": "courses"},
    "staff": {"label": "เจ้าหน้าที่หลักสูตร", "perms": ["map", "send"], "scope": "all"},
}  # fmt: skip

# (code, side, Thai, English, scope) · central = every curriculum must assess it (BR-M3-03)
SAMPLE_SKILLS: list[tuple[str, str, str, str, str]] = [
    ("GS1", "GS", "ทักษะการสื่อสาร", "Communication", "central"),
    ("GS2", "GS", "ทักษะการตั้งเป้าหมาย", "Goal Setting", "central"),
    ("GS3", "GS", "ทักษะการคิดแก้ปัญหาเชิงสร้างสรรค์และการคิดออกแบบ",
     "Creative Problem Solving & Design Thinking", "central"),
    ("GS4", "GS", "ทักษะการคิดวิเคราะห์สารสนเทศและความฉลาดรู้ AI",
     "Information Analysis & AI Literacy", "central"),
    ("GS5", "GS", "ทักษะการเรียนรู้ตลอดชีวิต", "Lifelong Learning", "central"),
    ("E1", "E", "ความซื่อสัตย์ทางวิชาการ", "Academic Integrity", "central"),
    ("E2", "E", "จรรยาบรรณตามวิชาชีพ/สาขาวิชา", "Professional Ethics", "program"),
    ("E3", "E", "ความรับผิดชอบต่อสังคม", "Social Responsibility", "central"),
    ("E4", "E", "การเคารพตนเองและผู้อื่น", "Respect for Self and Others", "central"),
    ("C1", "C", "การทำงานร่วมกัน", "Collaboration", "central"),
    ("C2", "C", "การคิดบวก", "Positive Thinking", "central"),
    ("C3", "C", "ความมั่นใจ", "Confidence", "program"),
    ("C4", "C", "ความอ่อนน้อมถ่อมตน", "Humility", "program"),
    ("C5", "C", "ความไว้เนื้อเชื่อใจ", "Trustworthiness", "program"),
]  # fmt: skip
SAMPLE_DEFINITION = "[นิยามตัวอย่าง · รอฐานข้อมูล Skill ของมหาวิทยาลัย (A7)]"


def blank_rubric() -> list[str]:
    return [f"[คำอธิบายพฤติกรรมระดับ {i + 1}]" for i in range(len(LEVELS))]


def seed_sql() -> str:
    def q(v: Any) -> str:
        return "'" + str(v).replace("'", "''") + "'"

    rows = ",\n".join(
        f"({q(c)}, {q(cat)}, {q(th)}, {q(en)}, {q(SAMPLE_DEFINITION)}, {q(scope)}, "
        f"{q(json.dumps(list(TOOLS)))}::jsonb, {q(json.dumps(['course', 'coop']))}::jsonb, "
        f"{q(json.dumps(blank_rubric(), ensure_ascii=False))}::jsonb, 'seed')"
        for c, cat, th, en, scope in SAMPLE_SKILLS
    )
    settings = ",\n".join(
        f"({q(k)}, {q(json.dumps(v, ensure_ascii=False))}::jsonb)"
        for k, v in {"levels": LEVELS, "ethics_pass": ETHICS_PASS, "frameworks": FRAMEWORKS}.items()
    )
    perms = (
        f"('role:central', {q(json.dumps(list(CATS)))}::jsonb, 'all'),\n"
        f"('role:curator', {q(json.dumps(['SS', 'E', 'C']))}::jsonb, 'program')"
    )
    return (
        "INSERT INTO skills (code, cat, name_th, name_en, definition, scope, tools, sources, "
        f"rubric, created_by) VALUES\n{rows}\nON CONFLICT DO NOTHING;\n"
        f"INSERT INTO skill_settings (key, data) VALUES\n{settings}\nON CONFLICT DO NOTHING;\n"
        f"INSERT INTO skill_db_perms (who, cats, unit_scope) VALUES\n{perms};\n"
    )
