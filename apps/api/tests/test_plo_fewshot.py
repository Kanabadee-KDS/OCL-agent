"""PLO per study plan, and few-shot examples (loader, leave-one-book-out, gateway messages)."""

from __future__ import annotations

import json

import httpx
import pytest

import ocl_api.fewshot as fs
from ocl_api.config import Settings
from ocl_api.evaluate import score_plo
from ocl_api.extract.plo import extract_plo, split_llm_code
from ocl_api.extract.render import render_plo
from ocl_api.fewshot import FEWSHOT_MODE, book_key, fewshot_examples, fewshot_kw
from ocl_api.ingest.model import Document, Paragraph, Table
from ocl_api.llm.gateway import LLMGateway


def _doc(blocks: list) -> Document:
    return Document(source_name="ศศ.ม. ทดสอบ (ปป.69).docx", source_type="docx",
                    blocks=[Paragraph(text="หมวดที่ 3 ผลลัพธ์การเรียนรู้", level=1, page=19), *blocks])  # fmt: skip


def test_plos_are_kept_per_plan() -> None:
    doc = _doc([
        Paragraph(text="1.1 เมื่อนิสิตจบการศึกษาแผน 1 แบบวิชาการ จะสามารถ", page=19),
        Paragraph(text="PLO1 วิเคราะห์แนวโน้มเศรษฐกิจ", page=19),
        Paragraph(text="PLO2 สร้างผลงานวิจัย", page=19),
        Table(rows=[["ผลลัพธ์การเรียนรู้", "ด้านความรู้ (K)"], ["PLO1: วิเคราะห์แนวโน้มเศรษฐกิจ และใช้เครื่องมือ", "K1-1"]], page=19),
        Paragraph(text="1.2 เมื่อนิสิตจบการศึกษาแผน 2 แบบวิชาชีพ จะสามารถ", page=20),
        Paragraph(text="PLO1 ประยุกต์ใช้เศรษฐศาสตร์ธุรกิจ", page=20),
        Paragraph(text="PLO2 วิเคราะห์ข้อมูลเชิงปริมาณ", page=20),
    ])  # fmt: skip
    r = extract_plo(doc)
    got = [(p["plan"], p["code"]) for p in r.data["plos"]]
    assert got == [
        ("แผน 1 แบบวิชาการ", "PLO1"),
        ("แผน 1 แบบวิชาการ", "PLO2"),
        ("แผน 2 แบบวิชาชีพ", "PLO1"),
        ("แผน 2 แบบวิชาชีพ", "PLO2"),
    ]
    assert r.data["plans"] == ["แผน 1 แบบวิชาการ", "แผน 2 แบบวิชาชีพ"] and r.data["count"] == 4
    assert r.data["plos"][0]["text"].endswith("และใช้เครื่องมือ"), (
        "longer table text wins within the same plan"
    )
    assert r.data["plos"][2]["text"] == "ประยุกต์ใช้เศรษฐศาสตร์ธุรกิจ"
    md = render_plo(r.data)
    assert "## แผน 1 แบบวิชาการ" in md and "## แผน 2 แบบวิชาชีพ" in md


def test_single_plo_set_ignores_later_plan_headings() -> None:
    # ปร.ด. layout: PLOs first, then year-level outcomes per plan that must not split the PLOs
    doc = _doc([
        Paragraph(text="PLO1: สังเคราะห์แนวคิดทฤษฎี", page=22),
        Paragraph(text="PLO2: ให้ข้อเสนอแนะเชิงนโยบาย", page=22),
        Paragraph(text="2.1 แผน 1 เน้นการทำวิจัย", page=24),
        Table(rows=[["ชั้นปี", "รายละเอียด"], ["PLO1: สังเคราะห์แนวคิดทฤษฎีทางเศรษฐศาสตร์", "-"]], page=24),
    ])  # fmt: skip
    r = extract_plo(doc)
    assert [(p["plan"], p["code"]) for p in r.data["plos"]] == [(None, "PLO1"), (None, "PLO2")]
    assert r.data["plans"] == []


def test_split_llm_code_and_plan_scoring() -> None:
    assert split_llm_code("PLO1 แผน1 แบบวิชาการ", None) == ("PLO1", "แผน 1 แบบวิชาการ")
    assert split_llm_code("PLO2", "แผน 2 แบบวิชาชีพ") == ("PLO2", "แผน 2 แบบวิชาชีพ")
    ref = {
        "plos": [
            {"plan": "แผน 1", "code": "PLO1", "text": "ก"},
            {"plan": "แผน 2", "code": "PLO1", "text": "ข"},
        ]
    }
    cand = {
        "plos": [
            {"plan": "แผน 1", "code": "PLO1", "text": "ก"},
            {"plan": "แผน 2", "code": "PLO1", "text": "ข"},
        ]
    }
    s = score_plo(ref, cand)
    assert s["recall"] == 1.0 and s["precision"] == 1.0 and s["text_accuracy"] == 1.0
    single = score_plo(
        {"plos": [{"code": "PLO1", "text": "ก"}]},
        {"plos": [{"code": "PLO1", "plan": "x", "text": "ก"}]},
    )
    assert single["recall"] == 1.0, "plan is ignored when the reference has no plans"


