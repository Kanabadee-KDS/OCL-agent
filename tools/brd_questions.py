#!/usr/bin/env python3
"""Questions for the customer meeting, collected from the BRD instead of copied by hand.

Writes docs/brd/98-customer-questions.md from three kinds of open item:
  docs/brd/99-open-questions.md  rows A1..A10, B1..B8, C1..C13, D1 (rows marked "ตอบแล้ว" skipped)
  docs/brd/0*.md, 90-*.md        assumption markers ([สมมติ ...], "— ถาม", [ต้องขอ ...]) under a
                                 user story or in a rule row
  docs/brd/06-nfr.md             NFR rows whose criterion is still [เสนอ]
Every item must be classified in TRIAGE (release it blocks, default if unanswered), or merged
into a 99 row that asks the same thing; the script stops on an item it does not know, so a new
assumption in the BRD cannot miss the meeting.

  uv run python tools/brd_questions.py           # rewrite docs/brd/98-customer-questions.md
  uv run python tools/brd_questions.py --check   # exit 1 if the file is stale or an item is new
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRD = ROOT / "docs/brd"
OUT = BRD / "98-customer-questions.md"
STAMP = "สร้างโดย `tools/brd_questions.py`"

GATES = {
    "R1": "ต้องตอบก่อนทำ R1 ต่อ (คู่มือหลักสูตร หมวด 0–5 · นำเข้า · สิทธิ์ · SSO)",
    "R1-รับงาน": "เกณฑ์รับงาน R1 (requirement ที่ไม่ใช่ฟังก์ชัน)",
    "R2": "ตอบก่อนเริ่ม R2 (สมอ.08 · บริหารรายวิชา · บุคคลภายนอก · M2)",
    "R3": "ตอบก่อนเริ่ม R3 (M3 Skill Transcript)",
    "R4": "ตอบก่อนเริ่ม R4 (M4 ประเมินหลักสูตร · M5 รายงาน)",
    "ภายใน": "คำถามภายในคณะผู้พัฒนา",
}

# key -> (gate, default if the customer does not answer[, question]) for items that are their own
# question (assumptions in stories need the question written out), or "=<99 id>" for an
# assumption the 99 list already asks.
TRIAGE: dict[str, tuple[str, ...] | str] = {
    # 99 A: documents and access
    "A1": ("R1", "ใช้ขอบเขตตาม mock และ BRD v0.2 ต่อ"),
    "A2": ("R1", "ใช้ชื่อฟิลด์ที่ถอดจาก mock ต่อ และปรับเมื่อได้สเปก"),
    "A3": ("R1", "เลื่อน US-M1-13 จับคู่ HURIS ไป R2 และใช้ข้อมูลจำลอง"),
    "A4": ("R2", "ใช้ข้อมูลจำลองของ SUPREME"),
    "A5": ("R1", "ใช้บัวศรีไอดี + รหัสผ่านในระบบต่อ ไม่เปิด Google"),
    "A6": ("R1", "ทดสอบ OCR ด้วยภาพที่สร้างจาก PDF ดิจิทัลต่อ"),
    "A7": ("R3", "เริ่ม M3 ด้วยฐานข้อมูล Skill ตัวอย่าง"),
    "A8": ("R2", "ทำ Preview สมอ.08 ตามช่องใน mock"),
    "A9": ("R1", "เข้าผ่าน Tailscale ด้วย IP ต่อ ไม่เปิด Google SSO"),
    "A10": ("R1", "เก็บรหัสผ่านในระบบนี้ต่อ (scrypt)"),
    # 99 B: assumptions behind the BRD (the "ถ้าไม่ใช่" column says what changes)
    "B1": ("R1", "ถือว่าอยู่ในขอบเขต"),
    "B2": ("R2", "ฐานข้อมูลรายวิชากลางอยู่ในระบบนี้"),
    "B3": ("R1", "กำหนดสิทธิ์ curator อัตโนมัติจากรายชื่ออาจารย์"),
    "B4": ("R1", "ตรี 5 คน · โท/เอก 3 คน"),
    "B5": ("R1", "เข้าผ่าน Tailscale เท่านั้น"),
    "B6": ("R4", "รหัสยืนยันทางอีเมล"),
    "B7": ("R1", "เก็บหมวด 5–8 เป็น Markdown ไม่ทำเป็นฟิลด์"),
    "B8": ("R1", "รองรับเฉพาะโครงหมวดที่ 1–8 แบบ มศว"),
    # 99 C: per screen
    "C1": ("R1", "แสดง 3 มุมมองตามคำบรรยายใน mock (US-M1-02)"),
    "C2": ("R2", "ทำเฉพาะกรณีอาจารย์ตาม mock"),
    "C3": ("R2", "ใช้ฟิลด์ที่เห็นใน mock หน้าบริหารรายวิชา"),
    "C4": ("R1", "ใช้เกณฑ์ อว. 2565 ที่ validator ใช้อยู่ · นับความซ้ำซ้อนข้ามคณะ"),
    "C5": ("R1", "ผู้ใช้เลือกเองต่องาน ทุกเล่มส่งขึ้น cloud ได้"),
    "C6": ("R1", "เก็บค่าที่ผู้ใช้แก้แล้วไว้ สกัดใหม่เฉพาะส่วนที่ยังไม่แก้"),
    "C7": ("R1", "ภาษาไทยอย่างเดียว"),
    "C8": ("R3", "PDF ลงนามดิจิทัล"),
    "C9": ("R1", "ไม่นับ CLO ในหน้าสรุปการนำเข้า"),
    "C10": ("R1", "คงหน้าประวัติการนำเข้าทั้งหมดไว้"),
    "C11": ("R2", "ใช้ 70% และให้ผู้ดูแลแก้ได้"),
    "C12": ("R4", "10 นาที · 5 ครั้งต่อชั่วโมง"),
    "C13": ("R2", "ใช้ขั้นตอนฉบับเดิมจนจบ"),
    "D1": ("ภายใน", "ส่งภายใน ศ. 31 ต.ค. 2569"),
    # assumptions written into user stories and rules
    "00-overview.md:ฐานข้อมูลรายวิชากลาง (CUR23)": "=B2",
    "US-U-02": "=C12",
    "US-U-05": "=C13",
    "US-M1-02": "=C1",
    "US-M1-06": "=B3",
    "US-M1-10": "=C2",
    "US-M1-18": "=C3",
    "90-ai-import-data-dictionary.md:`teacher_count`": "=B4",
    "90-ai-import-data-dictionary.md:`teachers`": "=C4",
    "02-m2-learning-plan.md:BR-M2-04": "=C11",
    "US-M2-02": (
        "R2",
        "ส่วนกลางขยายเวลาการบันทึกรายหน่วยงานได้",
        "เมื่อหมดช่วงเวลาบันทึกแผน/รายงานผลแล้ว ส่วนกลางขยายเวลาให้บางหน่วยงานได้หรือไม่",
    ),
    "US-M2-03": (
        "R2",
        "% ความคืบหน้า = (ส่งตรวจสอบ + เผยแพร่) ÷ รายวิชาที่เปิดสอน",
        "ภาพรวมการบันทึกแผน: % ความคืบหน้านับจากสถานะใด (บันทึกแล้ว · ส่งตรวจสอบ · เผยแพร่)",
    ),
    "US-M2-04": (
        "R2",
        "ใช้หัวข้อของ มคอ.3 เดิมเป็นฟิลด์หมวด 2–6",
        "แผนการจัดการเรียนรู้หมวด 2–6 มีฟิลด์อะไร (mock แสดงเฉพาะหมวด 1) · ใช้แบบ มคอ.3 เดิมได้หรือไม่",
    ),
    "US-M2-05": (
        "R2",
        "ยกเลิกเผยแพร่แล้วกลับเป็นสถานะส่งตรวจสอบ",
        "ยกเลิกเผยแพร่แผนแล้ว เอกสารกลับเป็นสถานะใด และต้องรับรองใหม่หรือไม่",
    ),
    "US-M2-06": (
        "R2",
        "ใช้หัวข้อของ มคอ.5 เดิม · ส่งรายงานได้หลังวันสุดท้ายของภาค",
        "รายงานผลการจัดการเรียนรู้หมวด 2–4 มีฟิลด์อะไร (ใช้แบบ มคอ.5 เดิมได้หรือไม่) และส่งได้ตั้งแต่เมื่อใด",
    ),
    "02-m2-learning-plan.md:BR-M2-03": (
        "R2",
        "ดึง PLO จากคู่มือที่ตรวจสอบสำเร็จแล้วเท่านั้น",
        "แผนการจัดการเรียนรู้ดึง PLO จากคู่มือหลักสูตรที่ตรวจสอบสำเร็จแล้วเท่านั้น หรือใช้ฉบับร่างได้",
    ),
    "US-M3-08": (
        "R3",
        "ค่าเฉลี่ย Ethics ≥ 2.50 = S",
        "Skill Transcript แสดง Ethics เป็น S/U แต่ Portfolio แสดงคะแนน · ใช้เกณฑ์ใดแปลงคะแนนเป็น S/U",
    ),
    "US-M3-10": (
        "R3",
        "นับนิสิตที่ได้คะแนนครบทุก Skill ใน Mapping",
        'แดชบอร์ด Skill: "% ประเมินครบ" นับอย่างไร (ต่อนิสิต ต่อรายวิชา-กลุ่ม หรือต่อจุดประเมิน)',
    ),
    "03-m3-skill-transcript.md:BR-M3-05": (
        "R3",
        "เปิดสาธารณะเฉพาะหน้าตรวจสอบเอกสาร",
        "หน้าตรวจสอบ Skill Transcript ด้วย QR ต้องเปิดให้บุคคลภายนอกเข้าได้ "
        "ระบบจึงต้องมีส่วนที่เปิดสาธารณะ ยอมรับได้หรือไม่ (ต่างจาก B5)",
    ),
    "US-M4-01": ("R4", "เปิดใช้งานได้ครั้งละ 1 รอบ", "เปิดรอบการประเมินหลักสูตรพร้อมกันได้มากกว่า 1 รอบหรือไม่"),
    "US-M4-02": (
        "R4",
        "แก้เกณฑ์แล้วไม่กระทบรอบที่ล็อกแล้ว",
        "เมื่อแก้เกณฑ์หรือข้อคำถาม รอบที่กำลังเปิดอยู่ใช้ฉบับใหม่หรือฉบับเดิม",
    ),
    "US-M5-03": (
        "R4",
        "ส่งแจ้งเตือนซ้ำรายการเดิมได้วันละ 1 ครั้ง",
        "ปุ่มแจ้งเตือนในรายงานติดตาม ส่งซ้ำรายการเดิมได้บ่อยแค่ไหน",
    ),
    "US-M5-04": (
        "R4",
        "ใช้คอลัมน์ตาม mock · ข้อมูลจากคู่มือที่ตรวจสอบสำเร็จหรือเผยแพร่",
        "ขอแบบฟอร์ม Excel ของรายงาน R12 ตาม TOR 6.1 ทั้ง 12 รายงาน "
        "และยืนยันว่านับเฉพาะคู่มือที่ตรวจสอบสำเร็จหรือเผยแพร่แล้ว",
    ),
    # non-functional criteria proposed by the team
    "NFR-03": ("R1-รับงาน", "≥ 97% และเล่มดิจิทัลไม่มีค่าคลาดเคลื่อนที่ไม่ติดธง"),
    "NFR-04": ("R1-รับงาน", "≥ 10 / 11 ฟิลด์ · OCR ≥ 90%"),
    "NFR-05": ("R1-รับงาน", "ข้อมูลที่ผู้ใช้ได้รับเหมือนเดิมทุกครั้ง"),
    "NFR-07": ("R1-รับงาน", "≤ 5 นาทีต่อเล่มไม่เกิน 250 หน้า"),
    "NFR-08": ("R1-รับงาน", "≤ 3 วินาทีต่อหน้า"),
    "NFR-09": ("R1-รับงาน", "ประมวลผลทีละงาน งานที่เหลือต่อคิว"),
    "NFR-17": ("R1-รับงาน", "ส่งเฉพาะข้อความของส่วนที่แบบจำลองช่วย ไม่ส่งตารางอาจารย์"),
    "NFR-20": ("R1-รับงาน", "งานกลับมาทำต่อหรือขึ้นล้มเหลวพร้อมเหตุผล"),
    "NFR-21": ("R1-รับงาน", "สำรองทุกวัน เก็บ 14 วัน"),
    "NFR-23": ("R1-รับงาน", "Cloud ไม่เกิน 2 บาทต่อเล่ม"),
    "NFR-25": ("R1-รับงาน", "Chrome Edge Safari รุ่นปัจจุบัน · จอ 375 px ขึ้นไป"),
}

RE_ROW = re.compile(r"^\| ([ABCD]\d+) \| (.*) \|$")
RE_BULLET = re.compile(r"^- \*\*([A-D]\d+) ([^*]+)\*\*:?\s*(.*)$")
RE_US = re.compile(r"^- \*\*(US-[A-Z][A-Z0-9]*-\d+)")
RE_MARK = re.compile(r"\[สมมติ|— ถาม|\[ถาม|\[ต้องขอ|ยังไม่เห็น")
RE_NFR = re.compile(r"^\| (NFR-\d+) \| ([^|]+) \| ([^|]+) \|")


@dataclass
class Item:
    key: str
    source: str
    text: str
    gate: str = ""
    default: str = ""
    also: str = ""  # keys merged into this question


def clean(s: str) -> str:
    s = re.sub(r"\*\*|`", "", s)
    return re.sub(r"\s+", " ", s).strip()


def from_open_questions(path: Path) -> list[Item]:
    out = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        m = RE_ROW.match(line) or RE_BULLET.match(line)
        if not m or "ตอบแล้ว" in line:
            continue
        key = m.group(1)
        cells = [c.strip() for c in m.group(2).split(" | ")] if RE_ROW.match(line) else []
        if RE_ROW.match(line):
            # A: รายการ | ใช้ทำอะไร | สถานะ · B: ข้อสมมติ | ถ้าไม่ใช่ · C: หน้า | คำถาม (| ค่าเริ่มต้น)
            if key[0] == "A":
                text = f"ขอ: {cells[0]} · ใช้เพื่อ {cells[1]}"
            elif key[0] == "B":
                text = f"ยืนยันว่า: {cells[0]} · ถ้าไม่ใช่: {cells[1]}"
            elif key[0] == "C":
                text = f"[{cells[0]}] {cells[1]}"
            else:
                text = cells[0]
        else:
            text = f"{m.group(2)}: {m.group(3)}"
        out.append(Item(key, "99-open-questions.md", clean(text)))
    return out


def from_markers(files: list[Path]) -> list[Item]:
    out: dict[str, Item] = {}
    for f in files:
        story = None
        for line in f.read_text(encoding="utf-8").split("\n"):
            m = RE_US.match(line)
            if m:
                story = m.group(1)
            elif not line.startswith("  "):
                story = None
            if not RE_MARK.search(line):
                continue
            if story:
                key = story
            elif line.startswith("|"):
                key = f"{f.name}:{line.split('|')[1].strip()}"
            else:
                tick = re.search(r"`([^`]+)`", line)
                key = f"{f.name}:`{tick.group(1)}`" if tick else f"{f.name}:{line[:30]}"
            marks = re.findall(r"`?\[(?:สมมติ|ถาม|ต้องขอ)[^\]]*\]`?|\[[^\]]*ยังไม่เห็น[^\]]*\]", line)
            note = clean(" · ".join(marks)) or clean(line)[:120]
            if key in out:
                out[key].text += " · " + note
            else:
                out[key] = Item(key, f.name, note)
    return list(out.values())


def from_nfr(path: Path) -> list[Item]:
    out = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        m = RE_NFR.match(line)
        if m and "[เสนอ]" in line:
            crit = re.sub(r"\*\*\[(?:เสนอ|ยืนยันแล้ว)\]\*\*", "", m.group(3))
            out.append(Item(m.group(1), path.name, clean(f"{m.group(2)} · เกณฑ์ที่เสนอ: {crit}")))
    return out


def order(i: Item) -> tuple:
    m = re.fullmatch(r"([A-D])(\d+)", i.key)
    return (0, m.group(1), int(m.group(2)), "") if m else (1, "", 0, i.key)


def collect() -> list[Item]:
    files = sorted(BRD.glob("0*.md")) + sorted(BRD.glob("90-*.md"))
    items = (
        from_open_questions(BRD / "99-open-questions.md")
        + from_markers([f for f in files if f.name != "06-nfr.md"])
        + from_nfr(BRD / "06-nfr.md")
    )
    unknown = sorted(i.key for i in items if i.key not in TRIAGE)
    if unknown:
        sys.exit(f"new open items, add them to TRIAGE in tools/brd_questions.py: {unknown}")
    stale = sorted(set(TRIAGE) - {i.key for i in items})
    if stale:
        sys.exit(f"TRIAGE lists items no longer open in the BRD (remove them): {stale}")
    by_key = {i.key: i for i in items}
    kept = []
    for i in items:
        t = TRIAGE[i.key]
        if isinstance(t, str):
            target = by_key[t[1:]]
            target.also = f"{target.also} · {i.key}" if target.also else i.key
            continue
        i.gate, i.default = t[0], t[1]
        if len(t) > 2:
            i.text = t[2]
        kept.append(i)
    return sorted(kept, key=order)


def build() -> str:
    items = collect()
    by_gate: dict[str, list[Item]] = {g: [i for i in items if i.gate == g] for g in GATES}
    today = dt.date.today().isoformat()
    md: list[str] = []
    w = md.append
    w("# 98 คำถามและวาระประชุมกับลูกค้า")
    w("")
    w(
        f"> {STAMP} จาก `99-open-questions.md` · ข้อสมมติใน user story และกฎ · เกณฑ์ที่เสนอใน "
        f"`06-nfr.md` · {today} · ห้ามแก้ด้วยมือ ให้แก้ต้นทางหรือ `TRIAGE` แล้วรันใหม่"
    )
    w("")
    w("## 1. วาระประชุม (90 นาที)")
    w("")
    w("| เวลา | หัวข้อ | คำถาม |")
    w("|---|---|---|")
    w("| 10 นาที | สถานะ BRD v0.2 และงานที่สร้างแล้ว (`91-traceability.md`) | – |")
    w(f"| 35 นาที | เรื่องที่ต้องตอบก่อนทำ R1 ต่อ (ข้อ 2) | {len(by_gate['R1'])} ข้อ |")
    w(f"| 25 นาที | เกณฑ์รับงาน R1 (ข้อ 3) | {len(by_gate['R1-รับงาน'])} ข้อ |")
    later = sum(len(by_gate[g]) for g in ("R2", "R3", "R4"))
    w(f"| 10 นาที | แนะนำแบบสอบถามสำหรับ R2–R4 ให้ตอบภายหลัง (ข้อ 4) | {later} ข้อ |")
    w("| 10 นาที | สรุปคำตอบ ผู้รับผิดชอบ และวันที่ต้องได้คำตอบ | – |")
    w("")
    w(
        "ข้อที่ไม่ได้คำตอบภายในวันที่ตกลง คณะผู้พัฒนาจะใช้ **ค่าเริ่มต้น** ในตาราง "
        "และบันทึกไว้ใน `99-open-questions.md`"
    )
    w("")
    sections = [
        ("2", "R1", "ต้องตอบก่อนทำ R1 ต่อ"),
        ("3", "R1-รับงาน", "เกณฑ์รับงาน R1"),
        ("4.1", "R2", "R2 · สมอ.08 · บริหารรายวิชา · บุคคลภายนอก · M2"),
        ("4.2", "R3", "R3 · M3 Skill Transcript"),
        ("4.3", "R4", "R4 · M4 ประเมินหลักสูตร · M5 รายงาน"),
    ]
    for num, gate, title in sections:
        if num == "4.1":
            w("## 4. แบบสอบถามสำหรับ R2–R4 (ตอบภายหลังได้)")
            w("")
        w(f"{'###' if '.' in num else '##'} {num}. {title} ({len(by_gate[gate])} ข้อ)")
        w("")
        w("| # | คำถาม | ค่าเริ่มต้นถ้าไม่ตอบ | ที่มา |")
        w("|---|---|---|---|")
        for i in by_gate[gate]:
            src = i.source + (f" · เกี่ยวกับ {i.also}" if i.also else "")
            key = i.key.split(":", 1)[-1].strip("`")
            w(f"| {key} | {i.text} | {i.default} | {src} |")
        w("")
    w("## 5. คำถามภายใน")
    w("")
    for i in by_gate["ภายใน"]:
        w(f"- **{i.key}** {i.text} · ค่าเริ่มต้น: {i.default}")
    w("")
    w(f"รวม {len(items)} คำถาม (รวมข้อสมมติที่ซ้ำกับคำถามใน 99 ไว้ในข้อเดียวกันแล้ว)")
    w("")
    return "\n".join(md)


def strip_stamp(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if STAMP not in line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = ap.parse_args()
    text = build()
    if args.check:
        old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if strip_stamp(old) != strip_stamp(text):
            print(f"stale: {OUT.relative_to(ROOT)} · run tools/brd_questions.py")
            return 1
        print("ok")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
