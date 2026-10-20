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


def test_graduate_plan_table_and_unnumbered_rows() -> None:
    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 24),
        H("1. จำนวนหน่วยกิตตลอดหลักสูตรและโครงสร้างหลักสูตร", 2, 24),
        P("1.1 จำนวนหน่วยกิตตลอดหลักสูตร รวมไม่น้อยกว่า 48 หน่วยกิต", 24),
        Table(
            rows=[
                ["หมวดวิชา", "แผน 1.1 เน้นการทำวิจัย", "แผน 2.1 เน้นการทำวิจัยและเรียน"],
                ["หมวดวิชา", "หน่วยกิต", "หน่วยกิต"],
                ["หมวดวิชาบังคับ", "-", "8 หน่วยกิต"],
                ["หมวดวิชาเลือก ไม่น้อยกว่า", "-", "4 หน่วยกิต"],
                ["หมวดวิชาปริญญานิพนธ์", "48 หน่วยกิต", "36 หน่วยกิต"],
                ["รวมไม่น้อยกว่า", "48 หน่วยกิต", "48 หน่วยกิต"],
            ],
            page=24,
        ),
    ]
    doc = Document(source_name="phd.docx", source_type="docx", blocks=blocks)
    st = extract_structure(doc).data
    assert st["total_credits"] == 48
    plans = st["tree"]
    assert [
        n["name"].startswith(x) for n, x in zip(plans, ["แผน 1.1", "แผน 2.1"], strict=True)
    ] == [True, True]
    assert [n["credits"] for n in plans] == [48, 48]
    assert [c["name"] for c in plans[0]["children"]] == ["หมวดวิชาปริญญานิพนธ์"]
    assert [c["credits"] for c in plans[1]["children"]] == [8, 4, 36]
    checks = {c.key: c for c in run_checks({"structure": st, "plo": {}, "courses": {}})}
    assert checks["credits_total"].status == "pass"


def test_course_table_rows_with_th_en_cells() -> None:
    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 24),
        H("2. รายละเอียดของหมวดวิชาและหน่วยกิต", 2, 24),
        P("2.2.1 ชุดวิชาทฤษฎีเศรษฐศาสตร์ธุรกิจและการจัดการ", 24),
        Table(
            rows=[
                ["ศฐ510*\nEC510*", "เศรษฐศาสตร์พื้นฐาน\nFundamental Economics", "2(2-0-4)"],
                ["ศฐ511\nEC511", "การวิเคราะห์เชิงปริมาณ\nQuantitative Analysis", "3(3-0-6)"],
            ],
            page=24,
        ),
        H("3. คำอธิบายชุดวิชา/รายวิชา", 2, 30),
        P("ศฐ511 การวิเคราะห์เชิงปริมาณ 3(3-0-6)", 30),
        P("EC511 Quantitative Analysis", 30),
        P("ศึกษาเครื่องมือเชิงปริมาณ", 30),
    ]
    doc = Document(source_name="ma.docx", source_type="docx", blocks=blocks)
    cs = extract_courses(doc).data["courses"]
    by = {c["code_th"]: c for c in cs}
    assert set(by) == {"ศฐ510", "ศฐ511"}
    assert by["ศฐ510"]["code_en"] == "EC510" and by["ศฐ510"]["name_en"] == "Fundamental Economics"
    assert by["ศฐ510"]["credit_text"] == "2(2-0-4)" and by["ศฐ510"]["name_th"] == "เศรษฐศาสตร์พื้นฐาน"
    assert by["ศฐ511"]["module"] == "ชุดวิชาทฤษฎีเศรษฐศาสตร์ธุรกิจและการจัดการ"
    assert by["ศฐ511"]["description_th"] == "ศึกษาเครื่องมือเชิงปริมาณ"


