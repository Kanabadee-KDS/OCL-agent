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
)
from ocl_api.extract.ksec import RE_PLAN
from ocl_api.fewshot import fewshot_kw
from ocl_api.ingest.model import Document, Paragraph, Table

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
                    "plan": {"type": ["string", "null"]},
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


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def same_wording(a: str, b: str) -> bool:
    """One text is the other cut short (table cells wrap mid-sentence), not a different PLO."""
    a, b = _squash(a), _squash(b)
    return a in b or b in a


def _plan_label(text: str) -> str | None:
    """'1.1 เมื่อนิสิตจบการศึกษาแผน 1 แบบวิชาการ จะสามารถ' -> 'แผน 1 แบบวิชาการ' (short lines only)."""
    if len(text) >= 160 or RE_PLO.match(text) or RE_SUB.match(text):
        return None
    m = RE_PLAN.search(text)
    return re.sub(r"แผน\s*", "แผน ", m.group(1)).strip() if m else None


def split_llm_code(code: str, plan: str | None) -> tuple[str, str | None]:
    """Models sometimes put the plan inside the code ('PLO1 แผน 1 แบบวิชาการ'); split it out."""
    m = re.match(r"\s*((?:Sub-?)?PLO\s?\d+(?:\.\d+)?)(.*)$", code or "", re.I | re.S)
    if not m:
        return code, plan
    rest = m.group(2)
    if not plan:
        pm = RE_PLAN.search(rest)
        if pm:
            plan = re.sub(r"แผน\s*", "แผน ", pm.group(1)).strip()
    return m.group(1), plan