@pytest.fixture
def shots(tmp_path, monkeypatch):
    data = {"part": "plo", "examples": [
        {"id": "plo-01", "status": "approved", "source": {"book": "ศศ.ม. ทดสอบ (ปป.69).docx"}, "input": "A", "output": {"plos": [1]}},
        {"id": "plo-02", "status": "draft", "source": {"book": "ปร.ด. อื่น.docx"}, "input": "B", "output": {"plos": [2]}},
        {"id": "plo-03", "status": "approved", "source": {"book": "วท.บ. อื่น.docx"}, "input": "C", "output": {"plos": [3]}},
        {"id": "plo-04", "status": "rejected", "source": {"book": "วท.บ. อีก.docx"}, "input": "D", "output": {"plos": [4]}},
    ]}  # fmt: skip
    (tmp_path / "plo.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(fs, "DIR", tmp_path)
    fs.load.cache_clear()
    yield
    fs.load.cache_clear()


def test_fewshot_modes_and_leave_one_book_out(shots) -> None:
    book = "ศศ.ม. ทดสอบ (ปป.69).docx"
    assert fewshot_examples("plo", book) == [], "off by default"
    assert [i for i, _ in fewshot_examples("plo", book, "approved")] == ["C"], (
        "own book excluded, draft not approved"
    )
    assert [i for i, _ in fewshot_examples("plo", book, "all")] == ["B", "C"], "rejected never sent"
    assert [i for i, _ in fewshot_examples("plo", "อื่นๆ.docx", "approved")] == ["A", "C"]
    assert json.loads(fewshot_examples("plo", "x.docx", "approved")[0][1]) == {"plos": [1]}
    assert fewshot_examples("missing", "x.docx", "all") == []
    assert book_key("ศศ.ม. ทดสอบ (ปป.69).docx") == book_key("ศศ-ม-ทดสอบ-ปป-69.pdf")
    tok = FEWSHOT_MODE.set("approved")
    try:
        assert fewshot_kw("plo", book) == {"examples": [("C", '{"plos": [3]}')]}
    finally:
        FEWSHOT_MODE.reset(tok)
    assert fewshot_kw("plo", book) == {}


def _settings(**kw) -> Settings:
    base = dict(ollama_model="gemma4:26b", ollama_keep_alive="10m", ollama_num_ctx="32768",
                ollama_base_url="http://ollama.test:11434", gemini_base_url="https://gemini.test")  # fmt: skip
    base.update(kw)
    return Settings(_env_file=None, **base)


def test_gateway_sends_examples_to_ollama_and_gemini() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        if "gemini" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}
                    ],
                    "usageMetadata": {},
                },
            )
        return httpx.Response(
            200, json={"message": {"content": "{}"}, "prompt_eval_count": 1, "eval_count": 1}
        )

    ex = [("ตัวอย่างเข้า", '{"a": 1}')]
    LLMGateway(_settings(), client=httpx.Client(transport=httpx.MockTransport(handler))).chat_json(
        "sys", "จริง", examples=ex
    )
    roles = [(m["role"], m["content"]) for m in seen["body"]["messages"]]
    assert roles == [
        ("system", "sys"),
        ("user", "ตัวอย่างเข้า"),
        ("assistant", '{"a": 1}'),
        ("user", "จริง"),
    ]
    LLMGateway(
        _settings(llm_provider="gemini", gemini_api_key="k"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).chat_json("sys", "จริง", examples=ex)
    contents = [(c["role"], c["parts"][0]["text"]) for c in seen["body"]["contents"]]
    assert contents == [("user", "ตัวอย่างเข้า"), ("model", '{"a": 1}'), ("user", "จริง")]


def test_fewshot_checker_on_repo_files_and_on_broken_file(tmp_path) -> None:
    from ocl_api.fewshot.check import run

    rep = run()
    assert rep.errors == [], rep.errors
    assert len(rep.oks) >= 6
    bad = {"part": "plo", "examples": [
        {"id": "x", "status": "approved", "source": {"book": "b.docx"}, "teaches": "t", "reviewed_by": None, "reviewed_at": "24/10/2569", "review_notes": "",
         "input": "PLO1 วิเคราะห์ข้อมูล", "output": {"plos": [{"code": "PLO1 แผน 1", "plan": None, "text": "สร้างสรรค์งาน"}]}},
    ]}  # fmt: skip
    (tmp_path / "plo.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    rep = run(["plo"], tmp_path)
    text = "\n".join(rep.errors)
    assert "reviewed_by" in text and "reviewed_at" in text
    assert "ต้องเป็นรหัสล้วน" in text and "ไม่พบตามตัวอักษรใน input" in text
