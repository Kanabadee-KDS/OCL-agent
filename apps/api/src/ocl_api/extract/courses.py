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
    chapter,
    chunk_text,
    llm_only,
    meta,
    paragraphs_text,
    subsection,
)
from ocl_api.fewshot import fewshot_kw
from ocl_api.ingest.model import Document, Paragraph, Table

RE_CREDIT = re.compile(r"(\d+)\s*\(\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*\)")
RE_TH_CODE = re.compile(r"^([ก-ฮ]{2,4}\s?\d{3}(?:-\d)?)\s+(.+)$")
RE_EN_CODE = re.compile(r"^([A-Z]{2,5}\s?\d{3}(?:-\d)?)\s+(.+)$")
RE_GROUP = re.compile(r"^\s*(\d+(?:\.\d+)+)\s+(.+?)(?:\s+(?:กำหนดให้เรียน|ไม่น้อยกว่า|จำนวน).*)?$")
RE_MODULE = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?(ชุดวิชา\S.*)$")
RE_PREREQ = re.compile(r"(?:บุรพวิชา|วิชาบังคับก่อน|Prerequisite)\s*[:：]?\s*(.+)$", re.I)
RE_CREDIT_WORDS = re.compile(r"(\d+)\s*หน่วยกิต")  # thesis / independent study: "12 หน่วยกิต"
RE_NO_CREDIT = re.compile(r"ไม่นับหน่วยกิต")


def credit_from(text: str) -> tuple[str, int | None, dict[str, int] | None, int] | None:
    """Return (credit_text, credits, hours, start_index) for the first credit mark in text."""
    mc = RE_CREDIT.search(text)
    if mc:
        hours = {"lecture": int(mc.group(2)), "lab": int(mc.group(3)), "self": int(mc.group(4))}
        return mc.group(0).replace(" ", ""), int(mc.group(1)), hours, mc.start()
    mn = RE_NO_CREDIT.search(text)
    if mn:
        return "ไม่นับหน่วยกิต", 0, None, mn.start()
    mw = RE_CREDIT_WORDS.search(text)
    if mw:
        return f"{mw.group(1)} หน่วยกิต", int(mw.group(1)), None, mw.start()
    return None


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

    pending: dict[str, Any] | None = None  # header seen, credit expected on the next line

    def lines_of(b) -> list[tuple[str, int | None]]:
        if isinstance(b, Paragraph):
            return [(b.text, b.page)]
        if isinstance(b, Table):
            return [(" ".join(c for c in row if c).strip(), b.page) for row in b.rows]
        return []

    def start(code: str, name: str | None, cr, page: int | None, text: str) -> dict[str, Any]:
        c = courses.get(code) or _new_course(code)
        conflicts = []
        if name and c["name_th"] and _squash(name) != _squash(c["name_th"]):
            conflicts.append(
                f"ชื่อต่างกันในเล่ม: {c['name_th']!r} (หน้า {_page(c)}) vs {name!r} (หน้า {page})"
            )
        if cr and c["credit_text"] and _squash(cr[0]) != _squash(c["credit_text"]):
            conflicts.append(f"หน่วยกิตต่างกันในเล่ม: {c['credit_text']} vs {cr[0]} (หน้า {page})")
        c.update(
            name_th=c["name_th"] or (name or None),
            group=c["group"] or group,
            module=c["module"] or module,
        )
        if cr and not c["credit_text"]:
            c.update(credit_text=cr[0], credits=cr[1], hours=cr[2])
        c["meta"] = c["meta"] or meta("high", page, text)
        if conflicts:
            c["meta"]["confidence"] = "low"
            c["meta"]["note"] = "; ".join([c["meta"].get("note", "")] + conflicts).strip("; ")
        courses[code] = c
        return c

    for b in blocks:
        if isinstance(b, Table):
            tcur: dict[str, Any] | None = None
            for row in b.rows:
                tc = _table_course_row(row)
                if tc is not None:
                    c = start(tc["code_th"], tc["name_th"], tc["credit"], b.page, " | ".join(row))
                    c["code_en"] = c["code_en"] or tc["code_en"]
                    c["name_en"] = c["name_en"] or tc["name_en"]
                    cur, expect_en, pending, tcur = c, False, None, c
                    continue
                cells = [x.strip() for x in row if x and x.strip()]
                if not cells or tcur is None:
                    continue
                me = re.match(r"^([A-Z]{2,5}\s?\d{3}(?:-\d)?)\*?\s*(.*)$", cells[0])
                if me and (len(cells[0]) < 12 or len(cells) > 1):
                    # "ECI721 | Advanced Applied Econometrics" row under the Thai code row
                    tcur["code_en"] = tcur["code_en"] or _norm_code(me.group(1))
                    rest = (me.group(2) + " " + " ".join(cells[1:])).strip()
                    tcur["name_en"] = tcur["name_en"] or RE_CREDIT.sub("", rest).strip()
                    continue
                joined = " ".join(cells)
                if re.search(r"[ก-๙]", joined):
                    tcur["description_th"] = ((tcur["description_th"] or "") + " " + joined).strip()
                else:
                    tcur["description_en"] = ((tcur["description_en"] or "") + " " + joined).strip()
            continue
        for text, page in lines_of(b):
            if not text:
                continue
            if isinstance(b, Paragraph) and b.level:
                cur, expect_en, pending = None, False, None
                continue
            cr = credit_from(text)
            mt = RE_TH_CODE.match(text)
            if pending is not None:
                # PDF layout: "ศท111 ชื่อวิชา" then "3(3-0-6) GEN111 The Art of Living"
                if cr and cr[3] <= 2:
                    c = start(
                        pending["code"], pending["name"], cr, pending["page"], pending["text"]
                    )
                    rest = text[cr[3] :]
                    rest = re.sub(
                        r"^\d+\s*\(\s*\d+\s*-\s*\d+\s*-\s*\d+\s*\)|^\d+\s*หน่วยกิต|^ไม่นับหน่วยกิต",
                        "",
                        rest,
                    ).strip()
                    me = RE_EN_CODE.match(rest)
                    if me:
                        c["code_en"] = _norm_code(me.group(1))
                        c["name_en"] = me.group(2).strip()
                    cur, expect_en, pending = c, not me, None
                    continue
                # not a course header after all: keep its text as ordinary description
                if cur is not None and not RE_GROUP.match(pending["text"]):
                    cur["description_th"] = (
                        (cur["description_th"] or "") + " " + pending["text"]
                    ).strip()
                pending = None
            if mt and cr and cr[3] > mt.start(2) - 1:
                code = _norm_code(mt.group(1))
                name = text[mt.start(2) : cr[3]].strip(" :")
                c = start(code, name, cr, page, text)
                cur, expect_en = c, True
                continue
            if mt and not cr and len(text) < 160 and not RE_GROUP.match(text):
                pending = {
                    "code": _norm_code(mt.group(1)),
                    "name": mt.group(2).strip(" :"),
                    "page": page,
                    "text": text,
                }
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


