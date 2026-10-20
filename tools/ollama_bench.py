#!/usr/bin/env python3
"""Ollama benchmark for OCL Agent (stdlib only, no project imports).

Two modes:
  extract  long Thai prompt -> measures prompt tokens/s and generation tokens/s of the
           OCL model (default gemma4:26b) and projects the time per curriculum book.
  hris     short prompt against gemma4:12b -> p50/p95 latency as seen by HRIS. ALWAYS
           sends keep_alive=-1 and NEVER sends num_ctx for that model: an omitted
           keep_alive makes Ollama apply its 5-minute default (overriding HRIS's -1) and
           a different num_ctx forces a reload (docs/server-constraints.md rule 2).

Examples (run inside the project venv, outside 02:30-04:00):
  uv run python tools/ollama_bench.py --mode extract --runs 3 --out docs/bench/26b.jsonl
  uv run python tools/ollama_bench.py --mode hris --runs 20 --out docs/bench/hris-A.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
import urllib.error
import urllib.request

HRIS_PINNED_MODEL = "gemma4:12b"

# Generic Thai text written for this benchmark (not customer content). Repeated to
# reach the requested prompt size so token counts resemble a curriculum chapter.
THAI_SAMPLE = (
    "หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต "
    "1. จำนวนหน่วยกิตตลอดหลักสูตร ไม่น้อยกว่า 120 หน่วยกิต "
    "2. โครงสร้างหลักสูตร แบ่งเป็น หมวดวิชาศึกษาทั่วไป ไม่น้อยกว่า 30 หน่วยกิต "
    "หมวดวิชาเฉพาะ ไม่น้อยกว่า 84 หน่วยกิต ประกอบด้วย วิชาแกน 18 หน่วยกิต "
    "วิชาบังคับ 54 หน่วยกิต วิชาเลือก ไม่น้อยกว่า 12 หน่วยกิต และหมวดวิชาเลือกเสรี "
    "ไม่น้อยกว่า 6 หน่วยกิต "
    "3. รายวิชา ตัวอย่างเช่น ทดส101 การเรียนรู้ในศตวรรษที่ยี่สิบเอ็ด 3(2-2-5) "
    "ศึกษาแนวคิดการเรียนรู้ตลอดชีวิต ทักษะการสื่อสาร การทำงานเป็นทีม และการใช้เทคโนโลยี "
    "ดิจิทัลอย่างมีจริยธรรม ทดส102 คณิตศาสตร์พื้นฐานสำหรับวิทยาศาสตร์ 3(3-0-6) "
    "ศึกษาฟังก์ชัน ลิมิต อนุพันธ์ ปริพันธ์ และการประยุกต์ในงานวิทยาศาสตร์ "
    "4. แผนที่กระจายความรับผิดชอบของผลลัพธ์การเรียนรู้ของหลักสูตรสู่รายวิชา "
    "รายวิชา ทดส101 รับผิดชอบ PLO1 และ PLO3 รายวิชา ทดส102 รับผิดชอบ PLO2 "
)

EXTRACT_INSTRUCTION = (
    "จากข้อความด้านล่าง ให้สกัดเป็น JSON ที่มีคีย์ total_credits (จำนวนเต็ม), "
    "structure (รายการของ {name, credits}), courses (รายการของ {code, name_th, credit_text, plos}) "
    "ตอบเป็น JSON อย่างเดียว ไม่ต้องอธิบาย\n\n"
)

HRIS_PROMPT = "สรุปใน 1 ประโยค: การประเมินผลการปฏิบัติงานประจำปีควรพิจารณาอะไรบ้าง"


def http_json(url: str, payload: dict | None = None, timeout: float = 900) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def loaded_models(base: str) -> list[dict]:
    try:
        return http_json(f"{base}/api/ps", timeout=30).get("models", [])
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"!! cannot read /api/ps: {e}", file=sys.stderr)
        return []


def fmt_ps(models: list[dict]) -> str:
    if not models:
        return "(none)"
    return " · ".join(
        f"{m['name']} {m.get('size', 0) / 1e9:.1f}GB ctx={m.get('context_length')} "
        f"expires={str(m.get('expires_at', ''))[:19]}"
        for m in models
    )


def build_prompt(mode: str, prompt_chars: int) -> str:
    if mode == "hris":
        return HRIS_PROMPT
    body = THAI_SAMPLE
    while len(body) < prompt_chars:
        body += THAI_SAMPLE
    return EXTRACT_INSTRUCTION + body[:prompt_chars]


def chat(
    base: str,
    model: str,
    prompt: str,
    num_ctx: int | None,
    keep_alive: str | None,
    think: bool | None,
    max_tokens: int,
) -> tuple[dict, float]:
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0},
    }
    if num_ctx is not None:
        body["options"]["num_ctx"] = num_ctx
    if think is not None:
        body["think"] = think
    if keep_alive is not None:
        # Ollama wants -1 as a number (a "-1" string fails: missing unit in duration)
        body["keep_alive"] = -1 if str(keep_alive).strip() == "-1" else keep_alive
    t0 = time.perf_counter()
    resp = http_json(f"{base}/api/chat", body)
    return resp, time.perf_counter() - t0


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, round((p / 100) * (len(s) - 1))))
    return s[k]


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # readable live output inside tmux/pipes
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base", default="http://127.0.0.1:11434", help="Ollama base URL")
    ap.add_argument("--mode", choices=["extract", "hris"], default="extract")
    ap.add_argument(
        "--model", default=None, help="default: gemma4:26b (extract) / gemma4:12b (hris)"
    )
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--num-ctx", type=int, default=32768)
    ap.add_argument("--prompt-chars", type=int, default=12000, help="extract mode prompt size")
    ap.add_argument("--max-tokens", type=int, default=800)
    ap.add_argument(
        "--keep-alive",
        default=None,
        help="e.g. 10m. Default: 10m for non-HRIS models, never sent for gemma4:12b",
    )
    ap.add_argument(
        "--think",
        choices=["false", "true", "omit"],
        default="false",
        help="send think=false (default), think=true, or omit the field",
    )
    ap.add_argument("--book-chars", type=int, default=300000, help="chars per book for projection")
    ap.add_argument("--out", default=None, help="append JSONL results here")
    args = ap.parse_args()

    model = args.model or (HRIS_PINNED_MODEL if args.mode == "hris" else "gemma4:26b")
    keep_alive = args.keep_alive
    num_ctx: int | None = args.num_ctx
    if model == HRIS_PINNED_MODEL:
        if keep_alive not in (None, "-1"):
            print(
                f"!! refusing: keep_alive for {HRIS_PINNED_MODEL} must be -1 (HRIS pin)",
                file=sys.stderr,
            )
            return 2
        keep_alive = "-1"  # re-pin on every request; omitting it would apply the 5m default
        num_ctx = None  # never change the loaded context of the shared model (forces reload)
    elif keep_alive is None:
        keep_alive = "10m"
    think = {"false": False, "true": True, "omit": None}[args.think]

    now = dt.datetime.now()
    if dt.time(2, 30) <= now.time() <= dt.time(4, 0):
        print("!! refusing: 02:30-04:00 is the HRIS backup/model-test window", file=sys.stderr)
        return 2

    prompt = build_prompt(args.mode, args.prompt_chars)
    print(
        f"mode={args.mode} model={model} runs={args.runs} num_ctx={num_ctx} "
        f"keep_alive={keep_alive} think={think} prompt_chars={len(prompt)}"
    )
    print("ps BEFORE:", fmt_ps(loaded_models(args.base)))

    rows: list[dict] = []
    for i in range(args.runs):
        try:
            resp, wall = chat(args.base, model, prompt, num_ctx, keep_alive, think, args.max_tokens)
        except urllib.error.HTTPError as e:
            print(f"run {i + 1}: HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
            return 1
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"run {i + 1}: cannot reach {args.base}: {e}", file=sys.stderr)
            return 1
        content = resp.get("message", {}).get("content", "") or ""
        row = {
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "mode": args.mode,
            "model": model,
            "run": i + 1,
            "wall_s": round(wall, 3),
            "load_s": round(resp.get("load_duration", 0) / 1e9, 3),
            "prompt_tokens": resp.get("prompt_eval_count"),
            "prompt_s": round(resp.get("prompt_eval_duration", 0) / 1e9, 3),
            "gen_tokens": resp.get("eval_count"),
            "gen_s": round(resp.get("eval_duration", 0) / 1e9, 3),
            "done_reason": resp.get("done_reason"),
            "content_chars": len(content),
            "content_head": content[:120].replace("\n", " "),
            "num_ctx": num_ctx,
            "keep_alive": keep_alive,
            "think": think,
            "prompt_chars": len(prompt),
        }
        rows.append(row)
        p_tps = (row["prompt_tokens"] or 0) / row["prompt_s"] if row["prompt_s"] else float("nan")
        g_tps = (row["gen_tokens"] or 0) / row["gen_s"] if row["gen_s"] else float("nan")
        print(
            f"run {i + 1}: wall={row['wall_s']}s load={row['load_s']}s "
            f"prompt={row['prompt_tokens']}tok ({p_tps:.0f} tok/s) "
            f"gen={row['gen_tokens']}tok ({g_tps:.1f} tok/s) done={row['done_reason']} "
            f"chars={row['content_chars']} | {row['content_head'][:60]}"
        )
        if args.out:
            with open(args.out, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("ps AFTER: ", fmt_ps(loaded_models(args.base)))

    walls = [r["wall_s"] for r in rows]
    if args.mode == "hris":
        print(
            f"latency p50={pct(walls, 50):.2f}s p95={pct(walls, 95):.2f}s "
            f"mean={statistics.fmean(walls):.2f}s n={len(walls)}"
        )
        return 0

    steady = rows[1:] if len(rows) > 1 else rows  # drop first run (model load)
    p_tok = [r["prompt_tokens"] for r in steady if r["prompt_tokens"]]
    if not p_tok:
        print("no token stats returned; cannot project")
        return 1
    p_tps = statistics.fmean(r["prompt_tokens"] / r["prompt_s"] for r in steady if r["prompt_s"])
    g_tps = statistics.fmean(r["gen_tokens"] / r["gen_s"] for r in steady if r["gen_s"])
    chars_per_tok = statistics.fmean(r["prompt_chars"] / r["prompt_tokens"] for r in steady)
    book_tokens = args.book_chars / chars_per_tok
    # projection: read the book once (prompt) + emit ~15% of it as structured output
    gen_tokens = book_tokens * 0.15
    est_s = book_tokens / p_tps + gen_tokens / g_tps
    empty = sum(1 for r in rows if r["content_chars"] == 0)
    print(
        f"steady: prompt {p_tps:.0f} tok/s · gen {g_tps:.1f} tok/s · "
        f"{chars_per_tok:.2f} Thai chars/token"
    )
    print(
        f"projection for a {args.book_chars:,}-char book: ~{book_tokens:,.0f} prompt tokens "
        f"→ ~{est_s / 60:.1f} min (single pass, excluding retries)"
    )
    if empty:
        print(
            f"!! {empty}/{len(rows)} runs returned EMPTY content "
            "→ thinking not disabled? try --think omit/true"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
