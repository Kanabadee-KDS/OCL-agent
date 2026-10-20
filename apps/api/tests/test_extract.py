"""Extraction plugin tests on a synthetic Document shaped like the มศว books."""

from __future__ import annotations

import json
from pathlib import Path

from ocl_api.extract.base import chapter, load_document, subsection
from ocl_api.extract.courses import extract_courses, merge_llm, parse_courses
from ocl_api.extract.pipeline import extract
from ocl_api.extract.plo import extract_plo
from ocl_api.extract.render import render_courses, render_structure
from ocl_api.extract.structure import build_tree, extract_structure
from ocl_api.extract.validators import run_checks
from ocl_api.ingest.model import Document, Paragraph, Table


def H(text: str, level: int, page: int = 1) -> Paragraph:
    return Paragraph(text=text, level=level, bold=True, page=page)


def P(text: str, page: int = 1) -> Paragraph:
    return Paragraph(text=text, page=page)


def sample_doc() -> Document:
    blocks = [
        H("หมวดที่ 1 ข้อมูลทั่วไป", 1, 5),
        H("4. จำนวนหน่วยกิตที่เรียนตลอดหลักสูตร", 2, 5),
        P("ไม่น้อยกว่า 127 หน่วยกิต", 5),
        H("หมวดที่ 3 รายละเอียดของผลลัพธ์การเรียนรู้", 1, 15),
        H("1. รายละเอียดผลลัพธ์การเรียนรู้ของหลักสูตร", 2, 15),
        P("PLO1: พัฒนาตนเองอย่างต่อเนื่อง", 15),
        P("PLO2 วิเคราะห์และประเมินการปล่อยก๊าซเรือนกระจก", 15),
        P("PLO2.1 ประเมินคาร์บอนฟุตพริ้นท์", 15),
        Table(rows=[["PLO", "K"], ["PLO1: พัฒนาตนเองอย่างต่อเนื่อง (ตาราง)", "K1"]], page=16),
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 25),
        H("1. จำนวนหน่วยกิตตลอดหลักสูตรและโครงสร้างหลักสูตร", 2, 25),
        P("1.1 จำนวนหน่วยกิตตลอดหลักสูตร รวม 127 หน่วยกิต", 25),
        Table(
            rows=[
                ["หมวดวิชา", "หน่วยกิต"],
                ["1. หมวดวิชาศึกษาทั่วไป", "24"],
                ["2. หมวดวิชาเฉพาะ", "91"],
                ["2.1 วิชาบังคับ", "67"],
                ["2.2 วิชาเลือก", "24"],
                ["3. หมวดวิชาเลือกเสรี", "12"],
                ["รวมไม่น้อยกว่า", "127"],
            ],
            page=25,
        ),
        H("2. รายละเอียดของหมวดวิชาและหน่วยกิต", 2, 26),
        P("2.1 หมวดวิชาศึกษาทั่วไป กำหนดให้เรียน ไม่น้อยกว่า 24 หน่วยกิต ประกอบด้วย", 26),
        P("2.1.1 วิชาบังคับ กำหนดให้เรียน จำนวน 12 หน่วยกิต ดังนี้", 26),
        P("ศท111 ศิลปะการใช้ชีวิต 3(3-0-6)", 26),
        P("ศท112 พลังการสื่อสาร 3 (3-0-6)", 26),
        H("3. คำอธิบายชุดวิชา/รายวิชา", 2, 30),
        P("3.1.1 วิชาบังคับ", 30),
        P("ศท111 ศิลปะการใช้ชีวิต 3(3-0-6)", 30),
        P("GEN111 The Art of Living", 30),
        P("พัฒนาผู้เรียนให้มีทักษะการเรียนรู้ตลอดชีวิต", 30),
        P("ผ่านการเรียนรู้ด้วยตนเอง", 30),
        P("ศท112 พลังการสื่อสาร 3(3-0-6)", 31),
        P("GEN112 Power of Communication", 31),
        P("บุรพวิชา: ศท111", 31),
        P("พัฒนาทักษะด้านการสื่อสาร", 31),
        P("Develop communication skills.", 31),
    ]
    return Document(source_name="sample.docx", source_type="docx", blocks=blocks, pages=40)


