"""R1-E: llm_only mode and the scorer that compares a run with the parser reference."""

from __future__ import annotations

import json
from pathlib import Path

from ocl_api.evaluate import (
    cost_usd,
    run_usage,
    score_courses,
    score_info,
    score_plo,
    score_run,
    score_structure,
)
from ocl_api.extract.base import EXTRACT_MODE, llm_only
from ocl_api.extract.pipeline import extract
from ocl_api.extract.plo import extract_plo
from ocl_api.ingest.model import Document, Paragraph
from tests.test_extract import FakeGateway


def _doc() -> Document:
    return Document(
        source_name="x.docx",
        source_type="docx",
        blocks=[
            Paragraph(text="หมวดที่ 3 ผลลัพธ์การเรียนรู้", level=1, page=10),
            Paragraph(text="PLO1 อธิบายหลักการทางวิทยาศาสตร์ได้", page=10),
            Paragraph(text="PLO2 ใช้เครื่องมือวิเคราะห์ได้", page=10),
        ],
    )


def test_llm_only_skips_parser_and_uses_gateway() -> None:
    gw = FakeGateway({"plos": [{"code": "PLO1", "text": "จากโมเดล", "sub_plos": []}]})
    parser = extract_plo(_doc(), gw)
    assert [p["code"] for p in parser.data["plos"]] == ["PLO1", "PLO2"], "parser wins by default"
    assert parser.llm_usage is None
    token = EXTRACT_MODE.set("llm_only")
    try:
        assert llm_only()
        only = extract_plo(_doc(), gw)
    finally:
        EXTRACT_MODE.reset(token)
    assert [p["code"] for p in only.data["plos"]] == ["PLO1"]
    assert only.data["plos"][0]["meta"]["by"] == "llm" and only.llm_usage is not None
    assert not llm_only()


def test_scorers() -> None:
    ref = {
        "values": {
            "name_th": "หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาเคมี",
            "total_credits": 130,
            "program_code": None,
        }
    }
    cand = {
        "values": {
            "name_th": "หลักสูตร วิทยาศาสตรบัณฑิต สาขาวิชาเคมี",
            "total_credits": 120,
            "program_code": "123",
        }
    }
    s = score_info(ref, cand)
    assert s["fields"] == 2 and s["correct"] == 1 and s["accuracy"] == 0.5
    assert s["wrong"][0]["field"] == "total_credits" and s["unscored_extra"] == ["program_code"]

    s = score_plo(
        {"plos": [{"code": "PLO1", "text": "อธิบายได้"}, {"code": "PLO2", "text": "ใช้เครื่องมือ"}]},
        {"plos": [{"code": "PLO1", "text": "อธิบายได้"}, {"code": "PLO9", "text": "แต่งเอง"}]},
    )
    assert (
        s["precision"] == 0.5
        and s["recall"] == 0.5
        and s["hallucinated"] == ["plo9"]
        and s["text_accuracy"] == 1.0
    )

    s = score_structure(
        {
            "total_credits": 130,
            "tree": [
                {
                    "number": "1",
                    "name": "หมวดวิชาศึกษาทั่วไป",
                    "credits": 30,
                    "children": [
                        {"number": "1.1", "name": "กลุ่มภาษา", "credits": 12, "children": []}
                    ],
                }
            ],
        },
        {
            "total_credits": 130,
            "tree": [
                {
                    "number": "A",
                    "name": "หมวดวิชาศึกษาทั่วไป",
                    "credits": 30,
                    "children": [
                        {"number": "A.1", "name": "กลุ่มภาษา", "credits": 9, "children": []}
                    ],
                }
            ],
        },
    )
    assert (
        s["recall"] == 1.0
        and s["precision"] == 1.0
        and s["credits_accuracy"] == 0.5
        and s["total_credits_match"] is True
    )

    s = score_courses(
        {
            "courses": [
                {
                    "code_th": "คม101",
                    "name_th": "เคมีทั่วไป",
                    "name_en": "General Chemistry",
                    "credits": 3,
                },
                {"code_th": "คม102", "name_th": "เคมีอินทรีย์", "name_en": None, "credits": 3},
            ]
        },
        {
            "courses": [
                {
                    "code_th": "คม101",
                    "name_th": "เคมี ทั่วไป",
                    "name_en": "General Chemistry",
                    "credits": 3,
                }
            ]
        },
    )
    assert (
        s["recall"] == 0.5
        and s["precision"] == 1.0
        and s["name_th_accuracy"] == 1.0
        and s["name_en_accuracy"] == 1.0
        and s["credits_accuracy"] == 1.0
    )

    assert (
        cost_usd("gemini", 1_000_000, 100_000) == 0.75 + 0.375 and cost_usd("ollama", 5, 5) == 0.0
    )
    u = run_usage(
        {
            "parts": {
                "info": {
                    "seconds": 1.5,
                    "llm": {
                        "calls": 1,
                        "prompt_tokens": 10,
                        "completion_tokens": 2,
                        "seconds": 1.0,
                        "retries": 0,
                        "model": "m",
                    },
                },
                "plo": {"seconds": 0.2},
            }
        }
    )
    assert (
        u["calls"] == 1
        and u["prompt_tokens"] == 10
        and u["model"] == "m"
        and u["extract_seconds"] == 1.7
    )


def test_score_run_and_pipeline_mode(tmp_path: Path) -> None:
    ingest_dir = tmp_path / "ingest"
    ingest_dir.mkdir()
    (ingest_dir / "document.json").write_text(
        json.dumps(_doc().to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    ref = extract(ingest_dir, parts=["plo"], gateway=None, out_dir=tmp_path / "ref")
    assert ref["mode"] == "parser_first"
    gw = FakeGateway(
        {"plos": [{"code": "PLO1", "text": "อธิบายหลักการทางวิทยาศาสตร์ได้", "sub_plos": []}]}
    )
    cand = extract(
        ingest_dir, parts=["plo"], gateway=gw, out_dir=tmp_path / "cand", mode="llm_only"
    )
    assert cand["mode"] == "llm_only" and cand["parts"]["plo"]["count"] == 1
    scores = score_run(tmp_path / "ref", tmp_path / "cand")
    assert (
        scores["plo"]["recall"] == 0.5
        and scores["plo"]["precision"] == 1.0
        and scores["info"] is None
    )
    try:
        extract(ingest_dir, parts=["plo"], gateway=None, out_dir=tmp_path / "bad", mode="llm_only")
        raise AssertionError("llm_only without gateway must fail")
    except ValueError:
        pass