def extract_plo(doc: Document, gateway=None) -> PartResult:
    """PLOs in document order, keyed by (plan, code).

    Programmes with several study plans (แผน 1 แบบวิชาการ / แผน 2 แบบวิชาชีพ) declare a
    separate PLO1..n under each plan heading, with different text; keying by code alone kept
    only the first plan. Single-plan books get plan = None and the same output as before.
    """
    res = PartResult(key="plo", data={"plos": [], "plans": [], "meta": {}})
    ch3 = chapter(doc, "3")
    if ch3 is None:
        res.notes.append("chapter 3 not found")
        return res

    plos: dict[tuple[str | None, str], dict[str, Any]] = {}
    order: list[tuple[str | None, str]] = []

    def add(
        code: str,
        text: str,
        page: int | None,
        snippet: str,
        conf: str,
        sub: bool,
        plan: str | None,
        table: bool = False,
    ) -> None:
        code = _norm(code)
        text = text.strip(" :")
        if sub:
            parent = code.split(".")[0].replace("SUB-", "").replace("SUBPLO", "PLO")
            key = (plan, parent)
            if key in plos and all(s["code"] != code for s in plos[key]["sub_plos"]):
                plos[key]["sub_plos"].append(
                    {"code": code, "text": text, "meta": meta(conf, page, snippet)}  # type: ignore[arg-type]
                )
            return
        key = (plan, code)
        if key in plos:
            cur = plos[key]
            if same_wording(text, cur["text"]):
                # keep the longest text (tables sometimes truncate), never overwrite with shorter
                if len(text) > len(cur["text"]):
                    cur["text"] = text
                return
            if table == (cur["meta"].get("from") == "table"):
                # A later line of the same kind re-mentions the code ("หมายเหตุ: PLO6 เป็น...",
                # "PLO 2-5 เป็น..."); the first definition stands.
                return
            # The book words this PLO differently in the list and in the K/S/E/C table.
            # Keep the list wording (the PLO statement itself), offer the table one, and
            # let the reviewer pick: neither text is silently dropped.
            alts = cur["meta"].setdefault("alternatives", [])
            if table:
                if all(not same_wording(text, a["text"]) for a in alts):
                    alts.append({"text": text, "page": page, "from": "table"})
            else:
                alts.append({"text": cur["text"], "page": cur["meta"]["source"]["page"],
                             "from": cur["meta"].get("from")})  # fmt: skip
                cur["text"] = text
                cur["meta"]["source"] = {"page": page, "snippet": snippet[:160]}
                cur["meta"]["from"] = "list"
            cur["meta"]["confidence"] = "low"
            seen = [cur["meta"]["source"]["page"], *(a["page"] for a in alts)]
            pages = sorted({p_ for p_ in seen if p_})
            cur["meta"]["note"] = (
                "ข้อความ PLO ในรายการกับในตารางไม่ตรงกัน"
                + (f" (หน้า {', '.join(map(str, pages))})" if pages else "")
                + " ระบบใช้ข้อความจากรายการ ให้ Admin ยืนยันฉบับทางการ"
            )
            return
        plos[key] = {
            "code": code,
            "plan": plan,
            "text": text,
            "sub_plos": [],
            "meta": {**meta(conf, page, snippet), "from": "table" if table else "list"},  # type: ignore[arg-type]
        }
        order.append(key)

    if not llm_only():
        plan: str | None = None
        for b in ch3.blocks:
            if isinstance(b, Paragraph):
                label = _plan_label(b.text)
                if label:
                    # A book that declared its PLOs before any plan heading has one PLO set;
                    # later plan headings (year-level outcomes per plan) only re-mention it.
                    if not any(k[0] is None for k in order):
                        plan = label
                    continue
                m = RE_SUB.match(b.text)
                if m:
                    add(m.group(1), m.group(2), b.page, b.text, "high", True, plan)
                    continue
                m = RE_PLO.match(b.text)
                if (
                    m
                    and not b.text.lower().startswith("plo ")
                    or (m and re.match(r"^PLO\s?\d", b.text, re.I))
                ):
                    add(m.group(1), m.group(2), b.page, b.text, "high", False, plan)
            elif isinstance(b, Table):
                for row in b.rows:
                    for cell in row:
                        for line in cell.split("\n"):
                            m = RE_SUB.match(line)
                            if m:
                                add(m.group(1), m.group(2), b.page, line, "medium", True, plan)
                                continue
                            m = RE_PLO.match(line)
                            if m:
                                add(m.group(1), m.group(2), b.page, line, "medium", False, plan,
                                    table=True)  # fmt: skip

    if not plos and gateway is not None:
        text = blocks_text(ch3.blocks, max_chars=30000)
        r = gateway.chat_json(
            SYSTEM,
            "สกัดรายการ PLO และ Sub-PLO (ถ้ามี) จากข้อความนี้ "
            "ถ้าเล่มแยก PLO ตามแผนการศึกษา (เช่น แผน 1 แบบวิชาการ / แผน 2 แบบวิชาชีพ) "
            "ให้ใส่ชื่อแผนในช่อง plan และใส่เฉพาะรหัส (เช่น PLO1) ในช่อง code "
            "ถ้าไม่แยกแผนให้ plan เป็น null\n\n" + text,
            schema=SCHEMA,
            **fewshot_kw("plo", doc.source_name),
        )
        res.llm_usage = r.usage.to_dict()
        for item in r.data.get("plos", []):
            code, plan_ = split_llm_code(item.get("code", ""), item.get("plan"))
            add(code, item.get("text", ""), None, item.get("text", ""), "low", False, plan_)
            key = (plan_, _norm(code))
            if key in plos:
                plos[key]["meta"]["by"] = "llm"
            for s_ in item.get("sub_plos", []) or []:
                add(
                    s_.get("code", ""),
                    s_.get("text", ""),
                    None,
                    s_.get("text", ""),
                    "low",
                    True,
                    plan_,
                )

    res.data["plos"] = [plos[k] for k in order]
    res.data["plans"] = list(dict.fromkeys(k[0] for k in order if k[0]))
    res.data["count"] = len(order)
    if not order:
        res.notes.append("no PLO lines matched in chapter 3")
    elif res.data["plans"]:
        res.notes.append(f"PLO แยกตามแผน: {', '.join(res.data['plans'])}")
    conflicts = [plos[k]["code"] for k in order if plos[k]["meta"].get("alternatives")]
    res.data["text_conflicts"] = conflicts
    if conflicts:
        res.notes.append("ข้อความ PLO ในรายการกับตารางไม่ตรงกัน: " + ", ".join(conflicts))
    return res
