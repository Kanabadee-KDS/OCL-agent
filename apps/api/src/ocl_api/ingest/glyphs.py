"""Symbol-font glyph mapping.

Curriculum books mark Curriculum Mapping cells with Wingdings glyphs (w:sym in
.docx, private-use code points in PDF text layers). Plain text extraction turns
them into blanks, which silently empties the most important table in the book.

The table below is the working assumption; D3 verifies each code against a
rendered page. Unknown codes are kept as a visible placeholder and counted in the
ingest report so they cannot disappear unnoticed.
"""

from __future__ import annotations

WINGDINGS: dict[int, str] = {
    0x6C: "●",  # l  black circle (filled bullet in mapping tables)
    0x6D: "○",  # m  circle
    0x6E: "■",  # n  black square
    0x6F: "□",  # o  square
    0x75: "◆",  # u  diamond
    0x76: "❖",  # v
    0x9F: "●",  # bullet (verified on the food-science PDF, page 56)
    0xA7: "▪",  # small square
    0xA8: "■",  # square
    0xFC: "✔",  # check mark
    0xFD: "☒",  # ballot box with x
    0xFE: "☑",  # ballot box with check
}

WINGDINGS2: dict[int, str] = {
    0x50: "☑",
    0x52: "☒",
    0xA3: "□",  # seen in ศศ.บ. ภูมิสังคม book; unverified
}

SYMBOL_FONTS = {"wingdings": WINGDINGS, "wingdings 2": WINGDINGS2}


def map_symbol(font: str | None, code: int, unknown: dict[str, int] | None = None) -> str:
    """Return the Unicode replacement for a symbol-font code point.

    `code` may be given with the 0xF000 private-use offset (as in w:char="F09F")
    or without it. Unknown glyphs come back as a visible placeholder.
    """
    base = code & 0xFF if code >= 0xF000 else code
    table = SYMBOL_FONTS.get((font or "").strip().lower())
    if table and base in table:
        return table[base]
    key = f"{font or '?'}:{base:02X}"
    if unknown is not None:
        unknown[key] = unknown.get(key, 0) + 1
    return f"⟨sym {key}⟩"


def map_pua_text(font: str | None, text: str, unknown: dict[str, int] | None = None) -> str:
    """Map private-use characters (U+F000..U+F0FF) in a run whose font is a symbol font."""
    if not text or (font or "").strip().lower() not in SYMBOL_FONTS:
        return text
    return "".join(
        map_symbol(font, ord(ch), unknown) if 0xF000 <= ord(ch) <= 0xF0FF else ch for ch in text
    )