def test_subsection_slicing() -> None:
    doc = sample_doc()
    ch4 = chapter(doc, "4")
    assert ch4 is not None
    s1 = subsection(ch4.blocks, "1")
    assert any(isinstance(b, Table) for b in s1) and len(s1) == 2
    assert len(subsection(ch4.blocks, "3")) == 10


def test_structure_from_table() -> None:
    r = extract_structure(sample_doc())
    assert r.data["total_credits"] == 127
    tree = r.data["tree"]
    assert [n["name"] for n in tree] == ["หมวดวิชาศึกษาทั่วไป", "หมวดวิชาเฉพาะ", "หมวดวิชาเลือกเสรี"]
    assert [n["credits"] for n in tree] == [24, 91, 12]
    assert [c["name"] for c in tree[1]["children"]] == ["วิชาบังคับ", "วิชาเลือก"]
    assert tree[0]["meta"]["confidence"] == "high" and tree[0]["meta"]["source"]["page"] == 25


def test_build_tree_levels() -> None:
    flat = [
        {"number": "1", "level": 1, "children": []},
        {"number": "1.1", "level": 2, "children": []},
        {"number": "1.1.1", "level": 3, "children": []},
        {"number": "2", "level": 1, "children": []},
    ]
    roots = build_tree(flat)
    assert [r["number"] for r in roots] == ["1", "2"]
    assert roots[0]["children"][0]["children"][0]["number"] == "1.1.1"


def test_plo_regex_and_dedupe() -> None:
    r = extract_plo(sample_doc())
    plos = r.data["plos"]
    assert [p["code"] for p in plos] == ["PLO1", "PLO2"]
    assert plos[0]["text"].startswith("พัฒนาตนเองอย่างต่อเนื่อง")
    assert plos[0]["meta"]["confidence"] == "high"
    assert plos[1]["sub_plos"][0]["code"] == "PLO2.1"


def test_parse_courses_header_en_description_prereq() -> None:
    doc = sample_doc()
    ch4 = chapter(doc, "4")
    courses = parse_courses(subsection(ch4.blocks, "2") + subsection(ch4.blocks, "3"))
    assert set(courses) == {"ศท111", "ศท112"}
    c = courses["ศท111"]
    assert c["name_th"] == "ศิลปะการใช้ชีวิต" and c["credit_text"] == "3(3-0-6)" and c["credits"] == 3
    assert c["hours"] == {"lecture": 3, "lab": 0, "self": 6}
    assert c["code_en"] == "GEN111" and c["name_en"] == "The Art of Living"
    assert c["description_th"] == "พัฒนาผู้เรียนให้มีทักษะการเรียนรู้ตลอดชีวิต ผ่านการเรียนรู้ด้วยตนเอง"
    assert c["group"] == "วิชาบังคับ"
    d = courses["ศท112"]
    assert d["credit_text"] == "3(3-0-6)" and d["prerequisite"] == "ศท111"
    assert d["description_th"] == "พัฒนาทักษะด้านการสื่อสาร"
    assert d["description_en"] == "Develop communication skills."
    assert d["meta"]["source"]["page"] == 26


def test_merge_llm_fills_and_flags() -> None:
    doc = sample_doc()
    ch4 = chapter(doc, "4")
    courses = parse_courses(subsection(ch4.blocks, "3"))
    notes = merge_llm(
        courses,
        [
            {"code_th": "ศท111", "name_th": "ศิลปะการใช้ชีวิต", "credit_text": "3(3-0-6)"},
            {"code_th": "ศท112", "name_th": "พลังการสื่อสาร", "credit_text": "2(2-0-4)"},
            {
                "code_th": "ศท113",
                "name_th": "ถอดรหัสยุคดิจิทัล",
                "credit_text": "3(3-0-6)",
                "code_en": "GEN113",
            },
        ],
    )
    assert (
        courses["ศท111"]["meta"]["confidence"] == "high"
        and courses["ศท111"]["meta"]["by"] == "merged"
    )
    assert (
        courses["ศท112"]["meta"]["confidence"] == "low"
        and "credit" in courses["ศท112"]["meta"]["note"]
    )
    assert courses["ศท113"]["meta"] == {
        "confidence": "medium",
        "source": {"page": None, "snippet": "ถอดรหัสยุคดิจิทัล"},
        "by": "llm",
        "inferred": False,
    }
    assert courses["ศท113"]["credits"] == 3
    assert len(notes) == 1


