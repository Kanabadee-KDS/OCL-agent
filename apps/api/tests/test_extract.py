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
    assert report["parts"]["courses"]["count"] == 2
    fails = [c["key"] for c in report["checks"]["items"] if c["status"] == "fail"]
    assert set(fails) == {
        "ksec_present",
        "approval_present",
        "teachers_present",
        "plan_present",
        "modules_present",
    }, "sample_doc has no KSEC table, item 13 or teacher table"
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


def test_mapping_table() -> None:
    from ocl_api.extract.mapping import extract_mapping

    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 40),
        H("4. แผนที่กระจายความรับผิดชอบ", 2, 48),
        Table(
            rows=[
                ["ชุดวิชา/รายวิชา", "ผลลัพธ์การเรียนรู้ของหลักสูตร", "", ""],
                ["ชุดวิชา/รายวิชา", "PLO1", "PLO2", "PLO3"],
                ["1. หมวดวิชาศึกษาทั่วไป", "", "", ""],
                ["ศท111 ศิลปะการใช้ชีวิต", "●", "", ""],
                ["ศท112 พลังการสื่อสาร", "●", "", "●"],
                ["2. หมวดวิชาเฉพาะ", "", "", ""],
                ["วป101 ภูมิอากาศเบื้องต้น", "", "●", ""],
                ["วป999 ไม่มีจุด", "", "", ""],
            ],
            page=48,
        ),
    ]
    doc = Document(source_name="x.docx", source_type="docx", blocks=blocks)
    r = extract_mapping(doc)
    assert r.data["plo_codes"] == ["PLO1", "PLO2", "PLO3"]
    rows = {x["course_code"]: x for x in r.data["rows"]}
    assert (
        rows["ศท112"]["plos"] == ["PLO1", "PLO3"] and rows["ศท112"]["group"] == "1. หมวดวิชาศึกษาทั่วไป"
    )
    assert rows["วป101"]["plos"] == ["PLO2"] and rows["วป101"]["meta"]["source"]["page"] == 48
    assert r.data["unmapped_courses"] == ["วป999"]
    checks = {
        c.key: c
        for c in run_checks(
            {
                "mapping": r.data,
                "courses": {"courses": [{"code_th": "ศท111"}, {"code_th": "ศท113"}]},
            }
        )
    }
    assert checks["plo_covered"].status == "pass"
    assert (
        checks["courses_unmapped"].status == "warn"
        and "วป999" in checks["courses_unmapped"].message
    )
    assert (
        checks["mapping_vs_courses"].status == "warn"
        and "ศท113" in checks["mapping_vs_courses"].message
    )
    from ocl_api.extract.render import render_mapping

    md = render_mapping(r.data)
    assert "| ศท112 พลังการสื่อสาร | ● |  | ● | 48 |" in md


def test_mapping_missing_plo_column_is_flagged() -> None:
    data = {
        "plo_codes": ["PLO1", "PLO2"],
        "rows": [{"course_code": "ศท111", "plos": ["PLO1", "PLO2"]}],
        "unmapped_courses": [],
    }
    plo = {"plos": [{"code": "PLO1"}, {"code": "PLO2"}, {"code": "PLO3"}]}
    checks = {c.key: c for c in run_checks({"mapping": data, "plo": plo, "courses": {}})}
    assert (
        checks["mapping_has_all_plos"].status == "warn"
        and "PLO3" in checks["mapping_has_all_plos"].message
    )
    assert checks["plo_covered"].status == "pass"


