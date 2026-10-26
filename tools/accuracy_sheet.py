#!/usr/bin/env python3
"""Build docs/testing/accuracy_test_script.csv: the item-level sheet the team fills in against
the real books, pre-filled with what each configuration extracted, so accuracy is measured
against the book and not against the parser. Guide: docs/testing/accuracy-test-guide_ocl.md.

Values are copied from saved outputs (nothing is re-run):
  ระบบจริง            run-2026-10-23-localllm-fewshot/<book>/ollama-parser_first
  Local LLM ล้วน        run-2026-10-23-localllm-fewshot/<book>/ollama-llm_only
  Local LLM ปรับปรุง    run-2026-10-23-localllm-fewshot/<book>/ollama-llm_only-fs-all
  Gemini ล้วน           run-2026-10-23/<book>/gemini-llm_only (first round)

  uv run python tools/accuracy_sheet.py [--out docs/testing/accuracy_test_script.csv]

Structure rows are matched by (study plan, category path), not by name: books with several
plans repeat category names ("หมวดวิชาปริญญานิพนธ์" is 48 credits in แผน 1.1 and 36 in
แผน 2.1), and matching by name alone copied the last plan's value into every row
(R1 accuracy test, 26 ต.ค. 2569: ACC-154 and ACC-185 looked wrong for the system although it
had extracted 12 and 48 correctly). Models may also nest the other way round (category → plan).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

from ocl_api.extract.plo import split_llm_code

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "docs/eval/run-2026-10-23-localllm-fewshot"
OLD = ROOT / "docs/eval/run-2026-10-23"

BOOKS = [  # folder, short name, kind
    ("วท-บ-วิทยาการการเปลี่ยนแปลงสภาพภูมิอากาศ", "วท.บ. ภูมิอากาศ", "bachelor"),
    ("4-1-4-วท-บ-วิทยาศาสตร์การอาหารและโภชนาการ-ปรั", "วท.บ. อาหาร (PDF)", "bachelor"),
    ("ศศ-บ-การจัดการภูมิสังคมและวัฒนธรรม-ปป-69", "ศศ.บ. ภูมิสังคม", "bachelor"),
    ("ศศ-ม-เศรษฐศาสตร์ธุรกิจและการจัดการ-ปป-69", "ศศ.ม. เศรษฐศาสตร์ธุรกิจ", "postgrad"),
    ("ปร-ด-เศรษฐศาสตร์เพื่อการพัฒนาอย่างยั่งยื", "ปร.ด. เศรษฐศาสตร์", "postgrad"),
    ("วท-บ-อาหาร-สแกน-14-หน้า", "วท.บ. อาหาร (ภาพสแกน 14 หน้า)", "scan"),
]
INFO = [
    ("program_code", "รหัสหลักสูตร สกอ. (14 หลัก · ถ้าเล่มเขียน xxxx ให้กรอก (ว่าง))"),
    ("name_th", "ชื่อหลักสูตรภาษาไทย"),
    ("name_en", "ชื่อหลักสูตรภาษาอังกฤษ"),
    ("degree_full_th", "ชื่อปริญญาเต็มภาษาไทย"),
    ("degree_abbr_th", "ชื่อปริญญาย่อภาษาไทย"),
    ("degree_full_en", "ชื่อปริญญาเต็มภาษาอังกฤษ"),
    ("degree_abbr_en", "ชื่อปริญญาย่อภาษาอังกฤษ"),
    ("total_credits", "หน่วยกิตรวมตลอดหลักสูตร (ตัวเลข)"),
    ("duration_years", "ระยะเวลาการศึกษา (ปี · ช่องที่ทำเครื่องหมาย ☑)"),
    ("start_semester", "ภาคการศึกษาที่เริ่มใช้หลักสูตร"),
    ("start_year", "ปีการศึกษาที่เริ่มใช้หลักสูตร (พ.ศ.)"),
]
COLS = ["TC_ID", "เล่ม", "ส่วน", "รายการ", "สิ่งที่ต้องตรวจ", "หน้าโดยประมาณ",
        "ค่าในเล่มจริง (กรอกก่อนดูคอลัมน์ถัดไป)",
        "ระบบจริง: ค่า", "ระบบจริง: ผล",
        "Local LLM ล้วน: ค่า", "Local LLM ล้วน: ผล",
        "Local LLM (ปรับปรุง) ล้วน: ค่า", "Local LLM (ปรับปรุง) ล้วน: ผล",
        "Gemini ล้วน: ค่า", "Gemini ล้วน: ผล",
        "ผู้ตรวจ", "วันที่ตรวจ", "หมายเหตุ"]  # fmt: skip
EMPTY, MISSING = "(ว่าง)", "(ไม่พบ)"
RE_PLAN_NO = re.compile(r"แผน\s*(\d+(?:\.\d+)?)")
RE_GENERIC = re.compile(r"^(โครงสร้างหลักสูตร|จำนวนหน่วยกิต)")


def load(path: Path, part: str) -> dict[str, Any]:
    p = path / f"{part}.json"
    if not p.exists():
        return {}
    j = json.loads(p.read_text(encoding="utf-8"))
    return j.get("data", j)


def norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def show(v: Any) -> str:
    return EMPTY if v in (None, "", []) else str(v)


def legs(folder: str) -> dict[str, Path]:
    return {
        "sys": NEW / folder / "ollama-parser_first",
        "loc": NEW / folder / "ollama-llm_only",
        "imp": NEW / folder / "ollama-llm_only-fs-all",
        "gem": OLD / folder / "gemini-llm_only",
    }


def page_of(m: dict[str, Any] | None) -> Any:
    return ((m or {}).get("source") or {}).get("page") or ""


def structure_key(path: list[str]) -> tuple[str | None, tuple[str, ...]]:
    """(plan number, last two category names) for a node given the names from root to it.

    'แผน 1 แบบวิชาการ' > 'หมวดวิชาบังคับ' and 'หมวดวิชาบังคับ' > 'แผน 1 แบบวิชาการ' give the
    same key; a plan's total ('รวมไม่น้อยกว่า' > 'แผน 1 …') keys like the plan node itself.
    """
    plan = None
    cats = []
    for name in path:
        m = RE_PLAN_NO.search(name or "")
        if m and norm(name).startswith("แผน"):
            plan = m.group(1)
        elif not RE_GENERIC.match(name or "") and not norm(name).startswith("รวม"):
            cats.append(norm(name))
    return plan, tuple(cats[-2:])


def flat_structure(tree: list[dict[str, Any]] | None) -> list[tuple[tuple, list[str], dict]]:
    """(key, names from root, node) for every node, in document order."""
    out: list[tuple[tuple, list[str], dict]] = []

    def walk(nodes, path):
        for n in nodes or []:
            p = [*path, n.get("name") or ""]
            out.append((structure_key(p), p, n))
            walk(n.get("children"), p)

    walk(tree, [])
    return out


class StructureIndex:
    """Find a model's node for a system node: same (plan, last two categories); else the same
    last category when only one node has it (models often flatten the tree); a model that
    never splits by plan is looked up without the plan (its one figure covers every plan)."""

    def __init__(self, nodes: list[tuple[tuple, list[str], dict]]):
        self.full: dict[tuple, tuple[list[str], dict]] = {}
        self.last: dict[tuple, list[tuple[list[str], dict]]] = {}
        for key, path, n in nodes:
            if not key[0] and not key[1]:
                continue  # 'จำนวนหน่วยกิตตลอดหลักสูตร': the book total, never a plan or category
            self.full.setdefault(key, (path, n))  # first wins: a later same key is a repeat
            if key[1]:
                self.last.setdefault((key[0], key[1][-1]), []).append((path, n))
        self.has_plans = any(k[0] for k in self.full)

    def _find(self, plan, cats):
        if (plan, cats) in self.full:
            return self.full[(plan, cats)]
        hits = self.last.get((plan, cats[-1])) if cats else None
        return hits[0] if hits and len(hits) == 1 else None

    def get(self, key: tuple) -> tuple[list[str], dict] | None:
        found = self._find(*key)
        if found is None and key[0] and key[1] and not self.has_plans:
            found = self._find(None, key[1])
        return found


def build() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def add(book, part, item, what, page, vals, note=""):
        rows.append({
            "TC_ID": f"ACC-{len(rows) + 1:03d}", "เล่ม": book, "ส่วน": part, "รายการ": item,
            "สิ่งที่ต้องตรวจ": what, "หน้าโดยประมาณ": page,
            "ระบบจริง: ค่า": vals["sys"], "Local LLM ล้วน: ค่า": vals["loc"],
            "Local LLM (ปรับปรุง) ล้วน: ค่า": vals["imp"], "Gemini ล้วน: ค่า": vals["gem"],
            "หมายเหตุ": note,
        })  # fmt: skip

    for folder, book, kind in BOOKS:
        legs_ = legs(folder)
        # ---- info: all 11 fields ----
        info = {k: load(p, "info") for k, p in legs_.items()}
        for key, what in INFO:
            vals = {k: show((v.get("values") or {}).get(key)) for k, v in info.items()}
            note = "เล่มสแกน: อ่านจากภาพในไฟล์ PDF สแกน" if kind == "scan" else ""
            add(
                book,
                "ข้อมูลหลัก",
                key,
                what,
                page_of((info["sys"].get("meta") or {}).get(key)),
                vals,
                note,
            )
        if kind == "scan":
            continue
        # ---- PLO: every PLO in the system output, keyed by (plan, code) ----
        plo = {k: load(p, "plo").get("plos", []) for k, p in legs_.items()}

        def plo_key(p):
            code, plan = split_llm_code(p.get("code", ""), p.get("plan"))
            return norm(plan), norm(code)

        idx = {k: {plo_key(p): p for p in v} for k, v in plo.items()}
        for p in plo["sys"]:
            key = plo_key(p)
            vals = {}
            for k in legs_:
                q = idx[k].get(key) or (idx[k].get(("", key[1])) if not key[0] else None)
                vals[k] = show(q.get("text")) if q else MISSING
            label = p["code"] + (f" · {p['plan']}" if p.get("plan") else "")
            note = ""
            if folder.startswith("ปร-ด") and p["code"] in ("PLO2", "PLO3"):
                note = (
                    "เล่มเขียนข้อความ PLO นี้ต่างกันระหว่างรายการกับตาราง K/S/E/C หน้า 22 · "
                    "กรอกตามรายการ และจดข้อความในตารางในหมายเหตุ"
                )
            add(
                book,
                "PLO",
                label,
                "ข้อความ PLO เต็ม (รวมส่วนที่ขึ้นบรรทัดใหม่)",
                page_of(p.get("meta")),
                vals,
                note,
            )
        # ---- structure: every node with its credits, keyed by (plan, category path) ----
        st = {k: flat_structure(load(p, "structure").get("tree")) for k, p in legs_.items()}
        sidx = {k: StructureIndex(v) for k, v in st.items()}
        for key, _, n in st["sys"]:
            vals = {}
            for k in legs_:
                hit = sidx[k].get(key)
                if hit is None:
                    vals[k] = MISSING
                    continue
                path, q = hit
                # a model that nests category → plan names the node after the plan: show both
                name = (
                    q.get("name")
                    if norm(q.get("name")) == norm(n.get("name"))
                    else " › ".join(path[-2:])
                )
                vals[k] = f"{name} · {show(q.get('credits'))}"
            label = f"{n.get('number', '')} {n.get('name', '')}".strip()
            what = "ชื่อหมวด/กลุ่มวิชา และหน่วยกิต (รูปแบบ ชื่อ · หน่วยกิต)"
            add(book, "โครงสร้างหลักสูตร", label, what, page_of(n.get("meta")), vals)
        # ---- courses: whole-book count + evenly spaced sample + every flagged course ----
        cr = {k: load(p, "courses").get("courses", []) for k, p in legs_.items()}
        cidx = {k: {norm(c.get("code_th")): c for c in v} for k, v in cr.items()}
        scope = (
            ""
            if kind == "bachelor"
            else "ระดับแบบจำลองอ่านเฉพาะย่อหน้า รายวิชาปริญญาโท/เอกอยู่ในตาราง จึงไม่นำมาคิดคะแนนระดับแบบจำลอง"
        )
        add(book, "รายวิชา", "จำนวนรายวิชาทั้งหมดในเล่ม",
            "นับรหัสวิชาทุกตัวในหมวด 4 ข้อ 3 (ค้นด้วย Ctrl/Cmd+F ทีละกลุ่ม) · ใช้ตรวจรายวิชาตกหล่นหรือแต่งเพิ่ม", "",
            {k: str(len(v)) for k, v in cr.items()}, scope)  # fmt: skip
        sys_courses = cr["sys"]
        n_pick = 8 if kind == "bachelor" else 5
        step = max(1, len(sys_courses) // n_pick)
        picked = sys_courses[::step][:n_pick]
        flagged = [c for c in sys_courses if (c.get("meta") or {}).get("note")]
        seen = set()
        for c in picked + flagged:
            key = norm(c.get("code_th"))
            if key in seen:
                continue
            seen.add(key)
            why = (
                "วิชามีธงแจ้งเตือน (ค่าระหว่างระบบกับแบบจำลองหรือในเล่มไม่ตรงกัน)"
                if c in flagged
                else f"สุ่มทุก {step} วิชา"
            )
            for field, label in (
                ("name_th", "ชื่อวิชาภาษาไทย"),
                ("credit_text", "หน่วยกิต x(a-b-c) ตรงทั้ง 4 ตัว"),
            ):
                vals = {
                    k: (show(q.get(field)) if (q := cidx[k].get(key)) else MISSING) for k in legs_
                }
                add(book, "รายวิชา", c.get("code_th"), label, page_of(c.get("meta")), vals,
                    "; ".join(x for x in (why, scope) if x))  # fmt: skip
    return rows


EXAMPLE = {
    "TC_ID": "EX-00", "เล่ม": "(ตัวอย่างวิธีกรอก)", "ส่วน": "ข้อมูลหลัก", "รายการ": "total_credits",
    "สิ่งที่ต้องตรวจ": "หน่วยกิตรวมตลอดหลักสูตร (ตัวเลข)", "หน้าโดยประมาณ": "5",
    "ค่าในเล่มจริง (กรอกก่อนดูคอลัมน์ถัดไป)": "127",
    "ระบบจริง: ค่า": "127", "ระบบจริง: ผล": "ตรง",
    "Local LLM ล้วน: ค่า": EMPTY, "Local LLM ล้วน: ผล": "ไม่ตรง",
    "Local LLM (ปรับปรุง) ล้วน: ค่า": "127", "Local LLM (ปรับปรุง) ล้วน: ผล": "ตรง",
    "Gemini ล้วน: ค่า": "127", "Gemini ล้วน: ผล": "ตรง",
    "ผู้ตรวจ": "สมชาย ใจดี", "วันที่ตรวจ": "2026-10-26",
    "หมายเหตุ": "ผล = ตรง / ไม่ตรง / ก้ำกึ่ง ตามกฎข้อ 8.3 ของ test-manual_ocl.md · "
    "(ว่าง) = แบบจำลองตอบว่าง · (ไม่พบ) = ไม่มีรายการนี้ในผลของชุดนั้น",
}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", default=str(ROOT / "docs/testing/accuracy_test_script.csv"))
    out = Path(ap.parse_args().out)
    rows = build()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerow({c: EXAMPLE.get(c, "") for c in COLS})
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    print(f"{out}: {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