class FakeGateway:
    provider = "fake"
    model = "fake"

    def __init__(self, data):
        self.data = data
        self.calls = 0

    def chat_json(self, system, user, *, schema=None, max_tokens=4096, retries=1):
        from ocl_api.llm.gateway import LLMResult, LLMUsage

        self.calls += 1
        return LLMResult(
            data=self.data, raw=json.dumps(self.data), usage=LLMUsage("fake", "fake", 10, 5, 0.1, 1)
        )


def test_extract_courses_with_fake_llm() -> None:
    gw = FakeGateway(
        {"courses": [{"code_th": "ศท 111", "name_th": "ศิลปะการใช้ชีวิต", "credit_text": "3(3-0-6)"}]}
    )
    r = extract_courses(sample_doc(), gw, llm_chunk_chars=100)
    assert gw.calls >= 2, "text longer than the chunk size must be sent in several chunks"
    assert r.data["count"] == 2 and r.llm_usage["calls"] == gw.calls
    assert r.data["parser_count"] == 2


def test_validators_and_render() -> None:
    doc = sample_doc()
    st = extract_structure(doc).data
    plo = extract_plo(doc).data
    crs = extract_courses(doc).data
    checks = {c.key: c for c in run_checks({"structure": st, "plo": plo, "courses": crs})}
    assert checks["credits_total"].status == "pass"
    assert checks["credits_sub"].status == "pass"
    assert checks["plo_present"].status == "pass"
    assert checks["course_code_unique"].status == "pass"
    md = render_structure(st)
    assert "| 1 หมวดวิชาศึกษาทั่วไป | 24 |" in md and "**127**" in md
    md = render_courses(crs)
    assert "| ศท111 | ศิลปะการใช้ชีวิต | GEN111 The Art of Living | 3(3-0-6) |" in md
    assert render_structure({"tree": []}).startswith("# โครงสร้างหลักสูตร\n\n> AI สกัดไม่ได้")


def test_pipeline_roundtrip(tmp_path: Path) -> None:
    doc = sample_doc()
    (tmp_path / "document.json").write_text(
        json.dumps(doc.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    loaded = load_document(tmp_path)
    assert [s.number for s in loaded.sections() if s.kind == "chapter"] == ["1", "3", "4"]
    report = extract(tmp_path, gateway=None)
    assert report["parts"]["courses"]["count"] == 2 and report["checks"]["fail"] == 0
    assert (tmp_path / "extract" / "courses.json").exists()
    assert (tmp_path / "extract" / "md" / "3-courses_list.md").exists()
    assert (tmp_path / "extract" / "checks.json").exists()


class TruncatingGateway(FakeGateway):
    """Pretends replies longer than `limit` chars of input get cut off."""

    def __init__(self, data, limit: int):
        super().__init__(data)
        self.limit = limit
        self.sizes: list[int] = []

    def chat_json(self, system, user, *, schema=None, max_tokens=4096, retries=1):
        from ocl_api.llm.gateway import LLMTruncated, LLMUsage

        size = len(user)
        self.sizes.append(size)
        if size > self.limit:
            raise LLMTruncated("cut", LLMUsage("fake", "fake", 1, max_tokens, 0.1, 1))
        return super().chat_json(system, user, schema=schema, max_tokens=max_tokens)


def test_truncated_chunks_are_split_and_retried(monkeypatch) -> None:
    import ocl_api.extract.courses as courses_mod

    monkeypatch.setattr(courses_mod, "MIN_CHUNK_CHARS", 50)
    doc = sample_doc()
    gw = TruncatingGateway(
        {"courses": [{"code_th": "ศท111", "name_th": "ศิลปะการใช้ชีวิต"}]}, limit=400
    )
    r = extract_courses(doc, gw, llm_chunk_chars=100000)
    assert any(s > 400 for s in gw.sizes) and all(s <= 400 for s in gw.sizes[-2:])
    assert any("truncated; split" in n for n in r.notes)
    assert r.llm_usage["calls"] == len(gw.sizes)
    assert r.data["count"] == 2
