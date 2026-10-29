"""ขอบเขตข้อมูล of the คู่มือหลักสูตร (FS-2e · US-M1-06 07): ส่วนงาน by the user's units,
หลักสูตร by the user's HURIS id among the teachers in 0.2, ทั้งมหาวิทยาลัย for the rest."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import User, clear_user_cache, sign_token
from ocl_api.curricula import visible
from ocl_api.db import connect

SECRET = "scope-secret-for-tests-only-32bytes"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


ADMIN, CENTRAL = h("admin@g.swu.ac.th"), h("central@g.swu.ac.th")
SCI, ECON, CUR = h("sci@g.swu.ac.th"), h("econ@g.swu.ac.th"), h("cur@g.swu.ac.th")
EXEC = h("exec@g.swu.ac.th")


@pytest.fixture
def env(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {"DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url,
                 "DATABASE_SCHEMA": schema, "AUTH_SECRET": SECRET}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    users = UserStore(pg_url, schema)
    users.upsert("admin@g.swu.ac.th", roles=["admin"])
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("sci@g.swu.ac.th", roles=["faculty"], unit="คณะวิทยาศาสตร์")
    users.upsert("econ@g.swu.ac.th", roles=["faculty"], unit="คณะเศรษฐศาสตร์")
    users.upsert("cur@g.swu.ac.th", roles=["curator"])
    users.upsert("exec@g.swu.ac.th", roles=["exec"])
    with connect(pg_url, schema) as conn:
        conn.execute("UPDATE users SET pid = 'SWU01001' WHERE email = 'cur@g.swu.ac.th'")
    clear_user_cache()
    c = TestClient(app)

    def new(name: str, faculty: str, pids: list[str]) -> int:
        did = c.post(
            "/api/curricula", json={"name_th": name, "faculty": faculty}, headers=CENTRAL
        ).json()["id"]
        s0 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
        s0["teachers"] = {"teachers": [{"name": f"อ.{p}", "pid": p} for p in pids]}
        c.put(f"/api/curricula/{did}/sections/0", json={"data": s0}, headers=CENTRAL)
        return did

    sci = new("วท.บ. ก", "คณะวิทยาศาสตร์", ["SWU01001", "SWU01002"])
    econ = new("ศ.ม. ข", "คณะเศรษฐศาสตร์", ["SWU09009"])
    return c, sci, econ


def ids(c: TestClient, headers: dict[str, str]) -> list[int]:
    return sorted(i["id"] for i in c.get("/api/curricula", headers=headers).json()["items"])


def test_each_role_sees_its_own_curricula(env) -> None:
    c, sci, econ = env
    assert ids(c, ADMIN) == ids(c, CENTRAL) == sorted([sci, econ]), "ทั้งมหาวิทยาลัย"
    assert ids(c, SCI) == [sci] and ids(c, ECON) == [econ], "ส่วนงาน: by the user's units"
    assert ids(c, CUR) == [sci], "หลักสูตร: the HURIS id is among the teachers in 0.2"
    assert c.get("/api/curricula", headers=SCI).json()["counts"]["import"] == 1


def test_opening_another_curriculum_directly_is_refused(env) -> None:
    c, sci, econ = env
    for path in ("", "/sections", "/teachers/check", "/book"):
        assert c.get(f"/api/curricula/{econ}{path}", headers=SCI).status_code == 403, path
        assert c.get(f"/api/curricula/{econ}{path}", headers=CUR).status_code == 403, path
    put = c.put(f"/api/curricula/{econ}/sections/3", json={"data": {}}, headers=SCI)
    assert put.status_code == 403 and "นอกขอบเขตข้อมูล" in put.json()["detail"]
    act = {"action": "check", "section": "3"}
    assert c.post(f"/api/curricula/{econ}/transition", json=act, headers=SCI).status_code == 403
    assert c.get(f"/api/curricula/{sci}", headers=SCI).status_code == 200
    assert c.get("/api/curricula/9999", headers=SCI).status_code == 404


def test_the_scope_follows_the_teacher_list_and_the_group(env) -> None:
    c, sci, econ = env
    # the curator joins the economics curriculum's teachers: it shows up at once
    s0 = c.get(f"/api/curricula/{econ}/sections", headers=CENTRAL).json()["0"]["data"]
    s0["teachers"]["teachers"].append({"name": "อ.ใหม่", "pid": "SWU01001"})
    c.put(f"/api/curricula/{econ}/sections/0", json={"data": s0}, headers=CENTRAL)
    assert ids(c, CUR) == sorted([sci, econ])
    # the admin widens the faculty group's ขอบเขตข้อมูล on the role-edit page
    r = c.put("/api/roles/faculty", json={"scope_kind": "all"}, headers=ADMIN)
    assert r.status_code == 200
    clear_user_cache()
    assert ids(c, SCI) == sorted([sci, econ])


def test_rule_without_a_database() -> None:
    row = {"scope_faculty": "คณะวิทยาศาสตร์", "scope_pids": ["SWU01001"]}
    assert visible(User("a", roles=["admin"]), row) and visible(None, row)
    assert visible(User("f", roles=["faculty"], units=["คณะวิทยาศาสตร์"]), row)
    assert not visible(User("f", roles=["faculty"], units=["คณะอื่น"]), row)
    assert visible(User("f", roles=["faculty"], units=["ทั้งมหาวิทยาลัย"]), row)
    assert visible(User("f", roles=["faculty"]), row), "no units = everywhere (as for e-mail)"
    assert visible(User("c", roles=["curator"], pid="SWU01001"), row)
    assert not visible(User("c", roles=["curator"]), row), "no HURIS id: nothing"
    assert not visible(User("s", roles=["student"], pid="SWU01001"), {**row, "scope_pids": []})


def test_dashboard_counts_within_the_scope(env, pg_url: str, schema: str) -> None:
    """แดชบอร์ดหลักสูตร (FS-2f · US-M1-01 02)."""
    from ocl_api.mail import Outbox

    c, sci, econ = env
    d = c.get("/api/curricula/dashboard", headers=CENTRAL).json()
    assert d["total"] == 2 and d["counts"] == {
        "import": 2,
        "review": 0,
        "verified": 0,
        "published": 0,
    }
    assert {f["faculty"] for f in d["by_faculty"]} == {"คณะวิทยาศาสตร์", "คณะเศรษฐศาสตร์"}
    assert set(d["completeness"]) == {"0", "1", "2", "3", "4", "5"}
    assert [x["id"] for x in d["stuck"]] and all(
        x["days"] == 0 and x["missing"] for x in d["stuck"]
    )
    assert d["options"]["faculties"] == ["คณะวิทยาศาสตร์", "คณะเศรษฐศาสตร์"]
    one = c.get("/api/curricula/dashboard?faculty=คณะเศรษฐศาสตร์", headers=CENTRAL).json()
    assert one["total"] == 1 and one["items"][0]["id"] == econ
    assert c.get("/api/curricula/dashboard", headers=SCI).json()["total"] == 1, "scope applies"
    # the executive sees the dashboard (menu d1) but not the คู่มือ pages, and cannot send
    assert c.get("/api/curricula/dashboard", headers=EXEC).json()["total"] == 2
    assert c.get("/api/curricula", headers=EXEC).status_code == 403
    assert c.post(f"/api/curricula/{sci}/remind", headers=EXEC).status_code == 403

    # แจ้งเตือน: to the holders of the current step (a draft: the drafters), once a day
    r = c.post(f"/api/curricula/{sci}/remind", headers=CENTRAL).json()
    assert r["sent"] is True and r["to"] >= 1
    assert c.post(f"/api/curricula/{sci}/remind", headers=CENTRAL).json()["sent"] is False
    mails = [m for m in Outbox(pg_url, schema).list() if m["kind"] == "reminder"]
    assert len(mails) == 1 and "วท.บ. ก" in mails[0]["subject"]
    assert c.post(f"/api/curricula/{econ}/remind", headers=SCI).status_code == 403
