"""Render the Document model as Markdown (layer A: whole book, no LLM)."""

from __future__ import annotations

from ocl_api.ingest.model import Block, Document, Image, Paragraph, Section, Table


def _esc_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", "<br>").strip()


def render_table(t: Table) -> str:
    if not t.rows:
        return ""
    width = t.n_cols
    rows = [r + [""] * (width - len(r)) for r in t.rows]
    header = rows[0]
    lines = [
        "| " + " | ".join(_esc_cell(c) or " " for c in header) + " |",
        "|" + "|".join([" --- "] * width) + "|",
    ]
    for r in rows[1:]:
        lines.append("| " + " | ".join(_esc_cell(c) or " " for c in r) + " |")
    return "\n".join(lines)


def render_blocks(blocks: list[Block], *, page_markers: bool = True) -> str:
    out: list[str] = []
    last_page: int | None = None
    for b in blocks:
        if page_markers and b.page is not None and b.page != last_page:
            out.append(f"<!-- page: {b.page} -->")
            last_page = b.page
        if isinstance(b, Paragraph):
            if b.level:
                out.append("#" * min(b.level, 6) + " " + b.text)
            elif b.list_item:
                out.append("- " + b.text)
            else:
                out.append(b.text)
        elif isinstance(b, Table):
            out.append(render_table(b))
        elif isinstance(b, Image):
            out.append(f"![{b.alt or 'image'}]({b.path})")
    return "\n\n".join(out) + "\n"


def render_section(s: Section) -> str:
    head = f"# {s.title}\n\n" if s.kind != "front" else ""
    return head + render_blocks(s.blocks)


def render_book(doc: Document) -> str:
    parts = [f"<!-- source: {doc.source_name} · type: {doc.source_type} · pages≈{doc.pages} -->"]
    for s in doc.sections():
        parts.append(render_section(s).rstrip())
    return "\n\n".join(parts) + "\n"
