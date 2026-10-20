"""Part 6: curriculum structure (หมวด/กลุ่มวิชา tree with credits) + total credits."""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import (
    PartResult,
    blocks_text,
    chapter,
    meta,
    paragraphs,
    subsection,
    tables,
    to_int,
)
from ocl_api.ingest.model import Document, Table

RE_TOTAL = re.compile(r"(?:ไม่น้อยกว่า|รวม(?:ไม่น้อยกว่า)?|จำนวน)\s*([\d,๐-๙]+)\s*หน่วยกิต")
RE_NODE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s*(.+?)\s*$")
RE_CREDIT_TAIL = re.compile(r"(?:ไม่น้อยกว่า\s*)?([\d,๐-๙]+)\s*หน่วยกิต")

SYSTEM = "คุณเป็นผู้ช่วยสกัดข้อมูลจากเล่มหลักสูตรของมหาวิทยาลัยไทย ตอบเป็น JSON เท่านั้น ห้ามแต่งข้อมูลที่ไม่มีในข้อความ"
SCHEMA = {
    "type": "object",
    "properties": {
        "total_credits": {"type": ["integer", "null"]},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "name": {"type": "string"},
                    "credits": {"type": ["integer", "null"]},
                },
                "required": ["number", "name"],
            },
        },
    },
    "required": ["nodes"],
}


def _node(number: str, name: str, credits: int | None, page: int | None, snippet: str, conf: str):
    return {
        "number": number,
        "level": number.count(".") + 1,
        "name": name.strip(" :"),
        "credits": credits,
        "children": [],
        "meta": meta(conf, page, snippet),  # type: ignore[arg-type]
    }


