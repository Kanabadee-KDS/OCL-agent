"""PLO per study plan, and few-shot examples (loader, leave-one-book-out, gateway messages)."""

from __future__ import annotations

import json

import httpx
import pytest

import ocl_api.fewshot as fs
from ocl_api.config import Settings
from ocl_api.evaluate import score_plo
from ocl_api.extract.ksec import clean_plan
from ocl_api.extract.plo import extract_plo, split_llm_code
from ocl_api.extract.render import render_plo
from ocl_api.extract.validators import run_checks
from ocl_api.fewshot import FEWSHOT_MODE, book_key, fewshot_examples, fewshot_kw, source_keys
from ocl_api.ingest.model import Document, Paragraph, Table
from ocl_api.llm.gateway import LLMGateway


def _doc(blocks: list) -> Document:
    return Document(source_name="ศศ.ม. ทดสอบ (ปป.69).docx", source_type="docx",
                    blocks=[Paragraph(text="หมวดที่ 3 ผลลัพธ์การเรียนรู้", level=1, page=19), *blocks])  # fmt: skip


def test_plos_are_kept_per_plan() -> None:
    doc = _doc([
        Paragraph(text="1.1 เมื่อนิสิตจบการศึกษาแผน 1 แบบวิชาการ จะสามารถ", page=19),
        Paragraph(text="PLO1 วิเคราะห์แนวโน้มเศรษฐกิจ", page=19),
        Paragraph(text="และใช้เครื่องมือ", page=19),  # the book wraps the PLO by hand
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
    p1 = r.data["plos"][0]
    assert p1["text"].endswith("และใช้เครื่องมือ") and "alternatives" not in p1["meta"], (
        "the wrapped list line is joined, so the list and the table are the same PLO"
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


def test_list_and_table_wording_mismatch_is_flagged_not_dropped() -> None:
    # ปร.ด. p.22: the PLO list and the K/S/E/C table word PLO2 differently
    doc = _doc([
        Paragraph(text="PLO1: สังเคราะห์แนวคิดทฤษฎีทางเศรษฐศาสตร์", page=22),
        Paragraph(text="PLO2: ให้ข้อเสนอแนะเชิงนโยบาย", page=22),
        Table(rows=[["ผลลัพธ์การเรียนรู้", "ด้านความรู้ (K)"],
                    ["PLO1: สังเคราะห์แนวคิดทฤษฎี\nทางเศรษฐศาสตร์", "K1-1"],
                    ["PLO2: สามารถออกแบบงานวิจัยดั้งเดิมระดับนานาชาติ", "K2-1"]], page=23),
    ])  # fmt: skip
    r = extract_plo(doc)
    p1, p2 = r.data["plos"]
    assert p1["text"] == "สังเคราะห์แนวคิดทฤษฎีทางเศรษฐศาสตร์" and "alternatives" not in p1["meta"], (
        "a table cell that wraps onto a second line is joined: same wording, not a conflict"
    )
    assert p2["text"] == "ให้ข้อเสนอแนะเชิงนโยบาย", "list wording kept even though the table is longer"
    assert p2["meta"]["alternatives"] == [
        {"text": "สามารถออกแบบงานวิจัยดั้งเดิมระดับนานาชาติ", "page": 23, "from": "table"}
    ]
    assert p2["meta"]["confidence"] == "low" and "หน้า 22, 23" in p2["meta"]["note"]
    assert r.data["text_conflicts"] == ["PLO2"]
    checks = {c.key: c for c in run_checks({"plo": r.data})}
    assert (
        checks["plo_text_conflict"].status == "warn"
        and "PLO2" in checks["plo_text_conflict"].message
    )


def test_table_before_list_still_keeps_list_wording() -> None:
    doc = _doc([
        Table(rows=[["PLO1: ออกแบบงานวิจัย", "K1"]], page=21),
        Paragraph(text="PLO1: ให้ข้อเสนอแนะเชิงนโยบาย", page=22),
    ])  # fmt: skip
    (p,) = extract_plo(doc).data["plos"]
    assert p["text"] == "ให้ข้อเสนอแนะเชิงนโยบาย" and p["meta"]["source"]["page"] == 22
    assert p["meta"]["alternatives"] == [{"text": "ออกแบบงานวิจัย", "page": 21, "from": "table"}]


def test_later_note_lines_are_not_conflicts() -> None:
    # ศศ.บ. p.17: "หมายเหตุ" lines re-mention PLO codes after the list
    doc = _doc([
        Paragraph(text="PLO2: วิเคราะห์บริบททางสังคม", page=17),
        Paragraph(text="PLO6: ผลลัพธ์การเรียนรู้ของวิชาเอก ดังนี้", page=17),
        Paragraph(text="PLO 2-5 เป็นผลลัพธ์การเรียนรู้ของหลักสูตร", page=17),
        Paragraph(text="PLO6 เป็นผลลัพธ์การเรียนรู้ของวิชาเอก", page=17),
    ])  # fmt: skip
    r = extract_plo(doc)
    assert [p["text"] for p in r.data["plos"]] == [
        "วิเคราะห์บริบททางสังคม",
        "ผลลัพธ์การเรียนรู้ของวิชาเอก ดังนี้",
    ]
    assert r.data["text_conflicts"] == []
    assert "plo_text_conflict" not in {c.key for c in run_checks({"plo": r.data})}


def test_wrapped_list_lines_are_joined_and_an_extra_clause_is_flagged() -> None:
    # ศศ.บ. p.17 (R1 accuracy test ACC-095): PLOs wrap into separate paragraphs; the table
    # copy of PLO5 stops before the list's last clause
    doc = _doc([
        Paragraph(text="PLO4: ประยุกต์ใช้เทคโนโลยีสมัยใหม่เพื่อสร้างนวัตกรรมที่ตอบสนองความต้องการ", page=17),
        Paragraph(text="ของชุมชนและสังคม", page=17),
        Paragraph(text="PLO5: ออกแบบและดำเนินโครงการอย่างมี", page=17),
        Paragraph(text="ส่วนร่วมและยั่งยืน ด้วยจิตสาธารณะ และมีความรับผิดชอบต่อสังคม", page=17),
        Paragraph(text="PLO6: ผลลัพธ์การเรียนรู้ของวิชาเอก ดังนี้", page=17),
        Paragraph(text="วิชาเอกการจัดการภูมิสังคม", page=17),
        Paragraph(text="PLO6.1: สามารถจัดการทุนชุมชน", page=17),
        Paragraph(text="หมายเหตุ: PLO6 เป็นผลลัพธ์การเรียนรู้ของวิชาเอก", page=17),
        Table(rows=[["ผลลัพธ์การเรียนรู้", "ด้านความรู้ (K)"],
                    ["PLO4: ประยุกต์ใช้เทคโนโลยีสมัยใหม่เพื่อสร้างนวัตกรรมที่ตอบสนองความต้องการของชุมชนและสังคม", "K4.1"],
                    ["PLO5: ออกแบบและดำเนินโครงการอย่างมีส่วนร่วมและยั่งยืนด้วยจิตสาธารณะ", "K5.1"]], page=18),
    ])  # fmt: skip
    r = extract_plo(doc)
    p4, p5, p6 = r.data["plos"]
    assert p4["text"].endswith("ความต้องการของชุมชนและสังคม"), "Thai wrap joined without a space"
    assert "alternatives" not in p4["meta"]
    assert p5["text"] == (
        "ออกแบบและดำเนินโครงการอย่างมีส่วนร่วมและยั่งยืน ด้วยจิตสาธารณะ และมีความรับผิดชอบต่อสังคม"
    )
    assert p5["meta"]["alternatives"] == [
        {"text": "ออกแบบและดำเนินโครงการอย่างมีส่วนร่วมและยั่งยืนด้วยจิตสาธารณะ", "page": 18, "from": "table"}
    ]
    assert p5["meta"]["confidence"] == "low" and r.data["text_conflicts"] == ["PLO5"]
    assert p6["text"] == "ผลลัพธ์การเรียนรู้ของวิชาเอก ดังนี้", "a line ending 'ดังนี้' opens a list"
    assert [s["code"] for s in p6["sub_plos"]] == ["PLO6.1"]
    assert p6["sub_plos"][0]["text"] == "สามารถจัดการทุนชุมชน", "'หมายเหตุ' is not a wrap"


def test_bare_plo_code_takes_the_next_paragraph() -> None:
    # อาหาร PDF p.19: "PLO1:" on its own line, the statement (over 160 chars) below it
    long = "พัฒนาตนเองอย่างต่อเนื่องด้วยการเรียนรู้ตลอดชีวิต " * 4
    doc = _doc([
        Paragraph(text="PLO1:", page=19),
        Paragraph(text=long.strip(), page=19),
        Paragraph(text="PLO2:", page=19),
        Paragraph(text="แปรรูปวัตถุดิบ", page=19),
        Paragraph(text="หมายเหตุ: PLO1 เป็นผลลัพธ์การเรียนรู้ของหลักสูตร", page=19),
        Paragraph(text="โดยมีรายละเอียดของผลลัพธ์การเรียนรู้ของหลักสูตร ในแต่ละด้าน ดังนี้", page=19),
    ])  # fmt: skip
    p1, p2 = extract_plo(doc).data["plos"]
    assert p1["text"] == long.strip() and p1["meta"]["from"] == "list"
    assert p2["text"] == "แปรรูปวัตถุดิบ"


def test_split_llm_code_and_plan_scoring() -> None:
    assert split_llm_code("PLO1 แผน1 แบบวิชาการ", None) == ("PLO1", "แผน 1 แบบวิชาการ")
    assert split_llm_code("PLO2", "แผน 2 แบบวิชาชีพ") == ("PLO2", "แผน 2 แบบวิชาชีพ")
    # first-round Gemini wrote the plan in brackets with the spaces squashed
    assert split_llm_code("PLO1(แผน1แบบวิชาการ)", None) == ("PLO1", "แผน 1 แบบวิชาการ")
    assert split_llm_code("PLO3 (แผน 2 แบบวิชาชีพ),", None) == ("PLO3", "แผน 2 แบบวิชาชีพ")
    assert split_llm_code("PLO1", "(แผน 1 แบบวิชาการ)") == ("PLO1", "แผน 1 แบบวิชาการ")
    assert split_llm_code("ข้อ 1", "แผน2แบบวิชาชีพ") == ("ข้อ 1", "แผน 2 แบบวิชาชีพ")
    assert clean_plan(None) is None and clean_plan("แผน 1.1") == "แผน 1.1"
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


def test_same_as_counts_every_copy_of_a_book(tmp_path, monkeypatch) -> None:
    data = {"part": "info", "examples": [
        {"id": "a", "status": "approved", "input": "A", "output": {},
         "source": {"book": "อาหาร ดิจิทัล.pdf", "same_as": ["อาหาร (สแกน 14 หน้า).pdf"]}},
        {"id": "b", "status": "approved", "input": "B", "output": {}, "source": {"book": "อื่น.docx"}},
    ]}  # fmt: skip
    (tmp_path / "info.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(fs, "DIR", tmp_path)
    fs.load.cache_clear()
    try:
        for name in ("อาหาร ดิจิทัล.pdf", "อาหาร (สแกน 14 หน้า).pdf", "อาหาร-สแกน-14-หน้า.PDF"):
            assert [i for i, _ in fewshot_examples("info", name, "approved")] == ["B"], name
        assert [i for i, _ in fewshot_examples("info", "อื่นอีก.docx", "approved")] == ["A", "B"]
    finally:
        fs.load.cache_clear()
    assert source_keys({"source": {"book": "x.docx", "same_as": []}}) == {"x"}
    assert source_keys({}) == set()


def test_repo_food_example_is_not_shown_to_the_scanned_food_book() -> None:
    """The scanned sample is made from the food-science PDF, so info-02 would leak its answers."""
    fs.load.cache_clear()
    scanned = "วท.บ. อาหาร (สแกน 14 หน้า).pdf"
    food_pdf = "4.1.4 วท.บ.วิทยาศาสตร์การอาหารและโภชนาการ ปรั.pdf"
    climate = "วท.บ. วิทยาการการเปลี่ยนแปลงสภาพภูมิอากาศ.docx"
    ids = {
        ex["input"]: ex["id"] for ex in fs.load("info")["examples"] if ex["status"] != "rejected"
    }
    shown = {n: [ids[i] for i, _ in fewshot_examples("info", n, "all")] for n in (scanned, food_pdf, climate)}  # fmt: skip
    assert "info-02" not in shown[scanned] and "info-02" not in shown[food_pdf]
    assert "info-01" in shown[scanned], "another book's example is still sent"
    assert "info-01" not in shown[climate]


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
    bad["examples"][0]["source"]["same_as"] = "สแกน.pdf"
    (tmp_path / "plo.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
    assert any("source.same_as" in e for e in run(["plo"], tmp_path).errors)
