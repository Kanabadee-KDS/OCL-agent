"""Typhoon OCR on scanned pages (OCR-1): its Markdown becomes the same blocks the text-layer
reader makes, picture descriptions stay AI notes no extractor reads, a page it cannot read
falls back to Tesseract, and the request keeps the shared server's rules."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from ocl_api.config import Settings
from ocl_api.extract.base import blocks_text, paragraphs_text
from ocl_api.ingest.markdown import render_blocks
from ocl_api.ingest.model import Image, Paragraph, Table
from ocl_api.ingest.pdf_reader import PdfReader, find_tessdata
from ocl_api.ingest.typhoon import (
    AI_NOTE,
    HARD_PAGE,
    NUM_CTX,
    PROMPT_V15,
    TyphoonError,
    TyphoonOcr,
    agreement,
    cross_check,
    from_settings,
    markdown_blocks,
    parse_table,
    promote_items,
    unsupported,
)
from tests.test_ingest_pdf import build_scanned_pdf

# shaped like the server's output for scan page 5 and 14 (OCR-0, data/ocr0)
PAGE = """```markdown
หมวดที่ 1 ข้อมูลทั่วไป

1.  **รหัสและชื่อหลักสูตร**
    รหัสหลักสูตร 25290091100204
    5.1 **รูปแบบ**
        ☑ หลักสูตรปริญญาตรีทางวิชาการ

<figure>
ตราสัญลักษณ์ของมหาวิทยาลัยเป็นวงกลม
</figure>

<table><tr><td rowspan="2">Employers</td><td>BCG / Green Technology</td></tr><tr><td>Soft Skills</td></tr><tr><td colspan="2">รวม &amp; สรุป</td></tr></table>

*   เป้าหมายความยั่งยืน SDG 2, 3, 12

<page_number>1</page_number>
```"""


def test_markdown_becomes_blocks() -> None:
    blocks = markdown_blocks(PAGE, 5, "assets/page-005.png")
    paras = [b for b in blocks if isinstance(b, Paragraph)]
    assert [p.text for p in paras] == [
        "หมวดที่ 1 ข้อมูลทั่วไป",
        "1. รหัสและชื่อหลักสูตร",
        "รหัสหลักสูตร 25290091100204",
        "5.1 รูปแบบ",
        "☑ หลักสูตรปริญญาตรีทางวิชาการ",
        "เป้าหมายความยั่งยืน SDG 2, 3, 12",
    ], "markers gone, page number dropped"
    assert paras[0].level == 1, "a chapter starts a section as in the text-layer reader"
    assert paras[1].bold and paras[1].level == 2
    assert paras[-1].list_item and all(p.ocr and p.page == 5 for p in paras)
    table = next(b for b in blocks if isinstance(b, Table))
    assert table.ocr and table.rows == [
        ["Employers", "BCG / Green Technology"],
        ["", "Soft Skills"],
        ["รวม & สรุป", ""],
    ], "merged cells are left empty, entities decoded"
    note = next(b for b in blocks if isinstance(b, Image))
    assert note.ai_note == "ตราสัญลักษณ์ของมหาวิทยาลัยเป็นวงกลม" and note.alt == AI_NOTE
    # the note is shown to the reviewer but never reaches an extractor
    assert "ตราสัญลักษณ์" not in blocks_text(blocks) + paragraphs_text(blocks)
    assert f"> **{AI_NOTE}:** ตราสัญลักษณ์" in render_blocks(blocks)


def test_table_spans() -> None:
    t = "<table><tr><th>ก</th><th colspan='2'>ข</th></tr><tr><td>1<br/>2</td><td>3</td><td>4</td></tr></table>"
    assert parse_table(t) == [["ก", "ข", ""], ["1\n2", "3", "4"]]


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_request_keeps_the_shared_server_rules() -> None:
    seen = []

    def ok(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "ข้อความ"}, "done_reason": "stop"})

    t = TyphoonOcr("http://ollama:11434/", "scb10x/typhoon-ocr1.5-3b", client=_client(ok))
    assert t.read_png(b"png") == "ข้อความ"
    body = seen[0]
    assert body["keep_alive"] == "10m" and body["options"]["num_ctx"] == NUM_CTX
    assert body["options"]["temperature"] == 0.1 and body["messages"][0]["content"] == PROMPT_V15
    for reply in (
        httpx.Response(500, text="boom"),
        httpx.Response(200, json={"message": {"content": "x"}, "done_reason": "length"}),
        httpx.Response(200, json={"message": {"content": "  "}}),
        httpx.Response(200, json={"message": {"content": "วนซ้ำอยู่\n" * 20}}),
    ):
        bad = TyphoonOcr("http://o", "m", client=_client(lambda r, x=reply: x))
        with pytest.raises(TyphoonError):
            bad.read_png(b"png")


class _Fake:
    model = "fake-typhoon"

    def __init__(self, md: str | None):
        self.md = md

    def read_page(self, page) -> str:
        if self.md is None:
            raise TyphoonError("ConnectError: no route")
        return self.md


def test_scanned_page_read_by_typhoon(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    build_scanned_pdf(pdf)
    doc = PdfReader(pdf, tmp_path / "assets", typhoon=_Fake(PAGE)).read()
    assert doc.ocr_pages == [1] and any("Typhoon fake-typhoon" in n for n in doc.notes)
    kinds = [b.kind for b in doc.blocks]
    assert kinds[0] == "image" and "table" in kinds, "page image first, then the page read"
    assert any(isinstance(b, Paragraph) and b.text == "1. รหัสและชื่อหลักสูตร" for b in doc.blocks)


def test_a_page_typhoon_cannot_read_falls_back(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    build_scanned_pdf(pdf)
    doc = PdfReader(pdf, tmp_path / "assets", typhoon=_Fake(None)).read()
    assert any("Typhoon OCR failed (ConnectError" in n for n in doc.notes)
    assert not any("Typhoon fake-typhoon" in n for n in doc.notes)
    # Tesseract took the page (or the placeholder where its language data is missing)
    texts = [b.text for b in doc.blocks if isinstance(b, Paragraph)]
    assert texts and not any("รหัสและชื่อหลักสูตร" in t for t in texts)


def test_engine_comes_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    assert from_settings(Settings(_env_file=None)) is None, "Tesseract stays the default"
    monkeypatch.setenv("OCR_ENGINE", "typhoon")
    t = from_settings(Settings(_env_file=None))
    assert t is not None and t.model == "scb10x/typhoon-ocr1.5-3b"
    monkeypatch.setenv("OCR", "false")
    assert from_settings(Settings(_env_file=None)) is None
    monkeypatch.setenv("TYPHOON_MODEL", "gemma4:12b")
    with pytest.raises(ValueError, match="HRIS"):
        Settings(_env_file=None)


def test_item_headings_follow_the_chapter_not_a_list() -> None:
    """OCR-0 scan: Typhoon bolded items 1-8 (pages 5-6) but not 10-13 (pages 7-10), so the
    teacher table under item 11 was not found; a list "1. 2. 3." on a diagram page must stay
    a list."""

    def p(text: str, level: int = 0, page: int = 7) -> Paragraph:
        return Paragraph(text=text, level=level, bold=level == 2, page=page, ocr=True)

    blocks = [
        p("หมวดที่ 1 ข้อมูลทั่วไป", 1, 5),
        p("1. รหัสและชื่อหลักสูตร", 2, 5),
        p("8. สถานที่จัดการเรียนการสอน", 2, 6),
        p("10. อาชีพที่ประกอบได้หลังสำเร็จการศึกษา"),
        p("11. อาจารย์ผู้รับผิดชอบหลักสูตรและคุณสมบัติ", page=8),
        p("15. ข้ามไปไกลเกินไป ไม่ใช่หัวข้อ", page=8),
        p("หมวดที่ 2 ข้อมูลเฉพาะของหลักสูตร", 1, 11),
        p("1. ปรัชญา วัตถุประสงค์ และผลลัพธ์การเรียนรู้", page=11),
        p("1. เจ้าหน้าที่ฝ่ายผลิต", page=14),
        p("2. เจ้าหน้าที่ควบคุมคุณภาพ", page=14),
        p("3. นักวิจัยและพัฒนาผลิตภัณฑ์อาหาร", page=14),
        p("2. ความสำคัญของหลักสูตร", page=99),  # not a Typhoon page
    ]
    assert promote_items(blocks, {5, 6, 7, 8, 11, 14}) == 3
    assert [b.text[:3] for b in blocks if b.level == 2] == ["1. ", "8. ", "10.", "11.", "1. "]


def test_cross_check_flags_what_tesseract_did_not_see() -> None:
    """OCR-2a1 on the OCR-0 misreads: a changed letter in a name and made-up words are
    flagged; marks Tesseract drops anyway (and ำ split as ํ+า) are not."""
    tess = "ผศ.ดร.ศรวกรณ ดษฐอดมโพธ\nแผนแม่บท (เกษตรแปรรูปมูลค่าสูง) กระทรวงอุดมศึกษาฯ (อว.)\nกํากับ ดูแล"
    page = __import__("ocl_api.ingest.typhoon", fromlist=["skeleton"]).skeleton(tess)[0]
    assert unsupported("ผศ.ดร.ศรีวิภรณ์ ดิษฐอุดมโพธิ์", page) == ["วิภร"]
    assert "ณฑ์การ" in unsupported("(เกณฑ์การประมูลค่าสูง)", page)[0], "made-up words"
    assert unsupported("กระทรวงอุดมศึกษาฯ (วอ.)", page) == ["ฯ (วอ.)"]
    assert unsupported("กำกับ ดูแล", page) == [], "sara am and dropped marks are not errors"
    blocks = [Paragraph(text="กระทรวงอุดมศึกษาฯ (วอ.)", page=14, ocr=True),
              Table(rows=[["ผศ.ดร.ศรีวิภรณ์ ดิษฐอุดมโพธิ์"]], page=14, ocr=True)]  # fmt: skip
    c = cross_check(blocks, tess)
    assert c["flags"] == 2 and blocks[0].ocr_flags == ["ฯ (วอ.)"] and blocks[1].ocr_flags == ["วิภร"]
    assert agreement("กำกับ ดูแล", "กํากับ ดูแล") == 1.0
    assert agreement("หน้าหนึ่ง", "อีกหน้าหนึ่งที่ต่างกันมากมาย") < HARD_PAGE


@pytest.mark.skipif(
    find_tessdata("tha+eng") is None, reason="tesseract language data not installed"
)
def test_typhoon_pages_carry_their_check_and_progress(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    build_scanned_pdf(pdf)
    seen: list[str] = []
    md = "1. Program code and name\nBachelor of Science Program in Food Science\nTotal credits not less than 130 credits"
    doc = PdfReader(pdf, tmp_path / "assets", typhoon=_Fake(md), progress=seen.append).read()
    assert seen == ["อ่านหน้าสแกนด้วย Typhoon OCR หน้า 1/1"]
    c = doc.ocr_checks[1]
    assert c["agreement"] > 0.9 and not c["hard"], "both engines read the same page"
    made_up = "1. Program code and name\nMaster of Arts in Underwater Basket Weaving"
    doc = PdfReader(pdf, tmp_path / "assets", typhoon=_Fake(made_up)).read()
    flags = [f for b in doc.blocks if isinstance(b, Paragraph) for f in b.ocr_flags]
    assert any("Basket" in f for f in flags) and doc.stats()["ocr_flags"] == len(flags)
    assert doc.to_dict()["ocr_checks"]["1"]["flags"] == len(flags)
