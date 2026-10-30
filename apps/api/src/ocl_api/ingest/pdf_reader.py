"""Read a PDF into the Document model with PyMuPDF.

Curriculum PDFs are exported from Word, so they have a text layer, ruled tables and
a few embedded images; appendices may contain scanned pages without text. This
reader keeps the same guarantees as the .docx reader: symbol glyphs survive,
tables come out as rows, every block knows its page, and split tables merge.

A page with (almost) no text layer is treated as scanned: it is rendered to PNG
for the reviewer and, when Tesseract language data is available, OCR'd with
MuPDF's built-in Tesseract (``tha+eng``). OCR lines come back fragmented (Thai
vowel/tone marks make Tesseract split one printed line into several), so they
are regrouped by row before the normal paragraph logic runs. OCR paragraphs
carry ``ocr=True`` so downstream consumers can show them as lower-trust.

Thai text needs two special cases. Lines wrap without spaces, so a wrapped line
joins its predecessor without inserting one. And combining marks (vowels above
and below, tone marks) are separate glyphs, so any extraction that re-sorts
characters by position scrambles words; table cell text is therefore taken from
the content-stream lines that fall inside each cell, never from a position sort.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path

import pymupdf

from ocl_api.ingest.docx_reader import merge_split_tables
from ocl_api.ingest.glyphs import map_pua_text, symbol_table
from ocl_api.ingest.model import Block, Document, Image, Paragraph, Table, heading_level
from ocl_api.ingest.typhoon import (
    TyphoonError,
    TyphoonOcr,
    cross_check,
    markdown_blocks,
    promote_items,
)

_WS = re.compile(r"[ \t ]+")
_PAGE_NO = re.compile(r"^[\d๐-๙]{1,4}$|^[ก-ฮ]$")
# "1. ", "2.1 ", "(ก) ", "- ", "• " at the start of a line begin a new paragraph
_STARTS_ITEM = re.compile(r"^\s*(\d+(\.\d+)*\.?\s|\([ก-ฮa-z\d]+\)\s|[-–•●]\s|หมวดที่\s|ภาคผนวก\s)")
SCANNED_TEXT_THRESHOLD = 30  # chars of text below which a page counts as scanned
OCR_LANGUAGE = "tha+eng"
# OCR drops vowel/tone marks: "หมวดที่ 1" comes back as "หมวดที1" or "หมวดท 2"
_RE_CHAPTER_LOOSE = re.compile(r"^\s*หมวดท[ี่]*\s*(\d+)\b")
_LETTERS = re.compile(r"[A-Za-zก-๙]")
OCR_DPI = 200  # 200 vs 300 dpi: same accuracy on curriculum pages, 15% faster
_TESSDATA_CANDIDATES = (
    "/usr/share/tesseract-ocr/5/tessdata",  # Debian/Ubuntu tesseract-ocr-* packages
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tessdata",  # Alpine
    "/opt/homebrew/share/tessdata",  # macOS brew (arm64)
    "/usr/local/share/tessdata",  # macOS brew (x86)
)


def find_tessdata(language: str = OCR_LANGUAGE) -> str | None:
    """Directory holding <lang>.traineddata for every language in `language`, or None.
    `TESSDATA_PREFIX` wins; otherwise the usual package locations are probed."""
    langs = [x for x in language.split("+") if x]
    cands = [os.environ.get("TESSDATA_PREFIX") or ""] + list(_TESSDATA_CANDIDATES)
    for c in cands:
        if c and all(Path(c, f"{lang}.traineddata").exists() for lang in langs):
            return c
    return None


class _Line:
    __slots__ = ("text", "rect", "bold")

    def __init__(self, text: str, rect: pymupdf.Rect, bold: bool):
        self.text = text
        self.rect = rect
        self.bold = bold

    @property
    def center(self) -> pymupdf.Point:
        return pymupdf.Point((self.rect.x0 + self.rect.x1) / 2, (self.rect.y0 + self.rect.y1) / 2)


def _is_thai(ch: str) -> bool:
    return "฀" <= ch <= "๿"


def join_lines(lines: list[str]) -> str:
    """Join wrapped lines when line geometry is unknown. Thai has no inter-word
    spaces, so a line break inside a Thai word must not become a space; Latin text
    keeps the space."""
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if not out:
            out = ln
        elif _is_thai(out[-1]) and _is_thai(ln[0]):
            out += ln
        elif out.endswith("-") and not out.endswith(" -"):
            out = out[:-1] + ln
        else:
            out += " " + ln
    return out


def _join_geometry(lines: list[_Line], right_edge: float, tolerance: float) -> str:
    """Join lines using their geometry: a line that reaches the right edge wrapped,
    so Thai continues without a space; a short line ended at a word boundary."""
    text = lines[0].text
    for prev, ln in zip(lines, lines[1:], strict=False):
        wrapped = prev.rect.x1 >= right_edge - tolerance
        if wrapped and text and _is_thai(text[-1]) and _is_thai(ln.text[0]):
            text += ln.text
        else:
            text += " " + ln.text
    return _WS.sub(" ", text).strip()


def _span_text(span: dict, unknown: dict[str, int]) -> str:
    font = span.get("font")
    text = span.get("text", "")
    if symbol_table(font) is not None:
        return map_pua_text(font, text, unknown)
    # Some exporters keep Wingdings private-use chars in a non-symbol-named font.
    if any(0xF000 <= ord(c) <= 0xF0FF for c in text):
        return map_pua_text("wingdings", text, unknown)
    return text


def _span_bold(span: dict) -> bool:
    return bool(span.get("flags", 0) & 16) or "bold" in (span.get("font") or "").lower()


class PdfReader:
    def __init__(
        self,
        path: str | Path,
        assets_dir: str | Path,
        *,
        render_scanned: bool = True,
        ocr: bool = True,
        ocr_language: str = OCR_LANGUAGE,
        ocr_dpi: int = OCR_DPI,
        typhoon: TyphoonOcr | None = None,
        progress: Callable[[str], None] | None = None,
    ):
        """`typhoon` set: scanned pages are read by Typhoon OCR (OCR-1), Tesseract when a
        page fails; unset: Tesseract only."""
        self.path = Path(path)
        self.assets_dir = Path(assets_dir)
        self.render_scanned = render_scanned
        self.ocr = ocr
        self.ocr_language = ocr_language
        self.ocr_dpi = ocr_dpi
        self.typhoon = typhoon
        self.progress = progress  # OCR-2: "อ่านหน้าสแกน N/M" for the job page (slow pages)
        self._n_pages = 0
        self.typhoon_pages: list[int] = []
        self.ocr_checks: dict[int, dict] = {}
        self.unknown_symbols: dict[str, int] = {}
        self.notes: list[str] = []
        self._asset_by_xref: dict[int, str] = {}
        self.scanned_pages: list[int] = []
        self.ocr_pages: list[int] = []
        self._tessdata: str | None | bool = False  # False = not probed yet

    def read(self) -> Document:
        blocks: list[Block] = []
        with pymupdf.open(self.path) as doc:
            self._n_pages = doc.page_count
            for pno, page in enumerate(doc, start=1):
                blocks.extend(self._page_blocks(doc, page, pno))
            n_pages = doc.page_count
        blocks = merge_split_tables(blocks)
        if self.typhoon_pages:
            promote_items(blocks, set(self.typhoon_pages))
        out = Document(
            source_name=self.path.name,
            source_type="pdf",
            blocks=blocks,
            pages=n_pages,
            pages_declared=n_pages,
        )
        out.scanned_pages = list(self.scanned_pages)
        out.ocr_pages = list(self.ocr_pages)
        out.ocr_checks = dict(self.ocr_checks)
        if self.unknown_symbols:
            out.notes.append(f"unknown symbol glyphs: {self.unknown_symbols}")
        if self.scanned_pages:
            out.notes.append(f"scanned pages (no text layer): {self.scanned_pages}")
        if self.typhoon_pages:
            out.notes.append(
                f"OCR (Typhoon {self.typhoon.model}) applied to pages: {self.typhoon_pages}"  # type: ignore[union-attr]
            )
        tess = [p for p in self.ocr_pages if p not in self.typhoon_pages]
        if tess:
            out.notes.append(f"OCR ({self.ocr_language}) applied to pages: {tess}")
        out.notes.extend(self.notes)
        return out

    # ---------- per page ----------

    def _page_blocks(self, doc: pymupdf.Document, page: pymupdf.Page, pno: int) -> list[Block]:
        items: list[tuple[float, int, Block]] = []  # (y0, order, block)
        order = 0
        lines = self._lines(page)

        tables = self._tables(page, pno, lines)
        table_rects = [r for r, _ in tables]
        for rect, tbl in tables:
            items.append((rect.y0, order, tbl))
            order += 1

        text_len = 0
        for y0, para in self._paragraphs(page, pno, lines, table_rects):
            text_len += len(para.text)
            items.append((y0, order, para))
            order += 1

        page_images = self._images(doc, page, pno)
        scanned = text_len < SCANNED_TEXT_THRESHOLD and not tables
        for y0, img, rect in page_images:
            if scanned and self.render_scanned and rect.get_area() >= 0.8 * page.rect.get_area():
                continue  # the scan itself; the rendered page PNG below stands in for it
            items.append((y0, order, img))
            order += 1

        if scanned:
            self.scanned_pages.append(pno)
            rel = None
            if self.render_scanned:
                rel = self._render_page(page, pno)
                items.append((0.0, order, Image(path=rel, page=pno, alt=f"scanned page {pno}")))
                order += 1
            if self.ocr and self.progress is not None:
                engine = "Typhoon OCR" if self.typhoon is not None else "OCR"
                self.progress(f"อ่านหน้าสแกนด้วย {engine} หน้า {pno}/{self._n_pages}")
            ocr_blocks = self._typhoon_blocks(page, pno, rel) if self.ocr else []
            if not ocr_blocks and self.ocr:
                ocr_blocks = self._ocr_paragraphs(page, pno)
            if ocr_blocks:
                self.ocr_pages.append(pno)
                for y0, blk in ocr_blocks:
                    items.append((0.1 + y0, order, blk))
                    order += 1
            else:
                items.append(
                    (0.1, order, Paragraph(text=f"[หน้าสแกน {pno}: ไม่มีข้อความ ต้อง OCR]", page=pno))
                )

        items.sort(key=lambda t: (t[0], t[1]))
        return [b for _, _, b in items]

    # ---------- OCR of scanned pages ----------

    def _typhoon_blocks(
        self, page: pymupdf.Page, pno: int, image_path: str | None
    ) -> list[tuple[float, Block]]:
        """Typhoon OCR in reading order; [] (-> Tesseract) when it is off or the page fails."""
        if self.typhoon is None:
            return []
        try:
            md = self.typhoon.read_page(page)
        except TyphoonError as e:
            self.notes.append(f"page {pno}: Typhoon OCR failed ({e}), used Tesseract")
            return []
        blocks = markdown_blocks(md, pno, image_path)
        if not any(isinstance(b, Paragraph | Table) for b in blocks):
            self.notes.append(f"page {pno}: Typhoon OCR found no text, used Tesseract")
            return []
        self.typhoon_pages.append(pno)
        other = self._tesseract_text(page, pno)
        if other is not None:  # OCR-2a1: what Tesseract did not see is flagged for review
            self.ocr_checks[pno] = cross_check(blocks, other)
        return [(i / 1000, b) for i, b in enumerate(blocks)]

    def tessdata(self) -> str | None:
        if self._tessdata is False:
            self._tessdata = find_tessdata(self.ocr_language)
            if self._tessdata is None:
                self.notes.append(
                    f"OCR unavailable: no tessdata for {self.ocr_language} "
                    "(install tesseract language packs or set TESSDATA_PREFIX)"
                )
        return self._tessdata  # type: ignore[return-value]

    def _tesseract_text(self, page: pymupdf.Page, pno: int) -> str | None:
        """Tesseract's plain text of a page (for the cross-check), None when unavailable."""
        tessdata = self.tessdata()
        if tessdata is None:
            return None
        try:
            tp = page.get_textpage_ocr(
                language=self.ocr_language, dpi=self.ocr_dpi, full=True, tessdata=tessdata
            )
            return page.get_text(textpage=tp)
        except Exception as e:  # pragma: no cover - tesseract runtime failure
            self.notes.append(f"page {pno}: Tesseract cross-check failed: {e}")
            return None

    def _ocr_paragraphs(self, page: pymupdf.Page, pno: int) -> list[tuple[float, Paragraph]]:
        tessdata = self.tessdata()
        if tessdata is None:
            return []
        try:
            tp = page.get_textpage_ocr(
                language=self.ocr_language, dpi=self.ocr_dpi, full=True, tessdata=tessdata
            )
            lines = self._lines(page, textpage=tp)
        except Exception as e:  # pragma: no cover - tesseract runtime failure
            self.notes.append(f"page {pno}: OCR failed: {e}")
            return []
        lines = regroup_ocr_lines(lines)
        out = []
        for y0, para in self._paragraphs(page, pno, lines, []):
            if not _looks_like_text(para.text):
                continue  # stray marks Tesseract read as letters ("a y a")
            para.ocr = True
            m = _RE_CHAPTER_LOOSE.match(para.text)
            if m:
                # a real chapter heading is centred on its own line; a table-of-contents
                # entry is left-aligned with (garbled) leader dots after it
                if para.align == "center" and para.level == 0:
                    para.text = f"หมวดที่ {m.group(1)} {para.text[m.end() :].strip()}".strip()
                    para.level = 1
                elif para.align != "center":
                    para.level = 0
            out.append((y0, para))
        return out

    def _lines(self, page: pymupdf.Page, textpage: pymupdf.TextPage | None = None) -> list[_Line]:
        """Text lines in content-stream order (keeps Thai combining marks intact)."""
        out: list[_Line] = []
        for block in page.get_text("dict", textpage=textpage).get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text")]
                txt = _WS.sub(" ", "".join(_span_text(s, self.unknown_symbols) for s in spans))
                if not txt.strip():
                    continue
                bold = all(_span_bold(s) for s in spans if s["text"].strip())
                out.append(_Line(txt.strip(), pymupdf.Rect(line["bbox"]), bold))
        return out

    def _tables(
        self, page: pymupdf.Page, pno: int, lines: list[_Line]
    ) -> list[tuple[pymupdf.Rect, Table]]:
        out: list[tuple[pymupdf.Rect, Table]] = []
        try:
            found = page.find_tables()
        except Exception as e:  # pragma: no cover - defensive, PyMuPDF internals
            self.notes.append(f"page {pno}: find_tables failed: {e}")
            return out
        for tab in found.tables:
            # tab.rows[i].cells gives per-row cell boxes (None = merged away). tab.cells
            # is NOT row-major in PyMuPDF 2.x, so it is not used here.
            try:
                row_cells = [list(r.cells) for r in tab.rows]
            except Exception:  # pragma: no cover - older PyMuPDF
                row_cells = []
            if row_cells:
                rows = [
                    ["" if c is None else self._cell_text(pymupdf.Rect(c), lines) for c in rc]
                    for rc in row_cells
                ]
            else:
                rows = self._rows_from_extract(tab)
            if not rows or all(not any(r) for r in rows):
                continue
            width = max(len(r) for r in rows)
            for r in rows:
                r.extend([""] * (width - len(r)))
            out.append((pymupdf.Rect(tab.bbox), Table(rows=rows, page=pno)))
        return out

    def _cell_text(self, cell: pymupdf.Rect, lines: list[_Line]) -> str:
        inside = [ln for ln in lines if cell.contains(ln.center)]
        if not inside:
            return ""
        inside.sort(key=lambda ln: (round(ln.rect.y0 / 2), ln.rect.x0))
        return _join_geometry(inside, cell.x1, max(6.0, 0.12 * cell.width))

    def _rows_from_extract(self, tab) -> list[list[str]]:
        """Fallback when the cell grid is unavailable (position-sorted; may scramble Thai)."""
        rows: list[list[str]] = []
        for row in tab.extract():
            cells = []
            for cell in row:
                txt = "" if cell is None else str(cell)
                txt = map_pua_text("wingdings", txt, self.unknown_symbols)
                cells.append(_WS.sub(" ", txt.replace("\n", " ")).strip())
            rows.append(cells)
        return rows

    def _paragraphs(
        self, page: pymupdf.Page, pno: int, lines: list[_Line], table_rects: list[pymupdf.Rect]
    ) -> list[tuple[float, Paragraph]]:
        """Rebuild paragraphs from lines.

        PyMuPDF blocks often span a whole page, so paragraph boundaries are decided per
        line: a line starts a new paragraph when it looks like a heading or list item,
        when the vertical gap is large, when boldness changes, or when the previous
        line stopped short of the right margin.
        """
        out: list[tuple[float, Paragraph]] = []
        pw = page.rect.width
        ph = page.rect.height
        body: list[_Line] = []
        for ln in lines:
            if any(self._mostly_inside(ln.rect, tr) for tr in table_rects):
                continue
            if _PAGE_NO.match(ln.text) and (ln.rect.y0 > ph * 0.9 or ln.rect.y1 < ph * 0.08):
                continue  # running page number in header/footer
            body.append(ln)
        if not body:
            return out
        body.sort(key=lambda ln: (round(ln.rect.y0 / 3), ln.rect.x0))
        right_edge = max(ln.rect.x1 for ln in body)

        cur: list[_Line] = []

        def flush() -> None:
            if not cur:
                return
            text = _join_geometry(cur, right_edge, 0.03 * pw)
            x0 = min(ln.rect.x0 for ln in cur)
            x1 = max(ln.rect.x1 for ln in cur)
            bold = all(ln.bold for ln in cur)
            centered = abs((x0 + x1) / 2 - pw / 2) < pw * 0.08 and (x1 - x0) < pw * 0.7
            align = "center" if centered else None
            level = heading_level(text, bold, align)
            out.append(
                (
                    cur[0].rect.y0,
                    Paragraph(text=text, page=pno, level=level, bold=bold, align=align),
                )
            )
            cur.clear()

        for ln in body:
            if cur:
                prev = cur[-1]
                gap = ln.rect.y0 - prev.rect.y1
                line_h = max(prev.rect.height, 1.0)
                prev_short = prev.rect.x1 < right_edge - 0.12 * pw
                new_para = (
                    gap > 0.6 * line_h
                    or prev_short
                    or _STARTS_ITEM.match(ln.text) is not None
                    or ln.bold != prev.bold
                    or heading_level(ln.text, ln.bold, None) > 0
                )
                if new_para:
                    flush()
            cur.append(ln)
        flush()
        return out

    @staticmethod
    def _mostly_inside(inner: pymupdf.Rect, outer: pymupdf.Rect) -> bool:
        if inner.is_empty or outer.is_empty:
            return False
        overlap = inner & outer
        return (not overlap.is_empty) and overlap.get_area() >= 0.5 * inner.get_area()

    def _images(
        self, doc: pymupdf.Document, page: pymupdf.Page, pno: int
    ) -> list[tuple[float, Image, pymupdf.Rect]]:
        out: list[tuple[float, Image, pymupdf.Rect]] = []
        for info in page.get_image_info(xrefs=True):
            xref = info.get("xref", 0)
            if not xref:
                continue
            rect = pymupdf.Rect(info["bbox"])
            if rect.width < 20 or rect.height < 20:
                continue  # decorative specks / rules
            rel = self._asset_by_xref.get(xref)
            if rel is None:
                try:
                    img = doc.extract_image(xref)
                except Exception as e:  # pragma: no cover
                    self.notes.append(f"page {pno}: cannot extract image xref {xref}: {e}")
                    continue
                if not img or not img.get("image"):
                    continue
                n = len(self._asset_by_xref) + 1
                ext = img.get("ext", "png")
                rel = f"assets/img-{n:03d}.{ext}"
                self.assets_dir.mkdir(parents=True, exist_ok=True)
                (self.assets_dir / f"img-{n:03d}.{ext}").write_bytes(img["image"])
                self._asset_by_xref[xref] = rel
            out.append((rect.y0, Image(path=rel, page=pno), rect))
        return out

    def _render_page(self, page: pymupdf.Page, pno: int) -> str:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        name = f"page-{pno:03d}.png"
        page.get_pixmap(dpi=150).save(str(self.assets_dir / name))
        return f"assets/{name}"


