"""Part 4: PLO / Sub-PLO from chapter 3 (รายละเอียดของผลลัพธ์การเรียนรู้)."""

from __future__ import annotations

import re
from typing import Any

from ocl_api.extract.base import (
    PartResult,
    blocks_text,
    chapter,
    llm_only,
    meta,
    paragraphs,
    tables,
)
from ocl_api.ingest.model import Document

RE_PLO = re.compile(r"^\s*(PLO\s?\d+)\s*[:：.)]?\s*(.+)$", re.I)
RE_SUB = re.compile(r"^\s*(PLO\s?\d+\.\d+|Sub-?PLO\s?\d+(?:\.\d+)?)\s*[:：.)]?\s*(.+)$", re.I)

SYSTEM = "คุณเป็นผู้ช่วยสกัดข้อมูลจากเล่มหลักสูตรของมหาวิทยาลัยไทย ตอบเป็น JSON เท่านั้น ห้ามแต่งข้อมูลที่ไม่มีในข้อความ"
SCHEMA = {
    "type": "object",
    "properties": {
        "plos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "text": {"type": "string"},
                    "sub_plos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"code": {"type": "string"}, "text": {"type": "string"}},
                            "required": ["code", "text"],
                        },
                    },
                },
                "required": ["code", "text"],
            },
        }
    },
    "required": ["plos"],
}


def _norm(code: str) -> str:
    return re.sub(r"\s+", "", code.upper())


def extract_plo(doc: Document, gateway=None) -> PartResult:
    res = PartResult(key="plo", data={"plos": [], "meta": {}})
    ch3 = chapter(doc, "3")
    if ch3 is None:
        res.notes.append("chapter 3 not found")
        return res

    plos: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def add(code: str, text: str, page: int | None, snippet: str, conf: str, sub: bool) -> None:
        code = _norm(code)
        text = text.strip(" :")
        if sub:
            parent = code.split(".")[0].replace("SUB-", "").replace("SUBPLO", "PLO")
            if parent in plos and all(s["code"] != code for s in plos[parent]["sub_plos"]):
                plos[parent]["sub_plos"].append(
                    {"code": code, "text": text, "meta": meta(conf, page, snippet)}  # type: ignore[arg-type]
                )
            return
        if code in plos:
            # keep the longest text (tables sometimes truncate), never overwrite with shorter
            if len(text) > len(plos[code]["text"]):
                plos[code]["text"] = text
            return
        plos[code] = {"code": code, "text": text, "sub_plos": [], "meta": meta(conf, page, snippet)}  # type: ignore[arg-type]
        order.append(code)

    # paragraphs first (item 1), then table cells
    for p in paragraphs(ch3.blocks) if not llm_only() else []:
        m = RE_SUB.match(p.text)
        if m:
            add(m.group(1), m.group(2), p.page, p.text, "high", True)
            continue
        m = RE_PLO.match(p.text)
        if (
            m
            and not p.text.lower().startswith("plo ")
            or (m and re.match(r"^PLO\s?\d", p.text, re.I))
        ):
            add(m.group(1), m.group(2), p.page, p.text, "high", False)
    for t in tables(ch3.blocks) if not llm_only() else []:
        for row in t.rows:
            for cell in row:
                for line in cell.split("\n"):
                    m = RE_SUB.match(line)
                    if m:
                        add(m.group(1), m.group(2), t.page, line, "medium", True)
                        continue
                    m = RE_PLO.match(line)
                    if m:
                        add(m.group(1), m.group(2), t.page, line, "medium", False)

    if not plos and gateway is not None:
        text = blocks_text(ch3.blocks, max_chars=30000)
        r = gateway.chat_json(
            SYSTEM, "สกัดรายการ PLO และ Sub-PLO (ถ้ามี) จากข้อความนี้\n\n" + text, schema=SCHEMA
        )
        res.llm_usage = r.usage.to_dict()
        for item in r.data.get("plos", []):
            add(
                item.get("code", ""), item.get("text", ""), None, item.get("text", ""), "low", False
            )
            plos[_norm(item.get("code", ""))]["meta"]["by"] = "llm"
            for s in item.get("sub_plos", []) or []:
                add(s.get("code", ""), s.get("text", ""), None, s.get("text", ""), "low", True)

    res.data["plos"] = [plos[c] for c in order]
    res.data["count"] = len(order)
    if not order:
        res.notes.append("no PLO lines matched in chapter 3")
    return res
