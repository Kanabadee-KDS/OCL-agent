#!/usr/bin/env python3
"""Traceability of the BRD: mock page -> user story -> acceptance criteria -> test case.

Writes docs/brd/91-traceability.md from three sources, so the table is regenerated rather
than edited by hand whenever one of them changes:
  samples/ui-mock.html            the customer's mock (acceptance spec); not in git
  docs/brd/0*.md                  user stories "- **US-M1-nn** ..." (US-U-nn, US-G-nn for the
                                  shared pages) with "  - AC: ..." below,
                                  pages cited as "[mock: a, b]" in the story or its heading
  docs/testing/test-script_ocl.csv  every test case; tied to stories by category (TEST_MAP)

  uv run python tools/brd_trace.py           # rewrite docs/brd/91-traceability.md
  uv run python tools/brd_trace.py --check   # exit 1 if the file is stale
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / "samples/ui-mock.html"
BRD = ROOT / "docs/brd"
TESTS = ROOT / "docs/testing/test-script_ocl.csv"
OUT = BRD / "91-traceability.md"
STAMP = "สร้างโดย `tools/brd_trace.py`"

MODULES = {
    "c": "M1 บริหารข้อมูลหลักสูตร",
    "p": "M2 แผนการจัดการเรียนรู้",
    "s": "M3 Skill Transcript",
    "q": "M4 ประเมินผลหลักสูตร",
    "r": "M5 รายงาน",
    "u": "บริหารจัดการสิทธิ์",
    "m": "สำหรับนิสิต",
    "x": "ทุกบทบาท",
}

# Every page of the mock, in menu order. Menu names are the mock's own; sub-pages (opened
# from a list) are named after what they show. Checked against the mock's route table.
PAGES: list[tuple[str, str, str]] = [
    ("login", "x", "เข้าสู่ระบบ (บุคลากร)"),
    ("login-ext", "x", "เข้าสู่ระบบ (ผู้ประเมินภายนอก)"),
    ("dash", "x", "แดชบอร์ดภาพรวม / งานของฉัน"),
    ("dash-cur", "c", "แดชบอร์ดหลักสูตร"),
    ("cur", "c", "คู่มือหลักสูตรตาม TOR"),
    ("cur-edit", "c", "บันทึกคู่มือหลักสูตร หมวด 0–5"),
    ("st-courses", "c", "รายวิชาในกลุ่มวิชา (จากหมวด 4)"),
    ("fac-plo", "c", "ตรวจสอบและบันทึก PLO โดยคณะ"),
    ("fac-plo-edit", "c", "ตรวจหมวด 3–4 ของหลักสูตร"),
    ("smo", "c", "งานปรับปรุงแก้ไขหลักสูตร (สมอ.08)"),
    ("smo-new", "c", "สร้างคำขอ สมอ.08"),
    ("smo-view", "c", "ดูคำขอ สมอ.08"),
    ("import", "c", "นำเข้าข้อมูลเล่มหลักสูตร"),
    ("import-review", "c", "ตรวจผลที่ AI สกัด"),
    ("import-done", "c", "สรุปผลการนำเข้า"),
    ("course-master", "c", "บริหารรายวิชา"),
    ("ext-person", "c", "บริหารบุคคลภายนอก"),
    ("dash-plan", "p", "แดชบอร์ดแผนการจัดการเรียนรู้"),
    ("plan-assign", "p", "กำหนดผู้บันทึกแผนและรายงานผลฯ"),
    ("rep-assign", "p", "กำหนดผู้บันทึกรายงานผล"),
    ("plan", "p", "บันทึกแผนการจัดการเรียนรู้"),
    ("plan-edit", "p", "แบบบันทึกแผนรายวิชา/ชุดวิชา"),
    ("rep", "p", "บันทึกรายงานการจัดการการเรียนรู้"),
    ("rep-edit", "p", "แบบบันทึกรายงานผลรายวิชา/ชุดวิชา"),
    ("dash-skill", "s", "แดชบอร์ด Skill"),
    ("skill-db", "s", "บริหารฐานข้อมูล Skill"),
    ("skill-assign", "s", "กำหนดผู้บันทึกแผนการประเมิน Skill"),
    ("skill-cur", "s", "กำหนด Skill ตามหลักสูตร"),
    ("skill-map", "s", "กำหนดรายวิชาประเมิน Skill"),
    ("assess", "s", "บันทึกประเมิน Skill"),
    ("assess-form", "s", "แบบบันทึกผลประเมิน Skill รายวิชา"),
    ("portfolio", "s", "Skill Portfolio"),
    ("portfolio-detail", "s", "Skill Portfolio รายบุคคล"),
    ("issue", "s", "ออกเอกสาร Skill Transcript"),
    ("transcript", "s", "เอกสาร Skill Transcript"),
    ("qa-rounds", "q", "รอบการประเมิน"),
    ("qa-criteria", "q", "เกณฑ์และข้อคำถาม"),
    ("qa-assign", "q", "กำหนดผู้บันทึกและผู้ยืนยันข้อมูล"),
    ("qa-check", "q", "ตรวจสอบข้อมูลองค์ประกอบที่ 1"),
    ("qa-check-detail", "q", "บันทึกข้อมูลตามเกณฑ์ของหลักสูตร"),
    ("qa-preview", "q", "Preview รายงานผลการประเมิน"),
    ("qa-result", "q", "สรุปผลการประเมิน"),
    ("reports", "r", "ศูนย์รายงาน"),
    ("rpt", "r", "รายงาน R01–R14"),
    ("roles", "u", "กำหนดกลุ่มสิทธิ์การใช้งาน"),
    ("role-edit", "u", "สิทธิ์รายเมนูของกลุ่ม"),
    ("approval", "u", "กำหนดการตั้งค่าการอนุมัติ"),
    ("flow-edit", "u", "ขั้นตอนอนุมัติของงาน"),
    ("users", "u", "กำหนดผู้ใช้งาน"),
    ("me", "m", "Skill Portfolio ของฉัน"),
    ("my-transcript", "m", "Skill Transcript ของฉัน"),
]
LOGIN_SCREENS = {"login", "login-ext"}  # drawn before sign-in, not in the route table

# Pages of the running web app (apps/web) and the mock page each one implements.
BUILT: dict[str, str] = {
    "dash-cur": "มีแล้ว (FS-2f `/dashboard` · เมนู d1 · แท็บสถิติตามค่าสมมติรอ C1)",
    "login": "มีแล้ว (บัวศรีไอดี+รหัสผ่าน · Google รอ OAuth client)",
    "cur": "บางส่วน (รายการ + ตัวนับสถานะ + เพิ่มหลักสูตร · ข้อมูลหมวด 0–5 ของคู่มือเอง FS-2a)",
    "cur-edit": "มีแล้ว (หมวด 0–5 FS-2b FS-2c · Preview แบบเล่มและ PDF A4 FS-2d)",
    "st-courses": "มีแล้ว (FS-2c FS-3a · เลือกจากฐานรายวิชากลางหรือสร้างใหม่ · รหัส-Version)",
    "fac-plo": "มีแล้ว (FS-2e `/curricula/review` · รอตรวจ/ครบหมวด 3–4/ดำเนินการแล้ว ตามขอบเขตข้อมูล)",
    "fac-plo-edit": "มีแล้ว (หน้าคู่มือ: ติ๊กหมวด 3–4 ตรวจสอบสำเร็จ ส่งคืน · แก้ที่หน้าข้อมูลคู่มือ)",
    "import": "มีแล้ว",
    "course-master": "มีแล้ว (FS-3a `/courses` · Version · สร้างจากรายวิชาในคู่มือเดิม)",
    "ext-person": "มีแล้ว (FS-3b `/persons`)",
    "smo": "มีแล้ว (FS-3c `/smo`)",
    "smo-new": "มีแล้ว (FS-3c `/smo/[id]` ร่าง/ส่งคืน · Preview แบบ สมอ.08 [สมมติ: รอ A8])",
    "smo-view": "มีแล้ว (FS-3c `/smo/[id]` อนุมัติทีละขั้น · อนุมัติครบแก้หมวด 0.2 เอง)",
    "plan-assign": "มีแล้ว (FS-4a `/plans/assign` · ผู้บันทึกแผนและรายงานในหน้าเดียว · ช่วงเวลาบันทึก)",
    "rep-assign": "มีแล้ว (FS-4a รวมกับ `/plans/assign` · ช่องผู้บันทึกรายงาน และปุ่ม = แผน)",
    "plan": "มีแล้ว (FS-4b `/plans` · ภาพรวมต่อหน่วยงาน · เข้าทำ)",
    "plan-edit": "มีแล้ว (FS-4b FS-4c `/plans/[ภาค]/[รายการ]` 6 หมวด · หมวด 2–6 [สมมติ: รอ มคอ.3])",
    "rep": "มีแล้ว (FS-4d `/reports`)",
    "rep-edit": "มีแล้ว (FS-4d `/reports/[ภาค]/[รายการ]` 4 หมวด · เกรดกรอกเอง [สมมติ: รอ มคอ.5])",
    "dash-plan": "มีแล้ว (FS-4e `/dashboard/plans` · เมนู d2)",
    "dash-skill": "มีแล้ว (FS-5g `/dashboard/skills` · เมนู d3)",
    "skill-db": "มีแล้ว (FS-5a `/skills` · ฐาน Skill ตัวอย่างรอ A7 · นำเข้า .xlsx)",
    "skill-assign": "มีแล้ว (FS-5b `/skills/assign` · สิทธิ์เพิ่ม Skill ในฐานข้อมูล)",
    "skill-cur": "มีแล้ว (FS-5b `/skills/curricula` · flow skill_set)",
    "skill-map": "มีแล้ว (FS-5c `/skills/mapping` · flow skill_mapping)",
    "assess": "มีแล้ว (FS-5d `/assess` · รายชื่อนิสิตตัวอย่างรอ A4)",
    "assess-form": "มีแล้ว (FS-5d `/assess/[ภาค]/[วิชา]/[กลุ่ม]` · แบบฟอร์ม .xlsx)",
    "portfolio": "มีแล้ว (FS-5e `/portfolio`)",
    "portfolio-detail": "มีแล้ว (FS-5e `/portfolio/[รหัสนิสิต]`)",
    "issue": "มีแล้ว (FS-5f `/transcripts` · ลงนามด้วยบริการตัวอย่าง)",
    "transcript": "มีแล้ว (FS-5f `/portfolio/[รหัสนิสิต]/transcript` · QR ตรวจที่ `/verify/[เลขที่]`)",
    "me": "มีแล้ว (FS-5e `/me` · บัญชีนิสิตผูกรหัสนิสิต)",
    "my-transcript": "มีแล้ว (FS-5f `/me/transcript`)",
    "qa-rounds": "มีแล้ว (FS-6a `/qa/rounds` · เปิดได้ครั้งละ 1 รอบ · ล็อกเมื่อประเมินครบ)",
    "qa-criteria": "มีแล้ว (FS-6a `/qa/criteria` · ชุด 2548/2558 ใช้โครง 2565 [สมมติ])",
    "qa-assign": "มีแล้ว (FS-6b `/qa/assign`)",
    "qa-check": "มีแล้ว (FS-6d `/qa` · ผู้ประเมินเห็นเฉพาะที่ได้รับมอบหมาย)",
    "qa-check-detail": "มีแล้ว (FS-6c FS-6d `/qa/[รอบ]/[หลักสูตร]` · ผลตามเกณฑ์จากข้อมูล)",
    "qa-preview": "มีแล้ว (FS-6d `/qa/[รอบ]/preview` · R10 ฉบับร่าง/สมบูรณ์)",
    "qa-result": "มีแล้ว (FS-6d `/qa/result`)",
    "import-review": "มีแล้ว",
    "import-done": "มีแล้ว",
    "users": "มีแล้ว (FS-1c · รหัสผ่านบัวศรีไอดีตั้งทาง server · คนนอก login ใน FS-8)",
    "roles": "มีแล้ว (FS-1b)",
    "role-edit": "มีแล้ว (FS-1b · สิทธิ์อัตโนมัติจากรายชื่ออาจารย์เก็บค่าไว้ รอ B3)",
    "approval": "มีแล้ว (FS-1d)",
    "flow-edit": "มีแล้ว (FS-1d · คู่มือหลักสูตรใช้งานจริง งานอื่นใช้เมื่อเปิดโมดูลนั้น)",
}
BUILT_EXTRA = ["`/import/history` ประวัติการนำเข้าทั้งหมด (US-M1-21 · UI-2 · กรณีทดสอบ E-06)"]

# Test categories -> (mock pages, user stories). Non-functional requirements name their
# own test cases in the last column of docs/brd/06-nfr.md, so they are not listed here.
TEST_MAP: dict[str, tuple[list[str], list[str]]] = {
    "A": ([], []),
    "J": (["login", "users", "roles"], ["US-U-01", "US-U-03", "US-U-04"]),
    "B": (["import"], ["US-M1-11"]),
    "C": (["import-review"], ["US-M1-12", "US-M1-14"]),
    "D": (["import-review"], ["US-M1-12", "US-M1-14"]),
    "E": (["import-review", "import-done"], ["US-M1-15", "US-M1-16", "US-M1-17", "US-M1-21"]),
    "F": (["import"], ["US-M1-11"]),
    "G": (["import"], ["US-M1-11"]),
    "H": (["import"], ["US-M1-11"]),
    "K": (
        ["dash-cur", "cur", "fac-plo", "fac-plo-edit"],
        ["US-M1-01", "US-M1-03", "US-M1-07", "US-M1-08"],
    ),
    "L": (
        ["course-master", "ext-person", "smo", "smo-new", "smo-view"],
        ["US-M1-09", "US-M1-10", "US-M1-13", "US-M1-18", "US-M1-19"],
    ),
    "P": (
        ["plan-assign", "rep-assign", "plan", "plan-edit", "rep", "rep-edit", "dash-plan"],
        ["US-M2-01", "US-M2-02", "US-M2-03", "US-M2-04", "US-M2-05", "US-M2-06", "US-M2-07"],
    ),
    "T": (
        [
            "dash-skill",
            "skill-db",
            "skill-assign",
            "skill-cur",
            "skill-map",
            "assess",
            "assess-form",
            "portfolio",
            "portfolio-detail",
            "issue",
            "transcript",
            "me",
            "my-transcript",
        ],
        [f"US-M3-{n:02d}" for n in range(1, 11)],
    ),
    "Q": (
        [
            "qa-rounds",
            "qa-criteria",
            "qa-assign",
            "qa-check",
            "qa-check-detail",
            "qa-preview",
            "qa-result",
        ],
        [f"US-M4-{n:02d}" for n in range(1, 9)],
    ),
    "I": ([], []),
    "V": (["import-review"], []),
    "M": (["import"], []),
    "S": ([], []),
}

RE_US = re.compile(r"^- \*\*(US-[A-Z][A-Z0-9]*-\d+)[^*]*\*\*\s*(.*)$")
RE_MOCK = re.compile(r"\[mock: ([^\]]+)\]")
RE_OPEN = re.compile(r"ยังไม่เห็น|— ถาม|\[สมมติ|\[ต้องขอ")
RE_NFR = re.compile(r"^\| (NFR-\d+) \| (.*) \|$")
RE_TC = re.compile(r"([A-Z])-(\d{2})(?:–[A-Z]-(\d{2}))?")


@dataclass
class Nfr:
    id: str
    title: str
    proposed: bool
    tests: list[str]


def expand_tests(cell: str) -> list[str]:
    """'M-01–M-03 · G-05' -> ['M-01', 'M-02', 'M-03', 'G-05']"""
    out: list[str] = []
    for cat, a, b in RE_TC.findall(cell):
        out.extend(f"{cat}-{n:02d}" for n in range(int(a), int(b or a) + 1))
    return out


def parse_nfrs(path: Path) -> list[Nfr]:
    out: list[Nfr] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        m = RE_NFR.match(line)
        if m:
            cells = m.group(2).split(" | ")
            out.append(Nfr(m.group(1), cells[0], "[เสนอ]" in line, expand_tests(cells[-1])))
    return out


@dataclass
class Story:
    id: str
    file: str
    text: str
    pages: list[str]
    ac: int = 0
    open_q: bool = False
    tests: list[str] = field(default_factory=list)


def mock_routes(html: str) -> set[str]:
    return set(re.findall(r"routes\[['\"]([A-Za-z0-9_\-]+)['\"]\]\s*=", html)) | set(
        re.findall(r"routes\.([A-Za-z0-9_]+)\s*=", html)
    )


def parse_stories(files: list[Path]) -> list[Story]:
    out: list[Story] = []
    for f in files:
        lines = f.read_text(encoding="utf-8").split("\n")
        heading_pages: list[str] = []
        for i, line in enumerate(lines):
            if line.startswith("#"):
                m = RE_MOCK.search(line)
                heading_pages = [x.strip() for x in m.group(1).split(",")] if m else []
                continue
            m = RE_US.match(line)
            if not m:
                continue
            inline = [x.strip() for g in RE_MOCK.findall(line) for x in g.split(",")]
            st = Story(m.group(1), f.name, m.group(2), inline or heading_pages)
            j = i + 1
            while j < len(lines) and lines[j].startswith("  "):
                if lines[j].lstrip().startswith("- AC"):
                    st.ac += 1
                j += 1
            st.open_q = bool(RE_OPEN.search(" ".join(lines[i:j])))
            out.append(st)
    return out


def test_cases(path: Path) -> list[tuple[str, str]]:
    rows = csv.DictReader(path.open(encoding="utf-8-sig"))
    return [(r["TC_ID"], r["หัวข้อทดสอบ"]) for r in rows if r["TC_ID"] and r["TC_ID"] != "EX-00"]


def ranges(ids: list[str]) -> str:
    """['K-01','K-02','K-03','B-04'] -> 'B-04 · K-01–K-03'"""
    by_cat: dict[str, list[int]] = {}
    for t in ids:
        cat, num = t.split("-")
        by_cat.setdefault(cat, []).append(int(num))
    parts = []
    for cat in sorted(by_cat):
        nums = sorted(set(by_cat[cat]))
        a = b = nums[0]
        for n in nums[1:] + [None]:
            if n is not None and n == b + 1:
                b = n
                continue
            parts.append(f"{cat}-{a:02d}" if a == b else f"{cat}-{a:02d}–{cat}-{b:02d}")
            if n is not None:
                a = b = n
    return " · ".join(parts)


def build() -> str:
    routes = mock_routes(MOCK.read_text(encoding="utf-8"))
    listed = {p for p, _, _ in PAGES} - LOGIN_SCREENS
    if routes != listed:
        sys.exit(
            f"PAGES is out of date with the mock: missing {sorted(routes - listed)}, "
            f"not in mock {sorted(listed - routes)}"
        )
    stories = parse_stories(sorted(BRD.glob("0*.md")))
    by_id = {s.id: s for s in stories}
    cases = test_cases(TESTS)
    case_ids = {tc for tc, _ in cases}
    nfrs = parse_nfrs(BRD / "06-nfr.md")
    for n in nfrs:
        unknown = sorted(set(n.tests) - case_ids)
        if unknown:
            sys.exit(f"06-nfr.md {n.id} cites test cases that do not exist: {unknown}")
    in_nfr = {t for n in nfrs for t in n.tests}
    page_tests: dict[str, list[str]] = {}
    for tc, _ in cases:
        pages, ids = TEST_MAP[tc.split("-")[0]]
        for p in pages:
            page_tests.setdefault(p, []).append(tc)
        for i in ids:
            by_id[i].tests.append(tc)
    page_stories: dict[str, list[Story]] = {}
    for s in stories:
        for p in s.pages:
            page_stories.setdefault(p, []).append(s)

    no_story = [p for p in PAGES if p[0] not in page_stories]
    no_ac = [s for s in stories if not s.ac]
    with_tests = [s for s in stories if s.tests]
    tied_us = {tc for tc, _ in cases if TEST_MAP[tc.split("-")[0]][1]}
    loose = [tc for tc, _ in cases if tc not in tied_us and tc not in in_nfr]
    today = dt.date.today().isoformat()
    md: list[str] = []
    w = md.append
    w("# 91 ตารางไล่ความครบของ requirement (traceability)")
    w("")
    w(
        f"> {STAMP} จาก mock ({len(routes)} หน้า + หน้าเข้าสู่ระบบ 2 หน้า) · "
        f"user story ใน `docs/brd/0*.md` · กรณีทดสอบใน `docs/testing/test-script_ocl.csv` · "
        f"{today} · ห้ามแก้ด้วยมือ ให้แก้ต้นทางแล้วรันใหม่"
    )
    w("")
    w("## 1. สรุป")
    w("")
    w("| ตัวชี้วัด | ค่า |")
    w("|---|---|")
    w(f"| หน้าใน mock ที่มี user story รองรับ | {len(PAGES) - len(no_story)} / {len(PAGES)} |")
    w(f"| user story ที่มี AC | {len(stories) - len(no_ac)} / {len(stories)} |")
    w(f"| user story ที่ยังมีคำถามหรือข้อสมมติค้าง | {sum(s.open_q for s in stories)} |")
    w(f"| user story ที่มีกรณีทดสอบ | {len(with_tests)} / {len(stories)} |")
    w(f"| requirement ที่ไม่ใช่ฟังก์ชัน (`06-nfr.md`) | {len(nfrs)} ข้อ |")
    w(f"| NFR ที่มีกรณีทดสอบ | {sum(1 for n in nfrs if n.tests)} / {len(nfrs)} |")
    w(f"| NFR ที่เกณฑ์ยังเป็นข้อเสนอ รอลูกค้ายืนยัน | {sum(n.proposed for n in nfrs)} |")
    w(
        f"| กรณีทดสอบที่ผูกกับ user story หรือ NFR | {len(cases) - len(loose)} / {len(cases)} "
        "(ที่เหลือดูข้อ 6) |"
    )
    w(f"| หน้าที่มีในระบบแล้ว (ทั้งหมดหรือบางส่วน) | {len(BUILT)} / {len(PAGES)} |")
    w("")
    w("## 2. หน้า mock → user story → AC → กรณีทดสอบ")
    w("")
    w("| โมดูล | หน้า (`#/route`) | user story | AC | กรณีทดสอบ | ในระบบ ณ วันนี้ |")
    w("|---|---|---|---|---|---|")
    for route, mod, name in PAGES:
        sts = page_stories.get(route, [])
        ids = ", ".join(s.id + ("?" if s.open_q else "") for s in sts) or "**ไม่มี**"
        ac = f"{sum(1 for s in sts if s.ac)} / {len(sts)}" if sts else "–"
        tcs = ranges(page_tests.get(route, [])) or "–"
        built = BUILT.get(route, "ยังไม่มี")
        w(f"| {MODULES[mod]} | {name} (`{route}`) | {ids} | {ac} | {tcs} | {built} |")
    w("")
    w(
        "`?` = user story ที่ยังมีคำถามหรือข้อสมมติค้าง (ดู `99-open-questions.md`) · "
        "AC x / y = user story ที่มี AC x เรื่องจาก y เรื่องของหน้านั้น"
    )
    w("")
    w("สร้างเพิ่มนอก mock: " + " · ".join(BUILT_EXTRA))
    w("")
    w(f"## 3. หน้าที่ยังไม่มี user story ({len(no_story)} หน้า)")
    w("")
    if no_story:
        w("| โมดูล | หน้า |")
        w("|---|---|")
        for route, mod, name in no_story:
            w(f"| {MODULES[mod]} | {name} (`{route}`) |")
    else:
        w("ทุกหน้าใน mock มี user story รองรับแล้ว")
    w("")
    todo = [s for s in stories if not s.ac or s.open_q]
    w(f"## 4. user story ที่ยังไม่มี AC หรือยังมีคำถามค้าง ({len(todo)} เรื่อง)")
    w("")
    if todo:
        w("| ไฟล์ | user story | ไม่มี AC | คำถาม/ข้อสมมติค้าง | กรณีทดสอบที่มี |")
        w("|---|---|---|---|---|")
        for s in todo:
            no = "✗" if not s.ac else ""
            q = "?" if s.open_q else ""
            w(f"| `{s.file}` | {s.id} | {no} | {q} | {ranges(s.tests) or '–'} |")
    else:
        w("ทุก user story มี AC และไม่มีคำถามค้าง")
    w("")
    w("## 5. requirement ที่ไม่ใช่ฟังก์ชัน → กรณีทดสอบ")
    w("")
    w("| NFR | requirement | เกณฑ์ | กรณีทดสอบ |")
    w("|---|---|---|---|")
    for n in nfrs:
        state = "เสนอ รอลูกค้ายืนยัน" if n.proposed else "ยืนยันแล้ว"
        w(f"| {n.id} | {n.title} | {state} | {ranges(n.tests) or '**ไม่มี**'} |")
    w("")
    w(f"## 6. กรณีทดสอบที่ไม่ผูกกับ user story หรือ NFR ({len(loose)} กรณี)")
    w("")
    w(ranges(loose) if loose else "ทุกกรณีทดสอบผูกกับ requirement แล้ว")
    w("")
    w("## 7. วิธีผูกกรณีทดสอบ")
    w("")
    w(
        "user story: ผูกทั้งกลุ่มตามรหัสหมวดของกรณีทดสอบ (`TEST_MAP` ใน `tools/brd_trace.py`) "
        "จึงบอกได้ว่า user story มีการทดสอบหรือไม่ แต่ไม่ได้บอกว่าทดสอบ AC ครบทุกข้อ · "
        "NFR: ผูกทีละกรณีตามคอลัมน์สุดท้ายของ `06-nfr.md` และสคริปต์หยุดถ้าอ้างรหัสที่ไม่มีอยู่"
    )
    w("")
    return "\n".join(md)


def strip_stamp(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if STAMP not in line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = ap.parse_args()
    if not MOCK.exists():
        print(f"skip: {MOCK.relative_to(ROOT)} not found (not in git)")
        return 0
    text = build()
    if args.check:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if strip_stamp(old) != strip_stamp(text):
            print(f"stale: {OUT.relative_to(ROOT)} · run tools/brd_trace.py")
            return 1
        print("ok")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
