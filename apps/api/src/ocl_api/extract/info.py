"""Part 1: ข้อมูลหลัก + หมวด 1 ข้อมูลทั่วไป (items 1–10, 13 and the cover page).

Deterministic first: every field is read from the item it lives in, with the page and
the literal line as evidence. Fields the book never states (กลุ่มการศึกษา, เกณฑ์มาตรฐาน,
ภาคที่นับ, ประเภทรับสมัคร, CWIE) are inferred and flagged `inferred` so the reviewer sees
them. The LLM is only asked for text fields the parser left empty, and its answers are
kept only when they occur literally in chapter 1.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import (
    PartResult,
    chapter,
    llm_only,
    meta,
    paragraphs,
    paragraphs_text,
    subsection,
    to_int,
)
from ocl_api.fewshot import fewshot_examples, narrow_fields
from ocl_api.ingest.model import Document, Paragraph
from ocl_api.llm.gateway import LLMTruncated

CHECKED = "☑☒✔✓🗹🗷"
UNCHECKED = "□■☐▪○"
BOXES = CHECKED + UNCHECKED
RE_BOX = re.compile(rf"([{BOXES}])\s*([^{BOXES}]+)")
RE_SUB5 = re.compile(r"^\s*5\.(\d)\s*(.*)$")
SUB5_BY_TITLE = [
    ("รูปแบบ", "1"),
    ("ระยะเวลา", "2"),
    ("ภาษา", "3"),
    ("รับเข้า", "4"),
    ("ความร่วมมือ", "5"),
    ("ให้ปริญญา", "6"),
]
RE_SUB5_INLINE = re.compile(r"\s5\.(\d)\s")
RE_NAME_PAIR = re.compile(
    r"(ชื่อเต็ม|ชื่อย่อ)\s*[:：]\s*(.+?)(?=\s*(?:ภาษาไทย|ภาษาอังกฤษ)?\s*(?:ชื่อเต็ม|ชื่อย่อ)\s*[:：]|$)"
)
RE_TOTAL = re.compile(r"(ไม่น้อยกว่า|รวม|จำนวน)?\s*([\d,๐-๙]+)\s*หน่วยกิต")
RE_EDITION = re.compile(r"\(\s*หลักสูตร\s*(ใหม่|ปรับปรุง)\s*พ\.?ศ\.?\s*(\d{4})\s*\)")
RE_START = re.compile(r"ภาคการศึกษา(?:ที่)?\s*(\d)\s*ของ\s*ปีการศึกษา\s*(\d{4})")
RE_PREVIOUS = re.compile(
    r"จากหลักสูตร\s*(.+?)\s*\(\s*หลักสูตร\s*(?:ใหม่|ปรับปรุง)\s*พ\.?ศ\.?\s*(\d{4})\s*\)"
)
RE_CAREER_NUM = re.compile(r"^\s*(?:10\.\d+|\d+[.)]|[-•–])\s*(.+)$")
RE_YEARS = re.compile(r"(\d+)\s*ปี")
THAI = re.compile(r"[ก-๙]")

LEVELS = [
    ("ประกาศนียบัตรบัณฑิตชั้นสูง", "ป.บัณฑิตชั้นสูง"),
    ("ประกาศนียบัตรบัณฑิต", "ป.บัณฑิต"),
    ("ดุษฎีบัณฑิต", "ป.เอก"),
    ("มหาบัณฑิต", "ป.โท"),
    ("บัณฑิต", "ป.ตรี"),
]
PROGRAM_TYPES = [
    ("ปริญญาตรีทางวิชาการ", "ปริญญาตรีทางวิชาการ"),
    ("ปริญญาตรีทางวิชาชีพ", "ปริญญาตรีทางวิชาชีพหรือปฏิบัติการ"),
    ("ประกาศนียบัตรบัณฑิตขั้นสูง", "ประกาศนียบัตรบัณฑิตชั้นสูง"),
    ("ประกาศนียบัตรบัณฑิตชั้นสูง", "ประกาศนียบัตรบัณฑิตชั้นสูง"),
    ("ประกาศนียบัตรบัณฑิต", "ประกาศนียบัตรบัณฑิต"),
    ("ปริญญาโท", "ปริญญาโท"),
    ("ปริญญาเอก", "ปริญญาเอก"),
]
CATEGORIES = [
    ("นอกระบบ", "การศึกษานอกระบบแบบสะสมเครดิต"),
    ("ในระบบ", "การศึกษาในระบบ"),
    ("ออนไลน์", "ออนไลน์"),
    ("สองภาษา", "สองภาษา"),
    ("นานาชาติ", "นานาชาติ"),
    ("พหุวิทยาการ", "พหุวิทยาการ-สหวิทยาการ"),
]

# key, label, group, kind, options — the web editor and the golden sheet render from this
FIELDS: list[dict[str, Any]] = [
    {"key": "program_code", "label": "รหัสหลักสูตร สกอ. (14 หลัก)", "group": "ทะเบียน", "kind": "text"},
    {
        "key": "revision_type",
        "label": "หลักสูตรใหม่/ปรับปรุง",
        "group": "ทะเบียน",
        "kind": "enum",
        "options": ["ใหม่", "ปรับปรุง"],
    },
    {"key": "edition_year", "label": "พ.ศ. ของฉบับนี้", "group": "ทะเบียน", "kind": "int"},
    {
        "key": "previous_program",
        "label": "ปรับปรุงจากหลักสูตร (ฉบับเดิม)",
        "group": "ทะเบียน",
        "kind": "text",
    },
    {"key": "previous_year", "label": "พ.ศ. ของฉบับเดิม", "group": "ทะเบียน", "kind": "int"},
    {"key": "faculty", "label": "คณะ/วิทยาลัย", "group": "ทะเบียน", "kind": "text"},
    {
        "key": "education_group",
        "label": "กลุ่มการศึกษา",
        "group": "ทะเบียน",
        "kind": "enum",
        "options": ["ปริญญาตรีหรือต่ำกว่า", "สูงกว่าปริญญาตรี"],
    },
    {"key": "name_th", "label": "ชื่อหลักสูตร (ไทย)", "group": "ชื่อ", "kind": "text"},
    {"key": "name_en", "label": "ชื่อหลักสูตร (อังกฤษ)", "group": "ชื่อ", "kind": "text"},
    {
        "key": "level",
        "label": "ระดับการศึกษา",
        "group": "ชื่อ",
        "kind": "enum",
        "options": ["ป.ตรี", "ป.บัณฑิต", "ป.โท", "ป.บัณฑิตชั้นสูง", "ป.เอก"],
    },
    {"key": "field_of_study", "label": "สาขาวิชา", "group": "ชื่อ", "kind": "text"},
    {"key": "degree_full_th", "label": "ชื่อปริญญา เต็ม (ไทย)", "group": "ชื่อ", "kind": "text"},
    {"key": "degree_abbr_th", "label": "ชื่อปริญญา ย่อ (ไทย)", "group": "ชื่อ", "kind": "text"},
    {"key": "degree_full_en", "label": "ชื่อปริญญา เต็ม (อังกฤษ)", "group": "ชื่อ", "kind": "text"},
    {"key": "degree_abbr_en", "label": "ชื่อปริญญา ย่อ (อังกฤษ)", "group": "ชื่อ", "kind": "text"},
    {
        "key": "total_credits",
        "label": "หน่วยกิตตลอดหลักสูตร (ไม่น้อยกว่า)",
        "group": "เวลา/หน่วยกิต",
        "kind": "int",
    },
    {"key": "duration_years", "label": "จำนวนปีที่ศึกษา", "group": "เวลา/หน่วยกิต", "kind": "int"},
    {
        "key": "study_mode",
        "label": "เต็มเวลา/ไม่เต็มเวลา",
        "group": "เวลา/หน่วยกิต",
        "kind": "enum",
        "options": ["เต็มเวลา", "ไม่เต็มเวลา"],
    },
    {"key": "lifelong", "label": "แบบการศึกษาตลอดชีวิต", "group": "เวลา/หน่วยกิต", "kind": "bool"},
    {
        "key": "education_system",
        "label": "ระบบการจัดการศึกษา",
        "group": "เวลา/หน่วยกิต",
        "kind": "enum",
        "options": ["ทวิภาค", "ไตรภาค", "อื่น ๆ"],
    },
    {
        "key": "semesters_counted",
        "label": "ภาคการศึกษาที่นับ",
        "group": "เวลา/หน่วยกิต",
        "kind": "enum",
        "options": ["(1,2)", "(1,2,3)", "(1,2,ฤดูร้อน)", "อื่น ๆ"],
    },
    {"key": "start_semester", "label": "ภาคการศึกษาที่เริ่มใช้", "group": "เวลา/หน่วยกิต", "kind": "int"},
    {"key": "start_year", "label": "ปีการศึกษาที่เริ่มใช้", "group": "เวลา/หน่วยกิต", "kind": "int"},
    {
        "key": "program_type",
        "label": "รูปแบบของหลักสูตร",
        "group": "รูปแบบ",
        "kind": "enum",
        "options": [
            "ปริญญาตรีทางวิชาการ",
            "ปริญญาตรีทางวิชาชีพหรือปฏิบัติการ",
            "ประกาศนียบัตรบัณฑิต",
            "ปริญญาโท",
            "ประกาศนียบัตรบัณฑิตชั้นสูง",
            "ปริญญาเอก",
        ],
    },
    {"key": "program_type_text", "label": "ข้อความรูปแบบตามเล่ม", "group": "รูปแบบ", "kind": "text"},
    {
        "key": "program_categories",
        "label": "ประเภทหลักสูตร (บัณฑิตศึกษา)",
        "group": "รูปแบบ",
        "kind": "list",
    },
    {"key": "is_international", "label": "หลักสูตรนานาชาติ", "group": "รูปแบบ", "kind": "bool"},
    {"key": "cwie", "label": "หลักสูตรฝึกปฏิบัติ CWIE", "group": "รูปแบบ", "kind": "bool"},
    {
        "key": "language",
        "label": "ภาษาที่ใช้สอน",
        "group": "รูปแบบ",
        "kind": "enum",
        "options": ["ไทย", "อังกฤษ", "ไทยและอังกฤษ", "อื่น ๆ"],
    },
    {"key": "language_text", "label": "ข้อความภาษาตามเล่ม", "group": "รูปแบบ", "kind": "text"},
    {
        "key": "admission_type",
        "label": "ประเภทการรับสมัคร",
        "group": "รูปแบบ",
        "kind": "enum",
        "options": ["ไทย", "นานาชาติ"],
    },
    {"key": "admission_text", "label": "การรับเข้าศึกษาตามเล่ม", "group": "รูปแบบ", "kind": "text"},
    {
        "key": "standard_criteria",
        "label": "เกณฑ์มาตรฐานหลักสูตร",
        "group": "รูปแบบ",
        "kind": "enum",
        "options": [
            "ประกาศ อว. 2565 (ตรี)",
            "ศธ. 2558 (ตรี)",
            "ประกาศ อว. 2565 (บัณฑิตศึกษา)",
            "ศธ. 2558 (บัณฑิตศึกษา)",
        ],
    },
    {
        "key": "collaboration_text",
        "label": "ความร่วมมือกับสถาบันอื่น (ข้อความ)",
        "group": "ความร่วมมือ",
        "kind": "text",
    },
]
FIELD_KEYS = [f["key"] for f in FIELDS]
REQUIRED = ["name_th", "name_en", "level", "degree_full_th", "total_credits", "start_year"]
LLM_FIELDS = [
    "program_code",
    "name_th",
    "name_en",
    "degree_full_th",
    "degree_abbr_th",
    "degree_full_en",
    "degree_abbr_en",
    "total_credits",
    "duration_years",
    "start_semester",
    "start_year",
]

SYSTEM = (
    "คุณเป็นผู้ช่วยสกัดข้อมูลทั่วไปของหลักสูตรจากหมวดที่ 1 ของเล่มหลักสูตรมหาวิทยาลัยไทย "
    "ตอบเป็น JSON เท่านั้น คัดลอกข้อความตามต้นฉบับทุกตัวอักษร ถ้าไม่มีในข้อความให้ตอบ null"
)
SCHEMA = {
    "type": "object",
    "properties": {
        **{k: {"type": ["string", "null"]} for k in LLM_FIELDS[:7]},
        **{k: {"type": ["integer", "null"]} for k in LLM_FIELDS[7:]},
    },
    "required": LLM_FIELDS,
}


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def _lines(blocks) -> list[Paragraph]:
    return [p for p in paragraphs(blocks) if p.text.strip()]


def _joined(ps: list[Paragraph]) -> str:
    return " ".join(p.text.strip() for p in ps)


def _page(ps: list[Paragraph]) -> int | None:
    return ps[0].page if ps else None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip(" :：-")


# ---------- item parsers ----------


def parse_item1(ps: list[Paragraph]) -> dict[str, tuple[Any, int | None, str]]:
    out: dict[str, tuple[Any, int | None, str]] = {}
    for p in ps:
        m = re.search(r"รหัสหลักสูตร\s*[:：]?\s*(\S+)", p.text)
        if m:
            code = m.group(1).strip()
            out["program_code"] = (
                code if re.fullmatch(r"\d{8,16}", code) else None,
                p.page,
                p.text,
            )
            break
    text = _joined(ps)
    m = re.search(r"ภาษาไทย\s*[:：]\s*(.+?)(?=\s*ภาษาอังกฤษ\s*[:：]|$)", text)
    if m:
        out["name_th"] = (_clean(m.group(1)), _page(ps), m.group(0))
    m = re.search(r"ภาษาอังกฤษ\s*[:：]\s*(.+)$", text)
    if m:
        out["name_en"] = (_clean(m.group(1)), _page(ps), m.group(0))
    return out


def parse_item2(ps: list[Paragraph]) -> dict[str, tuple[Any, int | None, str]]:
    out: dict[str, tuple[Any, int | None, str]] = {}
    text = _joined(ps)
    for m in RE_NAME_PAIR.finditer(text):
        kind = "full" if m.group(1) == "ชื่อเต็ม" else "abbr"
        value = _clean(m.group(2))
        lang = "th" if THAI.search(value) else "en"
        key = f"degree_{kind}_{lang}"
        if key not in out:
            out[key] = (value, _page(ps), m.group(0))
    return out


def parse_majors(ps: list[Paragraph]) -> list[dict[str, Any]]:
    rows = []
    for p in ps:
        t = p.text.strip()
        if re.fullmatch(r"[-–]?\s*ไม่มี\s*", t):
            return []
        t = re.sub(r"^\s*(?:\d+[.)]|[-•–])\s*", "", t)
        if t:
            rows.append({"name": t, "meta": meta("high", p.page, p.text)})
    return rows


def parse_boxes(text: str) -> list[tuple[bool, str]]:
    """'□ 2 ปี ☑ 4 ปี' -> [(False, '2 ปี'), (True, '4 ปี')]"""
    return [(mark in CHECKED, _clean(label)) for mark, label in RE_BOX.findall(text)]


def split_item5(ps: list[Paragraph]) -> dict[str, list[Paragraph]]:
    """Group item-5 lines by sub-item 5.1–5.6; a heading glued to the previous line
    ('... มหาวิทยาลัย 5.6 การให้ปริญญา') is split as well."""
    subs: dict[str, list[Paragraph]] = {}
    cur: str | None = None
    for p in ps:
        text = p.text
        m = RE_SUB5.match(text)
        if m:
            cur = _sub5_key(m.group(1), m.group(2))
            subs.setdefault(cur, [])
            continue  # the heading line itself ("5.3 ภาษาที่ใช้...") carries no value
        m = RE_SUB5_INLINE.search(text)
        if m and cur is not None:
            subs[cur].append(Paragraph(text=text[: m.start()].strip(), page=p.page))
            cur = _sub5_key(m.group(1), text[m.end() :])
            subs.setdefault(cur, [])
            continue
        if cur is not None:
            subs[cur].append(p)
    return subs


def _sub5_key(number: str, title: str) -> str:
    """Prefer the heading words over the number: books misnumber (ศศ.ม. has two 5.5)."""
    return next((k for needle, k in SUB5_BY_TITLE if needle in title), number)


def parse_item5(ps: list[Paragraph]) -> dict[str, tuple[Any, int | None, str]]:
    out: dict[str, tuple[Any, int | None, str]] = {}
    subs = split_item5(ps)
    # 5.1 รูปแบบ + ประเภทหลักสูตร (graduate books)
    checked: list[tuple[str, int | None]] = []
    for p in subs.get("1", []):
        checked += [(label, p.page) for ok, label in parse_boxes(p.text) if ok]
    cats: list[str] = []
    for label, page in checked:
        hit = next((t for needle, t in PROGRAM_TYPES if needle in label), None)
        if hit and "program_type" not in out:
            out["program_type"] = (hit, page, label)
            out["program_type_text"] = (label, page, label)
            m = RE_YEARS.search(label)
            if m:
                out["duration_years"] = (int(m.group(1)), page, label)
            continue
        cat = next((t for needle, t in CATEGORIES if needle in label), None)
        if cat and cat not in cats:
            cats.append(cat)
    if subs.get("1"):
        out["program_categories"] = (cats, _page(subs["1"]), "; ".join(cats))
    # 5.2 ระยะเวลา
    for p in subs.get("2", []):
        for ok, label in parse_boxes(p.text):
            if "เต็มเวลา" in label and ok and "study_mode" not in out:
                out["study_mode"] = ("เต็มเวลา", p.page, p.text)
            if "ตลอดชีวิต" in label:
                out["lifelong"] = (ok, p.page, p.text)
            m = RE_YEARS.fullmatch(label) or (
                RE_YEARS.search(label) if "ระยะเวลา" in label else None
            )
            if ok and m:
                out["duration_years"] = (int(m.group(1)), p.page, p.text)
        if "duration_years" not in out:
            m = re.search(r"ระยะเวลา(?:การศึกษา)?\s*(\d+)\s*ปี", p.text)
            if m:
                out["duration_years"] = (int(m.group(1)), p.page, p.text)
    if subs.get("2") and "study_mode" not in out:
        out["study_mode"] = ("ไม่เต็มเวลา", _page(subs["2"]), _joined(subs["2"]))
    # 5.3 ภาษา
    if subs.get("3"):
        text = _joined(subs["3"])
        head = re.split(r"เอกสาร|สำหรับ|,", text, maxsplit=1)[0]
        th, en = "ไทย" in head, "อังกฤษ" in head
        lang = "ไทยและอังกฤษ" if th and en else "ไทย" if th else "อังกฤษ" if en else "อื่น ๆ"
        out["language"] = (lang, _page(subs["3"]), text)
        out["language_text"] = (text, _page(subs["3"]), text)
    # 5.4 การรับเข้า
    if subs.get("4"):
        out["admission_text"] = (_joined(subs["4"]), _page(subs["4"]), _joined(subs["4"]))
    # 5.5 ความร่วมมือ
    if subs.get("5"):
        text = _clean(_joined(subs["5"]))
        out["collaboration_text"] = (text or None, _page(subs["5"]), _joined(subs["5"]))
        out["_collab_lines"] = (subs["5"], None, "")
    return out


def parse_collaborations(ps: list[Paragraph]) -> list[dict[str, Any]]:
    rows = []
    for p in ps:
        t = p.text.strip()
        if not re.match(r"^[-•–]\s*\S", t):
            continue
        t = re.sub(r"^[-•–]\s*", "", t)
        m = re.search(r"\s(?:ประเทศ|สหราช)(\S.*)$", t)
        country = _clean(m.group(0)) if m else None
        inst = _clean(t[: m.start()]) if m else t
        rows.append(
            {
                "institution": inst,
                "country": country,
                "domestic": country is None or "ไทย" in country,
                "meta": meta("high", p.page, p.text),
            }
        )
    return rows


def parse_careers(ps: list[Paragraph]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    group: str | None = None
    for p in ps:
        t = p.text.strip()
        m = RE_CAREER_NUM.match(t)
        if m:
            rows.append(
                {"group": group, "name": _clean(m.group(1)), "meta": meta("high", p.page, p.text)}
            )
            continue
        if ("ประกอบอาชีพ" in t and len(t) > 60) or t.endswith(("ดังนี้", ":", "：")):
            continue  # introductory sentence
        if len(t) < 60 and (p.bold or t.startswith(("วิชาเอก", "แขนง", "กลุ่ม", "สาขา"))):
            group = t
            continue
        if rows and rows[-1]["name"].endswith(("/", ",", "และ")):
            rows[-1]["name"] = _clean(rows[-1]["name"] + " " + t)
            continue
        rows.append({"group": group, "name": t, "meta": meta("medium", p.page, p.text)})
    return rows


def parse_item13(ps: list[Paragraph]) -> dict[str, tuple[Any, int | None, str]]:
    out: dict[str, tuple[Any, int | None, str]] = {}
    status = [p for p in ps if not p.text.strip().startswith("ได้รับอนุมัติ")]
    text = _joined(status)
    page = _page(status)
    if "หลักสูตรใหม่" in text:
        out["revision_type"] = ("ใหม่", page, text)
    elif "หลักสูตรปรับปรุง" in text:
        out["revision_type"] = ("ปรับปรุง", page, text)
    m = RE_PREVIOUS.search(text)
    if m:
        prev = re.sub(r"^(หลักสูตร\s*)+", "", _clean(m.group(1)))
        out["previous_program"] = (prev, page, m.group(0))
        out["previous_year"] = (int(m.group(2)), page, m.group(0))
    m = RE_START.search(text)
    if m:
        out["start_semester"] = (int(m.group(1)), page, m.group(0))
        out["start_year"] = (int(m.group(2)), page, m.group(0))
    return out


def parse_cover(doc: Document) -> dict[str, tuple[Any, int | None, str]]:
    out: dict[str, tuple[Any, int | None, str]] = {}
    front = [s for s in doc.sections() if s.kind == "front"]
    if not front:
        return out
    ps = _lines(front[0].blocks)[:40]
    for p in ps:
        m = RE_EDITION.search(p.text)
        if m and "edition_year" not in out:
            out["edition_year"] = (int(m.group(2)), p.page, p.text)
            out["revision_type_cover"] = (m.group(1), p.page, p.text)
        t = p.text.strip()
        if "faculty" not in out and re.match(r"^(คณะ|วิทยาลัย|บัณฑิตวิทยาลัย|สำนัก)", t):
            fac = re.sub(r"\s*มหาวิทยาลัยศรีนครินทรวิโรฒ.*$", "", t).strip()
            out["faculty"] = (fac, p.page, p.text)
    return out


# ---------- main ----------


def extract_info(doc: Document, gateway=None) -> PartResult:
    res = PartResult(
        key="info",
        data={
            "fields": FIELDS,
            "values": {k: None for k in FIELD_KEYS},
            "meta": {},
            "majors": [],
            "collaborations": [],
            "careers": [],
        },
    )
    values: dict[str, Any] = res.data["values"]
    metas: dict[str, Any] = res.data["meta"]

    def put(key: str, value: Any, page: int | None, snippet: str, conf: str = "high", **kw) -> None:
        if key not in values or value is None:
            return
        values[key] = value
        metas[key] = meta(conf, page, snippet, **kw)  # type: ignore[arg-type]

    for key, (value, page, snippet) in parse_cover(doc).items():
        if key == "revision_type_cover":
            continue
        put(key, value, page, snippet)

    ch1 = chapter(doc, "1")
    if ch1 is None:
        res.notes.append("chapter 1 not found")
        return res
    items = {
        n: _lines(subsection(ch1.blocks, n))
        for n in ("1", "2", "3", "4", "5", "6", "7", "10", "13")
    }

    for key, (value, page, snippet) in parse_item1(items["1"]).items():
        if value is None:
            res.notes.append(f"{key}: เล่มยังไม่ระบุ ({snippet[:40]})")
        put(key, value, page, snippet)
    for key, (value, page, snippet) in parse_item2(items["2"]).items():
        put(key, value, page, snippet)
    res.data["majors"] = parse_majors(items["3"])
    for p in items["4"]:
        m = RE_TOTAL.search(p.text)
        if m:
            put("total_credits", to_int(m.group(2)), p.page, p.text)
            break
    item5 = parse_item5(items["5"])
    collab_lines = item5.pop("_collab_lines", ([], None, ""))[0]
    for key, (value, page, snippet) in item5.items():
        put(key, value, page, snippet)
    res.data["collaborations"] = parse_collaborations(collab_lines)
    text6 = _joined(items["6"])
    if text6:
        sys_ = "ทวิภาค" if "ทวิภาค" in text6 else "ไตรภาค" if "ไตรภาค" in text6 else "อื่น ๆ"
        put("education_system", sys_, _page(items["6"]), text6[:160])
    text7 = _joined(items["7"])
    if text7:
        has_summer = "ฤดูร้อน" in text7
        counted = (
            "(1,2,ฤดูร้อน)"
            if has_summer
            else "(1,2)"
            if values.get("education_system") != "ไตรภาค"
            else "(1,2,3)"
        )
        put("semesters_counted", counted, _page(items["7"]), text7[:160], "medium", inferred=True)
    res.data["careers"] = parse_careers(items["10"])
    for key, (value, page, snippet) in parse_item13(items["13"]).items():
        put(key, value, page, snippet)

    # ----- derived / inferred -----
    name_th = values.get("name_th") or ""
    degree_th = values.get("degree_full_th") or ""
    m = re.search(r"สาขาวิชา\s*(.+?)\s*(?:\(|$)", name_th)
    if m:
        put("field_of_study", _clean(m.group(1)), metas["name_th"]["source"]["page"], name_th)
    elif degree_th:
        m = re.search(r"\((.+?)\)", degree_th)
        if m:
            put(
                "field_of_study",
                m.group(1).strip(),
                metas["degree_full_th"]["source"]["page"],
                degree_th,
                "medium",
            )
    level = next((lv for needle, lv in LEVELS if needle in (degree_th or name_th)), None)
    if level is None and values.get("program_type"):
        level = {"ปริญญาโท": "ป.โท", "ปริญญาเอก": "ป.เอก"}.get(values["program_type"], "ป.ตรี")
    if level:
        src = metas.get("degree_full_th") or metas.get("name_th") or {}
        put(
            "level",
            level,
            (src.get("source") or {}).get("page"),
            degree_th or name_th,
            "medium",
            inferred=True,
        )
        put(
            "education_group",
            "ปริญญาตรีหรือต่ำกว่า" if level == "ป.ตรี" else "สูงกว่าปริญญาตรี",
            None,
            level,
            "medium",
            inferred=True,
        )
    intl = (
        "นานาชาติ" in (values.get("program_categories") or [])
        or "นานาชาติ" in name_th
        or "international" in (values.get("name_en") or "").lower()
    )
    put(
        "is_international",
        intl,
        (metas.get("name_th") or {}).get("source", {}).get("page"),
        name_th or "",
        "medium",
        inferred=True,
    )
    put(
        "admission_type",
        "นานาชาติ" if intl else "ไทย",
        None,
        values.get("admission_text") or "",
        "low",
        inferred=True,
    )
    year = values.get("edition_year") or values.get("start_year")
    if level and year:
        grad = level != "ป.ตรี"
        crit = ("ประกาศ อว. 2565" if year >= 2565 else "ศธ. 2558") + (
            " (บัณฑิตศึกษา)" if grad else " (ตรี)"
        )
        put("standard_criteria", crit, None, f"ระดับ {level} · ปี {year}", "low", inferred=True)
    if values.get("edition_year") is None and values.get("start_year"):
        put(
            "edition_year",
            values["start_year"],
            metas["start_year"]["source"]["page"],
            metas["start_year"]["source"]["snippet"],
            "low",
            inferred=True,
        )
    ch4 = chapter(doc, "4")
    cw = next(
        (
            p
            for p in paragraphs(ch4.blocks if ch4 else [])
            if re.search(r"CWIE|สหกิจศึกษา|ฝึกปฏิบัติ(?:งาน)?วิชาชีพ|ฝึกงาน", p.text)
        ),
        None,
    )
    put(
        "cwie",
        cw is not None,
        cw.page if cw else None,
        cw.text if cw else "ไม่พบ CWIE/สหกิจศึกษา/ฝึกงาน ในหมวดที่ 4",
        "low",
        inferred=True,
    )

    # ----- LLM fills only what is still empty, with literal evidence -----
    if llm_only():  # evaluation: the model answers every LLM-capable field itself
        for k in LLM_FIELDS:
            values[k] = None
            metas.pop(k, None)
    missing = [k for k in LLM_FIELDS if values.get(k) is None]
    if missing and gateway is not None:
        blocks = [
            b for n in ("1", "2", "3", "4", "5", "6", "7", "13") for b in subsection(ch1.blocks, n)
        ]
        text = paragraphs_text(blocks, max_chars=12000)
        prompt = "จากหมวดที่ 1 ด้านล่าง ให้ค่าของฟิลด์: " + ", ".join(missing) + "\n\n" + text
        shots = narrow_fields(fewshot_examples("info", doc.source_name), missing)
        try:
            r = gateway.chat_json(
                SYSTEM,
                prompt,
                schema=SCHEMA,
                max_tokens=1024,
                **({"examples": shots} if shots else {}),
            )
        except LLMTruncated:
            if not shots:
                raise
            # examples can push a small model into a repetition loop; the plain request worked
            res.notes.append("ตัวอย่างทำให้คำตอบยาวเกิน จึงถามซ้ำโดยไม่ใช้ตัวอย่าง")
            r = gateway.chat_json(SYSTEM, prompt, schema=SCHEMA, max_tokens=1024)
        res.llm_usage = r.usage.to_dict()
        squashed = _squash(text)
        for k in missing:
            v = r.data.get(k)
            if v in (None, ""):
                continue
            if isinstance(v, str) and _squash(v) not in squashed:
                res.notes.append(f"{k}: LLM ตอบ '{v[:40]}' แต่ไม่พบในข้อความ จึงไม่รับ")
                continue
            if isinstance(v, int) and str(v) not in text:
                continue
            if k == "program_code" and not re.fullmatch(r"\d{8,16}", str(v)):
                continue
            put(k, v, None, str(v), "low", by="llm")

    res.data["count"] = sum(1 for k in FIELD_KEYS if values.get(k) not in (None, "", []))
    res.data["missing_required"] = [k for k in REQUIRED if values.get(k) in (None, "")]
    return res
