#!/usr/bin/env python3
"""OCR-0: Tesseract (as the system runs it today) vs Typhoon OCR on Ollama, on scanned pages.

Each page of the scanned PDF is read twice:
  tesseract  PyMuPDF's built-in Tesseract, the same call as ocl_api.ingest.pdf_reader
             (tha+eng, 200 dpi, full page).
  typhoon    the page rendered with its longest side at 1800 px (what Typhoon OCR 1.5 was
             trained on), sent to Ollama /api/chat with the developer's v1.5 prompt.
When the text-layer PDF the scan was made from is given (--truth), its text of the same page
is the ground truth and each engine gets a character error rate (CER) after both sides are
normalised the same way (no whitespace, tags, Markdown marks or dot leaders). CER counts
reading order (a table read column by column scores badly), so an order-free character
3-gram F1 is reported next to it. Pages whose text is a picture in the truth PDF too (a
diagram) have no ground truth: --no-truth leaves them out of both, they are still read.

Shared-server rules (docs/brd/06-nfr.md · server constraints): never runs between 02:30 and
04:00 Thai time, refuses the HRIS model gemma4:12b, sends keep_alive "10m" and its own
num_ctx (the OCR model is OCL's own), records /api/ps before and after.

Run inside the API image so PyMuPDF and the Tesseract language data match production:
  docker compose -f deploy/docker-compose.yml run --rm --no-deps --user "$(id -u):$(id -g)" \\
    -v "$PWD/tools:/app/tools:ro" -v /home/arsoft/ocl-samples:/samples:ro \\
    -v /home/arsoft/ocl-bench:/out api python tools/ocr_bench.py \\
    --scan "/samples/<scan>.pdf" --truth "/samples/<text>.pdf" --out /out/ocr0

The v1.5 prompt is copied from scb-10x/typhoon-ocr packages/typhoon_ocr/typhoon_ocr/ocr_utils.py
(Apache-2.0); the model card says the model only works with that prompt.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

HRIS_PINNED_MODEL = "gemma4:12b"
DEFAULT_MODEL = "scb10x/typhoon-ocr1.5-3b"
TARGET_DIM = 1800
TESSERACT_DPI = 200  # ocl_api.ingest.pdf_reader.OCR_DPI
QUIET = (dt.time(2, 30), dt.time(4, 0))  # HRIS backup and model test (Thai time)
TH = dt.timezone(dt.timedelta(hours=7))

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
# the developer's sampling for v1.5 (temperature must stay at 0-0.1)
OPTIONS = {"temperature": 0.1, "top_p": 0.6, "repeat_penalty": 1.1, "num_predict": 8192}
NUM_CTX = 16384  # image ~3k tokens + output; the model's 125k default would reserve far more memory


# ---------- text normalisation and CER ----------

RE_FIGURE = re.compile(r"<figure>.*?</figure>", re.S)
RE_TAG = re.compile(r"<[^>]+>")
RE_FENCE = re.compile(r"^```[a-z]*\s*|```\s*$", re.M)
RE_LEADER = re.compile(r"…+|[.·_]{2,}")  # dot leaders of a table of contents, however read
RE_MD = re.compile(r"[#*|`>$\\]")


def md_to_text(md: str) -> str:
    """Typhoon's Markdown/HTML to the plain text a reader sees (figure descriptions dropped:
    they describe a picture, they are not text on the page)."""
    t = RE_FENCE.sub("", md)
    t = RE_FIGURE.sub(" ", t)
    t = re.sub(r"</(td|th|tr|p|li|h\d)>|<br\s*/?>", " ", t)
    t = RE_TAG.sub("", t)
    return html.unescape(t)


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFC", text).replace("ํา", "ำ")  # ํ+า -> ำ
    t = RE_LEADER.sub("", t)
    t = RE_MD.sub("", t)
    t = "".join(ch for ch in t if not (0xE000 <= ord(ch) <= 0xF8FF))  # symbol-font glyphs
    return re.sub(r"\s+", "", t)


def edit_distance(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        append = cur.append
        for j, cb in enumerate(b, 1):
            append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def ngram_f1(truth: str, hyp: str, n: int = 3) -> tuple[float | None, int, int, int]:
    """Order-free: (F1, shared n-grams, truth n-grams, output n-grams) on normalised text."""
    t, h = normalise(truth), normalise(hyp)
    a = Counter(t[i : i + n] for i in range(len(t) - n + 1))
    b = Counter(h[i : i + n] for i in range(len(h) - n + 1))
    if not a:
        return None, 0, 0, sum(b.values())
    both, nt, nh = sum((a & b).values()), sum(a.values()), sum(b.values())
    return (2 * both / (nt + nh) if nt + nh else 0.0), both, nt, nh


def cer(truth: str, hyp: str) -> tuple[float | None, int, int]:
    """(CER, edits, truth length) on normalised text; None when the page has no truth text."""
    t, h = normalise(truth), normalise(hyp)
    if not t:
        return None, 0, 0
    d = edit_distance(t, h)
    return d / len(t), d, len(t)


# ---------- engines ----------


def find_tessdata(lang: str) -> str | None:
    try:
        from ocl_api.ingest.pdf_reader import find_tessdata as f

        return f(lang)
    except Exception:  # noqa: BLE001 - outside the project venv
        return os.environ.get("TESSDATA_PREFIX")


def read_tesseract(page: Any, lang: str = "tha+eng") -> str:
    tp = page.get_textpage_ocr(
        language=lang, dpi=TESSERACT_DPI, full=True, tessdata=find_tessdata(lang)
    )
    return page.get_text(textpage=tp)


def render_png(page: Any, target: int = TARGET_DIM) -> bytes:
    import pymupdf

    z = target / max(page.rect.width, page.rect.height)
    return page.get_pixmap(matrix=pymupdf.Matrix(z, z)).tobytes("png")


def post_json(url: str, body: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - our own Ollama
        return json.loads(r.read())


def read_typhoon(png: bytes, base_url: str, model: str, timeout: float) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": [
            {"role": "user", "content": PROMPT_V15, "images": [base64.b64encode(png).decode()]}
        ],
        "stream": False,
        "keep_alive": "10m",
        "options": {**OPTIONS, "num_ctx": NUM_CTX},
    }
    r = post_json(f"{base_url.rstrip('/')}/api/chat", body, timeout)
    return {
        "text": r.get("message", {}).get("content", ""),
        "prompt_tokens": r.get("prompt_eval_count"),
        "output_tokens": r.get("eval_count"),
        "load_s": round((r.get("load_duration") or 0) / 1e9, 2),
        "done_reason": r.get("done_reason"),
    }


def ollama_ps(base_url: str) -> list[dict[str, Any]]:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/ps")
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
            ms = json.loads(r.read()).get("models", [])
    except (urllib.error.URLError, OSError, ValueError) as e:
        return [{"error": str(e)}]
    keep = ("name", "size", "size_vram", "expires_at", "context_length")
    return [{k: m.get(k) for k in keep} for m in ms]


# ---------- run ----------


def in_quiet_hours(now: dt.datetime | None = None) -> bool:
    t = (now or dt.datetime.now(TH)).astimezone(TH).time()
    return QUIET[0] <= t < QUIET[1]


def parse_pages(spec: str | None, count: int) -> list[int]:
    """'1-3,7' (1-based) -> [0, 1, 2, 6]; None -> every page."""
    if not spec:
        return list(range(count))
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.extend(range(int(a) - 1, int(b or a)))
    return [p for p in out if 0 <= p < count]


def run(args: argparse.Namespace) -> dict[str, Any]:
    import pymupdf

    scan = pymupdf.open(args.scan)
    truth = pymupdf.open(args.truth) if args.truth else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    engines = args.engines.split(",")
    no_truth = set(parse_pages(args.no_truth, scan.page_count)) if args.no_truth else set()
    no_truth = {p + 1 for p in no_truth}
    base = args.base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    result: dict[str, Any] = {
        "started": dt.datetime.now(TH).isoformat(timespec="seconds"),
        "scan": Path(args.scan).name,
        "truth": Path(args.truth).name if args.truth else None,
        "model": args.model,
        "engines": engines,
        "ps_before": ollama_ps(base) if "typhoon" in engines else None,
        "pages": [],
    }
    for i in parse_pages(args.pages, scan.page_count):
        page = scan[i]
        row: dict[str, Any] = {"page": i + 1}
        has_truth = truth is not None and (i + 1) not in no_truth
        ref = truth[i + args.truth_offset].get_text() if has_truth else ""
        if not has_truth and truth is not None:
            row["no_truth"] = True
        if has_truth:
            (out / f"page-{i + 1:02d}.truth.txt").write_text(ref, encoding="utf-8")
            row["truth_chars"] = len(normalise(ref))
        if "tesseract" in engines:
            t0 = time.perf_counter()
            text = read_tesseract(page)
            row["tesseract_s"] = round(time.perf_counter() - t0, 2)
            (out / f"page-{i + 1:02d}.tesseract.txt").write_text(text, encoding="utf-8")
            row["tesseract_cer"], row["tesseract_edits"], _ = cer(ref, text)
            row["tesseract_chars"] = len(normalise(text))
            _, row["tesseract_ng"], row["ng_truth"], row["tesseract_ng_out"] = ngram_f1(ref, text)
        if "typhoon" in engines:
            png = render_png(page, TARGET_DIM)
            t0 = time.perf_counter()
            try:
                r = read_typhoon(png, base, args.model, args.timeout)
            except (urllib.error.URLError, OSError, ValueError) as e:
                r = {"text": "", "error": str(e)}
            row["typhoon_s"] = round(time.perf_counter() - t0, 2)
            (out / f"page-{i + 1:02d}.typhoon.md").write_text(r["text"], encoding="utf-8")
            plain = md_to_text(r["text"])
            row["typhoon_cer"], row["typhoon_edits"], _ = cer(ref, plain)
            row["typhoon_chars"] = len(normalise(plain))
            _, row["typhoon_ng"], row["ng_truth"], row["typhoon_ng_out"] = ngram_f1(ref, plain)
            row.update({f"typhoon_{k}": v for k, v in r.items() if k != "text"})
            # much longer than the page: the model may have written text that is not there
            if has_truth and row["truth_chars"] and row["typhoon_chars"] > 1.3 * row["truth_chars"]:
                row["typhoon_suspect"] = True
        result["pages"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    if "typhoon" in engines:
        result["ps_after"] = ollama_ps(base)
    result["summary"] = summarise(result["pages"], engines)
    result["finished"] = dt.datetime.now(TH).isoformat(timespec="seconds")
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    (out / "summary.md").write_text(report(result), encoding="utf-8")
    return result


def summarise(pages: list[dict[str, Any]], engines: list[str]) -> dict[str, Any]:
    s: dict[str, Any] = {}
    truth = sum(p.get("truth_chars", 0) for p in pages if p.get("truth_chars"))
    for e in engines:
        secs = [p[f"{e}_s"] for p in pages if f"{e}_s" in p]
        edits = sum(p.get(f"{e}_edits", 0) for p in pages if p.get("truth_chars"))
        ng = sum(p.get(f"{e}_ng", 0) for p in pages if p.get("truth_chars"))
        ng_t = sum(p.get("ng_truth", 0) for p in pages if p.get("truth_chars"))
        ng_o = sum(p.get(f"{e}_ng_out", 0) for p in pages if p.get("truth_chars"))
        s[e] = {
            "cer": round(edits / truth, 4) if truth else None,
            "f1": round(2 * ng / (ng_t + ng_o), 4) if ng_t + ng_o else None,
            "mean_s": round(statistics.mean(secs), 2) if secs else None,
            "max_s": max(secs) if secs else None,
            "total_s": round(sum(secs), 1),
        }
    if "typhoon" in s:
        s["typhoon"]["suspect_pages"] = [p["page"] for p in pages if p.get("typhoon_suspect")]
        s["typhoon"]["errors"] = [p["page"] for p in pages if p.get("typhoon_error")]
    if {"tesseract", "typhoon"} <= set(s) and s["tesseract"]["cer"] and s["typhoon"]["cer"]:
        s["relative_gain"] = round(1 - s["typhoon"]["cer"] / s["tesseract"]["cer"], 3)
        s["gate"] = {
            "cer_30pct_lower": s["relative_gain"] >= 0.30,
            "no_suspect_pages": not s["typhoon"]["suspect_pages"],
            "mean_le_60s": (s["typhoon"]["mean_s"] or 0) <= 60,
        }
    return s


def report(r: dict[str, Any]) -> str:
    def pct(v: float | None) -> str:
        return "–" if v is None else f"{v:.1%}"

    def num(v: Any) -> str:
        return "–" if v is None else str(v)

    lines = [
        f"# OCR-0 · {r['scan']}",
        "",
        f"เริ่ม {r['started']} · จบ {r.get('finished')} · โมเดล `{r['model']}` · "
        f"ข้อความจริง {r['truth'] or 'ไม่มี'}",
        "",
        "| หน้า | ตัวอักษรจริง | CER Tesseract | CER Typhoon | วินาที Tesseract | วินาที Typhoon | หมายเหตุ |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in r["pages"]:
        note = " ".join(
            x
            for x in (
                "ไม่มีข้อความจริง (ภาพในเล่มต้นฉบับ)" if p.get("no_truth") else "",
                "ยาวเกินจริง" if p.get("typhoon_suspect") else "",
                f"ผิดพลาด: {p['typhoon_error']}" if p.get("typhoon_error") else "",
                f"หยุดเพราะ {p['typhoon_done_reason']}"
                if p.get("typhoon_done_reason") not in (None, "stop")
                else "",
            )
            if x
        )
        lines.append(
            f"| {p['page']} | {num(p.get('truth_chars'))} | {pct(p.get('tesseract_cer'))} | "
            f"{pct(p.get('typhoon_cer'))} | {num(p.get('tesseract_s'))} | "
            f"{num(p.get('typhoon_s'))} | {note} |"
        )
    s = r["summary"]
    lines += ["", "## สรุป", ""]
    for e, v in s.items():
        if isinstance(v, dict) and "cer" in v:
            lines.append(
                f"- **{e}** CER รวม {pct(v['cer'])} · 3-gram F1 {pct(v.get('f1'))} · เฉลี่ย {v['mean_s']} วินาที/หน้า · "
                f"สูงสุด {v['max_s']} · รวม {v['total_s']} วินาที"
            )
    if "relative_gain" in s:
        g = s["gate"]
        lines += [
            f"- Typhoon ผิดน้อยกว่า Tesseract {s['relative_gain']:.0%} (สัมพัทธ์)",
            f"- เกณฑ์ OCR-0: CER ต่ำกว่า ≥ 30% {'ผ่าน' if g['cer_30pct_lower'] else 'ไม่ผ่าน'} · "
            f"ไม่มีหน้ายาวเกินจริง {'ผ่าน' if g['no_suspect_pages'] else 'ไม่ผ่าน'} · "
            f"เฉลี่ย ≤ 60 วินาที {'ผ่าน' if g['mean_le_60s'] else 'ไม่ผ่าน'}",
        ]
    lines += ["", "## /api/ps", "", "ก่อน: `" + json.dumps(r.get("ps_before"), ensure_ascii=False)]
    lines[-1] += "`"
    lines.append("")
    lines.append("หลัง: `" + json.dumps(r.get("ps_after"), ensure_ascii=False) + "`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--scan", required=True, help="scanned PDF (pages without a text layer)")
    ap.add_argument("--truth", help="text-layer PDF the scan was made from (ground truth)")
    ap.add_argument("--truth-offset", type=int, default=0, help="truth page = scan page + N")
    ap.add_argument("--pages", help="1-based, e.g. 1-14 or 2,5")
    ap.add_argument("--no-truth", help="scan pages (1-based) to read but leave out of the scores")
    ap.add_argument("--engines", default="tesseract,typhoon")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", help="Ollama (default $OLLAMA_BASE_URL)")
    ap.add_argument("--timeout", type=float, default=600, help="seconds per page")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.model == HRIS_PINNED_MODEL:
        print(f"refused: {HRIS_PINNED_MODEL} belongs to HRIS", file=sys.stderr)
        return 2
    if "typhoon" in args.engines and in_quiet_hours():
        print("refused: 02:30-04:00 Thai time is reserved for HRIS backup/tests", file=sys.stderr)
        return 2
    r = run(args)
    print(report(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