def _ingest_dir(tmp_path: Path, doc: Document) -> Path:
    (tmp_path / "document.json").write_text(
        json.dumps(doc.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def info_doc() -> Document:
    blocks = [
        H("คู่มือ", 0, 1),
        H("หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาทดสอบ (หลักสูตรปรับปรุง พ.ศ. 2569)", 0, 1),
        H("คณะทดสอบ มหาวิทยาลัยศรีนครินทรวิโรฒ", 0, 1),
        H("หมวดที่ 1 ข้อมูลทั่วไป", 1, 5),
        H("1. รหัสและชื่อหลักสูตร", 2, 5),
        P("รหัสหลักสูตร 25290091100204", 5),
        P(
            "ภาษาไทย: หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาทดสอบ "
            "ภาษาอังกฤษ: Bachelor of Science Program in Testing",
            5,
        ),
        H("2. ชื่อปริญญาและสาขาวิชา", 2, 5),
        P("ภาษาไทย ชื่อเต็ม: วิทยาศาสตรบัณฑิต (ทดสอบ) ชื่อย่อ: วท.บ. (ทดสอบ)", 5),
        P("ภาษาอังกฤษ ชื่อเต็ม: Bachelor of Science (Testing)", 5),
        P("ชื่อย่อ: B.Sc. (Testing)", 5),
        H("3. วิชาเอก/แขนงวิชา (ถ้ามี)", 2, 5),
        P("1) วิชาเอกก", 5),
        P("2) วิชาเอกข", 5),
        H("4. จำนวนหน่วยกิตที่เรียนตลอดหลักสูตร", 2, 5),
        P("ไม่น้อยกว่า 127 หน่วยกิต", 5),
        H("5. รูปแบบของหลักสูตร", 2, 5),
        H("5.1 รูปแบบ", 3, 5),
        P("☑ หลักสูตรปริญญาตรีทางวิชาการ", 5),
        P("□ หลักสูตรปริญญาตรีทางวิชาชีพหรือปฏิบัติการ", 5),
        H("5.2 ระยะเวลาการศึกษา", 3, 5),
        P("☑ หลักสูตรแบบเต็มเวลา", 5),
        P("□ 2 ปี ☑ 4 ปี □ 5 ปี □ 6 ปี", 5),
        P("☒ หลักสูตรแบบการศึกษาตลอดชีวิต (Lifelong Learning) ไม่กำหนดระยะเวลาการศึกษา", 5),
        H("5.3 ภาษาที่ใช้ในการจัดการเรียนการสอน", 3, 6),
        P("ภาษาไทย เอกสารและตำราเป็นภาษาไทยและภาษาอังกฤษ", 6),
        H("5.4 การรับเข้าศึกษา", 3, 6),
        P("รับผู้เข้าศึกษาชาวไทยและชาวต่างประเทศ", 6),
        H("5.5 ความร่วมมือกับสถาบันอื่น", 3, 6),
        P("เป็นหลักสูตรความร่วมมือกับสถาบันอื่นได้แก่ 5.6 การให้ปริญญาแก่ผู้สำเร็จการศึกษา", 6),
        P("ให้ปริญญาเพียงสาขาวิชาเดียว", 6),
        H("6. ระบบการจัดการศึกษา", 2, 6),
        H("6.1 ระบบ", 3, 6),
        P("ระบบการศึกษาเป็นแบบทวิภาค", 6),
        H("7. การดำเนินการเรียนการสอน", 2, 6),
        P("ภาคต้น เดือนสิงหาคม – ธันวาคม", 6),
        P("ภาคปลาย เดือนมกราคม – พฤษภาคม", 6),
        H("10. อาชีพที่ประกอบได้หลังสำเร็จการศึกษา", 2, 7),
        P("วิชาเอกก", 7),
        P("10.1 นักวิชาการ", 7),
        P("10.2 นักวิจัย", 7),
        H("13. สถานภาพของหลักสูตรและการพิจารณาอนุมัติ/เห็นชอบหลักสูตร", 2, 11),
        P(
            "เป็นหลักสูตรปรับปรุง จากหลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาทดสอบ (หลักสูตรปรับปรุง พ.ศ. 2564) "
            "โดยจะเริ่มใช้หลักสูตรนี้ในภาคการศึกษา 1 ของปีการศึกษา 2569",
            11,
        ),
        P("ได้รับอนุมัติ/เห็นชอบหลักสูตรจากสภาวิชาการ ในการประชุมครั้งที่ 4/2568", 11),
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 25),
        P("2.2.3 วิชาสหกิจศึกษา 6 หน่วยกิต", 26),
    ]
    return Document(source_name="info.docx", source_type="docx", blocks=blocks, pages=40)


def test_info_fields_from_chapter_1() -> None:
    from ocl_api.extract.info import extract_info

    r = extract_info(info_doc())
    v = r.data["values"]
    assert v["program_code"] == "25290091100204" and v["faculty"] == "คณะทดสอบ"
    assert v["name_th"] == "หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาทดสอบ"
    assert v["name_en"] == "Bachelor of Science Program in Testing"
    assert (
        v["degree_full_th"] == "วิทยาศาสตรบัณฑิต (ทดสอบ)" and v["degree_abbr_en"] == "B.Sc. (Testing)"
    )
    assert v["field_of_study"] == "ทดสอบ" and v["level"] == "ป.ตรี"
    assert v["total_credits"] == 127 and v["duration_years"] == 4
    assert v["program_type"] == "ปริญญาตรีทางวิชาการ" and v["study_mode"] == "เต็มเวลา"
    assert v["lifelong"] is True, "☒ counts as a ticked box (Wingdings 2 letter R)"
    assert v["language"] == "ไทย" and v["education_system"] == "ทวิภาค"
    assert v["semesters_counted"] == "(1,2)" and r.data["meta"]["semesters_counted"]["inferred"]
    assert v["revision_type"] == "ปรับปรุง" and v["edition_year"] == 2569
    assert v["previous_program"] == "วิทยาศาสตรบัณฑิต สาขาวิชาทดสอบ" and v["previous_year"] == 2564
    assert v["start_semester"] == 1 and v["start_year"] == 2569
    assert v["cwie"] is True and r.data["meta"]["cwie"]["source"]["page"] == 26
    assert v["standard_criteria"] == "ประกาศ อว. 2565 (ตรี)"
    assert [m["name"] for m in r.data["majors"]] == ["วิชาเอกก", "วิชาเอกข"]
    assert [(c["group"], c["name"]) for c in r.data["careers"]] == [
        ("วิชาเอกก", "นักวิชาการ"),
        ("วิชาเอกก", "นักวิจัย"),
    ]
    assert (
        v["collaboration_text"].startswith("เป็นหลักสูตรความร่วมมือ")
        and "5.6" not in v["collaboration_text"]
    )
    assert r.data["missing_required"] == []
    assert r.data["meta"]["name_th"]["source"]["page"] == 5


def test_info_llm_fills_only_literal_values() -> None:
    from ocl_api.extract.info import extract_info

    doc = info_doc()
    # drop item 2 so the degree names are missing for the LLM to fill
    doc.blocks = [b for b in doc.blocks if "ชื่อเต็ม" not in b.text and "ชื่อย่อ" not in b.text]

    class FakeGateway:
        provider, model = "fake", "fake"

        def chat_json(self, system, user, schema=None, max_tokens=None):
            class R:
                data = {
                    "degree_full_th": "วิทยาศาสตรบัณฑิต (แต่งขึ้น)",  # not in text -> rejected
                    "degree_full_en": "Bachelor of Science Program in Testing",  # literal -> kept
                    "degree_abbr_th": None,
                    "degree_abbr_en": None,
                }

                class usage:
                    @staticmethod
                    def to_dict():
                        return {"calls": 1}

            return R()

    r = extract_info(doc, FakeGateway())
    v = r.data["values"]
    assert v["degree_full_th"] is None and any("แต่งขึ้น" in n for n in r.notes)
    assert v["degree_full_en"] == "Bachelor of Science Program in Testing"
    assert r.data["meta"]["degree_full_en"]["by"] == "llm"


def test_info_checks_and_render(tmp_path: Path) -> None:
    from ocl_api.extract.golden import render_golden
    from ocl_api.extract.info import extract_info
    from ocl_api.extract.render import render_info

    r = extract_info(info_doc())
    checks = {
        c.key: c
        for c in run_checks({"info": r.data, "structure": {"total_credits": 130, "tree": []}})
    }
    assert checks["info_required"].status == "pass"
    assert checks["program_code_format"].status == "pass"
    assert (
        checks["info_credits_match"].status == "fail"
        and "127" in checks["info_credits_match"].message
    )
    assert checks["name_consistent"].status == "pass"
    assert "2574" in checks["next_revision"].message
    assert "กลุ่มการศึกษา" in checks["info_inferred"].message
    md = render_info(r.data)
    assert "# ข้อมูลหลักสูตร" in md and "| รหัสหลักสูตร สกอ. (14 หลัก) | 25290091100204 |" in md
    assert "| วิชาเอกก | นักวิชาการ | 7 |" in md
    assert "AI สกัดไม่ได้" in render_info({"values": {}, "fields": []})

    out = extract(_ingest_dir(tmp_path, info_doc()), parts=["info", "structure", "plo", "courses"])
    assert out["parts"]["info"]["count"] >= 25
    sheet = render_golden(Path(out["out_dir"]), book="info")
    assert (
        "## 1. ข้อมูลหลัก + หมวดที่ 1" in sheet
        and "| ชื่อหลักสูตร (ไทย) | หลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาทดสอบ | 5 |" in sheet
    )


def test_ksec_table_codes_and_subtypes() -> None:
    from ocl_api.extract.ksec import extract_ksec

    blocks = [
        H("หมวดที่ 3 รายละเอียดของผลลัพธ์การเรียนรู้", 1, 19),
        P("1.1 เมื่อนิสิตจบการศึกษาแผน 1 แบบวิชาการ จะสามารถ", 19),
        Table(
            rows=[
                ["ผลลัพธ์การเรียนรู้ของหลักสูตร", "รายละเอียดผลลัพธ์การเรียนรู้", "", "", ""],
                ["", "ด้านความรู้ (K)", "ด้านทักษะ (S)", "ด้านจริยธรรม (E)", "ด้านคุณลักษณะ (C)"],
                [
                    "PLO1: พัฒนาตนเอง",
                    "K1-1: อธิบายแนวคิด\nK1.2 : ออกแบบ วางแผน",
                    "S1-1: ทักษะการเรียนรู้ S1-2: ทักษะการวางแผน",
                    "E1-1: มีความรับผิดชอบ",
                    "C1-1: รักการเรียนรู้\n(ใฝ่รู้ใฝ่เรียน)\nคุณลักษณะเฉพาะ\nC1-2: แสดงภาวะผู้นำ",
                ],
                ["", "ด้านความรู้ (K)", "ด้านทักษะ (S)", "ด้านจริยธรรม (E)", "ด้านคุณลักษณะ (C)"],
                ["", "K1-3: ต่อจากหน้าก่อน", "", "", ""],
                ["เอกการจัดการภูมิสังคม", "", "", "", ""],
                ["PLO6.1: วิชาเอก", "K6.1.1: วิเคราะห์ชุมชน", "S1-7: ทักษะเดิม", "", "C6.1.1 ทักษะดิจิทัล"],
            ],
            page=19,
        ),
    ]
    doc = Document(source_name="k.docx", source_type="docx", blocks=blocks)
    r = extract_ksec(doc)
    plos = {p["code"]: p for p in r.data["plos"]}
    assert set(plos) == {"PLO1", "PLO6.1"} and plos["PLO1"]["plan"] == "แผน 1 แบบวิชาการ"
    items = {it["code"]: it for it in plos["PLO1"]["items"]}
    assert set(items) == {"K1-1", "K1-2", "K1-3", "S1-1", "S1-2", "E1-1", "C1-1", "C1-2"}
    assert items["K1-2"]["text"] == "ออกแบบ วางแผน" and items["S1-2"]["text"] == "ทักษะการวางแผน"
    assert items["C1-1"]["text"] == "รักการเรียนรู้ (ใฝ่รู้ใฝ่เรียน)" and items["C1-1"]["subtype"] is None
    assert items["C1-2"]["subtype"] == "ลักษณะเฉพาะ"
    assert plos["PLO6.1"]["group"] == "เอกการจัดการภูมิสังคม"
    codes6 = [it["code"] for it in plos["PLO6.1"]["items"]]
    assert codes6 == ["K6-1-1", "S1-7", "C6-1-1"]
    assert r.data["count"] == 11 and "K6-1-1" in r.data["codes"]


def test_mapping_42_codes_and_checks() -> None:
    from ocl_api.extract.mapping import cell_codes, extract_mapping

    assert cell_codes("1,2", "K", "1") == ["K1-1", "K1-2"]
    assert cell_codes("1-7", "S", "2") == ["S1-7"]
    assert cell_codes("6.1.2", "K", "6") == ["K6-1-2"]
    assert cell_codes("2-3 2-4", "K", "2") == ["K2-3", "K2-4"]
    assert cell_codes("", "K", "1") == []

    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 40),
        H("4. แผนที่กระจายความรับผิดชอบ", 2, 48),
        Table(
            rows=[
                ["ชุดวิชา/รายวิชา", "ผลลัพธ์การเรียนรู้ของหลักสูตร", ""],
                ["ชุดวิชา/รายวิชา", "PLO1", "PLO2"],
                ["ศท111 ศิลปะการใช้ชีวิต", "●", ""],
                ["ศท112 พลังการสื่อสาร", "●", "●"],
            ],
            page=48,
        ),
        Table(
            rows=[
                ["ชุดวิชา/รายวิชา", "ผลลัพธ์การเรียนรู้ของหลักสูตร", "", "", "", "", "", "", ""],
                ["ชุดวิชา/รายวิชา", "PLO1", "", "", "", "PLO2", "", "", ""],
                ["ชุดวิชา/รายวิชา", "K1", "S1", "E1", "C1", "K2", "S2", "E2", "C2"],
                ["1. หมวดวิชาศึกษาทั่วไป", "", "", "", "", "", "", "", ""],
                ["ศท111 ศิลปะการใช้ชีวิต", "1,2", "1,2", "", "1", "", "", "", ""],
                ["ศท112 พลังการสื่อสาร", "3", "", "1", "", "", "1-7", "", "9"],
                ["", "", "", "", "", "2", "", "", ""],
            ],
            page=51,
        ),
    ]
    doc = Document(source_name="m.docx", source_type="docx", blocks=blocks)
    r = extract_mapping(doc)
    assert r.data["ksec_columns"] == ["K1", "S1", "E1", "C1", "K2", "S2", "E2", "C2"]
    rows = {x["course_code"]: x for x in r.data["ksec_rows"]}
    assert rows["ศท111"]["ksec_codes"] == ["K1-1", "K1-2", "S1-1", "S1-2", "C1-1"]
    assert rows["ศท111"]["group"] == "1. หมวดวิชาศึกษาทั่วไป" and rows["ศท111"]["plos"] == ["PLO1"]
    assert rows["ศท112"]["ksec_codes"] == ["K1-3", "E1-1", "K2-2", "S1-7", "C2-9"], (
        "empty course row continues"
    )
    assert rows["ศท112"]["plos"] == ["PLO1", "PLO2"]

    ksec = {
        "codes": ["K1-1", "K1-2", "K1-3", "S1-1", "C1-1", "E1-1", "S1-7", "K2-2"],
        "count": 8,
        "plos": [],
    }
    checks = {
        c.key: c for c in run_checks({"mapping": r.data, "ksec": ksec, "plo": {}, "courses": {}})
    }
    assert (
        checks["mapping_ksec_unknown"].status == "warn"
        and "C2-9" in checks["mapping_ksec_unknown"].message
    )
    assert checks["ksec_unmapped"].status == "pass"
    assert checks["mapping_42_vs_41"].status == "pass"
    from ocl_api.extract.render import render_mapping

    md = render_mapping(r.data)
    assert (
        "## 4.2 รายวิชา × KSEC" in md
        and "| ศท111 ศิลปะการใช้ชีวิต | K1-1, K1-2 | S1-1, S1-2 |  | C1-1 |" in md
    )


