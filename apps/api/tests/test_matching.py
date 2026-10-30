"""จับคู่ข้อมูล (FS-3d · US-M1-13 · BR-05 BR-09): proposals, then only what a person confirms."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.matching import bare

SECRET = "match-secret-for-tests-only-32bytes"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, DEAN = h("central@g.swu.ac.th"), h("dean@g.swu.ac.th")
COURSE = {"code_en": "X", "name_en": "X", "transcript_th": "x", "transcript_en": "X", "course_type": "วิชาแกน",
          "status": "ใช้งาน"}  # fmt: skip


@pytest.fixture
def env(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.external import ExternalStore
    from ocl_api.external.sample import SampleAdapter
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {"DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url,
                 "DATABASE_SCHEMA": schema, "AUTH_SECRET": SECRET}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    ExternalStore(pg_url, schema).load(SampleAdapter(), "huris")
    users = UserStore(pg_url, schema)
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    clear_user_cache()
    c = TestClient(app)
    did = c.post("/api/curricula", json={"name_th": "วท.บ. จับคู่"}, headers=CENTRAL).json()["id"]
    secs = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()
    s0, s4 = secs["0"]["data"], secs["4"]["data"]
    s0["teachers"] = {"teachers": [
        {"name": "ผศ.ดร. ชื่อ นามสกุล 1", "highest_level": "โท"},  # one HURIS hit, other qualification
        {"name": "คนที่ไม่มีในระบบ"},
        {"name": "มีแล้ว", "pid": "SWU01002"},
    ]}  # fmt: skip
    s4["courses"] = {"courses": [
        {"code_th": "ทวพ100", "name_th": "เดิม", "credit_text": "3(3-0-6)"},
        {"code_th": "ทวพ101", "name_th": "ชื่อในเล่มต่าง", "credit_text": "3(3-0-6)"},
        {"code_th": "ทวพ999", "name_th": "ใหม่", "credit_text": "1(0-2-1)"},
    ]}  # fmt: skip
    c.put(f"/api/curricula/{did}/sections/0", json={"data": s0}, headers=CENTRAL)
    c.put(f"/api/curricula/{did}/sections/4", json={"data": s4}, headers=CENTRAL)
    c.post(
        "/api/courses",
        json={**COURSE, "code_th": "ทวพ100", "name_th": "เดิม", "credit_text": "3(3-0-6)"},
        headers=CENTRAL,
    )
    c.post(
        "/api/courses",
        json={**COURSE, "code_th": "ทวพ101", "name_th": "ชื่อกลาง", "credit_text": "3(3-0-6)"},
        headers=CENTRAL,
    )
    return c, did


def test_teachers_are_proposed_then_confirmed(env) -> None:
    c, did = env
    m = c.get(f"/api/curricula/{did}/match", headers=CENTRAL).json()
    t = m["teachers"]
    assert [x["state"] for x in t] == ["one", "none", "linked"]
    assert (
        t[0]["candidates"][0]["pid"] == "SWU01001" and t[0]["candidates"][0]["differs"] is True
    ), "BR-05"

    def s0() -> list[dict]:
        sec = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
        return sec["teachers"]["teachers"]

    assert "pid" not in s0()[0], "nothing stored before a person confirms"
    # keep the book's qualification
    r = c.post(f"/api/curricula/{did}/match/teachers",
               json={"choices": [{"index": 0, "pid": "SWU01001", "quals": "book"}]}, headers=CENTRAL).json()  # fmt: skip
    assert r["matched"] == 1 and r["teachers"][0]["state"] == "linked"
    assert s0()[0]["pid"] == "SWU01001" and s0()[0]["highest_level"] == "โท"


def test_courses_follow_bis09(env) -> None:
    c, did = env
    co = c.get(f"/api/curricula/{did}/match", headers=CENTRAL).json()["courses"]
    assert [(x["state"], x["version"]) for x in co] == [("same", 1), ("changed", 2), ("new", 1)]
    r = c.post(f"/api/curricula/{did}/match/courses",
               json={"choices": [{"index": 0, "accept": True}, {"index": 1, "accept": True}, {"index": 2, "accept": False}]},
               headers=CENTRAL).json()  # fmt: skip
    assert r["matched"] == 2 and [x["state"] for x in r["courses"]] == ["linked", "linked", "new"]
    v = c.get("/api/courses/ทวพ101", headers=CENTRAL).json()
    assert (
        v["latest"] == 2 and v["versions"][0]["kind"] == "ปรับปรุง" and v["name_th"] == "ชื่อในเล่มต่าง"
    )
    assert c.get("/api/courses/ทวพ999", headers=CENTRAL).status_code == 404, (
        "not confirmed: not created"
    )
    c.post(
        f"/api/curricula/{did}/match/courses",
        json={"choices": [{"index": 2, "accept": True}]},
        headers=CENTRAL,
    )
    assert c.get("/api/courses/ทวพ999", headers=CENTRAL).json()["versions"][0]["kind"] == "ใหม่"
    # under faculty review the courses may not change, and the central database stays as it was
    c.post(f"/api/curricula/{did}/transition", json={"action": "submit"}, headers=CENTRAL)
    no = c.post(
        f"/api/curricula/{did}/match/courses",
        json={"choices": [{"index": 0, "accept": True}]},
        headers=DEAN,
    )
    assert no.status_code == 403


def test_bare_names() -> None:
    assert bare("ผศ.ดร. ชื่อ  นามสกุล") == "ชื่อนามสกุล" == bare("[ชื่อ นามสกุล]")
    assert bare("รองศาสตราจารย์ ดร.สมชาย ใจดี") == "สมชายใจดี"


def test_a_name_one_letter_off_huris_is_offered_with_both_spellings(env) -> None:
    """OCR-2a2: an OCR model "corrected" a name; nothing changes until a person picks."""
    c, did = env
    secs = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()
    s0 = secs["0"]["data"]
    s0["teachers"]["teachers"][1] = {"name": "ชื่อ นามสกุลล 1"}  # HURIS: [ชื่อ นามสกุล 1]
    c.put(f"/api/curricula/{did}/sections/0", json={"data": s0}, headers=CENTRAL)
    t = c.get(f"/api/curricula/{did}/match", headers=CENTRAL).json()["teachers"][1]
    assert t["state"] == "near" and all(x["near"] for x in t["candidates"])
    assert t["candidates"][0]["huris_name"] == "[ชื่อ นามสกุล 1]", "the nearest first"
    r = c.post(f"/api/curricula/{did}/match/teachers",
               json={"choices": [{"index": 1, "pid": t["candidates"][0]["pid"], "name": "huris"}]},
               headers=CENTRAL).json()  # fmt: skip
    assert r["matched"] == 1
    sec = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
    assert sec["teachers"]["teachers"][1]["name"] == "[ชื่อ นามสกุล 1]", "the person chose HURIS"
    assert sec["teachers"]["teachers"][0]["name"] == "ผศ.ดร. ชื่อ นามสกุล 1", "others untouched"


def test_near_names() -> None:
    from ocl_api.fuzzy import near

    assert near("ศรีวิกรณ์", "ศรีวิภรณ์") and near("พิสุทธิ", "พิสุทธิ์")
    assert not near("สมชาย", "สมชาย") and not near("อนุชา", "สมศักดิ์") and not near("ก", "ข")