def test_pdf_split_header_layout() -> None:
    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 30),
        H("3. คำอธิบายชุดวิชา/รายวิชา", 2, 30),
        P("3.1.1 วิชาบังคับ กำหนดให้เรียน จำนวน 24 หน่วยกิต ดังนี้", 30),
        P("ศท111 ศิลปะการใช้ชีวิต", 30),
        P("3(3-0-6) GEN111 The Art of Living", 30),
        P("พัฒนาผู้เรียนให้มีทักษะการเรียนรู้ตลอดชีวิต", 30),
        P("ศท112 พลังการสื่อสาร", 31),
        P("3(3-0-6) GEN112 Power of Communication", 31),
        P("พัฒนาทักษะด้านการสื่อสาร", 31),
        P("ศท999 บรรทัดที่อ้างถึงรายวิชาอื่นเฉย ๆ", 31),
        P("ไม่ใช่หัวข้อรายวิชาเพราะบรรทัดถัดไปไม่มีหน่วยกิต", 31),
    ]
    doc = Document(source_name="food.pdf", source_type="pdf", blocks=blocks)
    cs = {c["code_th"]: c for c in extract_courses(doc).data["courses"]}
    assert set(cs) == {"ศท111", "ศท112"}, (
        "a code line without a following credit line is not a course"
    )
    c = cs["ศท111"]
    assert c["credit_text"] == "3(3-0-6)" and c["code_en"] == "GEN111"
    assert c["name_en"] == "The Art of Living" and c["name_th"] == "ศิลปะการใช้ชีวิต"
    assert c["description_th"] == "พัฒนาผู้เรียนให้มีทักษะการเรียนรู้ตลอดชีวิต"
    assert cs["ศท112"]["description_th"].startswith("พัฒนาทักษะด้านการสื่อสาร ศท999")


def test_phd_multirow_table_and_word_credits() -> None:
    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 30),
        H("3. คำอธิบายชุดวิชา/รายวิชา", 2, 30),
        P("3.2.1.1 ชุดวิชาเศรษฐศาสตร์เชิงปริมาณ", 30),
        Table(
            rows=[
                ["ศฐน721", "เศรษฐมิติประยุกต์ขั้นสูง", "3 (2-2-5)"],
                ["ECI721", "Advanced Applied Econometrics", ""],
                ["ศึกษาวิธีเชิงปริมาณขั้นสูง", "", ""],
                ["Study of advanced quantitative methods", "", ""],
                ["", "", ""],
                ["ศฐน711", "เศรษฐศาสตร์จุลภาคขั้นสูง", "ไม่นับหน่วยกิต"],
                ["ECI711", "Advanced Microeconomics", ""],
                ["ประยุกต์เชิงนโยบาย", "", ""],
            ],
            page=31,
        ),
        P("ปพอ892 ปริญญานิพนธ์ระดับปริญญาเอก 36 หน่วยกิต", 40),
        P("GRD892 Doctoral Dissertation", 40),
        P("วิจัยเชิงลึกในหัวข้อที่ได้รับอนุมัติ", 40),
    ]
    doc = Document(source_name="phd.docx", source_type="docx", blocks=blocks)
    cs = {c["code_th"]: c for c in extract_courses(doc).data["courses"]}
    assert set(cs) == {"ศฐน721", "ศฐน711", "ปพอ892"}
    a = cs["ศฐน721"]
    assert a["credit_text"] == "3(2-2-5)" and a["credits"] == 3
    assert a["code_en"] == "ECI721" and a["name_en"] == "Advanced Applied Econometrics"
    assert a["description_th"] == "ศึกษาวิธีเชิงปริมาณขั้นสูง"
    assert a["description_en"] == "Study of advanced quantitative methods"
    assert a["module"] == "ชุดวิชาเศรษฐศาสตร์เชิงปริมาณ"
    b = cs["ศฐน711"]
    assert b["credit_text"] == "ไม่นับหน่วยกิต" and b["credits"] == 0
    assert b["description_th"] == "ประยุกต์เชิงนโยบาย"
    d = cs["ปพอ892"]
    assert d["credit_text"] == "36 หน่วยกิต" and d["credits"] == 36 and d["hours"] is None
    assert d["code_en"] == "GRD892" and d["description_th"] == "วิจัยเชิงลึกในหัวข้อที่ได้รับอนุมัติ"