RE_CODE_CELL = re.compile(r"^([ก-ฮ]{2,4}\s?\d{3}(?:-\d)?)\*?\s*$")


def _table_course_row(row: list[str]) -> dict[str, Any] | None:
    """'ศฐ510*\nEC510*' | 'ชื่อไทย\nEnglish name' | '2(2-0-4)' -> fields, else None."""
    if len(row) < 2:
        return None
    first_lines = [x.strip() for x in row[0].split("\n") if x.strip()]
    if not first_lines:
        return None
    m = RE_CODE_CELL.match(first_lines[0])
    if not m:
        return None
    code_en = None
    for x in first_lines[1:]:
        me = re.match(r"^([A-Z]{2,5}\s?\d{3}(?:-\d)?)\*?\s*$", x)
        if me:
            code_en = _norm_code(me.group(1))
            break
    name_lines = [x.strip() for x in row[1].split("\n") if x.strip()]
    name_th = next((x for x in name_lines if re.search(r"[ก-๙]", x)), None)
    name_en = next((x for x in name_lines if not re.search(r"[ก-๙]", x)), None)
    joined = " ".join(row)
    cr = credit_from(joined)
    if name_th is None and cr is None:
        return None
    return {
        "code_th": _norm_code(m.group(1)),
        "code_en": code_en,
        "name_th": RE_CREDIT.sub("", name_th).strip() if name_th else None,
        "name_en": RE_CREDIT.sub("", name_en).strip() if name_en else None,
        "credit": cr,
    }


def _verify_against_text(item: dict[str, Any], chunk: str) -> dict[str, Any] | None:
    """Keep only what the model copied from the text: the code must occur literally; a name
    or credit that does not occur (ignoring spaces) is dropped rather than trusted."""
    code = _norm_code(str(item.get("code_th") or ""))
    if not code or not RE_CODE_CELL.match(code):
        return None
    squashed = _squash(chunk)
    if _squash(code) not in squashed:
        return None
    out = dict(item)
    out["code_th"] = code
    for k in ("name_th", "credit_text", "name_en"):
        v = out.get(k)
        if v and _squash(str(v)) not in squashed:
            out[k] = None
    return out


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
            cr = credit_from(it.get("credit_text") or "")
            if cr:
                c["credits"], c["hours"] = cr[1], cr[2]
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


def _llm_chunk(
    gateway, chunk: str, res: PartResult, depth: int, shots: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Ask for the courses in one chunk; on truncation split the chunk and recurse."""
    from ocl_api.llm.gateway import LLMTruncated

    try:
        r = gateway.chat_json(
            SYSTEM, LLM_PROMPT + chunk, schema=SCHEMA, max_tokens=4096, **(shots or {})
        )
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
        return _llm_chunk(gateway, chunk[:cut], res, depth + 1, shots) + _llm_chunk(
            gateway, chunk[cut:], res, depth + 1, shots
        )
    _add_usage(res, r.usage)
    return r.data.get("courses", []) if isinstance(r.data, dict) else []


def _page(c: dict[str, Any]) -> Any:
    return ((c.get("meta") or {}).get("source") or {}).get("page")


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
    courses = parse_courses(blocks) if not llm_only() else {}
    res.data["parser_count"] = len(courses)

    if gateway is not None:
        shots = fewshot_kw("courses", doc.source_name)
        # Paragraphs only: tables (course lists, mapping) are the parser's job and only
        # tempt the model into listing hundreds of codes.
        text = paragraphs_text(subsection(ch4.blocks, "3") or blocks)
        total_items: list[dict[str, Any]] = []
        seen: set[str] = set()
        dropped = 0
        for i, chunk in enumerate(chunk_text(text, llm_chunk_chars), start=1):
            items = _llm_chunk(gateway, chunk, res, depth=0, shots=shots)
            kept = 0
            for it in items:
                it = _verify_against_text(it, chunk)
                if it is None or it["code_th"] in seen:
                    dropped += 1
                    continue
                seen.add(it["code_th"])
                total_items.append(it)
                kept += 1
            res.notes.append(f"llm chunk {i}: {len(items)} items, {kept} verified")
        if dropped:
            res.notes.append(f"llm: {dropped} items dropped (code not in text, or duplicate)")
        res.notes.extend(merge_llm(courses, total_items))
        res.data["llm_count"] = len(total_items)

    res.data["courses"] = list(courses.values())
    res.data["count"] = len(courses)
    if not courses:
        res.notes.append("no course lines matched in chapter 4")
    return res
