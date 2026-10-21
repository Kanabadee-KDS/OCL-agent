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
    0xA3: "□",  # empty check box (verified on the food-science PDF, page 156)
}

# keys are normalized font names: lowercase, letters and digits only
SYMBOL_FONTS = {"wingdings": WINGDINGS, "wingdings2": WINGDINGS2}


def normalize_font(name: str | None) -> str:
    """'Wingdings 2', 'Wingdings2', 'BCDMEE+Wingdings-Regular' -> 'wingdings2' / 'wingdings'."""
    n = (name or "").lower()
    if "+" in n:
        n = n.split("+", 1)[1]  # drop PDF subset prefix
    n = "".join(ch for ch in n if ch.isalnum())
    for suffix in ("regular", "bold", "italic"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n


def symbol_table(font: str | None) -> dict[int, str] | None:
    n = normalize_font(font)
    if n in SYMBOL_FONTS:
        return SYMBOL_FONTS[n]
    for key in sorted(SYMBOL_FONTS, key=len, reverse=True):
        if n.startswith(key):
            return SYMBOL_FONTS[key]
    return None


def map_symbol(font: str | None, code: int, unknown: dict[str, int] | None = None) -> str:
    """Return the Unicode replacement for a symbol-font code point.

    `code` may be given with the 0xF000 private-use offset (as in w:char="F09F")
    or without it. Unknown glyphs come back as a visible placeholder.
    """
    base = code & 0xFF if code >= 0xF000 else code
    table = symbol_table(font)
    if table and base in table:
        return table[base]
    key = f"{normalize_font(font) or '?'}:{base:02X}"
    if unknown is not None:
        unknown[key] = unknown.get(key, 0) + 1
    return f"⟨sym {key}⟩"


def map_pua_text(font: str | None, text: str, unknown: dict[str, int] | None = None) -> str:
    """Map private-use characters (U+F000..U+F0FF) in a run whose font is a symbol font."""
    table = symbol_table(font)
    if not text or table is None:
        return text
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if 0xF000 <= o <= 0xF0FF:
            out.append(map_symbol(font, o, unknown))
        elif 0x21 <= o <= 0xFF and o in table:
            # Word keeps the typed letter when a symbol font is applied to a normal run
            # (e.g. "R" in Wingdings 2 is a ticked box); map it like the w:sym code.
            out.append(table[o])
        else:
            out.append(ch)
    return "".join(out)
