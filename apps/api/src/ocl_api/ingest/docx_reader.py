"""Read a .docx into the Document model using only the standard library.

Why raw XML instead of python-docx: the books rely on things python-docx hides
or drops (w:sym glyphs, w:lastRenderedPageBreak page markers, tracked changes,
VML images, content controls), and each of those matters for a faithful Markdown
and for page citations.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ocl_api.ingest.glyphs import map_pua_text, map_symbol
from ocl_api.ingest.model import Block, Document, Image, Paragraph, Table, heading_level

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
V = "{urn:schemas-microsoft-com:vml}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"

_SKIP_TAGS = {W + "del", W + "instrText", W + "delText", W + "fldChar", W + "moveFrom"}
_WS = re.compile(r"[ \t ]+")


class DocxReader:
    """Streaming reader: body items in order, approximate page from rendered page breaks.

    Page counting uses only `w:lastRenderedPageBreak` (Word writes one at every
    rendered page boundary, including right after an explicit page break, so counting
    explicit breaks too would double-count). A table row that crosses a page carries
    one marker per cell, so increments are capped to one per row.
    """

    def __init__(self, path: str | Path, assets_dir: str | Path):
        self.path = Path(path)
        self.assets_dir = Path(assets_dir)
        self.page = 1
        self.unknown_symbols: dict[str, int] = {}
        self.notes: list[str] = []
        self._rels: dict[str, str] = {}
        self._asset_by_rel: dict[str, str] = {}
        self._pending_images: list[Image] = []
        self._zip: zipfile.ZipFile | None = None
        self._pm_for: ET.Element | None = None
        self._pm: dict[ET.Element, ET.Element] = {}
        self._first_text_page: int | None = None

    # ---------- public ----------

    def read(self) -> Document:
        with zipfile.ZipFile(self.path) as z:
            self._zip = z
            self._rels = self._read_rels(z)
            root = ET.fromstring(z.read("word/document.xml"))
            body = root.find(W + "body")
            if body is None:
                raise ValueError("word/document.xml has no w:body")
            blocks: list[Block] = []
            for el in self._iter_body_items(body):
                if el.tag == W + "p":
                    blocks.extend(self._paragraph(el))
                elif el.tag == W + "tbl":
                    blocks.append(self._table(el))
            declared = self._declared_pages(z)
            self._zip = None
        blocks = merge_split_tables(blocks)
        doc = Document(
            source_name=self.path.name,
            source_type="docx",
            blocks=blocks,
            pages=self.page,
            pages_declared=declared,
        )
        if self.unknown_symbols:
            doc.notes.append(f"unknown symbol glyphs: {self.unknown_symbols}")
        doc.notes.extend(self.notes)
        return doc

    # ---------- structure ----------

    def _iter_body_items(self, el: ET.Element):
        """Yield w:p / w:tbl in document order, descending into content controls."""
        for child in el:
            if child.tag in (W + "p", W + "tbl"):
                yield child
            elif child.tag in (W + "sdt", W + "sdtContent", W + "customXml", W + "smartTag"):
                yield from self._iter_body_items(child)
            # w:sectPr, w:bookmarkStart, ... are ignored

    def _paragraph(self, p: ET.Element) -> list[Block]:
        ppr = p.find(W + "pPr")
        align = None
        list_item = False
        if ppr is not None:
            jc = ppr.find(W + "jc")
            if jc is not None:
                align = jc.get(W + "val")
            list_item = ppr.find(W + "numPr") is not None
        text, all_bold = self._runs_text(p)
        page_of_text = self._first_text_page or self.page
        out: list[Block] = []
        clean = _WS.sub(" ", text).strip()
        if clean:
            level = heading_level(clean, all_bold, align)
            out.append(
                Paragraph(
                    text=clean,
                    page=page_of_text,
                    level=level,
                    bold=all_bold,
                    align=align,
                    list_item=list_item and level == 0,
                )
            )
        out.extend(self._pending_images)
        self._pending_images = []
        return out

    def _runs_text(self, p: ET.Element) -> tuple[str, bool]:
        """Concatenate run content in order; return (text, every_text_run_bold).

        Side effects: advances `self.page` on rendered page breaks, queues images,
        and records the page where the first visible character sits.
        """
        parts: list[str] = []
        bold_flags: list[bool] = []
        self._first_text_page = None
        # ElementTree.iter() is a flat pre-order walk, so deleted text (w:del) is
        # filtered per element via the parent map instead of by skipping subtrees.
        for el in p.iter():
            tag = el.tag
            if tag in _SKIP_TAGS:
                continue
            if tag in (W + "t", W + "sym") and self._inside_skipped(el, p):
                continue
            if tag == W + "t":
                run = self._enclosing_run(el, p)
                font = self._run_font(run)
                txt = map_pua_text(font, el.text or "", self.unknown_symbols)
                parts.append(txt)
                if txt.strip():
                    bold_flags.append(self._run_bold(run))
                    if self._first_text_page is None:
                        self._first_text_page = self.page
            elif tag == W + "sym":
                font = el.get(W + "font")
                code = int(el.get(W + "char", "0"), 16)
                parts.append(map_symbol(font, code, self.unknown_symbols))
                if self._first_text_page is None:
                    self._first_text_page = self.page
            elif tag == W + "tab":
                parts.append("\t")
            elif tag in (W + "br", W + "cr"):
                if el.get(W + "type") != "page":
                    parts.append("\n")
            elif tag == W + "noBreakHyphen":
                parts.append("-")
            elif tag == W + "lastRenderedPageBreak":
                self.page += 1
            elif tag == A + "blip":
                rid = el.get(R + "embed")
                if rid:
                    self._queue_image(rid)
            elif tag == V + "imagedata":
                rid = el.get(R + "id")
                if rid:
                    self._queue_image(rid)
        text = "".join(parts).replace("\t", " ")
        return text, bool(bold_flags) and all(bold_flags)

    # ElementTree has no parent pointers; build a small map per paragraph lazily.
    def _parent_map(self, p: ET.Element) -> dict[ET.Element, ET.Element]:
        if self._pm_for is not p:
            self._pm_for = p
            self._pm = {c: parent for parent in p.iter() for c in parent}
        return self._pm

    def _inside_skipped(self, el: ET.Element, p: ET.Element) -> bool:
        pm = self._parent_map(p)
        cur = el
        while cur is not p and cur in pm:
            cur = pm[cur]
            if cur.tag in (W + "del", W + "moveFrom"):
                return True
        return False

    def _enclosing_run(self, el: ET.Element, p: ET.Element) -> ET.Element | None:
        pm = self._parent_map(p)
        cur = el
        while cur is not p and cur in pm:
            cur = pm[cur]
            if cur.tag == W + "r":
                return cur
        return None

    @staticmethod
    def _run_bold(run: ET.Element | None) -> bool:
        if run is None:
            return False
        rpr = run.find(W + "rPr")
        if rpr is None:
            return False
        b = rpr.find(W + "b")
        if b is None:
            return False
        return b.get(W + "val", "true").lower() not in {"0", "false"}

    @staticmethod
    def _run_font(run: ET.Element | None) -> str | None:
        if run is None:
            return None
        rpr = run.find(W + "rPr")
        if rpr is None:
            return None
        rf = rpr.find(W + "rFonts")
        if rf is None:
            return None
        return rf.get(W + "ascii") or rf.get(W + "hAnsi") or rf.get(W + "cs")

    # ---------- tables ----------

    def _table(self, tbl: ET.Element) -> Table:
        page = self.page
        grid: list[list[str]] = []
        prev_row: list[str] = []
        for tr in tbl.findall(W + "tr"):
            row: list[str] = []
            col = 0
            page_before_row = self.page
            for tc in tr.findall(W + "tc"):
                tcpr = tc.find(W + "tcPr")
                span = 1
                vmerge = None
                if tcpr is not None:
                    gs = tcpr.find(W + "gridSpan")
                    if gs is not None:
                        span = int(gs.get(W + "val", "1"))
                    vm = tcpr.find(W + "vMerge")
                    if vm is not None:
                        vmerge = vm.get(W + "val", "continue")
                texts = []
                for p in tc.iter(W + "p"):
                    t, _ = self._runs_text(p)
                    t = _WS.sub(" ", t).strip()
                    if t:
                        texts.append(t)
                cell = "\n".join(texts)
                if vmerge == "continue" and not cell and col < len(prev_row):
                    cell = prev_row[col]  # carry merged value down (helps mapping tables)
                row.append(cell)
                for _ in range(span - 1):
                    row.append("")
                col += span
            grid.append(row)
            prev_row = row
            self.page = min(self.page, page_before_row + 1)
        width = max((len(r) for r in grid), default=0)
        for r in grid:
            r.extend([""] * (width - len(r)))
        return Table(rows=grid, page=page)

    # ---------- package parts ----------

    @staticmethod
    def _read_rels(z: zipfile.ZipFile) -> dict[str, str]:
        name = "word/_rels/document.xml.rels"
        if name not in z.namelist():
            return {}
        root = ET.fromstring(z.read(name))
        rels = {}
        for rel in root.findall(PR + "Relationship"):
            target = rel.get("Target", "")
            if rel.get("TargetMode") == "External":
                continue
            rels[rel.get("Id", "")] = target.lstrip("/")
        return rels

    @staticmethod
    def _declared_pages(z: zipfile.ZipFile) -> int | None:
        if "docProps/app.xml" not in z.namelist():
            return None
        m = re.search(rb"<Pages>(\d+)</Pages>", z.read("docProps/app.xml"))
        return int(m.group(1)) if m else None

    def _queue_image(self, rid: str) -> None:
        if rid in self._asset_by_rel:
            self._pending_images.append(Image(path=self._asset_by_rel[rid], page=self.page))
            return
        target = self._rels.get(rid)
        if not target or self._zip is None:
            self.notes.append(f"image relationship {rid} not found")
            return
        member = target if target.startswith("word/") else "word/" + target
        if member not in self._zip.namelist():
            self.notes.append(f"image part missing: {member}")
            return
        ext = Path(member).suffix.lower() or ".bin"
        n = len(self._asset_by_rel) + 1
        rel_path = f"assets/img-{n:03d}{ext}"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        (self.assets_dir / f"img-{n:03d}{ext}").write_bytes(self._zip.read(member))
        self._asset_by_rel[rid] = rel_path
        self._pending_images.append(Image(path=rel_path, page=self.page))


def merge_split_tables(blocks: list[Block]) -> list[Block]:
    """Merge consecutive tables that share the same header row (authors often split a
    long table per page). Only empty paragraphs may sit between the two parts."""
    out: list[Block] = []
    for b in blocks:
        if isinstance(b, Table) and b.rows:
            prev = _last_table(out)
            if (
                prev is not None
                and prev.n_cols == b.n_cols
                and len(prev.rows) >= 1
                and prev.rows[0] == b.rows[0]
            ):
                prev.rows.extend(b.rows[1:])
                prev.merged_from += 1
                continue
        out.append(b)
    return out


def _last_table(out: list[Block]) -> Table | None:
    for b in reversed(out):
        if isinstance(b, Table):
            return b
        if isinstance(b, Paragraph) and b.text.strip():
            return None
        if isinstance(b, Image):
            return None
    return None