def test_mapping_42_pdf_phantom_column_is_deduped() -> None:
    from ocl_api.extract.mapping import extract_mapping

    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 40),
        H("4. แผนที่กระจายความรับผิดชอบ", 2, 60),
        Table(
            rows=[
                ["ชุดวิชา/รายวิชา", "ผลลัพธ์การเรียนรู้ของหลักสูตร", "", "", "", "", "", "", "", ""],
                ["", "PLO1", "", "", "", "", "PLO2", "", "", ""],
                ["", "K1", "S1", "E1", "C1", "", "K2", "S2", "E2", "C2"],
                ["วอภ112 ปฏิบัติการเคมี", "", "", "", "", "2-1", "2-1", "", "1-7", ""],
            ],
            page=63,
        ),
    ]
    doc = Document(source_name="m.pdf", source_type="pdf", blocks=blocks)
    r = extract_mapping(doc)
    row = r.data["ksec_rows"][0]
    assert row["by_column"] == {"K2": ["K2-1"], "E2": ["E1-7"]}, "phantom column 5 duplicates K2"


def test_approval_rows_blank_and_wrapped() -> None:
    from ocl_api.extract.approval import extract_approval, parse_date
    from ocl_api.extract.render import render_approval

    assert parse_date("เมื่อวันที่ 28 เดือน เมษายน พ.ศ. 2569")["iso"] == "2026-04-28"
    assert parse_date("เมื่อวันที่ 2 ธ.ค. 2568") == {
        "day": 2,
        "month": 12,
        "year_be": 2568,
        "text": "2 ธ.ค. 2568",
        "iso": "2025-12-02",
    }
    assert parse_date("เมื่อวันที่ ......... เดือน ....... พ.ศ. ....") is None

    blocks = [
        H("หมวดที่ 1 ข้อมูลทั่วไป", 1, 5),
        H("13. สถานภาพของหลักสูตรและการพิจารณาอนุมัติ/เห็นชอบหลักสูตร", 2, 10),
        P(
            "เป็นหลักสูตรปรับปรุง จากหลักสูตรวิทยาศาสตรบัณฑิต สาขาวิชาทดสอบ (หลักสูตรปรับปรุง พ.ศ. 2565) "
            "โดยจะเริ่มใช้หลักสูตรนี้ในภาคการศึกษา 1 ของปีการศึกษา 2570",
            10,
        ),
        P("ได้รับอนุมัติ/เห็นชอบหลักสูตรจากคณะกรรมการการศึกษาระดับปริญญาตรี ในการประชุมครั้งที่ 6 เมื่อวันที่", 10),
        P("11 เดือน สิงหาคม พ.ศ. 2569", 10),
        P(
            "ได้รับอนุมัติ/เห็นชอบหลักสูตรจากสภาวิชาการ ในการประชุมครั้งที่ ........ "
            "เมื่อวันที่ ......... เดือน ...... พ.ศ. ....",
            10,
        ),
        P(
            "ได้รับอนุมัติ/เห็นชอบหลักสูตรจากสภามหาวิทยาลัย ในการประชุมครั้งที่ 7/2569 "
            "เมื่อวันที่ 7 เดือน กรกฎาคม พ.ศ. 2569",
            10,
        ),
        P("ได้รับอนุมัติ/เห็นชอบหลักสูตรจากสภาวิชาชีพ (ถ้ามี) เมื่อวันที่ ......... เดือน ...... พ.ศ. ......", 10),
    ]
    doc = Document(source_name="a.docx", source_type="docx", blocks=blocks)
    r = extract_approval(doc)
    d = r.data
    assert d["status"] == "ปรับปรุง" and d["previous_year"] == 2565 and d["start_year"] == 2570
    rows = {a["level_key"]: a for a in d["approvals"]}
    assert rows["committee_ug"]["meeting_no"] == "6"
    assert rows["committee_ug"]["date"]["iso"] == "2026-08-11", "wrapped date line is joined"
    assert rows["academic_council"]["pending"] is True and rows["academic_council"]["date"] is None
    assert rows["university_council"]["resolution"] == "อนุมัติ"
    assert rows["university_council"]["meeting_no"] == "7/2569"
    assert rows["professional_council"]["pending"] is True
    assert d["missing_levels"] == ["สภาวิชาการ", "อว. รับทราบความเห็นชอบหลักสูตร"]
    assert d["count"] == 2

    checks = {c.key: c for c in run_checks({"appr": d, "info": {"values": {"start_year": 2569}}})}
    assert checks["approval_present"].status == "pass"
    assert checks["approval_complete"].status == "warn"
    assert "สภาวิชาการ" in checks["approval_complete"].message
    assert checks["approval_order"].status == "warn", (
        "university council (Jul) before committee (Aug)"
    )
    assert checks["approval_vs_start"].status == "pass"
    assert checks["approval_vs_info"].status == "warn"
    md = render_approval(d)
    assert "| สภามหาวิทยาลัย | 7/2569 | 7 กรกฎาคม 2569 | อนุมัติ | 10 |" in md and "ยังไม่มีมติ" in md


