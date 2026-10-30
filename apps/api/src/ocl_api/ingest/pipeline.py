"""ingest(file, out_dir): reader -> Document -> book.md + sections/ + assets/ + document.json"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ocl_api.ingest.docx_reader import DocxReader
from ocl_api.ingest.markdown import render_book, render_section
from ocl_api.ingest.model import Document, Paragraph, Table
from ocl_api.ingest.typhoon import TyphoonOcr


class EmptyDocumentError(ValueError):
    """The file opened fine but holds no text and no table: a blank Word file, or a scanned
    PDF with OCR off. Nothing downstream can work on it, so the job must stop here with a
    message the user can act on (R1 test B-2: a blank .docx used to reach the review page)."""


def check_not_empty(doc: Document, *, ocr: bool) -> None:
    has_text = any(isinstance(b, Paragraph) and b.text.strip() for b in doc.blocks)
    has_table = any(isinstance(b, Table) and b.rows for b in doc.blocks)
    if has_text or has_table:
        return
    pages = doc.pages or 0
    # no file name here: a job stores the upload as source.docx, the UI shows the real name
    why = f"ไม่พบเนื้อหาในไฟล์: {pages} หน้า ไม่มีข้อความและตาราง"
    if doc.scanned_pages:
        why += f" · หน้าสแกน (ไม่มีชั้นข้อความ) {len(doc.scanned_pages)} หน้า"
        why += " · OCR ปิดอยู่ (OCR=false)" if not ocr else " · OCR อ่านข้อความไม่ได้"
    raise EmptyDocumentError(why + " · ตรวจว่าเลือกไฟล์ถูกต้องแล้วอัปโหลดใหม่")


def read_document(
    path: Path,
    assets_dir: Path,
    *,
    ocr: bool = True,
    ocr_language: str | None = None,
    typhoon: TyphoonOcr | None = None,
    progress: Callable[[str], None] | None = None,
) -> Document:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return DocxReader(path, assets_dir).read()
    if suffix == ".pdf":
        from ocl_api.ingest.pdf_reader import OCR_LANGUAGE, PdfReader

        return PdfReader(
            path,
            assets_dir,
            ocr=ocr,
            ocr_language=ocr_language or OCR_LANGUAGE,
            typhoon=typhoon,
            progress=progress,
        ).read()
    raise ValueError(f"unsupported file type: {path.suffix}")


def _safe_slug(s: str) -> str:
    return re.sub(r"[^0-9A-Za-zก-๙]+", "-", s).strip("-")[:60] or "section"


def ingest(
    file: str | Path,
    out_dir: str | Path,
    *,
    ocr: bool = True,
    ocr_language: str | None = None,
    typhoon: TyphoonOcr | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    path = Path(file)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    doc = read_document(
        path, out / "assets", ocr=ocr, ocr_language=ocr_language, typhoon=typhoon, progress=progress
    )
    check_not_empty(doc, ocr=ocr)

    (out / "book.md").write_text(render_book(doc), encoding="utf-8")
    sec_dir = out / "sections"
    sec_dir.mkdir(exist_ok=True)
    for old in sec_dir.glob("*.md"):
        old.unlink()
    section_files = []
    for i, s in enumerate(doc.sections()):
        name = f"{i:02d}-{_safe_slug(s.slug)}.md"
        (sec_dir / name).write_text(render_section(s), encoding="utf-8")
        section_files.append(
            {"file": f"sections/{name}", "title": s.title, "blocks": len(s.blocks)}
        )

    (out / "document.json").write_text(
        json.dumps(doc.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    report = {
        "source": path.name,
        "out_dir": str(out),
        "seconds": round(time.perf_counter() - t0, 2),
        **doc.stats(),
        "sections": section_files,
        "notes": doc.notes,
    }
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return report
