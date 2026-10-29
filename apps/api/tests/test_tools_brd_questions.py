"""tools/brd_questions.py: every open item in the BRD reaches the customer question list."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[3] / "tools" / "brd_questions.py"
spec = importlib.util.spec_from_file_location("brd_questions", TOOL)
q = importlib.util.module_from_spec(spec)
sys.modules["brd_questions"] = q  # @dataclass looks its module up while the file runs
spec.loader.exec_module(q)

OPEN = """# 99
| # | รายการ | ใช้ทำอะไร | สถานะ |
|---|---|---|---|
| A1 | TOR ฉบับจริง | ยืนยันขอบเขต | ยังไม่มี |
| # | ข้อสมมติ | ถ้าไม่ใช่ |
|---|---|---|
| B5 | เข้าผ่าน Tailscale | ต้องเพิ่ม proxy |
| # | คำถาม |
|---|---|
| D2 | GitHub แบบไหน → **ตอบแล้ว 21 ต.ค.: C** |
- **A9 ชื่อโดเมน**: Google OAuth ไม่รับ IP
"""

STORIES = """# 02
- **US-M2-05** ในฐานะประธาน ฉันต้องการรับรองแผน
  - AC: ยกเลิกเผยแพร่แล้วกลับเป็นส่งตรวจสอบ `[สมมติ]`
- **US-M2-06** ไม่มีข้อสมมติ
| BR-M2-03 | PLO จากคู่มือที่ตรวจสอบสำเร็จ `[สมมติ]` |
"""


def test_open_questions_skip_answered_rows(tmp_path):
    f = tmp_path / "99-open-questions.md"
    f.write_text(OPEN, encoding="utf-8")
    items = {i.key: i.text for i in q.from_open_questions(f)}
    assert set(items) == {"A1", "B5", "A9"}  # D2 is answered
    assert items["B5"] == "ยืนยันว่า: เข้าผ่าน Tailscale · ถ้าไม่ใช่: ต้องเพิ่ม proxy"


def test_markers_belong_to_their_story_or_rule(tmp_path):
    f = tmp_path / "02-m2.md"
    f.write_text(STORIES, encoding="utf-8")
    keys = {i.key for i in q.from_markers([f])}
    assert keys == {"US-M2-05", "02-m2.md:BR-M2-03"}


def test_question_list_is_current_and_complete():
    # stops on an assumption that TRIAGE does not classify, then compares the file
    r = subprocess.run([sys.executable, str(TOOL), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


INTERNAL = [
    "Gemma",
    "HRIS",
    "parser",
    "ด้วยกฎ",
    "POC",
    "scrypt",
    "validator",
    "TRIAGE",
    ".md",
    "tools/",
    "คำถามภายใน",
    "magic link",
    "curator",
    "release plan",
]


def test_customer_file_has_no_internal_words():
    text = q.OUT.read_text(encoding="utf-8")
    body = "\n".join(line for line in text.split("\n") if not line.startswith("<!--"))
    found = [w for w in INTERNAL if w in body]
    assert not found, (
        f"98-customer-questions.md goes to the customer, reword at the source: {found}"
    )