def test_teachers_degrees_institutions_and_checks() -> None:
    from ocl_api.extract.render import render_teachers
    from ocl_api.extract.teachers import (
        extract_teachers,
        split_degrees,
        split_institutions,
        split_name,
    )

    assert split_name("ผู้ช่วยศาสตราจารย์\nดร.ภัทรพงษ์ เกริกสกุล") == {
        "rank": "ผศ.",
        "doctor": True,
        "name": "ภัทรพงษ์ เกริกสกุล",
    }
    assert split_name("อาจารย์ ดร.ศุภิกา วานิชชัง")["rank"] == "อาจารย์"
    assert split_name("รศ.ดร.พรทิพย์ศิริสุนทราลักษณ์")["name"] == "พรทิพย์ศิริสุนทราลักษณ์"
    degs = split_degrees(
        "วท.บ. (จิตวิทยา), 2538\nPDSC, Economics, 2545\nM.A. (Economics of\nDevelopment), 2546\nศ.ด., 2558"
    )
    assert [(d["degree"], d["field"], d["year"], d["level"]) for d in degs] == [
        ("วท.บ.", "จิตวิทยา", 2538, "ตรี"),
        ("PDSC", "Economics", 2545, "โท"),
        ("M.A.", "Economics of Development", 2546, "โท"),
        ("ศ.ด.", None, 2558, "เอก"),
    ]
    # PDF: one line, Thai → Latin → country boundaries
    assert split_institutions(
        "มหาวิทยาลัยศรีนครินทรวิโรฒ Ecole Nationale (ENSIA), France University of Wisconsin-Madison, USA",
        3,
    ) == [
        "มหาวิทยาลัยศรีนครินทรวิโรฒ",
        "Ecole Nationale (ENSIA), France",
        "University of Wisconsin-Madison, USA",
    ]
    # docx: a Latin name wrapped over three lines
    assert split_institutions(
        "ม.เกษตรศาสตร์\nม.เกษตรศาสตร์\nThe United Graduate School of\nAgricultural Sciences, Tottori\nUniversity, Japan",
        3,
    )[2] == ("The United Graduate School of Agricultural Sciences, Tottori University, Japan")
    assert split_institutions("ก\nข\nค\nง", 2) is None, "Thai lines never merge"
    assert split_institutions("จุฬาลงกรณ์มหาวิทยาลัยมหาวิทยาลัยธรรมศาสตร์", 2) == [
        "จุฬาลงกรณ์มหาวิทยาลัย",
        "มหาวิทยาลัยธรรมศาสตร์",
    ]

    hdr = ["ลำดับที่", "รายชื่อคณาจารย์", "คุณวุฒิการศึกษา ตรี-โท-เอก (สาขาวิชา) ปีที่จบ", "สถาบันที่สำเร็จการศึกษา"]
    blocks = [
        H("หมวดที่ 1 ข้อมูลทั่วไป", 1, 5),
        H("11. อาจารย์ผู้รับผิดชอบหลักสูตรและคุณสมบัติ", 2, 8),
        Table(
            rows=[
                hdr,
                ["1", "รศ.ดร.สมชาย ใจดี", "วท.บ. (เคมี), 2540\nปร.ด. (เคมี), 2548", "ม.ก\nม.ข"],
            ],
            page=8,
        ),
        H("12. อาจารย์ประจำหลักสูตรและคุณสมบัติ", 2, 9),
        Table(
            rows=[
                hdr,
                ["วิชาเอกก", "", "", ""],
                ["1*", "รศ.ดร.สมชาย ใจดี", "วท.บ. (เคมี), 2540\nปร.ด. (เคมี), 2548", "ม.ก\nม.ข"],
                ["2", "อาจารย์สมหญิง ดีมาก", "ศศ.บ. (ไทย), 2550", "ม.ค"],
            ],
            page=9,
        ),
        P("* อาจารย์ผู้รับผิดชอบหลักสูตร", 9),
    ]
    doc = Document(source_name="t.docx", source_type="docx", blocks=blocks)
    r = extract_teachers(doc)
    ts = r.data["teachers"]
    assert [t["name"] for t in ts] == ["สมชาย ใจดี", "สมหญิง ดีมาก"] and r.data[
        "responsible_count"
    ] == 1
    assert ts[0]["responsible"] and ts[0]["group"] == "วิชาเอกก" and ts[0]["highest_level"] == "เอก"
    assert ts[0]["degrees"][1]["institution"] == "ม.ข" and ts[0]["meta"]["source"]["page"] == 9
    assert ts[1]["rank"] == "อาจารย์" and ts[1]["doctor"] is False and ts[1]["highest_level"] == "ตรี"
    checks = {
        c.key: c for c in run_checks({"teachers": r.data, "info": {"values": {"level": "ป.ตรี"}}})
    }
    assert checks["teachers_present"].status == "pass"
    assert (
        checks["teacher_count"].status == "warn" and "วิชาเอกก 1" in checks["teacher_count"].message
    )
    assert checks["teacher_qualification"].status == "pass"
    md = render_teachers(r.data)
    assert (
        "| 1* | สมชาย ใจดี | รศ. ดร. | วิชาเอกก | วท.บ. (เคมี), 2540 – ม.ก · ปร.ด. (เคมี), 2548 – ม.ข | 9 |"
        in md
    )