def test_golden_sheet(tmp_path: Path) -> None:
    from ocl_api.cli import main

    doc = sample_doc()
    (tmp_path / "document.json").write_text(
        json.dumps(doc.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    extract(tmp_path, gateway=None)
    out = tmp_path / "golden.md"
    assert main(["golden", str(tmp_path), "--out", str(out), "--reviewer", "ทดสอบ"]) == 0
    md = out.read_text(encoding="utf-8")
    assert "ผู้ตรวจ: ทดสอบ" in md and "| 1 | ศท111 |" in md and "| PLO1 |" in md
    assert "| 1 | หมวดวิชาศึกษาทั่วไป | 24 | 25 | สูง |" in md
    assert "| รายวิชา (แถว × 4 ช่อง) | 8 |" in md


def test_in_book_conflict_is_flagged_low() -> None:
    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 24),
        H("2. รายละเอียดของหมวดวิชาและหน่วยกิต", 2, 24),
        P("ศฐน722 การวิจัยทางเศรษฐศาสตร์ 3(2-2-5)", 24),
        H("3. คำอธิบายชุดวิชา/รายวิชา", 2, 33),
        P("ศฐน722 สัมมนาทางเศรษฐศาสตร์ 2(1-2-3)", 33),
        P("ECI722 Seminar in Economics", 33),
        P("พัฒนาทักษะการนำเสนอ", 33),
    ]
    doc = Document(source_name="phd.docx", source_type="docx", blocks=blocks)
    c = extract_courses(doc).data["courses"][0]
    assert c["meta"]["confidence"] == "low"
    assert "ชื่อต่างกันในเล่ม" in c["meta"]["note"] and "หน่วยกิตต่างกันในเล่ม" in c["meta"]["note"]


def test_llm_items_must_be_literal_in_text() -> None:
    from ocl_api.extract.courses import _verify_against_text

    chunk = "ศท111 ศิลปะการใช้ชีวิต 3(3-0-6)\nGEN111 The Art of Living\nรายละเอียด"
    ok = _verify_against_text(
        {"code_th": "ศท 111", "name_th": "ศิลปะการใช้ชีวิต", "credit_text": "3 (3-0-6)"}, chunk
    )
    assert ok == {"code_th": "ศท111", "name_th": "ศิลปะการใช้ชีวิต", "credit_text": "3 (3-0-6)"}
    renamed = _verify_against_text({"code_th": "ศท111", "name_th": "ศิลปะแห่งการใช้ชีวิต"}, chunk)
    assert renamed["name_th"] is None, "a paraphrased name is evidence of nothing"
    assert _verify_against_text({"code_th": "ศท999", "name_th": "x"}, chunk) is None
    assert _verify_against_text({"code_th": "GCM413", "name_th": "x"}, chunk) is None


def test_subsection_without_bold_headings() -> None:
    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 24),
        P("1. จำนวนหน่วยกิตตลอดหลักสูตรและโครงสร้างหลักสูตร", 24),
        P("เนื้อหาข้อ 1", 24),
        P("2. รายละเอียดของหมวดวิชาและหน่วยกิต", 25),
        P("เนื้อหาข้อ 2", 25),
        P("3. คำอธิบายชุดวิชา/รายวิชา", 30),
        P("เนื้อหาข้อ 3", 30),
    ]
    doc = Document(source_name="x.docx", source_type="docx", blocks=blocks)
    ch4 = chapter(doc, "4")
    assert [b.text for b in subsection(ch4.blocks, "3")] == ["เนื้อหาข้อ 3"]
    assert [b.text for b in subsection(ch4.blocks, "1")] == ["เนื้อหาข้อ 1"]
