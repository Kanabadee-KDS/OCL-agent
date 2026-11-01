#!/usr/bin/env python3
"""OCR-3a: write docs/eval/ocr-typhoon.md from the measurements in docs/eval/ocr-typhoon/.

  ocr0-results.json  tools/ocr_bench.py on the server (OCR-0): Tesseract vs Typhoon per page
  runs.json          Typhoon runs on the server and production after OCR-0 (OCR-1, OCR-2)
  errors.json        the misreads found against the page images and which check catches each

The report is never edited by hand: change the data or this script, then run it.
  uv run python tools/ocr_report.py          # write
  uv run python tools/ocr_report.py --check  # exit 1 when the report is stale (CI, tests)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/eval/ocr-typhoon"
OUT = ROOT / "docs/eval/ocr-typhoon.md"
CHECKS = {
    "①": "Tesseract ไม่เห็นคำนั้นในหน้าเดียวกัน (ระบายสี)",
    "②": "OCR สองเครื่องอ่านทั้งหน้าตรงกันต่ำกว่า 80% (หน้าอ่านยาก)",
    "③": "ชื่ออาจารย์คนเดียวกันสะกดต่างกันในเล่ม หรือต่างจาก HURIS 1–2 ตัวอักษร",
}


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def pct(v: float | None, digits: int = 1) -> str:
    return "–" if v is None else f"{v * 100:.{digits}f}%"


def num(v) -> str:
    return "–" if v is None else str(v)


def summary_numbers() -> dict:
    """The headline figures other documents quote (tested against 06-nfr.md)."""
    s = load("ocr0-results.json")["summary"]
    runs = load("runs.json")["runs"]
    prod = [r for r in runs if r["flags"] is not None]
    return {
        "tesseract_cer": pct(s["tesseract"]["cer"]),
        "typhoon_cer": pct(s["typhoon"]["cer"]),
        "typhoon_same": pct(1 - s["typhoon"]["cer"]),
        "tesseract_s": f"{s['tesseract']['mean_s']:.1f}",
        "typhoon_s": f"{s['typhoon']['mean_s']:.1f}",
        "typhoon_max_s": f"{s['typhoon']['max_s']:.1f}",
        "book_s": f"{prod[-1]['seconds']:.0f}" if prod else "–",
    }


def render() -> str:
    r0 = load("ocr0-results.json")
    runs = load("runs.json")["runs"]
    errs = load("errors.json")
    s = r0["summary"]
    n = summary_numbers()
    pages = r0["pages"]
    scored = [p for p in pages if p.get("truth_chars")]
    out = [
        "# ผลวัด Typhoon OCR กับหน้าสแกน (OCR-0 ถึง OCR-2)",
        "",
        "> สร้างโดย `tools/ocr_report.py` จาก `docs/eval/ocr-typhoon/*.json` · ห้ามแก้ด้วยมือ"
        " ให้แก้ข้อมูลหรือสคริปต์แล้วรันใหม่ · ข้อมูลเป็นตัวเลขอย่างเดียว ไม่มีข้อความจากเล่ม",
        "",
        "## 1. สรุป",
        "",
        "| | Tesseract (เดิม) | Typhoon OCR (ใช้งานตั้งแต่ 31 ต.ค. 2569) |",
        "|---|---|---|",
        f"| อักขระผิด (CER) หน้า 1–{len(scored)} | {n['tesseract_cer']} | **{n['typhoon_cer']}** |",
        f"| ความเหมือน 3-gram (ไม่นับลำดับ) | {pct(s['tesseract']['f1'])} | **{pct(s['typhoon']['f1'])}** |",
        f"| เวลาเฉลี่ยต่อหน้า | {n['tesseract_s']} วินาที | {n['typhoon_s']} วินาที"
        f" (สูงสุด {n['typhoon_max_s']}) + ตรวจไขว้ด้วย Tesseract ราว 1 วินาที |",
        f"| ตารางในเล่มสแกน 14 หน้า | 0 | {runs[-1]['tables']} |",
        f"| อาจารย์ที่สกัดได้ (อ่านด้วยกฎ) | 0 | {runs[-1]['teachers']}"
        f" (ผู้รับผิดชอบ {runs[-1]['responsible']}) |",
        "",
        f"- เล่ม 14 หน้าบนระบบจริงใช้ {n['book_s']} วินาทีรวมการตรวจไขว้ ·"
        " เล่มสแกน 150 หน้าประมาณ 35–40 นาที (ประมาณจากเวลาต่อหน้า ยังไม่ได้วัดเล่มยาว)",
        "- Typhoon ยังอ่านผิดได้ และผิดแบบอ่านลื่นจนดูไม่ออก (ข้อ 4) ระบบจึงระบายสีจุดที่ต้องตรวจ"
        " และผลอ่านไม่เหมือนกันทุกครั้ง",
        "",
        "## 2. วิธีวัด",
        "",
        f"- เล่ม: `{r0['scan']}` (14 หน้า ภาพสแกน 200 dpi ไม่มีชั้นข้อความ)",
        f"- ข้อความจริง: ชั้นข้อความของ `{r0['truth']}` หน้าเดียวกัน ·"
        " หน้า 14 เป็นแผนภาพที่ฝังเป็นรูปในเล่มต้นฉบับ จึงไม่มีข้อความจริงและไม่นับคะแนน",
        f"- โมเดล: `{r0['model']}` บน Ollama ของ server (Local LLM) · Tesseract `tha+eng` 200 dpi"
        " (คำสั่งเดียวกับระบบ)",
        "- CER = จำนวนอักขระที่ต้องแก้ ÷ จำนวนอักขระจริง หลังตัดช่องว่าง แท็ก และจุดนำสารบัญออกทั้งสองฝั่ง"
        " · นับลำดับการอ่าน ตารางที่อ่านคนละลำดับจึงได้ CER สูงเกินจริง จึงรายงานความเหมือน 3-gram คู่กัน",
        f"- รันเมื่อ {r0['started']} ถึง {r0['finished']} ด้วย `tools/ocr_bench.py`",
        "",
        "## 3. รายหน้า (OCR-0)",
        "",
        "| หน้า | อักขระจริง | CER Tesseract | CER Typhoon | วินาที Tesseract | วินาที Typhoon |",
        "|---|---|---|---|---|---|",
    ]
    for p in pages:
        out.append(
            f"| {p['page']} | {num(p.get('truth_chars'))} | {pct(p.get('tesseract_cer'))} |"
            f" {pct(p.get('typhoon_cer'))} | {num(p.get('tesseract_s'))} | {num(p.get('typhoon_s'))} |"
        )
    out += [
        "",
        "## 4. ข้อผิดที่พบและวิธีที่ระบบจับ (OCR-2a)",
        "",
        *[f"- {k} {v}" for k, v in CHECKS.items()],
        "",
        "| หน้า | ในภาพ | Typhoon อ่านเป็น | ลักษณะ | พบในรอบ | จับได้ด้วย |",
        "|---|---|---|---|---|---|",
    ]
    for e in errs["errors"]:
        out.append(
            f"| {e['page']} | {e['on_page']} | {e['typhoon']} | {e['kind']} | {e['run']} |"
            f" {' '.join(e['caught_by'])} |"
        )
    f = errs["flags_replay"]
    caught = sum(1 for e in errs["errors"] if e["caught_by"])
    out += [
        "",
        f"- จับได้ {caught} จาก {len(errs['errors'])} จุด · ไม่มีวิธีใดวิธีเดียวจับได้ครบ",
        f"- จุดที่ระบายสีทั้งเล่ม {f['total']} จุด อยู่บนหน้าอ่านยาก {len(f['hard_pages'])} หน้า"
        f" ({', '.join(map(str, f['hard_pages']))}) {f['on_hard_pages']} จุด"
        f" และบนหน้าปกติ {f['normal_pages']} หน้า {f['on_normal_pages']} จุด ·"
        " หน้าสารบัญขึ้นอ่านยากเกินจริงเพราะ Tesseract อ่านสารบัญได้ไม่ดี",
        "",
        "## 5. รอบที่รันบน server และระบบจริง",
        "",
        "| รอบ | วันที่ | ที่ไหน | วินาที | ตาราง | หน้าที่ถอยไป Tesseract | อาจารย์ (รับผิดชอบ)"
        " | ชื่อที่อ่านผิด | จุดที่ต้องตรวจ | หน้าอ่านยาก |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in runs:
        out.append(
            f"| {r['id']} | {r['date']} | {r['where']} | {r['seconds']:.0f} | {r['tables']} |"
            f" {r['fallback_pages']} | {r['teachers']} ({r['responsible']}) |"
            f" {', '.join(r['misread_names']) or 'ไม่มี'} | {num(r['flags'])} |"
            f" {', '.join(map(str, r['hard_pages'])) if r['hard_pages'] else '–'} |"
        )
    out += [
        "",
        "## 6. ข้อจำกัดของผลวัด",
        "",
        "- เล่มเดียว 14 หน้า ภาพสะอาด · ยังไม่มีไฟล์สแกนจริงจากลูกค้า (เล่มที่สแกนจากกระดาษ เอียง มีเงา หรือมีลายมือ)",
        "- วัดตอนเครื่องไม่มีงานอื่นใช้ GPU · ถ้ามีงานสกัดด้วย Gemma พร้อมกันอาจช้ากว่านี้",
        "- โมเดลบน Ollama คือ `typhoon-ocr1.5-3b` (Qwen2.5-VL 3.8B Q4_K_M) ไม่ใช่รุ่น 2B ล่าสุดบน Hugging Face"
        " ซึ่งยังไม่มีบน Ollama",
        "- ข้อผิดในข้อ 4 รวบรวมจาก 3 รอบของเล่มเดียว · จุดที่ทั้งสองเครื่องอ่านผิดเหมือนกันระบบจับไม่ได้",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    text = render()
    if "--check" in argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print(f"stale: {OUT.relative_to(ROOT)} · run tools/ocr_report.py")
            return 1
        print("ok")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
