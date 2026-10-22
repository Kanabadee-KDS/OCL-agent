"""PDF ingestion tests on a synthetic PDF built with PyMuPDF (ASCII only: the base-14
fonts have no Thai glyphs; Thai-specific line joining is tested as a pure function)."""

from __future__ import annotations

import base64
from pathlib import Path

import pymupdf
import pytest

from ocl_api.ingest.model import Image, Paragraph, Table
from ocl_api.ingest.pdf_reader import (
    PdfReader,
    _Line,
    _looks_like_text,
    find_tessdata,
    join_lines,
    regroup_ocr_lines,
)
from ocl_api.ingest.pipeline import ingest

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _draw_table(page: pymupdf.Page, x0: float, y0: float, rows: list[list[str]], cw=120, rh=22):
    """Ruled grid + cell text so find_tables() can see it."""
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            r = pymupdf.Rect(x0 + j * cw, y0 + i * rh, x0 + (j + 1) * cw, y0 + (i + 1) * rh)
            page.draw_rect(r, color=(0, 0, 0), width=0.8)
            page.insert_text((r.x0 + 4, r.y1 - 7), cell, fontsize=9)


def build_pdf(path: Path) -> None:
    doc = pymupdf.open()
    # page 1: heading-like text, body, a table split across pages (same header)
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((72, 72), "1. Program code and name", fontsize=12, fontname="hebo")
    p1.insert_text((72, 100), "Line one of a paragraph", fontsize=10)
    p1.insert_text((72, 112), "line two continues here", fontsize=10)
    _draw_table(p1, 72, 160, [["Course", "PLO1", "PLO2"], ["ABC101", "x", ""], ["ABC103", "", "x"]])
    p1.insert_text((297, 820), "1", fontsize=9)  # running page number
    # page 2: continuation of the table with repeated header + an image
    p2 = doc.new_page(width=595, height=842)
    _draw_table(p2, 72, 72, [["Course", "PLO1", "PLO2"], ["ABC102", "", "x"]])
    p2.insert_image(pymupdf.Rect(72, 200, 172, 300), stream=PNG)
    p2.insert_text((72, 320), "After the image", fontsize=10)
    # page 3: scanned-like page (no text at all)
    doc.new_page(width=595, height=842)
    doc.save(str(path))
    doc.close()


@pytest.fixture
def pdf_file(tmp_path: Path) -> Path:
    f = tmp_path / "sample.pdf"
    build_pdf(f)
    return f


def test_join_lines_thai_and_latin() -> None:
    assert join_lines(["หลักสูตรวิทยาศาสตร", "บัณฑิต"]) == "หลักสูตรวิทยาศาสตรบัณฑิต"
    assert join_lines(["Bachelor of", "Science"]) == "Bachelor of Science"
    assert join_lines(["ภาษาอังกฤษ:", "Bachelor"]) == "ภาษาอังกฤษ: Bachelor"
    assert join_lines(["self-", "contained"]) == "selfcontained"


def test_pdf_reader_structure(pdf_file: Path, tmp_path: Path) -> None:
    doc = PdfReader(pdf_file, tmp_path / "assets").read()
    assert doc.pages == 3 and doc.source_type == "pdf"
    paras = [b for b in doc.blocks if isinstance(b, Paragraph)]
    texts = [p.text for p in paras]
    assert "Line one of a paragraph line two continues here" in texts
    assert "1" not in texts, "running page number must be dropped"
    heading = next(p for p in paras if p.text.startswith("1. Program"))
    assert heading.level == 2 and heading.bold and heading.page == 1
    tables = [b for b in doc.blocks if isinstance(b, Table)]
    assert len(tables) == 1 and tables[0].merged_from == 2
    assert tables[0].rows[0] == ["Course", "PLO1", "PLO2"]
    # row-major order and cell placement (tab.cells in PyMuPDF 2.x is column-major)
    assert [r[0] for r in tables[0].rows[1:]] == ["ABC101", "ABC103", "ABC102"]
    assert tables[0].rows[1][1] == "x" and tables[0].rows[2][2] == "x"
    assert tables[0].rows[3][2] == "x"
    images = [b for b in doc.blocks if isinstance(b, Image)]
    assert any(i.path == "assets/img-001.png" and i.page == 2 for i in images)
    assert any(i.path == "assets/page-003.png" for i in images), "scanned page rendered"
    assert any("หน้าสแกน 3" in p.text for p in paras)
    assert "scanned pages (no text layer): [3]" in doc.notes