def build_tree(flat: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    for n in flat:
        while stack and stack[-1]["level"] >= n["level"]:
            stack.pop()
        (stack[-1]["children"] if stack else roots).append(n)
        stack.append(n)
    return roots


RE_PLAN = re.compile(r"^\s*แผน\s*[\d.ก-ฮ]+")


def _plan_columns(header: list[str]) -> list[tuple[int, str]]:
    """Graduate books lay plans out as columns: 'หมวดวิชา | แผน 1.1 … | แผน 2.1 …'."""
    return [(i, c.strip()) for i, c in enumerate(header) if i > 0 and RE_PLAN.match(c)]


def _is_header_or_blank(row: list[str]) -> bool:
    first = row[0].strip() if row else ""
    return not first or first == "หมวดวิชา" or all(c.strip() in ("", "หน่วยกิต") for c in row)


def _parse_simple_table(t: Table, res: PartResult) -> list[dict[str, Any]]:
    """'หมวดวิชา | หน่วยกิต' rows; numbered rows give levels, unnumbered rows are level 1."""
    flat: list[dict[str, Any]] = []
    seq = 0
    for row in t.rows[1:]:
        if _is_header_or_blank(row):
            continue
        credit_cell = next((c for c in row[1:] if to_int(c) is not None), "")
        credits = to_int(credit_cell) if credit_cell else None
        first = row[0].strip()
        if "รวม" in first:
            if credits and res.data["total_credits"] is None:
                res.data["total_credits"] = credits
                res.data["meta"]["total_credits"] = meta("high", t.page, " | ".join(row))
            continue
        m = RE_NODE.match(first)
        if m and re.match(r"^\d", first):
            flat.append(_node(m.group(1), m.group(2), credits, t.page, " | ".join(row), "high"))
        else:
            seq += 1
            name = RE_CREDIT_TAIL.sub("", first).strip(" :")
            flat.append(_node(str(seq), name, credits, t.page, " | ".join(row), "high"))
    return flat


def _parse_plan_table(
    t: Table, plans: list[tuple[int, str]], res: PartResult
) -> list[dict[str, Any]]:
    """One root per plan (แผน 1.1, แผน 2.1 …) with the หมวดวิชา rows as children."""
    flat: list[dict[str, Any]] = []
    for pi, (col, plan_name) in enumerate(plans, start=1):
        root = _node(f"P{pi}", plan_name, None, t.page, " | ".join(t.rows[0]), "high")
        root["plan"] = True
        children: list[dict[str, Any]] = []
        for row in t.rows[1:]:
            if _is_header_or_blank(row) or col >= len(row):
                continue
            first = row[0].strip()
            credits = to_int(row[col])
            if "รวม" in first:
                root["credits"] = credits
                if credits and res.data["total_credits"] is None:
                    res.data["total_credits"] = credits
                    res.data["meta"]["total_credits"] = meta("high", t.page, " | ".join(row))
                continue
            if credits is None or row[col].strip() in ("-", "–"):
                continue  # this หมวด does not apply to this plan
            name = RE_CREDIT_TAIL.sub("", first).strip(" :")
            children.append(
                _node(f"P{pi}.{len(children) + 1}", name, credits, t.page, " | ".join(row), "high")
            )
        flat.append(root)
        flat.extend(children)
    return flat


def extract_structure(doc: Document, gateway=None) -> PartResult:
    res = PartResult(key="structure", data={"total_credits": None, "tree": [], "meta": {}})
    ch4 = chapter(doc, "4")
    ch1 = chapter(doc, "1")

    # total credits: chapter 1 item 4 first, then chapter 4 item 1
    for sec, num in ((ch1, "4"), (ch4, "1")):
        if sec is None or res.data["total_credits"] is not None:
            continue
        for p in paragraphs(subsection(sec.blocks, num)):
            m = RE_TOTAL.search(p.text)
            if m:
                res.data["total_credits"] = to_int(m.group(1))
                res.data["meta"]["total_credits"] = meta("high", p.page, p.text)
                break

    flat: list[dict[str, Any]] = []
    if ch4 is not None:
        blocks = subsection(ch4.blocks, "1") or ch4.blocks
        for t in tables(blocks):
            head = " ".join(t.rows[0]).replace(" ", "")
            if "หมวดวิชา" not in head and "หน่วยกิต" not in head:
                continue
            plans = _plan_columns(t.rows[0])
            if plans:
                flat.extend(_parse_plan_table(t, plans, res))
            else:
                flat.extend(_parse_simple_table(t, res))
            if flat:
                break
        if not flat:  # text form: "1. หมวดวิชาศึกษาทั่วไป ไม่น้อยกว่า 30 หน่วยกิต"
            for p in paragraphs(blocks):
                m = RE_NODE.match(p.text)
                c = RE_CREDIT_TAIL.search(p.text)
                if m and c and re.match(r"^\d", p.text.strip()) and "จำนวนหน่วยกิตตลอด" not in p.text:
                    name = RE_CREDIT_TAIL.sub("", m.group(2)).strip(" :")
                    flat.append(
                        _node(m.group(1), name, to_int(c.group(1)), p.page, p.text, "medium")
                    )

    if not flat and gateway is not None and ch4 is not None:
        text = blocks_text(subsection(ch4.blocks, "1") or ch4.blocks, max_chars=20000)
        r = gateway.chat_json(
            SYSTEM,
            "สกัดโครงสร้างหลักสูตร (หมวดวิชา/กลุ่มวิชา และหน่วยกิต) จากข้อความนี้ "
            "ให้ number เป็นเลขข้อเช่น 1, 2.1, 2.1.1\n\n" + text,
            schema=SCHEMA,
        )
        res.llm_usage = r.usage.to_dict()
        for n in r.data.get("nodes", []):
            flat.append(
                _node(
                    str(n.get("number", "")),
                    n.get("name", ""),
                    n.get("credits"),
                    None,
                    n.get("name", ""),
                    "low",
                )
            )
            flat[-1]["meta"]["by"] = "llm"
        if res.data["total_credits"] is None and r.data.get("total_credits"):
            res.data["total_credits"] = int(r.data["total_credits"])
            res.data["meta"]["total_credits"] = meta("low", None, "LLM", by="llm", inferred=True)

    res.data["tree"] = build_tree(flat)
    res.data["node_count"] = len(flat)
    if not flat:
        res.notes.append("no structure table/text found in chapter 4 item 1")
    return res
