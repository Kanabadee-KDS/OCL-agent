"""ฐานข้อมูลรายวิชากลาง (FS-3a · US-M1-18 20): Versions, the curricula that use them."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.courses import CourseStore, same_content

SECRET = "courses-secret-for-tests-only-32bytes"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, DEAN = h("central@g.swu.ac.th"), h("dean@g.swu.ac.th")
FULL = {"code_en": "PMT211", "name_th": "พอลิเมอร์เบื้องต้น", "name_en": "Intro to Polymers",
        "transcript_th": "พอลิเมอร์เบื้องต้น", "transcript_en": "INTRO POLYMERS",
        "course_type": "วิชาแกน", "credit_text": "3(2-2-5)", "status": "ใช้งาน"}  # fmt: skip


@pytest.fixture
def env(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {"DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url,
                 "DATABASE_SCHEMA": schema, "AUTH_SECRET": SECRET}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    users = UserStore(pg_url, schema)
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    clear_user_cache()
    c = TestClient(app)

    def new(name: str, rows: list[dict]) -> int:
        did = c.post("/api/curricula", json={"name_th": name}, headers=CENTRAL).json()["id"]
        s4 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["4"]["data"]
        s4["courses"] = {"courses": rows}
        assert (
            c.put(
                f"/api/curricula/{did}/sections/4", json={"data": s4}, headers=CENTRAL
            ).status_code
            == 200
        )
        return did

    return c, new, CourseStore(pg_url, schema)


def s4(c: TestClient, did: int) -> list[dict]:
    return c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["4"]["data"]["courses"][
        "courses"
    ]


def test_backfill_turns_the_books_courses_into_versions(env) -> None:
    c, new, store = env
    a = new(
        "หลักสูตร ก",
        [
            {"code_th": "ศท111", "name_th": "ศิลปะการใช้ชีวิต", "credit_text": "3(3-0-6)"},
            {"code_th": "ทวพ211", "name_th": "พอลิเมอร์", "credit_text": "3(2-2-5)"},
        ],
    )
    b = new(
        "หลักสูตร ข",
        [
            {"code_th": "ศท111", "name_th": "ศิลปะ  การใช้ชีวิต", "credit_text": "3(3-0-6)"},
            {"code_th": "ทวพ211", "name_th": "พอลิเมอร์", "credit_text": "4(3-2-7)"},
        ],
    )
    assert store.backfill() == 4 and store.backfill() == 0, "once"
    assert [x["version"] for x in s4(c, a)] == [1, 1]
    assert [x["version"] for x in s4(c, b)] == [1, 2], "same text (spaces aside) = same Version"
    lst = c.get("/api/courses", headers=CENTRAL).json()
    assert lst["counts"]["all"] == 2 and lst["counts"]["ใช้งาน"] == 2
    poly = c.get("/api/courses/ทวพ211", headers=CENTRAL).json()
    assert poly["label"] == "ทวพ211-2" and [v["kind"] for v in poly["versions"]] == ["เดิม", "เดิม"]
    assert {(u["draft_id"], u["version"]) for u in poly["used_in"]} == {(a, 1), (b, 2)}
    assert c.get("/api/courses/ศท111", headers=CENTRAL).json()["unit"].startswith("สำนักนวัตกรรม")
    ev = c.get(f"/api/curricula/{a}", headers=CENTRAL).json()["sections"]["4"]["updated_by"]
    assert ev == "system"


def test_add_edit_version_and_delete(env) -> None:
    c, new, _ = env
    bad = c.post(
        "/api/courses", json={**FULL, "code_th": "ทวพ211", "credit_text": "3"}, headers=CENTRAL
    )
    assert bad.status_code == 400 and "x(a-b-c)" in bad.json()["detail"]
    miss = c.post("/api/courses", json={"code_th": "ทวพ211", "name_th": "x"}, headers=CENTRAL)
    assert miss.status_code == 400 and "รหัสวิชา (อังกฤษ)" in miss.json()["detail"]
    long = c.post(
        "/api/courses",
        json={**FULL, "code_th": "ทวพ211", "transcript_en": "X" * 41},
        headers=CENTRAL,
    )
    assert long.status_code == 400
    r = c.post("/api/courses", json={**FULL, "code_th": "ทวพ211"}, headers=CENTRAL)
    assert r.status_code == 201 and r.json()["label"] == "ทวพ211-1" and r.json()["credits"] == 3
    assert (
        c.post("/api/courses", json={**FULL, "code_th": "ทวพ211"}, headers=CENTRAL).status_code
        == 409
    )
    did = new("หลักสูตร ค", [{"code_th": "ทวพ211", "name_th": "พอลิเมอร์เบื้องต้น", "version": 1}])

    # a new Version: the curriculum keeps Version 1 (FS-3 Q2 ก) and sees that 2 exists
    up = {**FULL, "description_th": "ปรับคำอธิบาย", "new_version": True}
    r = c.put("/api/courses/ทวพ211", json=up, headers=CENTRAL).json()
    assert r["latest"] == 2 and r["versions"][0]["kind"] == "ปรับปรุง"
    assert s4(c, did)[0]["version"] == 1
    v = c.get(f"/api/curricula/{did}/courses/versions", headers=CENTRAL).json()["ทวพ211"]
    assert v["latest"] == 2 and v["description_th"] == "ปรับคำอธิบาย"
    # an edit without a new Version changes the latest in place
    r = c.put("/api/courses/ทวพ211", json={**FULL, "name_en": "Polymers I"}, headers=CENTRAL).json()
    assert r["latest"] == 2 and r["name_en"] == "Polymers I"
    # used: no delete (set ไม่ใช้งาน instead); faculty may edit but not delete
    assert c.delete("/api/courses/ทวพ211", headers=CENTRAL).status_code == 409
    assert c.delete("/api/courses/ทวพ211", headers=DEAN).status_code == 403
    c.post("/api/courses", json={**FULL, "code_th": "ทวพ999"}, headers=CENTRAL)
    assert c.delete("/api/courses/ทวพ999", headers=CENTRAL).status_code == 204


def test_curriculum_picks_and_creates_courses_in_the_central_database(env) -> None:
    c, new, _ = env
    for code, status in (("ทวพ211", "ใช้งาน"), ("ทวพ212", "ใช้งาน"), ("ทวพ213", "ไม่ใช้งาน")):
        c.post("/api/courses", json={**FULL, "code_th": code, "status": status}, headers=CENTRAL)
    did = new("หลักสูตร ง", [{"code_th": "ทวพ212", "name_th": "x", "version": 1}])
    got = c.get(f"/api/curricula/courses/catalog?exclude={did}", headers=DEAN).json()
    assert [x["code_th"] for x in got] == ["ทวพ211"], "in use only, not the ones it already has"
    assert got[0]["version"] == 1 and got[0]["credits"] == 3
    assert c.get(f"/api/curricula/courses/catalog?q=PMT&exclude={did}", headers=DEAN).json()
    assert c.get(f"/api/curricula/courses/catalog?q=zzz&exclude={did}", headers=DEAN).json() == []

    # สร้างรายวิชาใหม่ from a group: a ร่างรายวิชา, Version 1
    r = c.post(
        f"/api/curricula/{did}/courses",
        json={"code_th": "ทวพ300", "name_th": "ใหม่"},
        headers=CENTRAL,
    )
    assert r.status_code == 201 and r.json()["version"] == 1
    assert c.get("/api/courses/ทวพ300", headers=CENTRAL).json()["status"] == "ร่างรายวิชา"
    again = c.post(
        f"/api/curricula/{did}/courses", json={"code_th": "ทวพ211", "name_th": "x"}, headers=CENTRAL
    )
    assert again.status_code == 409 and "เลือกจากรายการแทน" in again.json()["detail"]
    # a curriculum under review: the faculty may not add courses
    c.post(f"/api/curricula/{did}/transition", json={"action": "submit"}, headers=CENTRAL)
    no = c.post(
        f"/api/curricula/{did}/courses", json={"code_th": "ทวพ301", "name_th": "x"}, headers=DEAN
    )
    assert no.status_code == 403


def test_same_content_reads_like_bis09() -> None:
    a = {"name_th": "พอลิเมอร์", "credit_text": "3(2-2-5)", "description_th": "ก ข"}
    assert same_content(a, {**a, "description_th": "กข"})
    assert not same_content(a, {**a, "credit_text": "3(3-0-6)"})
