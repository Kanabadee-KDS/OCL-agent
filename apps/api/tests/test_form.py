"""คู่มือหลักสูตร form (FS-2b): one spec for web and progress, options, approved book, teachers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.curriculum_form import FORM, SECTION1_VALUES, fields, progress
from ocl_api.extract.info import FIELDS as INFO_FIELDS
from ocl_api.sections import normalized

SECRET = "form-secret-for-tests-only-32bytes"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


ADMIN, CENTRAL, DEAN = h("admin@g.swu.ac.th"), h("central@g.swu.ac.th"), h("dean@g.swu.ac.th")


def test_one_spec_for_import_form_and_split() -> None:
    by_key = {f["key"]: f for n in FORM for f in fields(n)}
    for f in INFO_FIELDS:  # every field the import reads is on the form, with its label
        if f["key"] in by_key:
            assert by_key[f["key"]]["label"] == f["label"], f["key"]
    on_form = {f["key"] for f in INFO_FIELDS} & set(by_key)
    assert len(on_form) == len(INFO_FIELDS), "the form shows every field the import reads"
    s1 = {f["key"] for f in fields("1") if f["path"].startswith("info.values.")}
    assert s1 == SECTION1_VALUES and "name_th" not in SECTION1_VALUES

    # data stored under an older split reads in the right section
    old = {"0": {"info": {"values": {"name_th": "ก", "program_type_text": "ข"}}},
           "1": {"info": {"values": {"language": "ไทย"}}}}  # fmt: skip
    n = normalized(old)
    assert n["0"]["info"]["values"] == {"name_th": "ก"}
    assert n["1"]["info"]["values"] == {"language": "ไทย", "program_type_text": "ข"}


def test_progress_counts_required_items() -> None:
    blank = progress({})
    assert blank["0"]["done"] == 0 and "ชื่อหลักสูตร (ไทย)" in blank["0"]["missing"]
    assert blank["2"]["total"] == 2 and blank["5"]["missing"] == ["การอนุมัติ/เห็นชอบ"]
    renew = {"0": {"info": {"values": {"revision_type": "ปรับปรุง"}}}}
    assert progress(renew)["0"]["total"] == blank["0"]["total"] + 1, "ฉบับเดิม only when ปรับปรุง"
    plan = {"2": {"plan": {"plans": [{"rows": [{"values": [0, 50]}]}], "teaching_modes": ["WIL"]}}}
    assert progress(plan)["2"] == {"done": 2, "total": 2, "missing": []}


@pytest.fixture
def client(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {"DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url,
                 "DATABASE_SCHEMA": schema, "AUTH_SECRET": SECRET}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    users = UserStore(pg_url, schema)
    users.upsert("admin@g.swu.ac.th", roles=["admin"])
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    clear_user_cache()
    return TestClient(app)


def _new(c: TestClient, name: str, level: str = "ป.ตรี") -> int:
    return c.post("/api/curricula", json={"name_th": name, "level": level}, headers=CENTRAL).json()[
        "id"
    ]


def test_spec_options_and_progress_on_the_api(client: TestClient) -> None:
    c = client
    form = c.get("/api/curricula/form", headers=DEAN).json()
    assert sorted(form["sections"]) == ["0", "1", "2", "5"] and form["labels"]["0"].startswith(
        "หมวด 0"
    )
    modes = [f for g in form["sections"]["2"] for f in g["fields"] if f["key"] == "teaching_modes"][
        0
    ]
    assert (
        modes["options"] == ["On-site", "Online", "Hybrid", "WIL"]
        and modes["lookup_key"] == "teaching_modes"
    )

    add = {"key": "teaching_modes", "value": "Blended"}
    assert c.post("/api/curricula/form/options", json=add, headers=DEAN).status_code == 403
    out = c.post("/api/curricula/form/options", json=add, headers=ADMIN).json()
    modes = [f for g in out["sections"]["2"] for f in g["fields"] if f["key"] == "teaching_modes"][
        0
    ]
    assert modes["options"][-1] == "Blended"
    col = {"key": "approvals.level", "value": "สภาการพยาบาล"}
    assert c.post("/api/curricula/form/options", json=col, headers=ADMIN).status_code == 200
    assert (
        c.post(
            "/api/curricula/form/options", json={"key": "name_th", "value": "x"}, headers=ADMIN
        ).status_code
        == 400
    )

    did = _new(c, "หลักสูตร ก")
    p = c.get(f"/api/curricula/{did}", headers=CENTRAL).json()["progress"]
    assert p["0"]["done"] == 2, "name and level given at creation"
    s0 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
    s0["info"]["values"].update(name_en="Program A", faculty="คณะ ก")
    c.put(f"/api/curricula/{did}/sections/0", json={"data": s0}, headers=CENTRAL)
    assert c.get(f"/api/curricula/{did}", headers=CENTRAL).json()["progress"]["0"]["done"] == 4


def test_approved_book(client: TestClient, tmp_path: Path) -> None:
    c = client
    did = _new(c, "หลักสูตร ข")
    url = f"/api/curricula/{did}/book"
    assert c.get(url, headers=CENTRAL).status_code == 404
    assert c.post(url, files={"file": ("x.pdf", b"not a pdf")}, headers=CENTRAL).status_code == 400
    pdf = b"%PDF-1.4\n% book\n"
    assert c.post(url, files={"file": ("เล่ม.pdf", pdf)}, headers=DEAN).status_code == 403
    r = c.post(url, files={"file": ("เล่ม.pdf", pdf)}, headers=CENTRAL)
    assert r.status_code == 200
    book = r.json()["data"]["info"]["values"]["approved_book"]
    assert book["name"] == "เล่ม.pdf" and book["size"] == len(pdf) and book["label"] == "ฉบับอนุมัติ"
    got = c.get(url, headers=DEAN)
    assert got.status_code == 200 and got.content == pdf
    big = b"%PDF" + b"0" * (50 * 1024 * 1024)
    assert c.post(url, files={"file": ("big.pdf", big)}, headers=CENTRAL).status_code == 413
    p = c.get(f"/api/curricula/{did}", headers=CENTRAL).json()["progress"]["0"]["missing"]
    assert not any("ไฟล์เล่ม" in m for m in p)


def test_teacher_check(client: TestClient) -> None:
    c = client

    def teachers(did: int, rows: list[dict]) -> None:
        s0 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
        c.put(
            f"/api/curricula/{did}/sections/0",
            json={"data": {**s0, "teachers": {"teachers": rows}}},
            headers=CENTRAL,
        )

    a, b = _new(c, "หลักสูตร ค"), _new(c, "หลักสูตร ง", level="ป.โท")
    teachers(a, [
        {"name": "สมชาย ใจดี", "rank": "อาจารย์", "highest_level": "โท", "responsible": True},
        {"name": "สมหญิง  รักเรียน", "rank": "อาจารย์", "highest_level": "ตรี", "responsible": True},
        {"name": "สมศรี มีสุข", "rank": "อาจารย์", "highest_level": "ตรี", "responsible": False},
    ])  # fmt: skip
    teachers(
        b,
        [
            {
                "name": "สมหญิง รักเรียน",
                "rank": "รองศาสตราจารย์",
                "highest_level": "โท",
                "responsible": True,
            }
        ],
    )
    r = c.get(f"/api/curricula/{a}/teachers/check", headers=DEAN).json()
    assert r["responsible"] == 2 and r["required"] == 5
    assert any("2 คน" in i for i in r["issues"]) and any("สมหญิง" in i for i in r["issues"])
    assert not any("สมชาย" in i for i in r["issues"]), "a master's is enough for a bachelor's"
    assert r["duplicates"] == [{"name": "สมหญิง รักเรียน", "curriculum": "หลักสูตร ง", "id": b}]
    rb = c.get(f"/api/curricula/{b}/teachers/check", headers=DEAN).json()
    assert rb["required"] == 3 and not any("สมหญิง" in i for i in rb["issues"]), "รศ. qualifies"


def test_course_catalog_offers_other_curricula_courses(client: TestClient) -> None:
    """US-M1-20 until the central course database (FS-3): courses already in the system."""
    c = client
    a, b = _new(c, "หลักสูตร จ"), _new(c, "หลักสูตร ฉ")

    def courses(did: int, rows: list[dict]) -> None:
        s4 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["4"]["data"]
        c.put(
            f"/api/curricula/{did}/sections/4",
            json={"data": {**s4, "courses": {"courses": rows}}},
            headers=CENTRAL,
        )

    courses(
        a,
        [
            {"code_th": "ทวพ211", "name_th": "พอลิเมอร์เบื้องต้น", "credits": 3},
            {"code_th": "ศท111", "name_th": "ศิลปะการใช้ชีวิต"},
        ],
    )
    courses(b, [{"code_th": "ศท111", "name_th": "ศิลปะการใช้ชีวิต"}])
    got = c.get(f"/api/curricula/courses/catalog?exclude={b}", headers=DEAN).json()
    assert [x["code_th"] for x in got] == ["ทวพ211"], "not the courses this curriculum already has"
    assert got[0]["from"] == "หลักสูตร จ" and got[0]["credits"] == 3
    assert (
        c.get(f"/api/curricula/courses/catalog?q=พอลิ เมอร์&exclude={b}", headers=DEAN).json()[0][
            "code_th"
        ]
        == "ทวพ211"
    )
    assert c.get(f"/api/curricula/courses/catalog?q=zzz&exclude={b}", headers=DEAN).json() == []
