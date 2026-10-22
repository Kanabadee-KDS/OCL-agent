from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from ocl_api.ingest.model import Block, Document, Image, Paragraph, Section, Table

Confidence = Literal["high", "medium", "low"]
ExtractMode = Literal["parser_first", "llm_only"]
# parser_first (production): parsers read the book, the LLM fills what they could not.
# llm_only (evaluation only): the four LLM-capable parts skip their parsers so a model's
# own reading can be scored against the parser reference (docs/plan.md R1-E).
EXTRACT_MODE: ContextVar[ExtractMode] = ContextVar("extract_mode", default="parser_first")


def llm_only() -> bool:
    return EXTRACT_MODE.get() == "llm_only"


By = Literal["parser", "llm", "merged"]


def meta(
    confidence: Confidence,
    page: int | None,
    snippet: str,
    *,
    by: By = "parser",
    inferred: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    m: dict[str, Any] = {
        "confidence": confidence,
        "source": {"page": page, "snippet": snippet[:160]},
        "by": by,
        "inferred": inferred,
    }
    if note:
        m["note"] = note
    return m


@dataclass
class Check:
    key: str
    status: Literal["pass", "warn", "fail", "info"]
    message: str
    part: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PartResult:
    key: str
    data: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    llm_usage: dict[str, Any] | None = None

    @property
    def empty(self) -> bool:
        return not any(v for k, v in self.data.items() if k != "meta")


# ---------- Document access ----------


def load_document(ingest_dir: str | Path) -> Document:
    """Rebuild a Document from the document.json written by `ocl ingest`."""
    d = json.loads((Path(ingest_dir) / "document.json").read_text(encoding="utf-8"))
    blocks: list[Block] = []
    for sec in d["sections"]:
        if sec["kind"] != "front":
            blocks.append(Paragraph(text=sec["title"], page=sec.get("page"), level=1, bold=True))
        for b in sec["blocks"]:
            kind = b.pop("kind", "paragraph")
            if kind == "table":
                blocks.append(Table(**b))
            elif kind == "image":
                blocks.append(Image(**b))
            else:
                blocks.append(Paragraph(**b))
    return Document(
        source_name=d["source_name"],
        source_type=d["source_type"],
        blocks=blocks,
        pages=d.get("pages"),
        pages_declared=d.get("pages_declared"),
        notes=d.get("notes", []),
    )


def chapter(doc: Document, number: str) -> Section | None:
    for s in doc.sections():
        if s.kind == "chapter" and s.number == number:
            return s
    return None


_H2 = re.compile(r"^\s*(\d+)\.\s")


def _is_h2(b: Block, loose: bool) -> bool:
    if not isinstance(b, Paragraph):
        return False
    if b.level == 2:
        return True
    # Some books do not bold their item headings; accept short "N. ..." lines then.
    return loose and b.level == 0 and len(b.text) < 90 and _H2.match(b.text) is not None


def subsection(blocks: list[Block], number: str) -> list[Block]:
    """Blocks under the level-2 heading "N. ..." until the next level-2 heading."""
    loose = sum(1 for b in blocks if isinstance(b, Paragraph) and b.level == 2) < 2
    out: list[Block] = []
    inside = False
    for b in blocks:
        if _is_h2(b, loose):
            m = _H2.match(b.text)  # type: ignore[union-attr]
            if inside and m and m.group(1) != number:
                break
            inside = bool(m and m.group(1) == number)
            continue
        if inside:
            out.append(b)
    return out


def paragraphs_text(blocks: list[Block], *, max_chars: int | None = None) -> str:
    """Flatten paragraphs only (tables excluded) for an LLM prompt."""
    text = "\n".join(
        ("#" * b.level + " " if b.level else "") + b.text
        for b in blocks
        if isinstance(b, Paragraph)
    )
    return text[:max_chars] if max_chars else text


def paragraphs(blocks: list[Block]) -> Iterator[Paragraph]:
    for b in blocks:
        if isinstance(b, Paragraph):
            yield b


def tables(blocks: list[Block]) -> Iterator[Table]:
    for b in blocks:
        if isinstance(b, Table):
            yield b


def blocks_text(blocks: list[Block], *, max_chars: int | None = None) -> str:
    """Flatten blocks to plain text for an LLM prompt (tables as pipe rows)."""
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, Paragraph):
            parts.append(("#" * b.level + " " if b.level else "") + b.text)
        elif isinstance(b, Table):
            parts.extend(" | ".join(r) for r in b.rows)
    text = "\n".join(parts)
    return text[:max_chars] if max_chars else text


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most max_chars."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for para in text.split("\n"):
        if size + len(para) + 1 > max_chars and cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(para)
        size += len(para) + 1
    if cur:
        chunks.append("\n".join(cur))
    return chunks


THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def to_int(s: str) -> int | None:
    s = s.translate(THAI_DIGITS).replace(",", "")
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None
