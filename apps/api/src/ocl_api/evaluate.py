"""Score an extraction run against a reference run (docs/plan.md R1-E).

The reference is the parser-first extraction of the digital book (checked by hand on
the sample books); a candidate is the same book extracted by a model, in
parser_first or llm_only mode. Only the four LLM-capable parts are scored, because
the other six are parser-only and identical for every model.

Metrics per part
  info       field accuracy over the fields the LLM may fill (LLM_FIELDS), counting
             a field only when the reference has a value
  plo        precision/recall on PLO codes + text similarity of matched codes
  structure  precision/recall on nodes (number) + credits accuracy of matched nodes
  courses    precision/recall on course codes + name/credit accuracy of matched codes
hallucinations = candidate items whose key is not in the reference (= 1 - precision).
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from ocl_api.extract.info import LLM_FIELDS

SCORED_PARTS = ("info", "structure", "plo", "courses")
# USD per 1M tokens on the day of the run; Gemma on the shared on-prem GPU has no cash cost
PRICES_USD_PER_M = {
    "gemini": {"input": 0.75, "output": 3.75},  # Gemini 3.8 Flash introductory (to 2026-12-31)
    "ollama": {"input": 0.0, "output": 0.0},
}
TEXT_MATCH_RATIO = 0.85

_WS = re.compile(r"\s+")


def norm(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    s = _WS.sub("", s)
    return s.replace("(", "").replace(")", "").replace("–", "-")


def similar(a: Any, b: Any) -> float:
    na, nb = norm(a), norm(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _flatten_tree(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for n in nodes or []:
        out[str(n.get("number", ""))] = n
        out.update(_flatten_tree(n.get("children") or []))
    return out


def _pr(ref_keys: set[str], cand_keys: set[str]) -> dict[str, Any]:
    tp = len(ref_keys & cand_keys)
    precision = tp / len(cand_keys) if cand_keys else (1.0 if not ref_keys else 0.0)
    recall = tp / len(ref_keys) if ref_keys else 1.0
    return {
        "ref": len(ref_keys),
        "cand": len(cand_keys),
        "matched": tp,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "hallucinated": sorted(cand_keys - ref_keys)[:20],
        "missed": sorted(ref_keys - cand_keys)[:20],
    }


def score_info(ref: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    rv, cv = ref.get("values") or {}, cand.get("values") or {}
    scored = [k for k in LLM_FIELDS if rv.get(k) not in (None, "")]
    wrong = []
    ok = 0
    for k in scored:
        if isinstance(rv[k], int) or isinstance(cv.get(k), int):
            match = str(rv[k]) == str(cv.get(k))
        else:
            match = similar(rv[k], cv.get(k)) >= TEXT_MATCH_RATIO
        if match:
            ok += 1
        else:
            wrong.append({"field": k, "ref": rv[k], "cand": cv.get(k)})
    extra = [k for k in LLM_FIELDS if k not in scored and cv.get(k) not in (None, "")]
    return {
        "fields": len(scored),
        "correct": ok,
        "accuracy": round(ok / len(scored), 3) if scored else None,
        "wrong": wrong,
        "unscored_extra": extra,
    }


def score_plo(ref: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    # books with study plans have PLO1..n per plan: match on (plan, code) there, code elsewhere
    by_plan = any(p.get("plan") for p in ref.get("plos") or [])

    def key(p: dict[str, Any]) -> str:
        return (norm(p.get("plan")) + "|" if by_plan else "") + norm(p.get("code"))

    r = {key(p): p for p in ref.get("plos") or []}
    c = {key(p): p for p in cand.get("plos") or []}
    out = _pr(set(r), set(c))
    matched = [k for k in r if k in c]
    text_ok = sum(similar(r[k].get("text"), c[k].get("text")) >= TEXT_MATCH_RATIO for k in matched)
    out["text_accuracy"] = round(text_ok / len(matched), 3) if matched else None
    return out


def score_structure(ref: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    r = _flatten_tree(ref.get("tree") or [])
    c = _flatten_tree(cand.get("tree") or [])
    # nodes are matched by name (numbers differ between parser and LLM numbering)
    rn = {norm(n.get("name")): n for n in r.values() if n.get("name")}
    cn = {norm(n.get("name")): n for n in c.values() if n.get("name")}
    out = _pr(set(rn), set(cn))
    matched = [k for k in rn if k in cn]
    cr_ok = sum(str(rn[k].get("credits")) == str(cn[k].get("credits")) for k in matched)
    out["credits_accuracy"] = round(cr_ok / len(matched), 3) if matched else None
    out["total_credits_match"] = (
        str(ref.get("total_credits")) == str(cand.get("total_credits"))
        if ref.get("total_credits") is not None
        else None
    )
    return out


def score_courses(ref: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    r = {norm(x.get("code_th")): x for x in ref.get("courses") or []}
    c = {norm(x.get("code_th")): x for x in cand.get("courses") or []}
    out = _pr(set(r), set(c))
    matched = [k for k in r if k in c]
    name_ok = sum(
        similar(r[k].get("name_th"), c[k].get("name_th")) >= TEXT_MATCH_RATIO for k in matched
    )
    en_scored = [k for k in matched if r[k].get("name_en")]
    en_ok = sum(
        similar(r[k].get("name_en"), c[k].get("name_en")) >= TEXT_MATCH_RATIO for k in en_scored
    )
    cr_scored = [k for k in matched if r[k].get("credits") is not None]
    cr_ok = sum(str(r[k].get("credits")) == str(c[k].get("credits")) for k in cr_scored)
    out["name_th_accuracy"] = round(name_ok / len(matched), 3) if matched else None
    out["name_en_accuracy"] = round(en_ok / len(en_scored), 3) if en_scored else None
    out["credits_accuracy"] = round(cr_ok / len(cr_scored), 3) if cr_scored else None
    return out


SCORERS = {
    "info": score_info,
    "plo": score_plo,
    "structure": score_structure,
    "courses": score_courses,
}


def score_run(ref_dir: Path, cand_dir: Path) -> dict[str, Any]:
    """Compare <cand_dir>/<part>.json with <ref_dir>/<part>.json for every scored part."""
    out: dict[str, Any] = {}
    for part in SCORED_PARTS:
        rp, cp = ref_dir / f"{part}.json", cand_dir / f"{part}.json"
        if not rp.exists() or not cp.exists():
            out[part] = None
            continue
        ref = json.loads(rp.read_text(encoding="utf-8"))["data"]
        cand = json.loads(cp.read_text(encoding="utf-8"))["data"]
        out[part] = SCORERS[part](ref, cand)
    return out


def cost_usd(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = PRICES_USD_PER_M.get(provider, {"input": 0.0, "output": 0.0})
    return round((prompt_tokens * p["input"] + completion_tokens * p["output"]) / 1e6, 4)


def run_usage(report: dict[str, Any]) -> dict[str, Any]:
    """Sum LLM usage over the parts of an extract report.json."""
    tot = {"calls": 0, "retries": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0}
    model = None
    for part in report.get("parts", {}).values():
        u = part.get("llm") or {}
        for k in tot:
            tot[k] += u.get(k, 0) or 0
        model = u.get("model") or model
    tot["seconds"] = round(tot["seconds"], 2)
    tot["model"] = model
    tot["extract_seconds"] = round(
        sum(p.get("seconds", 0) for p in report.get("parts", {}).values()), 2
    )
    return tot
