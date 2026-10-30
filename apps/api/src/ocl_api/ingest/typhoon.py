"""Typhoon OCR (OCR-1): read a scanned PDF page with a Thai document OCR model on Ollama.

OCR-0 (docs/plan.md) measured it against Tesseract on the 14-page scan: CER 18.4% -> 0.4% on
text pages, about 13 s a page. The model returns Markdown with HTML tables; this module turns
that into the Document model's blocks:

- every line of text is a paragraph (the model already joins wrapped lines), with the same
  heading rules as the text-layer reader, marked ``ocr=True`` (lower trust);
- ``<table>`` becomes a Table (``ocr=True``), cells under a rowspan/colspan left empty the way
  the text-layer reader leaves merged cells;
- ``<figure>`` is the model's own description of a picture, not text on the page: it is kept
  as an AI note on an Image block, which no extractor reads (decision 30 ต.ค.);
- ``<page_number>`` and bare page numbers are dropped.

The prompt is the developer's v1.5 prompt, verbatim (scb-10x/typhoon-ocr
packages/typhoon_ocr/typhoon_ocr/ocr_utils.py, Apache-2.0): the model card says the model only
works with it. OCR-0 also found the model "corrects" spelling it reads (a name lost its
missing ์) and misreads small diagram text fluently, so a reviewer still checks OCR pages.
"""

from __future__ import annotations

import base64
import difflib
import html
import re
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from typing import Any

import httpx
import pymupdf

from ocl_api.ingest.model import Block, Image, Paragraph, Table, heading_level

TARGET_DIM = 1800  # the model is trained on images whose longest side is 1800 px
NUM_CTX = 16384  # image ~3k tokens + output; the model's 128k default reserves far more memory
OPTIONS = {"temperature": 0.1, "top_p": 0.6, "repeat_penalty": 1.1, "num_predict": 8192}
AI_NOTE = "หมายเหตุ AI (คำบรรยายภาพ ไม่ใช่ข้อความในเล่ม)"

PROMPT_V15 = """Extract all text from the image.


Instructions:
- Only return the clean Markdown.
- Do not include any explanation or extra text.
- You must include all information on the page.


Formatting Rules:
- Tables: Render tables using <table>...</table> in clean HTML format.
- Equations: Render equations using LaTeX syntax with inline ($...$) and block ($$...$$).
- Images/Charts/Diagrams: Wrap any clearly defined visual areas (e.g. charts, diagrams, pictures) in:


<figure>
Describe the image's main elements (people, objects, text), note any contextual clues (place, event, culture), mention visible text and its meaning, provide deeper analysis when relevant (especially for financial charts, graphs, or documents), comment on style or architecture if relevant, then give a concise overall summary. Describe in Thai.
</figure>


- Page Numbers: Wrap page numbers in <page_number>...</page_number> (e.g., <page_number>14</page_number>).
- Checkboxes: Use ☐ for unchecked and ☑ for checked boxes.
    """


class TyphoonError(RuntimeError):
    """The page could not be read; the caller falls back to Tesseract."""


class TyphoonOcr:
    def __init__(self, base_url: str, model: str, *, timeout: float = 180.0, client=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = client

    def read_page(self, page: pymupdf.Page) -> str:
        z = TARGET_DIM / max(page.rect.width, page.rect.height)
        png = page.get_pixmap(matrix=pymupdf.Matrix(z, z)).tobytes("png")
        return self.read_png(png)

    def read_png(self, png: bytes) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": PROMPT_V15, "images": [base64.b64encode(png).decode()]}
            ],
            "stream": False,
            "keep_alive": "10m",  # OCL's own model: short, never the HRIS pin
            "options": {**OPTIONS, "num_ctx": NUM_CTX},
        }
        try:
            if self._client is not None:
                r = self._client.post(f"{self.base_url}/api/chat", json=body)
            else:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.post(f"{self.base_url}/api/chat", json=body)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TyphoonError(f"{type(e).__name__}: {e}") from e
        text = (data.get("message") or {}).get("content") or ""
        if data.get("done_reason") == "length":
            raise TyphoonError("output cut at the token limit (the model may be looping)")
        if not text.strip():
            raise TyphoonError("empty output")
        if _looping(text):
            raise TyphoonError("the same line repeats (the model is looping)")
        return text


def _looping(text: str, limit: int = 8) -> bool:
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 3]
    return any(lines.count(ln) > limit for ln in set(lines))


# ---------- Markdown / HTML -> blocks ----------

