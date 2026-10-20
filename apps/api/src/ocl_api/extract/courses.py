"""Part 8: courses (code, names, credits, hours, description, group) from chapter 4.

Parser first: course header lines look like "ศท111 ศิลปะการใช้ชีวิต 3(3-0-6)" followed by
"GEN111 The Art of Living" and description paragraphs. The LLM then reads the same
text in chunks and returns only the short identifying fields (never the long
descriptions, which the parser already has); its answer is merged: parser values
win, LLM-only courses are medium confidence, disagreements are flagged low. A
chunk whose reply is truncated is split in half and sent again.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import (
    PartResult,
    blocks_text,
    chapter,
    chunk_text,
    meta,
    subsection,
)
from ocl_api.ingest.model import Document, Paragraph, Table

RE_CREDIT = re.compile(r"(\d+)\s*\(\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*\)")
RE_TH_CODE = re.compile(r"^([ก-ฮ]{2,4}\s?\d{3}(?:-\d)?)\s+(.+)$")
RE_EN_CODE = re.compile(r"^([A-Z]{2,5}\s?\d{3}(?:-\d)?)\s+(.+)$")
RE_GROUP = re.compile(r"^\s*(\d+(?:\.\d+)+)\s+(.+?)(?:\s+(?:กำหนดให้เรียน|ไม่น้อยกว่า|จำนวน).*)?$")
RE_MODULE = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?(ชุดวิชา\S.*)$")
RE_PREREQ = re.compile(r"(?:บุรพวิชา|วิชาบังคับก่อน|Prerequisite)\s*[:：]?\s*(.+)$", re.I)

SYSTEM = (
    "คุณเป็นผู้ช่วยสกัดรายวิชาจากเล่มหลักสูตรของมหาวิทยาลัยไทย "
    "ตอบเป็น JSON เท่านั้น ห้ามแต่งข้อมูลที่ไม่มีในข้อความ คัดลอกรหัสและชื่อตามต้นฉบับทุกตัวอักษร"
)
SCHEMA = {
    "type": "object",
    "properties": {
        "courses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code_th": {"type": "string"},
                    "name_th": {"type": "string"},
                    "code_en": {"type": ["string", "null"]},
                    "name_en": {"type": ["string", "null"]},
                    "credit_text": {"type": ["string", "null"]},
                },
                "required": ["code_th", "name_th"],
            },
        }
    },
    "required": ["courses"],
}


def _norm_code(code: str) -> str:
    return re.sub(r"\s+", "", code)


def _new_course(code: str) -> dict[str, Any]:
    return {
        "code_th": code,
        "code_en": None,
        "name_th": None,
        "name_en": None,
        "credit_text": None,
        "credits": None,
        "hours": None,
        "description_th": None,
        "description_en": None,
        "prerequisite": None,
        "group": None,
        "module": None,
        "meta": None,
    }


def parse_courses(blocks: list) -> dict[str, dict[str, Any]]:
    courses: dict[str, dict[str, Any]] = {}
    group: str | None = None
    module: str | None = None
    cur: dict[str, Any] | None = None
    expect_en = False

    def lines_of(b) -> list[tuple[str, int | None]]:
        if isinstance(b, Paragraph):
            return [(b.text, b.page)]
        if isinstance(b, Table):
            return [(" ".join(c for c in row if c).strip(), b.page) for row in b.rows]
        return []

    for b in blocks:
        for text, page in lines_of(b):
            if not text:
                continue
            if isinstance(b, Paragraph) and b.level:
                cur, expect_en = None, False
                continue
            mc = RE_CREDIT.search(text)
            mt = RE_TH_CODE.match(text)
            if mt and mc and mc.start() > mt.start(2) - 1:
                code = _norm_code(mt.group(1))
                name = text[mt.start(2) : mc.start()].strip(" :")
                c = courses.get(code) or _new_course(code)
                c.update(
                    name_th=c["name_th"] or name,
                    credit_text=mc.group(0).replace(" ", ""),
                    credits=int(mc.group(1)),
                    hours={
                        "lecture": int(mc.group(2)),
                        "lab": int(mc.group(3)),
                        "self": int(mc.group(4)),
                    },
                    group=c["group"] or group,
                    module=c["module"] or module,
                )
                c["meta"] = c["meta"] or meta("high", page, text)
                courses[code] = c
                cur, expect_en = c, True
                continue
            mg = RE_GROUP.match(text)
            if mg and not mt:
                group = mg.group(2).strip()
                mm = RE_MODULE.match(text)
                module = mm.group(1).strip() if mm else None
                cur, expect_en = None, False
                continue
            mm = RE_MODULE.match(text)
            if mm and len(text) < 120:
                module = mm.group(1).strip()
                cur, expect_en = None, False
                continue
            if cur is not None:
                me = RE_EN_CODE.match(text)
                if expect_en and me:
                    cur["code_en"] = _norm_code(me.group(1))
                    cur["name_en"] = RE_CREDIT.sub("", me.group(2)).strip()
                    expect_en = False
                    continue
                expect_en = False
                mp = RE_PREREQ.search(text)
                if mp:
                    cur["prerequisite"] = mp.group(1).strip()
                    continue
                if re.match(r"^[A-Za-z]", text) and cur["description_th"]:
                    cur["description_en"] = ((cur["description_en"] or "") + " " + text).strip()
                elif not re.match(r"^\d+(\.\d+)*\s", text):
                    cur["description_th"] = ((cur["description_th"] or "") + " " + text).strip()
    return courses


def merge_llm(courses: dict[str, dict[str, Any]], items: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for it in items:
        code = _norm_code(str(it.get("code_th") or ""))
        if not code:
            continue
        c = courses.get(code)
        if c is None:
            c = _new_course(code)
            c.update(
                name_th=it.get("name_th"),
                code_en=it.get("code_en"),
                name_en=it.get("name_en"),
                credit_text=it.get("credit_text"),
                description_th=it.get("description_th"),
            )
            mc = RE_CREDIT.search(it.get("credit_text") or "")
            if mc:
                c["credits"] = int(mc.group(1))
            c["meta"] = meta("medium", None, it.get("name_th") or code, by="llm")
            courses[code] = c
            continue
        # cross-check: name and credit must agree, otherwise flag for review
        conflicts = []
        if it.get("name_th") and c["name_th"] and _squash(it["name_th"]) != _squash(c["name_th"]):
            conflicts.append(f"name_th parser={c['name_th']!r} llm={it['name_th']!r}")
        if it.get("credit_text") and c["credit_text"]:
            if _squash(it["credit_text"]) != _squash(c["credit_text"]):
                conflicts.append(f"credit parser={c['credit_text']} llm={it['credit_text']}")
        if conflicts:
            c["meta"]["confidence"] = "low"
            c["meta"]["by"] = "merged"
            c["meta"]["note"] = "; ".join(conflicts)
            notes.append(f"{code}: " + "; ".join(conflicts))
        else:
            c["meta"]["by"] = "merged"
        for k in ("code_en", "name_en", "description_th"):
            if not c.get(k) and it.get(k):
                c[k] = it[k]
                c["meta"].setdefault("filled_by_llm", []).append(k)
    return notes


LLM_PROMPT = (
    "จากข้อความต่อไปนี้ ให้ระบุรายวิชาทุกรายวิชาที่ปรากฏ ตอบเฉพาะ code_th (รหัสไทย เช่น ศท111) "
    "name_th, code_en (รหัสอังกฤษ เช่น GEN111), name_en และ credit_text (เช่น 3(3-0-6)) "
    "ไม่ต้องใส่คำอธิบายรายวิชา\n\n"
)
MIN_CHUNK_CHARS = 4000


def _add_usage(res: PartResult, usage) -> None:
    u = usage.to_dict() if hasattr(usage, "to_dict") else dict(usage or {})
    if res.llm_usage is None:
        res.llm_usage = u
        return
    for k in ("prompt_tokens", "completion_tokens", "seconds", "calls", "retries"):
        res.llm_usage[k] += u.get(k, 0)


def _llm_chunk(gateway, chunk: str, res: PartResult, depth: int) -> list[dict[str, Any]]:
    """Ask for the courses in one chunk; on truncation split the chunk and recurse."""
    from ocl_api.llm.gateway import LLMTruncated

    try:
        r = gateway.chat_json(SYSTEM, LLM_PROMPT + chunk, schema=SCHEMA, max_tokens=4096)
    except LLMTruncated as e:
        if e.usage is not None:
            _add_usage(res, e.usage)
        if len(chunk) <= MIN_CHUNK_CHARS or depth >= 4:
            res.notes.append(f"llm: chunk of {len(chunk)} chars truncated; skipped")
            return []
        half = len(chunk) // 2
        cut = chunk.rfind("\n", 0, half)
        cut = half if cut <= 0 else cut
        res.notes.append(f"llm: chunk of {len(chunk)} chars truncated; split")
        return _llm_chunk(gateway, chunk[:cut], res, depth + 1) + _llm_chunk(
            gateway, chunk[cut:], res, depth + 1
        )
    _add_usage(res, r.usage)
    return r.data.get("courses", []) if isinstance(r.data, dict) else []


def _squash(s: str) -> str:
    return re.sub(r"[\s​]+", "", s).lower()


def extract_courses(doc: Document, gateway=None, *, llm_chunk_chars: int = 20000) -> PartResult:
    res = PartResult(key="courses", data={"courses": [], "meta": {}})
    ch4 = chapter(doc, "4")
    if ch4 is None:
        res.notes.append("chapter 4 not found")
        return res
    blocks = subsection(ch4.blocks, "2") + subsection(ch4.blocks, "3")
    if not blocks:
        blocks = ch4.blocks
    courses = parse_courses(blocks)
    res.data["parser_count"] = len(courses)

    if gateway is not None:
        text = blocks_text(subsection(ch4.blocks, "3") or blocks)
        total_items: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunk_text(text, llm_chunk_chars), start=1):
            items = _llm_chunk(gateway, chunk, res, depth=0)
            total_items.extend(items)
            res.notes.append(f"llm chunk {i}: {len(items)} courses")
        res.notes.extend(merge_llm(courses, total_items))
        res.data["llm_count"] = len(total_items)

    res.data["courses"] = list(courses.values())
    res.data["count"] = len(courses)
    if not courses:
        res.notes.append("no course lines matched in chapter 4")
    return res