def test_pdf_pipeline(pdf_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    report = ingest(pdf_file, out)
    assert report["pages"] == 3 and report["tables"] == 1
    md = (out / "book.md").read_text(encoding="utf-8")
    assert "| Course | PLO1 | PLO2 |" in md
    assert "![image](assets/img-001.png)" in md
    assert (out / "assets" / "page-003.png").exists()


# ---------- OCR of scanned pages ----------

HAS_TESSDATA = find_tessdata("tha+eng") is not None


def build_scanned_pdf(path: Path) -> None:
    """Page 1 is an image of rendered text (no text layer), like a scanned book."""
    src = pymupdf.open()
    p = src.new_page(width=595, height=842)
    p.insert_text((72, 90), "1. Program code and name", fontsize=16, fontname="hebo")
    p.insert_text((72, 130), "Bachelor of Science Program in Food Science", fontsize=14)
    p.insert_text((72, 160), "Total credits not less than 130 credits", fontsize=14)
    pix = p.get_pixmap(dpi=200)
    scan = pymupdf.open()
    sp = scan.new_page(width=595, height=842)
    sp.insert_image(sp.rect, pixmap=pix)
    scan.save(path)


def test_regroup_ocr_lines_joins_thai_fragments_on_one_row() -> None:
    r = pymupdf.Rect
    frags = [
        _Line("ตร25290091100204", r(120, 100, 300, 118), False),  # later piece, listed first
        _Line("รหัสหลักสู", r(72, 102, 118, 116), False),
        _Line("Next line", r(72, 130, 150, 144), False),
    ]
    out = regroup_ocr_lines(frags)
    assert [ln.text for ln in out] == ["รหัสหลักสูตร25290091100204", "Next line"]
    assert out[0].rect.y0 == 100 and out[0].rect.x1 == 300


def test_scanned_page_without_ocr_keeps_placeholder(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    build_scanned_pdf(pdf)
    doc = PdfReader(pdf, tmp_path / "assets", ocr=False).read()
    assert doc.scanned_pages == [1] and doc.ocr_pages == []
    texts = [b.text for b in doc.blocks if b.kind == "paragraph"]
    assert texts == ["[หน้าสแกน 1: ไม่มีข้อความ ต้อง OCR]"]
    assert doc.stats()["scanned_pages"] == 1 and doc.stats()["ocr_pages"] == 0


@pytest.mark.skipif(not HAS_TESSDATA, reason="tesseract tha+eng language data not installed")
def test_scanned_page_is_ocrd(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    build_scanned_pdf(pdf)
    doc = PdfReader(pdf, tmp_path / "assets").read()
    assert doc.ocr_pages == [1]
    paras = [b for b in doc.blocks if b.kind == "paragraph"]
    assert paras and all(p.ocr for p in paras)
    text = " ".join(p.text for p in paras)
    assert "Program code and name" in text and "130 credits" in text
    assert any("OCR (tha+eng) applied to pages: [1]" in n for n in doc.notes)
    # the rendered page image is still there for the reviewer's side-by-side view
    assert any(b.kind == "image" and b.path == "assets/page-001.png" for b in doc.blocks)
    # document.json carries the flag so the web can mark OCR text as lower-trust
    d = doc.to_dict()
    assert d["ocr_pages"] == [1] and d["stats"]["ocr_pages"] == 1
    assert any(b.get("ocr") for s in d["sections"] for b in s["blocks"] if b["kind"] == "paragraph")


def test_find_tessdata_prefers_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "tha.traineddata").write_bytes(b"x")
    (tmp_path / "eng.traineddata").write_bytes(b"x")
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path))
    assert find_tessdata("tha+eng") == str(tmp_path)
    assert find_tessdata("tha+eng+jpn") != str(tmp_path)  # jpn missing there


def test_ocr_noise_filter() -> None:
    assert not _looks_like_text("a y a")
    assert not _looks_like_text("| .")
    assert _looks_like_text("ไม่น้อยกว่า130 หน่วยกิต")
    assert _looks_like_text("B.Sc. (Food Science)")
