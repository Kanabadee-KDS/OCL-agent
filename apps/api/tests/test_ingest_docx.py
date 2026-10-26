"""Ingestion tests on a synthetic .docx built in-memory (no customer files in CI)."""

from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path

import pytest

from ocl_api.ingest.docx_reader import DocxReader, merge_split_tables
from ocl_api.ingest.glyphs import map_pua_text, map_symbol
from ocl_api.ingest.model import Paragraph, Table
from ocl_api.ingest.pipeline import ingest

# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

W_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
)


def p(text: str, *, bold: bool = False, center: bool = False, num: bool = False) -> str:
    ppr = ""
    if center or num:
        ppr = "<w:pPr>" + (
            "<w:numPr><w:ilvl w:val='0'/><w:numId w:val='1'/></w:numPr>" if num else ""
        )
        ppr += ("<w:jc w:val='center'/>" if center else "") + "</w:pPr>"
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space='preserve'>{text}</w:t></w:r></w:p>"


def tc(inner: str, span: int = 1, vmerge: str | None = None) -> str:
    pr = ""
    if span > 1 or vmerge:
        pr = "<w:tcPr>"
        if span > 1:
            pr += f"<w:gridSpan w:val='{span}'/>"
        if vmerge:
            pr += f"<w:vMerge w:val='{vmerge}'/>" if vmerge == "restart" else "<w:vMerge/>"
        pr += "</w:tcPr>"
    return f"<w:tc>{pr}{inner}</w:tc>"


def sym_p(font: str, char: str) -> str:
    return f"<w:p><w:r><w:sym w:font='{font}' w:char='{char}'/></w:r></w:p>"


def build_docx(path: Path) -> None:
    table1 = (
        "<w:tbl>"
        f"<w:tr>{tc(p('รายวิชา'))}{tc(p('PLO1'))}{tc(p('PLO2'))}</w:tr>"
        f"<w:tr>{tc(p('ชุดวิชาพื้นฐาน'), span=3)}</w:tr>"
        f"<w:tr>{tc(p('ทดส101 การเรียนรู้'))}{tc(sym_p('Wingdings', 'F09F'))}{tc(p(''))}</w:tr>"
        f"<w:tr>{tc(p('ทดส102 คณิตศาสตร์'), vmerge='restart')}{tc(p(''))}"
        f"{tc(sym_p('Wingdings', 'F06C'))}</w:tr>"
        f"<w:tr>{tc(p(''), vmerge='continue')}{tc(sym_p('Wingdings 2', 'F0A3'))}{tc(p(''))}</w:tr>"
        "</w:tbl>"
    )
    # second part of the same table on the "next page": same header row -> merged
    table2 = (
        "<w:tbl>"
        f"<w:tr>{tc(p('รายวิชา'))}{tc(p('PLO1'))}{tc(p('PLO2'))}</w:tr>"
        f"<w:tr>{tc(p('ทดส201 ฟิสิกส์'))}{tc(p(''))}{tc(sym_p('Wingdings', 'F09F'))}</w:tr>"
        "</w:tbl>"
    )
    drawing = (
        "<w:p><w:r><w:drawing><wp:inline><a:graphic><a:graphicData>"
        "<pic:pic><pic:blipFill><a:blip r:embed='rId9'/></pic:blipFill></pic:pic>"
        "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
    )
    deleted = (
        "<w:p><w:r><w:t>ข้อความคงอยู่ </w:t></w:r>"
        "<w:del><w:r><w:delText>ข้อความที่ถูกลบ</w:delText></w:r></w:del></w:p>"
    )
    page_break = "<w:p><w:r><w:lastRenderedPageBreak/><w:t>ย่อหน้าแรกของหน้า 2</w:t></w:r></w:p>"
    body = "".join(
        [
            p("คู่มือหลักสูตรทดสอบ", bold=True, center=True),
            p("หมวดที่ 1 ข้อมูลทั่วไป", bold=True, center=True),
            p("1. รหัสและชื่อหลักสูตร", bold=True),
            p("รหัสหลักสูตร 25290091100204"),
            p("1.1 ชื่อหลักสูตรภาษาไทย", bold=True),
            p("1. ข้อนี้เป็นรายการ ไม่ใช่หัวข้อ เพราะไม่หนา"),
            p("รายการที่หนึ่ง", num=True),
            deleted,
            page_break,
            p("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", bold=True),
            table1,
            p(""),
            table2,
            drawing,
            p("ภาคผนวก ก ข้อบังคับ", bold=True),
            p("เนื้อหาภาคผนวก"),
        ]
    )
    document = f"<w:document {W_NS}><w:body>{body}<w:sectPr/></w:body></w:document>"
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/image" Target="media/image1.png"/></Relationships>'
    )
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", rels)
        z.writestr("word/media/image1.png", PNG)


def build_blank_docx(path: Path) -> None:
    """What Word saves for a new, untouched document: a valid package with one empty
    paragraph (about 1 KB, so it passes the API's 0-byte check)."""
    document = f"<w:document {W_NS}><w:body><w:p/><w:sectPr/></w:body></w:document>"
    content_types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("word/document.xml", document)


@pytest.fixture
def docx_file(tmp_path: Path) -> Path:
    f = tmp_path / "sample.docx"
    build_docx(f)
    return f


def test_blank_docx_is_rejected(tmp_path: Path) -> None:
    from ocl_api.ingest.pipeline import EmptyDocumentError

    f = tmp_path / "x.docx"
    build_blank_docx(f)
    assert f.stat().st_size > 0
    with pytest.raises(EmptyDocumentError) as exc:
        ingest(f, tmp_path / "out")
    assert "ไม่พบเนื้อหาในไฟล์: 1 หน้า ไม่มีข้อความและตาราง" in str(exc.value)
    assert not (tmp_path / "out" / "document.json").exists(), "nothing written for a blank book"


