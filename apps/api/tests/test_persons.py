"""ทะเบียนบุคคลภายนอก (FS-3b · US-M1-19): one record, copied to every curriculum that uses it."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.persons import highest, masked

SECRET = "persons-secret-for-tests-only-32bytes"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, DEAN, TEACHER = h("central@g.swu.ac.th"), h("dean@g.swu.ac.th"), h("t@g.swu.ac.th")
P = {"kind": "อาจารย์พิเศษ", "title_full": "อาจารย์ ดร.", "title_short": "อ.ดร.", "position": "อาจารย์พิเศษ",
     "name_th": "สมหญิง ภายนอก", "name_en": "Somying Outside", "national_id": "1-2345-67890-12-3",
     "org": "สถาบันวิจัยยาง", "education": [["ปริญญาตรี", "วท.บ.", "เคมี", "ม.ก", "ไทย", "2548"],
     ["ปริญญาเอก", "ปร.ด.", "พอลิเมอร์", "ม.ข", "ไทย", "2556"]],
     "works": [{"title": "ยางธรรมชาติ", "type": "งานวิจัย", "year": "2566"}]}  # fmt: skip


@pytest.fixture
def client(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {"DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url,
                 "DATABASE_SCHEMA": schema, "AUTH_SECRET": SECRET}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    users = UserStore(pg_url, schema)
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    users.upsert("t@g.swu.ac.th", roles=["teacher"])
    clear_user_cache()
    return TestClient(app)


def test_register_validates_and_keeps_the_id_number_private(client: TestClient) -> None:
    c = client
    bad = c.post("/api/persons", json={**P, "national_id": "123"}, headers=CENTRAL)
    assert bad.status_code == 400 and "13 หลัก" in bad.json()["detail"]
    miss = c.post("/api/persons", json={"kind": "อาจารย์พิเศษ"}, headers=CENTRAL)
    assert miss.status_code == 400 and "ชื่อ-นามสกุล (ไทย)" in miss.json()["detail"]
    r = c.post("/api/persons", json=P, headers=CENTRAL)
    assert r.status_code == 201 and r.json()["id"] == "X001" and r.json()["highest"] == "เอก"
    lst = c.get("/api/persons", headers=CENTRAL).json()
    assert lst["counts"] == {"all": 1, "active": 1, "used": 0}
    assert lst["items"][0]["national_id"] == "x-xxxx-xxxxx-12-3", "masked in the list"
    assert c.get("/api/persons/X001", headers=CENTRAL).json()["national_id"] == P["national_id"]
    assert c.get("/api/persons", headers=TEACHER).status_code == 403
    found = c.get("/api/curricula/persons?q=สมหญิง", headers=DEAN).json()
    assert found == [{"xid": "X001", "name": "อ.ดร.สมหญิง ภายนอก", "rank": "อาจารย์พิเศษ",
                      "highest_level": "เอก", "org": "สถาบันวิจัยยาง", "kind": "อาจารย์พิเศษ"}]  # fmt: skip


def test_an_edit_reaches_every_curriculum_and_used_people_stay(client: TestClient) -> None:
    c = client
    c.post("/api/persons", json=P, headers=CENTRAL)
    row = c.get("/api/curricula/persons?q=สมหญิง", headers=CENTRAL).json()[0]
    ids = []
    for name in ("หลักสูตร ก", "หลักสูตร ข"):
        did = c.post("/api/curricula", json={"name_th": name}, headers=CENTRAL).json()["id"]
        s0 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
        s0["teachers"] = {"teachers": [{**row, "responsible": True}, {"name": "อ.อื่น"}]}
        c.put(f"/api/curricula/{did}/sections/0", json={"data": s0}, headers=CENTRAL)
        ids.append(did)
    p = c.get("/api/persons/X001", headers=CENTRAL).json()
    assert {u["draft_id"] for u in p["used_in"]} == set(ids)

    edu = [*P["education"], ["ปริญญาโท", "วท.ม.", "เคมี", "ม.ค", "ไทย", "2550"]]
    c.put(
        "/api/persons/X001",
        json={**P, "title_short": "รศ.ดร.", "position": "รองศาสตราจารย์", "education": edu},
        headers=CENTRAL,
    )
    for did in ids:
        t = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"][
            "teachers"
        ]["teachers"]
        assert t[0]["name"] == "รศ.ดร.สมหญิง ภายนอก" and t[0]["rank"] == "รองศาสตราจารย์"
        assert t[0]["responsible"] is True and t[1]["name"] == "อ.อื่น", (
            "the curriculum's own fields stay"
        )
    assert c.delete("/api/persons/X001", headers=CENTRAL).status_code == 409
    c.put("/api/persons/X001", json={**P, "active": False}, headers=CENTRAL)
    assert c.get("/api/curricula/persons?q=สมหญิง", headers=CENTRAL).json() == [], (
        "ไม่ใช้งาน: not offered"
    )
    c.post("/api/persons", json={**P, "name_th": "คนที่สอง"}, headers=CENTRAL)
    assert c.delete("/api/persons/X002", headers=CENTRAL).status_code == 204


def test_helpers() -> None:
    assert highest([["ปริญญาโท", "x"], ["ปริญญาตรี", "y"]]) == "โท" and highest([]) is None
    assert masked("1234567890123") == "x-xxxx-xxxxx-12-3" and masked(None) is None
