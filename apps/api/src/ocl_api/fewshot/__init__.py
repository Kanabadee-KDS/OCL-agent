"""Few-shot examples for the LLM-capable extraction parts (R1-E follow-up).

Each part has one JSON file next to this module (info.json, plo.json, courses.json) holding
examples cut from golden books: a short input in the same shape the plugin sends, and the
output a reviewer has confirmed against the book. The team reviews each example and sets
"status" to "approved" (docs/testing/fewshot-review-guide_ocl.md).

Which examples are sent is decided per extraction run (FEWSHOT_MODE):
  off       none (default; production behaviour is unchanged until results are measured)
  approved  only examples a reviewer approved
  all       approved + draft (for bench experiments before review)
An example is never sent while extracting the book it was cut from (leave-one-book-out),
so a book cannot be "taught" its own answers, and at most MAX_PER_PART are sent. A book
that exists as more than one file (the scanned sample is made from the food-science PDF)
lists the other file names in source.same_as, so every copy counts as the same book.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from functools import cache
from pathlib import Path
from typing import Any, Literal

FewshotMode = Literal["off", "approved", "all"]
FEWSHOT_MODE: ContextVar[FewshotMode] = ContextVar("fewshot_mode", default="off")
DIR = Path(__file__).parent
MAX_PER_PART = 2
STATUSES = ("draft", "approved", "rejected")


def book_key(name: str | None) -> str:
    """Compare book names without extension, spaces or punctuation."""
    stem = Path(name or "").stem
    return re.sub(r"[^0-9A-Za-zก-๙]+", "", stem).lower()


def source_keys(ex: dict[str, Any]) -> set[str]:
    """book_key of every file the example was cut from: source.book plus source.same_as."""
    src = ex.get("source") or {}
    names = [src.get("book"), *(src.get("same_as") or [])]
    return {k for k in map(book_key, names) if k}


@cache
def load(part: str) -> dict[str, Any]:
    p = DIR / f"{part}.json"
    if not p.exists():
        return {"part": part, "examples": []}
    return json.loads(p.read_text(encoding="utf-8"))


def fewshot_examples(
    part: str, source_name: str | None, mode: FewshotMode | None = None
) -> list[tuple[str, str]]:
    """(input, output-JSON) pairs to show the model before the real request."""
    mode = mode or FEWSHOT_MODE.get()
    if mode == "off":
        return []
    allowed = {"approved"} if mode == "approved" else {"approved", "draft"}
    me = book_key(source_name)
    out: list[tuple[str, str]] = []
    for ex in load(part).get("examples", []):
        if ex.get("status") not in allowed:
            continue
        if me and me in source_keys(ex):
            continue
        out.append((ex["input"], json.dumps(ex["output"], ensure_ascii=False)))
        if len(out) >= MAX_PER_PART:
            break
    return out


def narrow_fields(examples: list[tuple[str, str]], fields: list[str]) -> list[tuple[str, str]]:
    """Info examples ask for all 11 fields; the system asks only for the ones still missing.

    Rewrite each example's field list and answer to `fields`, so the shots match the real
    request. A one-field request shown 11-field answers made the local model echo a
    placeholder ("xxxxxxxxxxxxx") and then repeat characters until max_tokens.
    """
    head = "ให้ค่าของฟิลด์: " + ", ".join(fields)
    out = []
    for inp, ans in examples:
        data = json.loads(ans)
        inp = re.sub(r"ให้ค่าของฟิลด์: [^\n]*", lambda _m: head, inp, count=1)
        out.append((inp, json.dumps({k: data.get(k) for k in fields}, ensure_ascii=False)))
    return out


def fewshot_kw(part: str, source_name: str | None) -> dict[str, Any]:
    """`**fewshot_kw(...)` for gateway.chat_json: adds `examples=` only when there are some."""
    ex = fewshot_examples(part, source_name)
    return {"examples": ex} if ex else {}