def test_admission_plan_tables_and_checks() -> None:
    from ocl_api.extract.plan import extract_plan
    from ocl_api.extract.render import render_plan

    blocks = [
        H("หมวดที่ 1 ข้อมูลทั่วไป", 1, 5),
        P("8. สถานที่จัดการเรียนการสอน คณะเศรษฐศาสตร์ และผ่านระบบออนไลน์", 7),
        H("หมวดที่ 2 ข้อมูลเฉพาะของหลักสูตร", 1, 11),
        H("4. แผนการรับนิสิต", 2, 14),
        Table(
            rows=[
                ["ชั้นปีที่ศึกษา", "จำนวนนิสิตแต่ละปีการศึกษา", "", "", ""],
                ["ชั้นปีที่ศึกษา", "2569", "", "2570", ""],
                ["", "แผน 1", "แผน 2", "แผน 1", "แผน 2"],
                ["ชั้นปีที่ 1", "5", "6", "5", "6"],
                ["ชั้นปีที่ 2", "-", "-", "5", "6"],
                ["รวม", "5", "6", "10", "12"],
                ["คาดว่าจะสำเร็จการศึกษา", "-", "-", "5", "6"],
            ],
            page=14,
        ),
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 25),
        P("วอภ485 สหกิจศึกษา 6(0-18-0)", 30),
        H("หมวดที่ 5 การจัดกระบวนการเรียนรู้และการประเมินผล", 1, 40),
        H("1. การจัดกระบวนการเรียนรู้", 2, 40),
        Table(
            rows=[["ผลลัพธ์การเรียนรู้ของหลักสูตร", "วิธีการสอน/กิจกรรมการเรียนรู้"], ["PLO1: ก", "บรรยาย"]],
            page=40,
        ),
        H("2. การประเมินผลลัพธ์การเรียนรู้", 2, 41),
    ]
    doc = Document(source_name="p.docx", source_type="docx", blocks=blocks)
    r = extract_plan(doc)
    d = r.data
    assert [p["name"] for p in d["plans"]] == ["แผน 1", "แผน 2"], "side-by-side plans are split"
    p1, p2 = d["plans"]
    assert (
        p1["years"] == ["2569", "2570"]
        and p1["rows"][1]["values"] == [0, 5]
        and p1["total"] == [5, 10]
    )
    assert p2["graduates"] == [0, 6] and d["intake_per_year"] == 11 and d["duration_years"] == 2
    assert (
        d["teaching_modes"] == ["On-site", "Online", "Hybrid", "WIL"]
        and d["meta"]["teaching_modes"]["inferred"]
    )
    assert d["teaching_methods"] == [
        {"outcome": "PLO1: ก", "methods": "บรรยาย", "meta": d["teaching_methods"][0]["meta"]}
    ]
    checks = {
        c.key: c
        for c in run_checks(
            {"plan": d, "info": {"values": {"start_year": 2570, "duration_years": 2}}}
        )
    }
    assert checks["plan_present"].status == "pass" and checks["plan_totals"].status == "pass"
    assert checks["plan_vs_start"].status == "warn" and checks["plan_vs_duration"].status == "pass"
    assert checks["teaching_modes_inferred"].status == "info"
    md = render_plan(d)
    assert (
        "## แผน 2" in md and "| ชั้นปีที่ 2 | 0 | 6 |" in md and "On-site · Online · Hybrid · WIL" in md
    )

    # single plan with a merged "จำนวนนิสิต | 2570 | 2571" header and a mismatching total
    t = Table(
        rows=[
            ["จำนวนนิสิต", "2570", "2571"],
            ["ชั้นปีที่ 1", "70", "70"],
            ["ชั้นปีที่ 2", "-", "70"],
            ["รวม", "70", "150"],
        ],
        page=15,
    )
    doc2 = Document(
        source_name="q.docx",
        source_type="docx",
        blocks=[H("หมวดที่ 2 ข้อมูลเฉพาะของหลักสูตร", 1, 11), H("4. แผนการรับนิสิต", 2, 15), t],
    )
    d2 = extract_plan(doc2).data
    assert d2["plans"][0]["name"] is None and d2["plans"][0]["total"] == [70, 150]
    checks = {c.key: c for c in run_checks({"plan": d2, "info": {}})}
    assert checks["plan_totals"].status == "warn" and "2571" in checks["plan_totals"].message