def _looks_like_text(text: str) -> bool:
    """False for OCR noise: fewer than 3 letters, or only 1–2-letter tokens with no number."""
    letters = len(_LETTERS.findall(text))
    if letters < 3:
        return False
    tokens = text.split()
    if (
        len(tokens) >= 2
        and all(len(t) <= 2 for t in tokens)
        and not any(t.isdigit() for t in tokens)
    ):
        return False
    return True


def regroup_ocr_lines(lines: list[_Line]) -> list[_Line]:
    """Merge OCR fragments that sit on the same printed row.

    Tesseract splits a Thai line wherever the glyph height changes (vowels above,
    tone marks), giving pieces like "หลักสู" + "ตร25290091100204" with overlapping
    vertical extents. Pieces whose vertical centres fall inside each other's box
    are one row; they are sorted by x and joined (Thai→Thai without a space, a
    space otherwise)."""
    rows: list[list[_Line]] = []
    for ln in sorted(lines, key=lambda x: (x.rect.y0, x.rect.x0)):
        cy = (ln.rect.y0 + ln.rect.y1) / 2
        for row in rows:
            r0 = min(x.rect.y0 for x in row)
            r1 = max(x.rect.y1 for x in row)
            rc = (r0 + r1) / 2
            if r0 <= cy <= r1 and ln.rect.y0 <= rc <= ln.rect.y1:
                row.append(ln)
                break
        else:
            rows.append([ln])
    out: list[_Line] = []
    for row in rows:
        row.sort(key=lambda x: x.rect.x0)
        text = row[0].text
        for prev, ln in zip(row, row[1:], strict=False):
            gap = ln.rect.x0 - prev.rect.x1
            glue = (
                gap < 0.6 * max(prev.rect.height, 1.0)
                and _is_thai(text[-1])
                and _is_thai(ln.text[0])
            )
            text += ln.text if glue else " " + ln.text
        rect = pymupdf.Rect(
            min(x.rect.x0 for x in row), min(x.rect.y0 for x in row),
            max(x.rect.x1 for x in row), max(x.rect.y1 for x in row),
        )  # fmt: skip
        out.append(_Line(_WS.sub(" ", text).strip(), rect, all(x.bold for x in row)))
    out.sort(key=lambda x: (x.rect.y0, x.rect.x0))
    return out