def test_reader_structure(docx_file: Path, tmp_path: Path) -> None:
    doc = DocxReader(docx_file, tmp_path / "assets").read()
    secs = doc.sections()
    assert [s.number for s in secs] == ["front", "1", "4", "ก"]
    assert [s.kind for s in secs] == ["front", "chapter", "chapter", "appendix"]
    heads = [(b.level, b.text) for b in doc.blocks if isinstance(b, Paragraph) and b.level]
    assert (2, "1. รหัสและชื่อหลักสูตร") in heads
    assert (3, "1.1 ชื่อหลักสูตรภาษาไทย") in heads
    assert all(t != "1. ข้อนี้เป็นรายการ ไม่ใช่หัวข้อ เพราะไม่หนา" for _, t in heads)
    assert any(b.list_item for b in doc.blocks if isinstance(b, Paragraph))


def test_deleted_text_and_pages(docx_file: Path, tmp_path: Path) -> None:
    doc = DocxReader(docx_file, tmp_path / "assets").read()
    texts = [b.text for b in doc.blocks if isinstance(b, Paragraph)]
    assert "ข้อความคงอยู่" in texts
    assert not any("ถูกลบ" in t for t in texts)
    page2 = next(b for b in doc.blocks if isinstance(b, Paragraph) and "หน้า 2" in b.text)
    assert page2.page == 2 and doc.pages == 2


def test_tables_glyphs_span_merge(docx_file: Path, tmp_path: Path) -> None:
    doc = DocxReader(docx_file, tmp_path / "assets").read()
    tables = [b for b in doc.blocks if isinstance(b, Table)]
    assert len(tables) == 1, "two parts with the same header must merge into one table"
    t = tables[0]
    assert t.merged_from == 2 and t.n_cols == 3
    assert t.rows[0] == ["รายวิชา", "PLO1", "PLO2"]
    assert t.rows[1] == ["ชุดวิชาพื้นฐาน", "", ""]  # gridSpan=3
    assert t.rows[2] == ["ทดส101 การเรียนรู้", "●", ""]  # Wingdings F09F
    assert t.rows[3][2] == "●"  # Wingdings F06C
    assert t.rows[4][0] == "ทดส102 คณิตศาสตร์"  # vMerge continue carries value down
    assert t.rows[4][1].startswith("□") or t.rows[4][1].startswith("⟨sym")
    assert t.rows[5] == ["ทดส201 ฟิสิกส์", "", "●"]  # from the merged second part


def test_images_extracted(docx_file: Path, tmp_path: Path) -> None:
    doc = DocxReader(docx_file, tmp_path / "assets").read()
    imgs = [b for b in doc.blocks if b.kind == "image"]
    assert len(imgs) == 1 and imgs[0].path == "assets/img-001.png"
    assert (tmp_path / "assets" / "img-001.png").read_bytes() == PNG


def test_pipeline_outputs(docx_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    report = ingest(docx_file, out)
    assert (out / "book.md").exists() and (out / "document.json").exists()
    md = (out / "book.md").read_text(encoding="utf-8")
    assert "# หมวดที่ 1 ข้อมูลทั่วไป" in md
    assert "| รายวิชา | PLO1 | PLO2 |" in md
    assert "| ทดส101 การเรียนรู้ | ● |" in md
    assert "![image](assets/img-001.png)" in md
    assert "<!-- page: 2 -->" in md
    assert report["tables"] == 1 and report["images"] == 1
    assert report["chapters"] == ["1", "4"] and report["appendices"] == ["ก"]
    sections = sorted(x.name for x in (out / "sections").glob("*.md"))
    assert len(sections) == 4
    data = json.loads((out / "document.json").read_text(encoding="utf-8"))
    assert data["stats"]["tables"] == 1


def test_symbol_mapping_and_unknown() -> None:
    unknown: dict[str, int] = {}
    assert map_symbol("Wingdings", 0xF09F, unknown) == "●"
    assert map_symbol("Wingdings", 0x6C, unknown) == "●"
    assert map_symbol("Wingdings", 0xFE, unknown) == "☑"
    assert map_symbol("Wingdings 2", 0xF0A3, unknown) == "□"
    assert map_symbol("Wingdings2", 0xA3, unknown) == "□"
    assert map_symbol("BCDMEE+Wingdings-Regular", 0xF09F, unknown) == "●"
    assert map_symbol("Webdings", 0xF041, unknown).startswith("⟨sym")
    assert unknown == {"webdings:41": 1}


def test_merge_only_adjacent_same_header() -> None:
    a = Table(rows=[["h1", "h2"], ["1", "2"]])
    b = Table(rows=[["h1", "h2"], ["3", "4"]])
    c = Table(rows=[["x", "y"], ["5", "6"]])
    merged = merge_split_tables([a, Paragraph(text=""), b, Paragraph(text="ข้อความคั่น"), c])
    tables = [t for t in merged if isinstance(t, Table)]
    assert len(tables) == 2 and tables[0].rows == [["h1", "h2"], ["1", "2"], ["3", "4"]]


def test_letters_typed_in_a_symbol_font_are_mapped() -> None:
    # Word keeps the letter "R" when Wingdings 2 is applied to a normal run (ศศ.ม. book)
    assert map_pua_text("Wingdings 2", "R", {}) == "\u2612"
    assert map_pua_text("Wingdings 2", " ", {}) == " "  # unknown codes stay as typed
    assert map_pua_text("TH SarabunPSK", "R", {}) == "R"
