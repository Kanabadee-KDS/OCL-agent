"""Part 10: สถานภาพของหลักสูตรและมติอนุมัติ (chapter 1 item 13).

Item 13 is a fixed form: one status sentence, then one line per approving body
("ได้รับอนุมัติ/เห็นชอบหลักสูตรจาก<body> ในการประชุมครั้งที่ <n> เมื่อวันที่ <d> เดือน <m> พ.ศ. <y>").
Blank forms are dotted lines; a PDF may wrap the date onto the next line. Rows the book
leaves blank are kept with `pending: true` so the Admin fills them in later, and the
bodies the form always expects (plus the อว. acknowledgement, which never appears in the
book) are listed so the reviewer sees what is still missing. Deterministic: no LLM.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import PartResult, chapter, meta, paragraphs, subsection
from ocl_api.ingest.model import Document, Paragraph

RE_APPROVAL = re.compile(r"^\s*ได้รับ(?:การ)?(อนุมัติ/เห็นชอบ|อนุมัติ|เห็นชอบ)\s*(?:หลักสูตร)?\s*จาก\s*(.+)$")
RE_MEETING = re.compile(r"ในการประชุม\s*ครั้งที่\s*([\d๐-๙]+(?:\s*/\s*[\d๐-๙]{4})?)")
RE_DATE = re.compile(
    r"เมื่อวันที่\s*([\d๐-๙]{1,2})\s*(?:เดือน)?\s*([ก-๏]+(?:\.[ก-๏]+)*\.?)\s*(?:พ\.?ศ\.?)?\s*([\d๐-๙]{4})"
)
RE_START = re.compile(r"ภาคการศึกษา(?:ที่)?\s*(\d)\s*ของ\s*ปีการศึกษา\s*(\d{4})")
RE_EDITION = re.compile(r"\(\s*หลักสูตร\s*(ใหม่|ปรับปรุง)\s*พ\.?ศ\.?\s*(\d{4})\s*\)")
RE_DOTS = re.compile(r"\.{3,}")
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

MONTHS = {
    "มกราคม": 1, "ม.ค.": 1, "กุมภาพันธ์": 2, "ก.พ.": 2, "มีนาคม": 3, "มี.ค.": 3,
    "เมษายน": 4, "เม.ย.": 4, "พฤษภาคม": 5, "พ.ค.": 5, "มิถุนายน": 6, "มิ.ย.": 6,
    "กรกฎาคม": 7, "ก.ค.": 7, "สิงหาคม": 8, "ส.ค.": 8, "กันยายน": 9, "ก.ย.": 9,
    "ตุลาคม": 10, "ต.ค.": 10, "พฤศจิกายน": 11, "พ.ย.": 11, "ธันวาคม": 12, "ธ.ค.": 12,
}  # fmt: skip

# (needle in the body name, key, label shown to the reviewer)
LEVELS = [
    ("คณะกรรมการการศึกษาระดับปริญญาตรี", "committee_ug", "คณะกรรมการการศึกษาระดับปริญญาตรี"),
    ("คณะกรรมการการศึกษาระดับบัณฑิตศึกษา", "committee_grad", "คณะกรรมการการศึกษาระดับบัณฑิตศึกษา"),
    ("คณะกรรมการ", "committee", "คณะกรรมการประจำคณะ/บัณฑิตวิทยาลัย"),
    ("สภาวิชาการ", "academic_council", "สภาวิชาการ"),
    ("สภามหาวิทยาลัย", "university_council", "สภามหาวิทยาลัย"),
    ("สภาวิชาชีพ", "professional_council", "สภาวิชาชีพ (ถ้ามี)"),
    ("อว.", "mhesi", "อว. รับทราบความเห็นชอบหลักสูตร"),
]
EXPECTED = ["committee", "academic_council", "university_council", "mhesi"]


def _level_key(body: str) -> tuple[str, str]:
    for needle, key, label in LEVELS:
        if needle in body:
            return key, label
    return "other", body


def parse_date(text: str) -> dict[str, Any] | None:
    m = RE_DATE.search(text.translate(THAI_DIGITS))
    if not m:
        return None
    day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
    month = MONTHS.get(month_name)
    if month is None:
        return None
    return {
        "day": day,
        "month": month,
        "year_be": year,
        "text": f"{day} {month_name} {year}",
        "iso": f"{year - 543:04d}-{month:02d}-{day:02d}",
    }


def parse_approval_line(text: str, page: int | None) -> dict[str, Any] | None:
    m = RE_APPROVAL.match(text)
    if not m:
        return None
    body = re.split(r"\s+(?:ในการประชุม|เมื่อวันที่)", m.group(2), maxsplit=1)[0]
    body = RE_DOTS.sub("", body).strip(" :")
    key, label = _level_key(body)
    mm = RE_MEETING.search(text.translate(THAI_DIGITS))
    meeting = re.sub(r"\s", "", mm.group(1)) if mm else None
    date = parse_date(text)
    pending = date is None and bool(RE_DOTS.search(text))
    return {
        "level_key": key,
        "level": label if key != "other" else body,
        "body_text": body,
        "meeting_no": meeting,
        "date": date,
        "resolution": "อนุมัติ"
        if key == "university_council"
        else m.group(1).replace("อนุมัติ/เห็นชอบ", "เห็นชอบ"),
        "pending": pending,
        "meta": meta(
            "high" if date else "medium", page, text, note="เล่มเว้นว่าง" if pending else None
        ),
    }


def _lines(blocks) -> list[Paragraph]:
    return [p for p in paragraphs(blocks) if p.text.strip()]


def join_wrapped(ps: list[Paragraph]) -> list[Paragraph]:
    """A line that does not start a new sentence of the form continues the previous one
    (the PDF wraps '... เมื่อวันที่' / '11 เดือน สิงหาคม พ.ศ. 2569')."""
    out: list[Paragraph] = []
    for p in ps:
        t = p.text.strip()
        if out and not RE_APPROVAL.match(t) and not t.startswith("เป็นหลักสูตร"):
            prev = out[-1]
            out[-1] = Paragraph(text=prev.text.rstrip() + " " + t, page=prev.page, level=prev.level)
        else:
            out.append(p)
    return out


def extract_approval(doc: Document, gateway=None) -> PartResult:  # noqa: ARG001 - no LLM here
    res = PartResult(
        key="appr",
        data={
            "status": None,
            "previous_program": None,
            "previous_year": None,
            "start_semester": None,
            "start_year": None,
            "approvals": [],
            "missing_levels": [],
            "meta": {},
        },
    )
    ch1 = chapter(doc, "1")
    if ch1 is None:
        res.notes.append("chapter 1 not found")
        return res
    ps = join_wrapped(_lines(subsection(ch1.blocks, "13")))
    if not ps:
        res.notes.append("item 13 not found in chapter 1")
        return res
    data = res.data
    for p in ps:
        t = p.text.strip()
        if t.startswith("เป็นหลักสูตร"):
            data["status"] = "ใหม่" if "หลักสูตรใหม่" in t else "ปรับปรุง" if "ปรับปรุง" in t else None
            data["meta"]["status"] = meta("high", p.page, t)
            m = re.search(r"จากหลักสูตร\s*(.+?)\s*\(\s*หลักสูตร", t)
            if m:
                data["previous_program"] = re.sub(r"^(หลักสูตร\s*)+", "", m.group(1)).strip()
            m = RE_EDITION.search(t)
            if m:
                data["previous_year"] = int(m.group(2))
            m = RE_START.search(t)
            if m:
                data["start_semester"], data["start_year"] = int(m.group(1)), int(m.group(2))
                data["meta"]["start"] = meta("high", p.page, m.group(0))
            continue
        row = parse_approval_line(t, p.page)
        if row:
            data["approvals"].append(row)
    have = {a["level_key"] for a in data["approvals"] if not a["pending"]}
    labels = {key: label for _, key, label in LEVELS}
    data["missing_levels"] = [
        labels[k] for k in EXPECTED if not any(h == k or h.startswith(k + "_") for h in have)
    ]
    data["count"] = sum(1 for a in data["approvals"] if not a["pending"])
    if not data["approvals"]:
        res.notes.append("no 'ได้รับอนุมัติ/เห็นชอบ' lines in item 13")
    return res
