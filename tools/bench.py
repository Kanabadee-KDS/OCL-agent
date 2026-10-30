#!/usr/bin/env python3
"""Gemini vs Gemma evaluation (docs/plan.md R1-E): run books through the extractor with
each provider and mode, score against the parser reference, write CSV/JSON/summary.

  uv run python tools/bench.py --books samples/curriculum --out docs/eval/run-2026-10-22 \
      --providers ollama,gemini --modes parser_first,llm_only

Settings come from .env (OLLAMA_*, GEMINI_API_KEY). Each book is ingested once
(<out>/<book>/ingest) and the reference is extracted once (<out>/<book>/ref, no LLM).
Runs that already have a report.json are skipped, so a crashed batch can resume.
Never run the Ollama legs between 02:30 and 04:00 (shared GPU rules).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

from ocl_api.config import get_settings
from ocl_api.evaluate import SCORED_PARTS, cost_usd, run_usage, score_run
from ocl_api.extract.pipeline import extract
from ocl_api.ingest.pipeline import ingest
from ocl_api.ingest.typhoon import from_settings as typhoon_ocr
from ocl_api.llm.gateway import LLMGateway

BOOK_EXT = {".docx", ".pdf"}


def slug(name: str) -> str:
    return re.sub(r"[^0-9A-Za-zก-๙]+", "-", name).strip("-")[:50]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--books", required=True, help="folder of .docx/.pdf books, or one file")
    ap.add_argument("--out", required=True, help="output folder (created)")
    ap.add_argument(
        "--providers",
        default="ollama,gemini",
        help="ollama, gemini, or parser (no LLM; sanity check)",
    )
    ap.add_argument("--modes", default="parser_first,llm_only")
    ap.add_argument("--parts", default=",".join(SCORED_PARTS), help="parts to extract/score")
    ap.add_argument("--only", default="", help="substring filter on book file names")
    ap.add_argument(
        "--fewshot",
        default="off",
        choices=["off", "approved", "all"],
        help="few-shot examples for LLM legs",
    )
    ap.add_argument("--repeat", type=int, default=1, help="run each LLM leg N times (variance)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N books")
    args = ap.parse_args()

    src = Path(args.books)
    books = sorted(
        p for p in ([src] if src.is_file() else src.iterdir()) if p.suffix.lower() in BOOK_EXT
    )
    if args.only:
        books = [b for b in books if args.only in b.name]
    if args.limit:
        books = books[: args.limit]
    if not books:
        print("no books found", file=sys.stderr)
        return 2
    providers = [p for p in args.providers.split(",") if p]
    modes = [m for m in args.modes.split(",") if m]
    parts = [p for p in args.parts.split(",") if p]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    rows: list[dict] = []
    started = dt.datetime.now().isoformat(timespec="seconds")

    for book in books:
        bdir = out / slug(book.stem)
        ingest_dir = bdir / "ingest"
        if not (ingest_dir / "document.json").exists():
            t0 = time.perf_counter()
            rep = ingest(
                book,
                ingest_dir,
                ocr=settings.ocr,
                ocr_language=settings.ocr_language,
                typhoon=typhoon_ocr(settings),
            )
            print(
                f"[ingest] {book.name}: {rep['pages']} pages, ocr {rep['ocr_pages']} in {time.perf_counter() - t0:.1f}s"
            )
        ref_dir = bdir / "ref"
        if not (ref_dir / "report.json").exists():
            extract(ingest_dir, parts=parts, gateway=None, out_dir=ref_dir)
            print(f"[ref] {book.name}: parser reference written")
        for provider in providers:
            for mode in modes:
                for rep_i in range(1, max(1, args.repeat) + 1):
                    suffix = ("" if args.fewshot == "off" else f"-fs-{args.fewshot}") + (
                        "" if rep_i == 1 else f"-r{rep_i}"
                    )
                    run_dir = bdir / f"{provider}-{mode}{suffix}"
                    rep_path = run_dir / "report.json"
                    if rep_path.exists():
                        print(f"[skip] {book.name} {provider}/{mode} (exists)")
                    else:
                        if provider == "parser":  # sanity leg: must score 1.0 against the reference
                            if mode != "parser_first":
                                continue
                            gw = None
                        else:
                            gw = LLMGateway(settings.model_copy(update={"llm_provider": provider}))
                        t0 = time.perf_counter()
                        try:
                            extract(
                                ingest_dir,
                                parts=parts,
                                gateway=gw,
                                out_dir=run_dir,
                                mode=mode,
                                fewshot=args.fewshot,
                            )  # type: ignore[arg-type]
                            status = "ok"
                        except Exception as e:  # keep going with the other legs
                            status = f"error: {e}"[:300]
                            run_dir.mkdir(parents=True, exist_ok=True)
                            (run_dir / "error.txt").write_text(status, encoding="utf-8")
                            print(
                                f"[fail] {book.name} {provider}/{mode}: {status}", file=sys.stderr
                            )
                        print(
                            f"[run] {book.name} {provider}/{mode}: {status} in {time.perf_counter() - t0:.1f}s"
                        )
                    if not rep_path.exists():
                        rows.append(
                            {
                                "book": book.name,
                                "provider": provider,
                                "mode": mode,
                                "run": rep_i,
                                "status": "error",
                            }
                        )
                        continue
                    report = json.loads(rep_path.read_text(encoding="utf-8"))
                    usage = run_usage(report)
                    scores = score_run(ref_dir, run_dir)
                    row = {
                        "book": book.name,
                        "provider": provider,
                        "model": usage["model"] or report.get("model"),
                        "mode": mode,
                        "run": rep_i,
                        "status": "ok",
                        "extract_seconds": usage["extract_seconds"],
                        "llm_seconds": usage["seconds"],
                        "llm_calls": usage["calls"],
                        "llm_retries": usage["retries"],
                        "prompt_tokens": usage["prompt_tokens"],
                        "completion_tokens": usage["completion_tokens"],
                        "cost_usd": cost_usd(
                            provider, usage["prompt_tokens"], usage["completion_tokens"]
                        ),
                    }
                    info, plo, st, co = (
                        scores.get(k) or {} for k in ("info", "plo", "structure", "courses")
                    )
                    row.update(
                        info_accuracy=info.get("accuracy"),
                        plo_precision=plo.get("precision"), plo_recall=plo.get("recall"), plo_text=plo.get("text_accuracy"),
                        structure_precision=st.get("precision"), structure_recall=st.get("recall"), structure_credits=st.get("credits_accuracy"),
                        courses_precision=co.get("precision"), courses_recall=co.get("recall"),
                        courses_name_th=co.get("name_th_accuracy"), courses_credits=co.get("credits_accuracy"),
                    )  # fmt: skip
                    rows.append(row)
                    (run_dir / "scores.json").write_text(
                        json.dumps(scores, ensure_ascii=False, indent=1), encoding="utf-8"
                    )

    cols = sorted(
        {k for r in rows for k in r},
        key=lambda k: (k not in ("book", "provider", "model", "mode", "run", "status"), k),
    )
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    (out / "results.json").write_text(
        json.dumps(
            {
                "started": started,
                "providers": providers,
                "modes": modes,
                "parts": parts,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    (out / "summary.md").write_text(summary_md(rows, started), encoding="utf-8")
    print(f"wrote {out / 'results.csv'}, results.json, summary.md ({len(rows)} rows)")
    return 0


def _avg(rows: list[dict], key: str) -> str:
    vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
    return f"{sum(vals) / len(vals):.3f}" if vals else "–"


def summary_md(rows: list[dict], started: str) -> str:
    lines = [
        f"# Gemini vs Gemma · bench {started}",
        "",
        "ค่าเฉลี่ยต่อ provider/โหมด (เทียบกับ reference = parser จากเล่มดิจิทัล) · รายละเอียดต่อเล่มใน results.csv",
        "",
        "| provider | mode | books | info acc | PLO P/R | structure P/R | courses P/R | courses name/credits | LLM s/เล่ม | tokens in/out ต่อเล่ม | USD/เล่ม |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if r.get("status") == "ok":
            groups.setdefault((r["provider"], r["mode"]), []).append(r)
    for (prov, mode), g in sorted(groups.items()):
        lines.append(
            f"| {prov} ({g[0].get('model')}) | {mode} | {len(g)} | {_avg(g, 'info_accuracy')} | {_avg(g, 'plo_precision')}/{_avg(g, 'plo_recall')} "
            f"| {_avg(g, 'structure_precision')}/{_avg(g, 'structure_recall')} | {_avg(g, 'courses_precision')}/{_avg(g, 'courses_recall')} "
            f"| {_avg(g, 'courses_name_th')}/{_avg(g, 'courses_credits')} | {_avg(g, 'llm_seconds')} | {_avg(g, 'prompt_tokens')}/{_avg(g, 'completion_tokens')} | {_avg(g, 'cost_usd')} |"
        )
    errs = [r for r in rows if r.get("status") != "ok"]
    if errs:
        lines += [
            "",
            "ล้มเหลว: " + ", ".join(f"{r['book']} {r['provider']}/{r['mode']}" for r in errs),
        ]
    lines += [
        "",
        "หมายเหตุ: parser_first = ความแม่นยำของระบบจริง · llm_only = ความแม่นยำของโมเดลเอง · reference ยังต้องให้ Admin spot-check (E3)",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