_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*$", re.M)
_PIECE = re.compile(r"(<table\b.*?</table>|<figure>.*?</figure>)", re.S | re.I)
_PAGE_TAG = re.compile(r"<page_number>.*?</page_number>", re.S | re.I)
_PAGE_NO = re.compile(r"^[\d๐-๙]{1,4}$|^[ก-ฮ]$")
_HEADING = re.compile(r"^(#{1,6})\s+")
_BULLET = re.compile(r"^[*\-+•]\s+")
_NUMBERED = re.compile(r"^(\d+(?:\.\d+)*\.?)\s+")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_TAG = re.compile(r"<[^>]+>")


def markdown_blocks(md: str, page: int, image_path: str | None = None) -> list[Block]:
    """Typhoon's Markdown for one page -> blocks in reading order."""
    md = _PAGE_TAG.sub("\n", _FENCE.sub("", md))
    out: list[Block] = []
    for piece in _PIECE.split(md):
        low = piece[:8].lower()
        if low.startswith("<table"):
            rows = parse_table(piece)
            if rows:
                out.append(Table(rows=rows, page=page, ocr=True))
        elif low.startswith("<figure"):
            note = _clean(_TAG.sub(" ", piece))
            if note:
                out.append(Image(path=image_path or "", page=page, alt=AI_NOTE, ai_note=note))
        else:
            out.extend(_text_paragraphs(piece, page))
    return out


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _text_paragraphs(text: str, page: int) -> list[Paragraph]:
    out: list[Paragraph] = []
    for raw in text.splitlines():
        line = _TAG.sub("", raw).strip()
        if not line or _PAGE_NO.match(line):
            continue
        heading = bool(_HEADING.match(line))
        line = _HEADING.sub("", line)
        bullet = bool(_BULLET.match(line))
        line = _BULLET.sub("", line)
        num = _NUMBERED.match(line)
        rest = line[num.end() :] if num else line
        # bold when everything after the item number is one **...** run
        bold = heading or bool(re.fullmatch(r"\*\*[^*]+\*\*:?", rest.strip()))
        line = _clean(_BOLD.sub(lambda m: m.group(1) or m.group(2), line))
        if num:  # "1.  รหัส" -> "1. รหัส" (the text-layer reader's spacing)
            line = re.sub(r"^(\d+(?:\.\d+)*\.?)\s+", r"\1 ", line)
        if not line or _PAGE_NO.match(line):
            continue
        align = "center" if heading else None
        out.append(
            Paragraph(
                text=line,
                page=page,
                level=heading_level(line, bold, align),
                bold=bold,
                align=align,
                list_item=bullet,
                ocr=True,
            )
        )
    return out


# ---------- OCR-2a1: cross-check with Tesseract ----------

HARD_PAGE = 0.80  # agreement below this: "หน้าอ่านยาก ตรวจทั้งหน้า" [สมมติ: ตกลง 30 ต.ค. Q2 ก]
# Tesseract loses Thai vowel and tone marks and splits ำ, so both texts are compared as their
# letters and digits only: a mark Typhoon adds (พิสุทธิ์) is not caught here, a letter it
# changes (ศรีวิกรณ์ -> ศรีวิภรณ์) or words it makes up are.
_SKIP = re.compile("[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]|[^\\w]|_")


def skeleton(text: str) -> tuple[str, list[int]]:
    """Letters and digits of `text` (ำ as า), with each one's index in `text`."""
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        ch = "า" if ch == "ำ" else ch
        if not _SKIP.match(ch):
            out.append(ch)
            idx.append(i)
    return "".join(out), idx


def unsupported(text: str, page: str) -> list[str]:
    """Parts of `text` (one paragraph or table cell) that the other engine's page text does
    not contain: letters outside every shared run of 2+ letters, widened by one letter so a
    single changed letter reads as a word piece."""
    sk, idx = skeleton(text)
    if len(sk) < 2:
        return []
    cov = [False] * len(sk)
    for a, _, size in difflib.SequenceMatcher(None, sk, page, autojunk=False).get_matching_blocks():
        if size >= 2:
            cov[a : a + size] = [True] * size
    out: list[str] = []
    i = 0
    while i < len(sk):
        if cov[i]:
            i += 1
            continue
        j = i
        while j < len(sk) and not cov[j]:
            j += 1
        lo, hi = idx[max(i - 1, 0)], idx[min(j, len(sk) - 1)]
        while hi + 1 < len(text) and _SKIP.match(text[hi + 1]) and not text[hi + 1].isspace():
            hi += 1  # keep the marks that sit on the last letter
        piece = text[lo : hi + 1].strip()
        if piece and piece not in out:
            out.append(piece)
        i = j
    return out