def test_modules_headings_descriptions_and_checks() -> None:
    from ocl_api.extract.modules import extract_modules, parse_heading
    from ocl_api.extract.render import render_modules

    assert parse_heading("3.2.2.4 ชุดวิชาการประกอบอาหารเพื่อสุขภาพ (Health Food Preparation)") == {
        "number": "3.2.2.4",
        "name_th": "การประกอบอาหารเพื่อสุขภาพ",
        "name_en": "Health Food Preparation",
        "credits": None,
        "counted": True,
        "description_inline": None,
    }
    assert (
        parse_heading("3.2.2.2 ชุดวิชาการเงินเพื่อความยั่งยืน (Sustainable Finance) จำนวน 4 หน่วยกิต")[
            "credits"
        ]
        == 4
    )
    assert parse_heading("3.2.1.2 ชุดวิชาปรับพื้นฐาน (Foundation) ไม่นับหน่วยกิต")["counted"] is False
    assert parse_heading("1) ชุดวิชาวิถีชีวิตและชุมชน มีรายวิชาต่อไปนี้") == {
        "number": "1",
        "name_th": "วิถีชีวิตและชุมชน",
        "name_en": None,
        "credits": None,
        "counted": True,
        "description_inline": None,
    }
    assert parse_heading("3.2.1 วิชาบังคับ กำหนดให้เรียน จำนวน 10 ชุดวิชา") is None

    blocks = [
        H("หมวดที่ 4 โครงสร้างหลักสูตร รายวิชา และหน่วยกิต", 1, 25),
        H("2. รายละเอียดของหมวดวิชาและหน่วยกิต", 2, 26),
        P("2.2.1 วิชาบังคับ กำหนดให้เรียน จำนวน 2 ชุดวิชา รวม 6 หน่วยกิต ดังนี้", 27),
        P("2.2.1.1 ชุดวิชาพื้นฐานเคมี", 27),
        P("คม100 เคมีทั่วไป 1 3(3-0-6)", 27),
        P("2.2.1.2 ชุดวิชาฟิสิกส์", 27),
        P("ฟส100 ฟิสิกส์ทั่วไป 3(3-0-6)", 27),
        H("3. คำอธิบายชุดวิชา/รายวิชา", 2, 30),
        P("3.2.1 วิชาบังคับ กำหนดให้เรียน จำนวน 2 ชุดวิชา รวม 6 หน่วยกิต ดังนี้", 34),
        P("3.2.1.1 ชุดวิชาพื้นฐานเคมี", 34),
        P("(Basic Chemistry)", 34),
        P("ปริมาณสัมพันธ์ โครงสร้างอะตอม และสมดุลเคมี", 34),
        P("Stoichiometry, atomic structure and chemical equilibrium.", 34),
        P("คม100 เคมีทั่วไป 1 3(3-0-6)", 34),
        P("CH100 General Chemistry I", 34),
        P("ปริมาณสัมพันธ์ โครงสร้างอะตอม", 34),
        P("3.2.1.2 ชุดวิชาฟิสิกส์ (Physics) จำนวน 3 หน่วยกิต", 35),
        Table(rows=[["ฟส100", "ฟิสิกส์ทั่วไป", "3(3-0-6)"], ["PY100", "General Physics", ""]], page=35),
        P("3.2.2 วิชาเลือก กำหนดให้เลือกเรียน จำนวน 1 ชุดวิชา รวมไม่น้อยกว่า 10 หน่วยกิต จากชุดวิชาต่อไปนี้", 36),
    ]
    doc = Document(source_name="m.docx", source_type="docx", blocks=blocks)
    r = extract_modules(doc)
    mods = r.data["modules"]
    assert [m["name_th"] for m in mods] == ["พื้นฐานเคมี", "ฟิสิกส์"] and r.data["listed_in_item2"] == [
        "พื้นฐานเคมี",
        "ฟิสิกส์",
    ]
    assert mods[0]["name_en"] == "Basic Chemistry" and mods[0]["group"] == "วิชาบังคับ"
    assert mods[0]["description_th"] == "ปริมาณสัมพันธ์ โครงสร้างอะตอม และสมดุลเคมี"
    assert mods[0]["description_en"].startswith("Stoichiometry") and mods[0]["course_codes"] == [
        "คม100"
    ]
    assert (
        mods[1]["credits"] == 3
        and mods[1]["course_codes"] == ["ฟส100"]
        and mods[1]["description_th"] is None
    )
    assert mods[1]["meta"]["note"] == "ไม่พบคำอธิบายชุดวิชา"
    assert r.data["groups"][0] == {
        "name": "วิชาบังคับ",
        "declared_modules": 2,
        "declared_credits": 6,
        "page": 34,
    }
    assert (
        r.data["groups"][1]["declared_modules"] == 1
        and r.data["groups"][1]["declared_credits"] == 10
    )

    courses = {"courses": [{"code_th": "คม100", "credits": 3}, {"code_th": "ฟส100", "credits": 4}]}
    checks = {c.key: c for c in run_checks({"modules": r.data, "courses": courses})}
    assert checks["modules_present"].status == "pass"
    assert checks["modules_vs_declared"].status == "pass", "electives declare how many to choose"
    assert checks["modules_fields"].status == "warn" and "ฟิสิกส์" in checks["modules_fields"].message
    assert checks["modules_vs_courses"].status == "pass"
    assert (
        checks["modules_credits"].status == "warn" and "4 ≠ 3" in checks["modules_credits"].message
    )
    md = render_modules(r.data)
    assert "### 3.2.1.1 ชุดวิชาพื้นฐานเคมี (Basic Chemistry)" in md and "รายวิชา: ฟส100" in md


