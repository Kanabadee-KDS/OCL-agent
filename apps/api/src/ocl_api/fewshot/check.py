"""Check the few-shot files before (and after) a reviewer approves examples.

    uv run ocl fewshot check            # all parts
    uv run ocl fewshot check plo        # one part

ERROR = the file cannot be used as is (broken JSON shape, a value the model would learn that
is not in the input, an approved example without a reviewer). WARN = worth a look.
Exit code 1 when any ERROR is found.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ocl_api.extract.info import LLM_FIELDS
from ocl_api.fewshot import DIR, STATUSES

PARTS = ("info", "plo", "courses")
MAX_INPUT = 4000
WARN_INPUT = 3000
RE_PLO_CODE = re.compile(r"^(?:Sub-?)?PLO\d+(?:\.\d+)*$", re.I)
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def _sq(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or "")).translate(_THAI_DIGITS)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    oks: list[str] = field(default_factory=list)

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"ERROR {where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"WARN  {where}: {msg}")


def _literal(rep: Report, where: str, label: str, value: Any, inp: str) -> None:
    """The model copies what it sees: every output value must be readable in the input."""
    if value in (None, ""):
        return
    if isinstance(value, int):
        if not re.search(rf"(?<!\d){value}(?!\d)", inp.translate(_THAI_DIGITS)):
            rep.err(where, f"{label} = {value} ไม่พบตัวเลขนี้ใน input")
    elif _sq(value) not in _sq(inp):
        rep.err(where, f"{label} = '{str(value)[:60]}' ไม่พบตามตัวอักษรใน input")


def _check_output(rep: Report, part: str, where: str, out: Any, inp: str) -> None:
    if not isinstance(out, dict):
        rep.err(where, "output ต้องเป็น object")
        return
    if part == "info":
        for k in LLM_FIELDS:
            if k not in out:
                rep.err(where, f"output ขาดฟิลด์ {k} (ใส่ null ถ้าเล่มไม่มี)")
                continue
            v = out[k]
            numeric = LLM_FIELDS.index(k) >= 7
            if v is not None and numeric and not isinstance(v, int):
                rep.err(where, f"{k} ต้องเป็นตัวเลขจำนวนเต็มหรือ null (ได้ {v!r})")
            if v is not None and not numeric and not isinstance(v, str):
                rep.err(where, f"{k} ต้องเป็นข้อความหรือ null (ได้ {v!r})")
            _literal(rep, where, k, v, inp)
    elif part == "plo":
        plos = out.get("plos")
        if not isinstance(plos, list) or not plos:
            rep.err(where, "output.plos ต้องเป็นรายการที่ไม่ว่าง")
            return
        plans = {p.get("plan") for p in plos}
        if None in plans and len(plans) > 1:
            rep.warn(where, "บาง PLO มี plan บางข้อไม่มี (ปกติควรมีทุกข้อหรือไม่มีเลย)")
        seen = set()
        for i, p in enumerate(plos, 1):
            code = p.get("code", "")
            if not RE_PLO_CODE.match(str(code)):
                rep.err(
                    where,
                    f"PLO ลำดับ {i}: code '{code}' ต้องเป็นรหัสล้วน เช่น PLO1 (ชื่อแผนให้ใส่ในช่อง plan)",
                )
            key = (p.get("plan"), code)
            if key in seen:
                rep.err(where, f"PLO ซ้ำ: {code} ({p.get('plan')})")
            seen.add(key)
            if not p.get("text"):
                rep.err(where, f"{code}: text ว่าง")
            _literal(rep, where, f"{code} text", p.get("text"), inp)
            if p.get("plan"):
                _literal(rep, where, f"{code} plan", p.get("plan"), inp)
            for s_ in p.get("sub_plos") or []:
                _literal(rep, where, f"{s_.get('code')} text", s_.get("text"), inp)
    elif part == "courses":
        courses = out.get("courses")
        if not isinstance(courses, list) or not courses:
            rep.err(where, "output.courses ต้องเป็นรายการที่ไม่ว่าง")
            return
        codes = [c.get("code_th") for c in courses]
        if len(codes) != len(set(codes)):
            rep.err(where, "มีรหัสวิชาซ้ำใน output")
        for c in courses:
            code = c.get("code_th") or "?"
            if not c.get("code_th") or not c.get("name_th"):
                rep.err(where, f"{code}: ต้องมี code_th และ name_th")
            for k in ("code_th", "name_th", "code_en", "name_en", "credit_text"):
                _literal(rep, where, f"{code} {k}", c.get(k), inp)
        # every Thai course code in the input should be in the output (the lesson is "don't skip")
        found = set(re.findall(r"(?<![ก-๙])([ก-ฮ]{2,4}\s?\d{3})(?=\s)", inp))
        missing = sorted(
            {re.sub(r"\s", "", f) for f in found} - {re.sub(r"\s", "", x or "") for x in codes}
        )
        if missing:
            rep.warn(
                where,
                f"input มีรหัสที่ output ไม่ได้ตอบ: {', '.join(missing[:8])} (ถ้าเป็นรหัสวิชาจริงต้องเพิ่ม)",
            )


def check_part(part: str, rep: Report, directory: Path = DIR) -> None:
    path = directory / f"{part}.json"
    if not path.exists():
        rep.err(part, f"ไม่พบไฟล์ {path.name}")
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        rep.err(part, f"{path.name} ไม่ใช่ JSON ที่ถูกต้อง: บรรทัด {e.lineno} คอลัมน์ {e.colno} ({e.msg})")
        return
    if data.get("part") != part:
        rep.err(part, f"ช่อง part ต้องเป็น '{part}'")
    ids = [ex.get("id") for ex in data.get("examples", [])]
    for dup in {i for i in ids if ids.count(i) > 1}:
        rep.err(part, f"id ซ้ำ: {dup}")
    approved = 0
    for ex in data.get("examples", []):
        where = f"{part}/{ex.get('id', '?')}"
        n_err = len(rep.errors)
        for k in (
            "id",
            "status",
            "source",
            "teaches",
            "input",
            "output",
            "reviewed_by",
            "reviewed_at",
            "review_notes",
        ):
            if k not in ex:
                rep.err(where, f"ขาดช่อง {k}")
        status = ex.get("status")
        if status not in STATUSES:
            rep.err(where, f"status ต้องเป็น {' / '.join(STATUSES)} (ได้ '{status}')")
        if not (ex.get("source") or {}).get("book"):
            rep.err(where, "source.book ว่าง (ใช้กันไม่ให้ส่งตัวอย่างของเล่มเดียวกัน)")
        inp = ex.get("input") or ""
        if len(inp) > MAX_INPUT:
            rep.err(where, f"input ยาว {len(inp)} ตัวอักษร เกิน {MAX_INPUT}")
        elif len(inp) > WARN_INPUT:
            rep.warn(where, f"input ยาว {len(inp)} ตัวอักษร (แนะนำไม่เกิน {WARN_INPUT})")
        if status == "approved":
            approved += 1
            if not ex.get("reviewed_by"):
                rep.err(where, "approved แต่ไม่มี reviewed_by")
            try:
                date.fromisoformat(str(ex.get("reviewed_at")))
            except ValueError:
                rep.err(where, "approved แต่ reviewed_at ไม่ใช่วันที่รูปแบบ ปปปป-ดด-วว (ค.ศ.)")
        if status == "rejected" and not ex.get("review_notes"):
            rep.warn(where, "rejected ควรเขียนเหตุผลใน review_notes")
        _check_output(rep, part, where, ex.get("output"), inp)
        if len(rep.errors) == n_err:
            rep.oks.append(f"OK    {where} ({status})")
    if approved == 0:
        rep.warn(part, "ยังไม่มีตัวอย่างที่ approved (FEWSHOT=approved จะไม่ส่งตัวอย่างของส่วนนี้)")


def run(parts: list[str] | None = None, directory: Path = DIR) -> Report:
    rep = Report()
    for part in parts or list(PARTS):
        check_part(part, rep, directory)
    return rep


def main(parts: list[str] | None = None) -> int:
    rep = run(parts)
    for line in rep.oks + rep.warnings + rep.errors:
        print(line)
    print(f"\nสรุป: OK {len(rep.oks)} · WARN {len(rep.warnings)} · ERROR {len(rep.errors)}")
    return 1 if rep.errors else 0
