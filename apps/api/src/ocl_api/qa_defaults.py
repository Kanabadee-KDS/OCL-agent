"""Curriculum assessment defaults (BRD 04 · the mock's qa-criteria): the seed of migration 018.

No imports beyond json, so db.py can build the seed from it (qa.py uses the database).
The 2565 set is BRD 04 §2; 2548 and 2558 take the same ten items until the official texts
arrive (FS-6 Q1 ก), so the central office edits them on the criteria page.
"""

from __future__ import annotations

import json
from typing import Any

SETS = [2548, 2558, 2565]
LEVELS = {"all": "ทุกระดับ", "grad": "บัณฑิตศึกษา"}
# what the system computes as "ผลตามเกณฑ์จากข้อมูล" (FS-6 Q2 ก); none = the evaluator only
RULES = {
    "responsible_count": "นับอาจารย์ผู้รับผิดชอบในหมวด 0.2 และซ้ำกับหลักสูตรอื่น",
    "responsible_qual": "คุณวุฒิ/ตำแหน่งและผลงาน 5 ปีของอาจารย์ผู้รับผิดชอบ",
    "staff_qual": "คุณวุฒิ/ตำแหน่งและผลงาน 5 ปีของอาจารย์ประจำหลักสูตร",
    "teacher_qual": "คุณวุฒิ/ตำแหน่งของอาจารย์ผู้สอนตามตารางสอน",
    "revision_age": "ระยะเวลาจากวันที่สภามหาวิทยาลัยอนุมัติ",
    "none": "ไม่มีข้อมูลให้ระบบคำนวณ",
}
# (no, title, detail, sources, level, rule) · BRD 04 §2 (ชุด พ.ศ. 2565)
ITEMS: list[tuple[int, str, str, list[str], str, str]] = [
    (1, "จำนวนอาจารย์ผู้รับผิดชอบหลักสูตร",
     "ปริญญาตรีไม่น้อยกว่า 5 คน บัณฑิตศึกษาไม่น้อยกว่า 3 คน ไม่ซ้ำกับหลักสูตรอื่น และประจำหลักสูตรตลอดระยะเวลา",
     ["SUPREME งานหลักสูตร", "HURIS ประวัติ", "คู่มือหลักสูตร หมวด 0.2"], "all", "responsible_count"),
    (2, "คุณสมบัติของอาจารย์ผู้รับผิดชอบหลักสูตร",
     "คุณวุฒิปริญญาโทหรือตำแหน่งผู้ช่วยศาสตราจารย์ขึ้นไป สาขาตรงหรือสัมพันธ์ มีผลงานทางวิชาการอย่างน้อย 1 รายการใน 5 ปีย้อนหลัง",
     ["SUPREME งานหลักสูตร", "HURIS ตำแหน่ง", "HURIS ผลงาน"], "all", "responsible_qual"),
    (3, "คุณสมบัติของอาจารย์ประจำหลักสูตร",
     "คุณสมบัติเหมือนข้อ 2 ไม่จำกัดจำนวน",
     ["SUPREME งานหลักสูตร", "HURIS ตำแหน่ง", "HURIS ผลงาน"], "all", "staff_qual"),
    (4, "คุณสมบัติของอาจารย์ผู้สอน",
     "อาจารย์ประจำ: ปริญญาโทหรือผู้ช่วยศาสตราจารย์ขึ้นไป · อาจารย์พิเศษ: ปริญญาโท หรือปริญญาตรีที่มีประสบการณ์ไม่น้อยกว่า 6 ปี สอนไม่เกินร้อยละ 50 ของรายวิชา",
     ["SUPREME ตารางสอน", "SUPREME ทะเบียน", "HURIS ประวัติ"], "all", "teacher_qual"),
    (5, "คุณสมบัติของอาจารย์ที่ปรึกษาวิทยานิพนธ์หลักและการค้นคว้าอิสระ",
     "ปริญญาเอก หรือปริญญาโทและตำแหน่งรองศาสตราจารย์ ผลงาน 3 รายการใน 5 ปี มีวิจัยอย่างน้อย 1 รายการ",
     ["SUPREME ปริญญานิพนธ์", "HURIS ผลงาน"], "grad", "none"),
    (6, "คุณสมบัติของอาจารย์ที่ปรึกษาวิทยานิพนธ์ร่วม",
     "อาจารย์ประจำหรือผู้ทรงคุณวุฒิภายนอกที่มีคุณสมบัติตามประกาศ",
     ["SUPREME ปริญญานิพนธ์", "HURIS ผลงาน"], "grad", "none"),
    (7, "คุณสมบัติของอาจารย์ผู้สอบวิทยานิพนธ์",
     "ไม่น้อยกว่า 3 คน ประธานไม่ใช่อาจารย์ที่ปรึกษา",
     ["SUPREME ปริญญานิพนธ์", "HURIS ประวัติ"], "grad", "none"),
    (8, "การตีพิมพ์เผยแพร่ผลงานของผู้สำเร็จการศึกษา",
     "แผน ก1 ก2 และ ข ตามที่ประกาศกำหนด",
     ["SUPREME ปริญญานิพนธ์"], "grad", "none"),
    (9, "ภาระงานอาจารย์ที่ปรึกษาวิทยานิพนธ์และการค้นคว้าอิสระ",
     "วิทยานิพนธ์ 1 ต่อ 5 · การค้นคว้าอิสระ 1 ต่อ 15",
     ["SUPREME คณาจารย์บัณฑิต"], "grad", "none"),
    (10, "การปรับปรุงหลักสูตรตามรอบระยะเวลาที่กำหนด",
     "ไม่เกิน 5 ปีนับจากวันที่สภามหาวิทยาลัยอนุมัติ",
     ["SUPREME งานหลักสูตร", "คู่มือหลักสูตร หมวด 5"], "all", "revision_age"),
]  # fmt: skip
SAMPLE_NOTE = "[สมมติ: ใช้โครงเดียวกับชุด 2565 จนกว่าจะได้ประกาศฉบับทางการ]"


def seed_sql() -> str:
    def q(v: Any) -> str:
        return "'" + str(v).replace("'", "''") + "'"

    rows = []
    for year in SETS:
        for no, title, detail, sources, level, rule in ITEMS:
            d = detail if year == 2565 else f"{detail} {SAMPLE_NOTE}"
            rows.append(
                f"({year}, {no}, {q(title)}, {q(d)}, "
                f"{q(json.dumps(sources, ensure_ascii=False))}::jsonb, {q(level)}, {q(rule)})"
            )
    return (
        "INSERT INTO qa_criteria (set_year, no, title, detail, sources, level, rule) VALUES\n"
        + ",\n".join(rows)
        + "\nON CONFLICT DO NOTHING;\n"
    )
