"""Part 7: ชุดวิชา + คำอธิบายชุดวิชา (chapter 4 item 3, with item 2 as the fallback list).

A module is a numbered heading "3.2.1.1 ชุดวิชา<ชื่อ> (<English name>) [จำนวน n หน่วยกิต |
ไม่นับหน่วยกิต]" followed by its description (Thai, sometimes an English paragraph too)
and then its courses (paragraph lines or a table). The group line above it
("3.2.1 วิชาบังคับ กำหนดให้เรียน จำนวน 10 ชุดวิชา รวม 67 หน่วยกิต") gives the group, the
declared number of modules and their credits, which the validators compare with what
was found. Deterministic: no LLM.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import PartResult, chapter, meta, subsection, to_int
from ocl_api.ingest.model import Block, Document, Paragraph, Table

RE_MODULE = re.compile(r"^\s*(?:(\d+(?:\.\d+)+)|(\d+)\))\s*ชุดวิชา\s*(?:วิชา)?\s*(.+?)\s*$")
RE_GROUP = re.compile(
    r"^\s*(\d+(?:\.\d+)+)?\s*(?:หมวด)?(วิชา[ก-๙ ]*?)\s*กำหนดให้.{0,40}?เรียน"
    r".*?จำนวน\s*([\d๐-๙]+)\s*ชุดวิชา(?:.*?(?:รวม(?:ไม่น้อยกว่า)?|จำนวน)\s*([\d๐-๙]+)\s*หน่วยกิต)?"
)
RE_CREDITS = re.compile(r"จำนวน\s*([\d๐-๙]+)\s*หน่วยกิต|(ไม่นับหน่วยกิต)")
RE_EN = re.compile(r"\(([A-Za-z][^()]*)\)")
RE_CODE = re.compile(r"^\s*([ก-ฮ]{2,4})\s?(\d{3})\*?\b")
RE_SUBHEAD = re.compile(r"^\s*\d+(?:\.\d+)+\s")
RE_MAJOR = re.compile(r"^\s*(วิชาเอก[ก-๙ ]{2,60}|แขนง[ก-๙ ]{2,60})\s*$")
RE_INLINE_DESC = re.compile(r"\s*มีรายวิชาต่อไปนี้\s*")
LATIN = re.compile(r"^[A-Za-z]")


def parse_heading(text: str) -> dict[str, Any] | None:
    m = RE_MODULE.match(text)
    if not m:
        return None
    rest = m.group(3)
    credits: int | None = None
    counted = True
    cm = RE_CREDITS.search(rest)
    if cm:
        if cm.group(2):
            counted = False
        else:
            credits = to_int(cm.group(1))
        rest = rest[: cm.start()].strip()
    name_en = None
    em = RE_EN.search(rest)
    if em:
        name_en = em.group(1).strip()
        rest = (rest[: em.start()] + rest[em.end() :]).strip()
    inline_desc = None
    im = RE_INLINE_DESC.search(rest)
    if im:
        # "4) ชุดวิชาสื่อ… มีรายวิชาต่อไปนี้ หลักการ แนวคิด…" glues the description to the heading
        inline_desc = rest[im.end() :].strip() or None
        rest = rest[: im.start()]
    rest = re.sub(r"\s+(ให้นิสิตเลือก.*)$", "", rest).strip(" :")
    return {
        "number": m.group(1) or m.group(2),
        "name_th": rest,
        "name_en": name_en,
        "credits": credits,
        "counted": counted,
        "description_inline": inline_desc,
    }


def _codes_in(block: Block) -> list[str]:
    if isinstance(block, Paragraph):
        m = RE_CODE.match(block.text)
        return [m.group(1) + m.group(2)] if m else []
    if isinstance(block, Table):
        out = []
        for row in block.rows:
            m = RE_CODE.match(row[0] or "") if row else None
            if m:
                out.append(m.group(1) + m.group(2))
        return out
    return []


def parse_modules(blocks: list[Block], *, with_description: bool) -> list[dict[str, Any]]:
    modules: list[dict[str, Any]] = []
    group: dict[str, Any] | None = None
    major: str | None = None
    cur: dict[str, Any] | None = None
    in_desc = False
    for b in blocks:
        if isinstance(b, Paragraph):
            t = b.text.strip()
            if not t:
                continue
            gm = RE_GROUP.match(t)
            if gm and "ชุดวิชา" in t and not RE_MODULE.match(t):
                group = {
                    "name": re.sub(r"\s+", " ", gm.group(2)).strip(),
                    "declared_modules": to_int(gm.group(3)),
                    "declared_credits": to_int(gm.group(4)) if gm.group(4) else None,
                }
                major = None
                cur = None
                continue
            mm = RE_MAJOR.match(t)
            if mm and cur is None or (mm and not _codes_in(b)):
                major = mm.group(1).strip()
                cur = None
                continue
            h = parse_heading(t)
            if h:
                inline = h.pop("description_inline")
                cur = {
                    **h,
                    "group": group["name"] if group else None,
                    "major": major,
                    "description_th": inline,
                    "description_en": None,
                    "course_codes": [],
                    "meta": meta("high", b.page, t),
                }
                modules.append(cur)
                in_desc = with_description
                continue
            if cur is None:
                continue
            codes = _codes_in(b)
            if codes:
                in_desc = False
                cur["course_codes"] += [c for c in codes if c not in cur["course_codes"]]
                continue
            if RE_SUBHEAD.match(t) and len(t) < 160:
                # "3.2.3 วิชาสหกิจศึกษา/…" opens a group without the "กำหนดให้เรียน" sentence
                num = RE_SUBHEAD.match(t).group(0).strip()
                if num.count(".") == 2:
                    group = {
                        "name": re.sub(r"\s+", " ", t[len(num) :]).strip(" :"),
                        "declared_modules": None,
                        "declared_credits": None,
                    }
                    major = None
                cur = None
                continue
            if in_desc:
                if LATIN.match(t) and len(t) > 25:
                    cur["description_en"] = ((cur["description_en"] or "") + " " + t).strip()
                elif t.startswith("(") and t.endswith(")") and LATIN.match(t[1:2]):
                    cur["name_en"] = cur["name_en"] or t.strip("() ")
                elif not LATIN.match(t):
                    cur["description_th"] = ((cur["description_th"] or "") + " " + t).strip()
        elif isinstance(b, Table) and cur is not None:
            codes = _codes_in(b)
            if codes:
                in_desc = False
                cur["course_codes"] += [c for c in codes if c not in cur["course_codes"]]
    return modules


def _groups_summary(blocks: list[Block]) -> list[dict[str, Any]]:
    out = []
    for b in blocks:
        if isinstance(b, Paragraph):
            gm = RE_GROUP.match(b.text)
            if gm and "ชุดวิชา" in b.text and not RE_MODULE.match(b.text):
                out.append(
                    {
                        "name": re.sub(r"\s+", " ", gm.group(2)).strip(),
                        "declared_modules": to_int(gm.group(3)),
                        "declared_credits": to_int(gm.group(4)) if gm.group(4) else None,
                        "page": b.page,
                    }
                )
    return out


def extract_modules(doc: Document, gateway=None) -> PartResult:  # noqa: ARG001 - no LLM here
    res = PartResult(key="modules", data={"modules": [], "groups": [], "meta": {}})
    ch4 = chapter(doc, "4")
    if ch4 is None:
        res.notes.append("chapter 4 not found")
        return res
    item3 = subsection(ch4.blocks, "3")
    item2 = subsection(ch4.blocks, "2")
    mods = parse_modules(item3, with_description=True)
    listed = parse_modules(item2, with_description=False)
    if not mods and listed:
        res.notes.append("item 3 has no ชุดวิชา headings; using the item 2 list without descriptions")
        mods = listed
        for m in mods:
            m["meta"]["confidence"] = "medium"
    for m in mods:
        if not m["description_th"]:
            m["meta"]["confidence"] = "medium"
            m["meta"]["note"] = "ไม่พบคำอธิบายชุดวิชา"
    res.data["modules"] = mods
    res.data["groups"] = _groups_summary(item3) or _groups_summary(item2)
    res.data["count"] = len(mods)
    res.data["listed_in_item2"] = [m["name_th"] for m in listed]
    if not mods:
        res.notes.append("no ชุดวิชา headings in chapter 4 items 2–3")
    return res
