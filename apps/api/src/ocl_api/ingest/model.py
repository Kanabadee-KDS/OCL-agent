"""Document model shared by every reader (docx now, pdf in D3) and every consumer
(Markdown renderer in layer A, structured extraction plugins in layer B).

Every block carries the (approximate) source page so extracted values can cite
`{page, snippet}` later. Pages in .docx come from `w:lastRenderedPageBreak`
markers, which Word writes when it last paginated the file.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

BlockKind = Literal["paragraph", "table", "image"]

# Thai curriculum books (มคอ.2 style) use "หมวดที่ N" chapters and "ภาคผนวก X" appendices.
RE_CHAPTER = re.compile(r"^\s*หมวดที่\s*(\d+)\b")
RE_APPENDIX = re.compile(r"^\s*ภาคผนวก\s*([ก-ฮ])?\b")
RE_H2 = re.compile(r"^\s*(\d+)\.\s+\S")
RE_H3 = re.compile(r"^\s*(\d+\.\d+)\s+\S")
# Table-of-contents entry: leader dots and/or a bare page number at the end.
RE_TOC_LEADER = re.compile(r"(\.{3,}|…{2,}|(\.\s){3,})")
RE_TRAILING_PAGE = re.compile(r"\s\d{1,3}\s*$")


@dataclass
class Paragraph:
    text: str
    page: int | None = None
    level: int = 0  # 0 = body text, 1..3 = heading level
    bold: bool = False
    align: str | None = None
    list_item: bool = False
    ocr: bool = False  # text came from OCR of a scanned page (lower trust)
    kind: BlockKind = "paragraph"


@dataclass
class Table:
    rows: list[list[str]]
    page: int | None = None
    merged_from: int = 1  # how many source tables were merged into this one
    kind: BlockKind = "table"

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.rows), default=0)


@dataclass
class Image:
    path: str  # relative to the ingest output dir, e.g. "assets/img-001.png"
    page: int | None = None
    alt: str = ""
    kind: BlockKind = "image"


Block = Paragraph | Table | Image


@dataclass
class Section:
    number: str  # "front", "1".."8", "ก".."ฮ", or "appendix" for the cover page
    title: str
    kind: Literal["front", "chapter", "appendix", "other"]
    page: int | None = None
    blocks: list[Block] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return f"{self.kind}-{self.number}"


@dataclass
class Document:
    source_name: str
    source_type: Literal["docx", "pdf"]
    blocks: list[Block] = field(default_factory=list)
    pages: int | None = None  # counted from rendered page breaks
    pages_declared: int | None = None  # docProps/app.xml <Pages>, if present
    notes: list[str] = field(default_factory=list)
    scanned_pages: list[int] = field(default_factory=list)  # no text layer
    ocr_pages: list[int] = field(default_factory=list)  # scanned pages that were OCR'd

    def sections(self) -> list[Section]:
        """Split blocks at level-1 headings into front matter / chapters / appendices.

        Books list every chapter in a table of contents and on an appendix cover page,
        so the same number can start several candidate sections. The candidate with the
        most blocks is the real one; the others are folded back into the section before
        them as plain paragraphs.
        """
        out = self._split_sections()
        best: dict[tuple[str, str], int] = {}
        for i, s in enumerate(out):
            key = (s.kind, s.number)
            if s.kind in ("chapter", "appendix") and (
                key not in best or len(s.blocks) > len(out[best[key]].blocks)
            ):
                best[key] = i
        keep = set(best.values())
        merged: list[Section] = []
        for i, s in enumerate(out):
            if s.kind in ("chapter", "appendix") and i not in keep:
                if not merged:
                    merged.append(Section("front", "ส่วนหน้า", "front"))
                merged[-1].blocks.append(Paragraph(text=s.title, page=s.page, level=0))
                merged[-1].blocks.extend(s.blocks)
            else:
                merged.append(s)
        return [s for s in merged if s.blocks or s.kind != "front"]

    def _split_sections(self) -> list[Section]:
        out: list[Section] = [Section("front", "ส่วนหน้า", "front")]
        for b in self.blocks:
            if isinstance(b, Paragraph) and b.level == 1:
                title = b.text.strip()
                m = RE_CHAPTER.match(title)
                if m:
                    out.append(Section(m.group(1), title, "chapter", page=b.page))
                    continue
                m = RE_APPENDIX.match(title)
                if m:
                    out.append(Section(m.group(1) or "appendix", title, "appendix", page=b.page))
                    continue
                out.append(Section(f"h{len(out)}", title, "other", page=b.page))
                continue
            out[-1].blocks.append(b)
        return out

    def stats(self) -> dict[str, Any]:
        paragraphs = [b for b in self.blocks if isinstance(b, Paragraph)]
        tables = [b for b in self.blocks if isinstance(b, Table)]
        images = [b for b in self.blocks if isinstance(b, Image)]
        secs = self.sections()
        return {
            "paragraphs": len(paragraphs),
            "headings": sum(1 for p in paragraphs if p.level),
            "tables": len(tables),
            "tables_merged_from": sum(t.merged_from for t in tables),
            "table_rows": sum(len(t.rows) for t in tables),
            "images": len(images),
            "pages": self.pages,
            "pages_declared": self.pages_declared,
            "scanned_pages": len(self.scanned_pages),
            "ocr_pages": len(self.ocr_pages),
            "chapters": [s.number for s in secs if s.kind == "chapter"],
            "appendices": [s.number for s in secs if s.kind == "appendix"],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "pages": self.pages,
            "pages_declared": self.pages_declared,
            "notes": self.notes,
            "scanned_pages": self.scanned_pages,
            "ocr_pages": self.ocr_pages,
            "stats": self.stats(),
            "sections": [
                {
                    "number": s.number,
                    "title": s.title,
                    "kind": s.kind,
                    "page": s.page,
                    "blocks": [asdict(b) for b in s.blocks],
                }
                for s in self.sections()
            ],
        }


def heading_level(text: str, bold: bool, align: str | None) -> int:
    """Heuristic heading detection for books that use no Word heading styles."""
    t = text.strip()
    if not t or len(t) > 160 or RE_TOC_LEADER.search(t):
        return 0
    if RE_CHAPTER.match(t) or RE_APPENDIX.match(t):
        # "หมวดที่ 1 ข้อมูลทั่วไป 4" is a table-of-contents line, not the chapter start
        return 0 if RE_TRAILING_PAGE.search(t) else 1
    if t in {"สารบัญ", "คำนำ", "บทสรุป"} and (bold or align == "center"):
        return 1
    if bold and RE_H3.match(t):
        return 3
    if bold and RE_H2.match(t):
        return 2
    return 0
