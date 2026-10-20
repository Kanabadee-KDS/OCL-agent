"""Read a PDF into the Document model with PyMuPDF.

Curriculum PDFs are exported from Word, so they have a text layer, ruled tables and
a few embedded images; appendices may contain scanned pages without text. This
reader keeps the same guarantees as the .docx reader: symbol glyphs survive,
tables come out as rows, every block knows its page, and split tables merge.

Thai text needs two special cases. Lines wrap without spaces, so a wrapped line
joins its predecessor without inserting one. And combining marks (vowels above
and below, tone marks) are separate glyphs, so any extraction that re-sorts
characters by position scrambles words; table cell text is therefore taken from
the content-stream lines that fall inside each cell, never from a position sort.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from ocl_api.ingest.docx_reader import merge_split_tables
from ocl_api.ingest.glyphs import map_pua_text, symbol_table
from ocl_api.ingest.model import Block, Document, Image, Paragraph, Table, heading_level

_WS = re.compile(r"[ \t ]+")
_PAGE_NO = re.compile(r"^[\d๐-๙]{1,4}$|^[ก-ฮ]$")
# "1. ", "2.1 ", "(ก) ", "- ", "• " at the start of a line begin a new paragraph
_STARTS_ITEM = re.compile(r"^\s*(\d+(\.\d+)*\.?\s|\([ก-ฮa-z\d]+\)\s|[-–•●]\s|หมวดที่\s|ภาคผนวก\s)")
SCANNED_TEXT_THRESHOLD = 30  # chars of text below which a page counts as scanned


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
    def __init__(self, path: str | Path, assets_dir: str | Path, *, render_scanned: bool = True):
        self.path = Path(path)
        self.assets_dir = Path(assets_dir)
        self.render_scanned = render_scanned
        self.unknown_symbols: dict[str, int] = {}
        self.notes: list[str] = []
        self._asset_by_xref: dict[int, str] = {}
        self.scanned_pages: list[int] = []

    def read(self) -> Document:
        blocks: list[Block] = []
        with pymupdf.open(self.path) as doc:
            for pno, page in enumerate(doc, start=1):
                blocks.extend(self._page_blocks(doc, page, pno))
            n_pages = doc.page_count
        blocks = merge_split_tables(blocks)
        out = Document(
            source_name=self.path.name,
            source_type="pdf",
            blocks=blocks,
            pages=n_pages,
            pages_declared=n_pages,
        )
        if self.unknown_symbols:
            out.notes.append(f"unknown symbol glyphs: {self.unknown_symbols}")
        if self.scanned_pages:
            out.notes.append(f"scanned pages (no text layer): {self.scanned_pages}")
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

        for y0, img in self._images(doc, page, pno):
            items.append((y0, order, img))
            order += 1

        if text_len < SCANNED_TEXT_THRESHOLD and not tables:
            self.scanned_pages.append(pno)
            if self.render_scanned:
                rel = self._render_page(page, pno)
                items.append((0.0, order, Image(path=rel, page=pno, alt=f"scanned page {pno}")))
                order += 1
                items.append(
                    (0.1, order, Paragraph(text=f"[หน้าสแกน {pno}: ไม่มีข้อความ ต้อง OCR]", page=pno))
                )

        items.sort(key=lambda t: (t[0], t[1]))
        return [b for _, _, b in items]

    def _lines(self, page: pymupdf.Page) -> list[_Line]:
        """Text lines in content-stream order (keeps Thai combining marks intact)."""
        out: list[_Line] = []
        for block in page.get_text("dict").get("blocks", []):
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
    ) -> list[tuple[float, Image]]:
        out: list[tuple[float, Image]] = []
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
            out.append((rect.y0, Image(path=rel, page=pno)))
        return out

    def _render_page(self, page: pymupdf.Page, pno: int) -> str:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        name = f"page-{pno:03d}.png"
        page.get_pixmap(dpi=150).save(str(self.assets_dir / name))
        return f"assets/{name}"