def agreement(a: str, b: str, n: int = 3) -> float:
    """Character 3-gram F1 between two texts' skeletons (order-free, 0-1)."""
    x, y = skeleton(a)[0], skeleton(b)[0]
    ca = Counter(x[i : i + n] for i in range(len(x) - n + 1))
    cb = Counter(y[i : i + n] for i in range(len(y) - n + 1))
    total = sum(ca.values()) + sum(cb.values())
    return 2 * sum((ca & cb).values()) / total if total else 1.0


def cross_check(blocks: list[Block], other: str) -> dict[str, Any]:
    """Mark on each block what `other` (Tesseract's text of the same page) does not support;
    return the page's agreement, flag count and whether it is hard to read."""
    page = skeleton(other)[0]
    texts: list[str] = []
    flags = 0
    for b in blocks:
        if isinstance(b, Paragraph):
            b.ocr_flags = unsupported(b.text, page)
            texts.append(b.text)
            flags += len(b.ocr_flags)
        elif isinstance(b, Table):
            b.ocr_flags = [f for row in b.rows for cell in row for f in unsupported(cell, page)]
            texts.extend(cell for row in b.rows for cell in row)
            flags += len(b.ocr_flags)
    score = round(agreement("\n".join(texts), other), 3)
    return {"agreement": score, "flags": flags, "hard": score < HARD_PAGE}


_ITEM = re.compile(r"^(\d+)\.\s+\S")


def promote_items(blocks: list[Block], pages: set[int]) -> int:
    """Typhoon bolds a chapter's item headings ("1.  **รหัส...**") on some pages and not on
    others ("11. อาจารย์ผู้รับผิดชอบ..."), and the extractors find items by their level-2
    heading. A short "N. ..." line on a Typhoon page becomes a heading only when N continues
    the chapter's items (last + 1 or + 2) and does not continue a list right before it
    ("3." after a plain "2."), so a numbered list inside an item stays a list.
    Returns how many were promoted."""
    last = 0
    listed: int | None = None  # number of the last "N." line left as a list item
    n = 0
    for b in blocks:
        if not isinstance(b, Paragraph):
            continue
        if b.level == 1:
            last, listed = 0, None
            continue
        m = _ITEM.match(b.text)
        if not m:
            continue
        k = int(m.group(1))
        if b.level == 2:
            last, listed = k, None
        elif (
            b.level == 0
            and b.ocr
            and b.page in pages
            and len(b.text) < 90
            and last < k <= last + 2
            and listed != k - 1
        ):
            b.level, b.bold, last, listed = 2, True, k, None
            n += 1
        elif b.level == 0:
            listed = k
    return n


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int]]] = []
        self._cell: list[str] | None = None
        self._span = (1, 1)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            if not self.rows:
                self.rows.append([])
            self._cell = []
            self._span = (_int(a.get("rowspan")), _int(a.get("colspan")))
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            text = "\n".join(
                re.sub(r"[ \t]+", " ", x).strip() for x in "".join(self._cell).split("\n")
            ).strip()
            self.rows[-1].append((text, *self._span))
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data.replace("\n", " "))


def _int(v: str | None) -> int:
    try:
        return max(1, min(int(v or 1), 50))
    except ValueError:
        return 1


def parse_table(markup: str) -> list[list[str]]:
    """HTML table -> rows of cell text; a cell spanning rows/columns fills its first slot and
    leaves the others empty, as the text-layer reader does for merged cells."""
    p = _TableParser()
    p.feed(markup)
    grid: dict[tuple[int, int], str] = {}
    taken: set[tuple[int, int]] = set()
    width = 0
    for r, row in enumerate(p.rows):
        c = 0
        for text, rs, cs in row:
            while (r, c) in taken:
                c += 1
            grid[(r, c)] = text
            for dr in range(rs):
                for dc in range(cs):
                    taken.add((r + dr, c + dc))
            c += cs
            width = max(width, c)
    rows = [[grid.get((r, c), "") for c in range(width)] for r in range(len(p.rows))]
    return [row for row in rows if any(x.strip() for x in row)]


def from_settings(settings) -> TyphoonOcr | None:  # noqa: ANN001 - ocl_api.config.Settings
    """The reader for scanned pages when OCR_ENGINE=typhoon, else None (Tesseract)."""
    if not settings.ocr or settings.ocr_engine != "typhoon":
        return None
    return TyphoonOcr(
        settings.ollama_base_url, settings.typhoon_model, timeout=settings.typhoon_timeout
    )