def test_info_fewshot_matches_missing_fields_and_falls_back(monkeypatch) -> None:
    import json as _json

    import ocl_api.extract.info as info_mod
    from ocl_api.fewshot import narrow_fields
    from ocl_api.llm.gateway import LLMTruncated

    shot = ("จากหมวดที่ 1 ด้านล่าง ให้ค่าของฟิลด์: program_code, name_th, total_credits\n\nรหัส 1",
            _json.dumps({"program_code": None, "name_th": "ก", "total_credits": 127}))  # fmt: skip
    ((inp, out),) = narrow_fields([shot], ["total_credits"])
    assert "ให้ค่าของฟิลด์: total_credits\n" in inp and inp.endswith("รหัส 1")
    assert _json.loads(out) == {"total_credits": 127}

    # a one-field request with examples loops until max_tokens: ask again without them
    monkeypatch.setattr(info_mod, "fewshot_examples", lambda part, src: [shot])
    doc = info_doc()
    doc.blocks = [b for b in doc.blocks if "ชื่อเต็ม" not in b.text and "ชื่อย่อ" not in b.text]
    calls = []

    class FakeGateway:
        provider, model = "fake", "fake"

        def chat_json(self, system, user, schema=None, max_tokens=None, examples=None):
            calls.append(examples)
            if examples:
                assert _json.loads(examples[0][1]).keys() == {"degree_full_th", "degree_abbr_th",
                                                               "degree_full_en", "degree_abbr_en"}  # fmt: skip
                raise LLMTruncated("reply truncated at max_tokens=1024")

            class R:
                data = {"degree_full_en": "Bachelor of Science Program in Testing"}

                class usage:
                    @staticmethod
                    def to_dict():
                        return {"calls": 1}

            return R()

    r = info_mod.extract_info(doc, FakeGateway())
    assert len(calls) == 2 and calls[1] is None
    assert r.data["values"]["degree_full_en"] == "Bachelor of Science Program in Testing"
    assert any("ถามซ้ำโดยไม่ใช้ตัวอย่าง" in n for n in r.notes)
