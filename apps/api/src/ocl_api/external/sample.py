"""Sample adapter: a fixed, made-up university in the shape of the customer's mock.

Names are placeholders like the mock's ("[ชื่อ นามสกุล 1]"), e-mails end in .invalid, and
nothing is copied from a real person, so the data can sit on the server until the real
SUPREME / HURIS feed replaces it. Same input, same rows: running the seed again changes nothing.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from ocl_api.external.base import Snapshot

# the mock's FACS and MAJ (samples/ui-mock.html)
FACULTIES: list[tuple[str, list[str]]] = [
    ("คณะเทคโนโลยีและนวัตกรรมผลิตภัณฑ์การเกษตร",
     ["เทคโนโลยีวัสดุพอลิเมอร์", "เทคโนโลยีการอาหาร", "นวัตกรรมเกษตร", "เทคโนโลยีชีวภาพ"]),
    ("คณะศึกษาศาสตร์",
     ["ภาษาไทย", "คณิตศาสตร์ศึกษา", "การบริหารการศึกษา", "จิตวิทยาการศึกษา", "การศึกษาปฐมวัย"]),
    ("คณะวิทยาศาสตร์", ["เคมี", "ฟิสิกส์", "ชีววิทยา", "คณิตศาสตร์", "วิทยาการคอมพิวเตอร์"]),
    ("คณะมนุษยศาสตร์", ["ภาษาอังกฤษ", "ภาษาจีน", "ปรัชญาและศาสนา", "บรรณารักษศาสตร์"]),
    ("คณะสังคมศาสตร์", ["สังคมวิทยา", "ประวัติศาสตร์", "ภูมิศาสตร์", "รัฐศาสตร์"]),
    ("คณะแพทยศาสตร์", ["แพทยศาสตร์", "วิทยาศาสตร์การแพทย์", "เวชศาสตร์ชุมชน", "ระบาดวิทยา"]),
    ("คณะวิศวกรรมศาสตร์",
     ["วิศวกรรมคอมพิวเตอร์", "วิศวกรรมเครื่องกล", "วิศวกรรมโยธา", "วิศวกรรมไฟฟ้า"]),
    ("คณะศิลปกรรมศาสตร์", ["ทัศนศิลป์", "ดนตรีไทย", "การออกแบบ", "นาฏยศิลป์"]),
]  # fmt: skip
# bachelor degree per faculty: (full name, abbreviation); every faculty also has one master
BACHELOR = [
    ("วิทยาศาสตรบัณฑิต", "วท.บ."), ("การศึกษาบัณฑิต", "กศ.บ."), ("วิทยาศาสตรบัณฑิต", "วท.บ."),
    ("ศิลปศาสตรบัณฑิต", "ศศ.บ."), ("ศิลปศาสตรบัณฑิต", "ศศ.บ."), ("วิทยาศาสตรบัณฑิต", "วท.บ."),
    ("วิศวกรรมศาสตรบัณฑิต", "วศ.บ."), ("ศิลปกรรมศาสตรบัณฑิต", "ศป.บ."),
]  # fmt: skip
MASTER = ("วิทยาศาสตรมหาบัณฑิต", "วท.ม.")
COURSE_PREFIX = ["ทวพ", "กศท", "วทศ", "มนษ", "สคศ", "พทศ", "วศศ", "ศปก"]
TITLES = [  # (full, short, academic position)
    ("ผู้ช่วยศาสตราจารย์ ดร.", "ผศ.ดร.", "ผู้ช่วยศาสตราจารย์"),
    ("อาจารย์ ดร.", "อ.ดร.", "อาจารย์"),
    ("รองศาสตราจารย์ ดร.", "รศ.ดร.", "รองศาสตราจารย์"),
    ("อาจารย์", "อ.", "อาจารย์"),
    ("ผู้ช่วยศาสตราจารย์", "ผศ.", "ผู้ช่วยศาสตราจารย์"),
    ("ศาสตราจารย์ ดร.", "ศ.ดร.", "ศาสตราจารย์"),
]
WORK_TYPES = ["งานวิจัย", "บทความวิชาการ", "ตำรา"]
DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ."]
STAFF_PER_FACULTY = 6
STUDENTS_PER_PROGRAM = 8
TERM = "2/2569"


def _staff() -> list[dict[str, Any]]:
    rows = []
    for fi, (fac, majors) in enumerate(FACULTIES):
        for k in range(STAFF_PER_FACULTY):
            n = fi * STAFF_PER_FACULTY + k + 1
            full, short, pos = TITLES[k % len(TITLES)]
            major = majors[k % len(majors)]
            edu = [["ปริญญาตรี", "วท.บ.", major, "[สถาบัน]", "ไทย", str(2540 + k)],
                   ["ปริญญาโท", "วท.ม.", major, "[สถาบัน]", "ไทย", str(2543 + k)]]  # fmt: skip
            if "ดร." in short:
                edu.append(["ปริญญาเอก", "ปร.ด.", major, "[สถาบัน]", "ไทย", str(2548 + k)])
            works = [
                {"title": f"[ผลงานตัวอย่าง {n}.{j + 1}]", "type": WORK_TYPES[(n + j) % 3],
                 "year": str(2565 + j)}
                for j in range(k % 3 + 1)
            ]  # fmt: skip
            rows.append({
                "pid": f"SWU{fi + 1:02d}{k + 1:03d}", "title_full": full, "title_short": short,
                "position": pos, "name_th": f"[ชื่อ นามสกุล {n}]", "name_en": f"[Name Surname {n}]",
                "faculty": fac, "department": f"ภาควิชา{major}",
                "email": f"staff{n:03d}@sample.invalid", "education": edu, "works": works,
            })  # fmt: skip
    return rows


def _programs() -> list[dict[str, Any]]:
    rows = []
    for fi, (fac, majors) in enumerate(FACULTIES):
        degree, abbr = BACHELOR[fi]
        for j, major in enumerate(majors):
            rows.append({
                "code": f"25{50 + fi:02d}0091{fi + 1:02d}{j + 1:04d}",
                "name_th": f"หลักสูตร{degree} สาขาวิชา{major}", "name_en": None,
                "short": f"{abbr} {major}", "level": "ปริญญาตรี", "faculty": fac,
                "version": "ปป.67",
            })  # fmt: skip
        rows.append({
            "code": f"25{50 + fi:02d}0091{fi + 1:02d}9001",
            "name_th": f"หลักสูตร{MASTER[0]} สาขาวิชา{majors[0]}", "name_en": None,
            "short": f"{MASTER[1]} {majors[0]}", "level": "ปริญญาโท", "faculty": fac,
            "version": "ปป.66",
        })  # fmt: skip
    return rows


def _sections(programs: list[dict[str, Any]], staff: list[dict[str, Any]]) -> list[dict]:
    rng = random.Random(2569)
    rows = []
    for p in programs:
        if p["level"] != "ปริญญาตรี":
            continue
        fi = next(i for i, (f, _) in enumerate(FACULTIES) if f == p["faculty"])
        pool = [s["pid"] for s in staff if s["faculty"] == p["faculty"]]
        for c in range(3):
            code = f"{COURSE_PREFIX[fi]}{int(p['code'][-1]) * 100 + 11 + c * 10}"
            for sec in range(1 + c % 2):
                start = 9 + 4 * rng.randrange(2)
                rows.append({
                    "term": TERM, "course_code": code, "section": str(sec + 1),
                    "course_name": f"[รายวิชาตัวอย่าง {code}]", "program_code": p["code"],
                    "teachers": rng.sample(pool, 1 + (c + sec) % 2),
                    "schedule": f"{DAYS[rng.randrange(5)]} {start:02d}:00–{start + 3:02d}:00",
                    "room": f"[ห้อง {fi + 1}{c + 1}{sec + 1}]", "enrolled": rng.randrange(20, 61),
                })  # fmt: skip
    return rows


def _students(programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    n = 0
    for pi, p in enumerate(programs):
        if p["level"] != "ปริญญาตรี":
            continue
        for k in range(STUDENTS_PER_PROGRAM):
            n += 1
            graduated = k >= STUDENTS_PER_PROGRAM - 2  # two per program have finished
            entry = 2565 if graduated else 2567
            rows.append({
                "sid": f"{entry % 100}{pi + 1:03d}{k + 1:05d}", "name_th": f"[นิสิต {n}]",
                "program_code": p["code"], "entry_year": entry,
                "status": "สำเร็จการศึกษา" if graduated else "กำลังศึกษา",
                "graduated": "1/2569" if graduated else None,
            })  # fmt: skip
    return rows


SIGNERS = [
    {"id": "S01", "name_th": "[ชื่อผู้ลงนาม 1]", "position": "อธิการบดี",
     "scope": "Skill Transcript ทุกหลักสูตร"},
    {"id": "S02", "name_th": "[ชื่อผู้ลงนาม 2]", "position": "รองอธิการบดีฝ่ายวิชาการ",
     "scope": "Skill Transcript เมื่อได้รับมอบอำนาจ"},
]  # fmt: skip


class SampleAdapter:
    name = "sample"

    def __init__(self, today: date | None = None):
        self.today = today or date.today()

    def fetch(self, system: str) -> Snapshot:
        # data reaches the system through the Data Warehouse a day late (BRD 04 BR-M4-02)
        as_of = self.today - timedelta(days=1)
        staff = _staff()
        if system == "huris":
            return Snapshot({"ext_staff": staff}, as_of)
        if system == "supreme":
            programs = _programs()
            return Snapshot(
                {
                    "ext_programs": programs,
                    "ext_sections": _sections(programs, staff),
                    "ext_students": _students(programs),
                    "ext_signers": SIGNERS,
                },
                as_of,
            )
        raise ValueError(f"ไม่รู้จักระบบ {system}")
