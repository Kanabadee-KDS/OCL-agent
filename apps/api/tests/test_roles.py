"""กำหนดกลุ่มสิทธิ์ (US-U-04): copy a group, edit the matrix, guards, e-mail, role switch."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token

SECRET = "roles-secret-for-tests-only-32bytes"


@pytest.fixture
def env(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    app = create_app()
    users = UserStore(pg_url, schema)
    users.upsert("admin@g.swu.ac.th", roles=["admin"])
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    users.upsert("t1@g.swu.ac.th", roles=["teacher", "curator"])
    clear_user_cache()
    return TestClient(app), users


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


ADMIN, CENTRAL, DEAN, T1 = (
    h("admin@g.swu.ac.th"),
    h("central@g.swu.ac.th"),
    h("dean@g.swu.ac.th"),
    h("t1@g.swu.ac.th"),
)


def test_list_and_who_may_open_it(env) -> None:
    c, _ = env
    r = c.get("/api/roles", headers=ADMIN).json()
    by = {g["id"]: g for g in r["items"]}
    assert list(by)[:3] == ["admin", "central", "curator"] and len(by) == 9
    assert by["teacher"]["modules"] == ["p", "s", "r"] and by["teacher"]["users"] == 1
    assert by["faculty"]["scope_kind"] == "faculty" and by["admin"]["scope_kind"] == "all"
    assert set(r["actions"]) == {"view", "add", "edit", "delete", "approve", "print"}
    assert c.get("/api/roles", headers=CENTRAL).status_code == 200
    assert c.get("/api/roles", headers=DEAN).status_code == 403, "faculty does not see u1"


def test_copy_edit_and_take_effect(env, pg_url: str, schema: str) -> None:
    c, users = env
    r = c.post(
        "/api/roles", json={"name": "ผู้ช่วยงานวิชาการคณะ", "copy_from": "faculty"}, headers=ADMIN
    )
    assert r.status_code == 201
    g = r.json()
    gid = g["id"]
    assert not g["builtin"] and g["perms"]["c1"] == ["view", "add", "edit", "approve", "print"]
    assert g["scope_kind"] == "faculty" and g["events"][0]["action"] == "create"
    assert c.post("/api/roles", json={"name": "ผู้ช่วยงานวิชาการคณะ"}, headers=ADMIN).status_code == 409

    # a user can now hold the new group (users validate against role_groups)
    users.upsert("aide@g.swu.ac.th", roles=[gid])
    with pytest.raises(ValueError):
        users.upsert("x@g.swu.ac.th", roles=["nope"])
    aide = h("aide@g.swu.ac.th")
    assert c.get("/api/imports", headers=aide).status_code == 200

    # keep only คู่มือหลักสูตร (edit implies view) and the reports centre
    r = c.put(
        f"/api/roles/{gid}",
        json={"perms": {"c1": ["edit"], "r0": ["view"]}, "scope_kind": "program"},
        headers=CENTRAL,
    ).json()
    assert r["perms"] == {"c1": ["view", "edit"], "r0": ["view"]}
    assert set(r["actions"]) == set(g["actions"]) and r["scopes"], "same shape as GET"
    assert r["scope"].startswith("มุมมองหลักสูตร") and r["updated_by"] == "central@g.swu.ac.th"
    assert r["notified"] == 1, "the one member is told by e-mail"
    assert "c3:view" in r["events"][0]["detail"]["removed"]
    assert c.get("/api/imports", headers=aide).status_code == 403, "applied at once"
    me = c.get("/api/auth/me", headers=aide).json()
    assert me["menus"] == ["c1", "r0"]

    from ocl_api.mail import Outbox

    mail = Outbox(pg_url, schema).list()
    assert mail[0]["to_addrs"] == ["aide@g.swu.ac.th"] and mail[0]["kind"] == "perm_change"

    # no change, no event and no e-mail; notification can be switched off
    assert (
        c.put(
            f"/api/roles/{gid}",
            json={"perms": {"c1": ["view", "edit"], "r0": ["view"]}},
            headers=ADMIN,
        ).json()["notified"]
        == 0
    )  # noqa: E501
    r = c.put(
        f"/api/roles/{gid}",
        json={"perms": {"c1": ["view"]}, "notify_on_change": False},
        headers=ADMIN,
    ).json()
    assert r["notified"] == 0 and len(Outbox(pg_url, schema).list()) == 1

    bad = c.put(f"/api/roles/{gid}", json={"perms": {"zz": ["view"]}}, headers=ADMIN)
    assert bad.status_code == 400
    assert (
        c.put(f"/api/roles/{gid}", json={"perms": {"c1": ["fly"]}}, headers=ADMIN).status_code
        == 400
    )
    assert c.put(f"/api/roles/{gid}", json={"scope_kind": "moon"}, headers=ADMIN).status_code == 400

    # a group still held by a user cannot go; once empty it can
    assert c.delete(f"/api/roles/{gid}", headers=ADMIN).status_code == 409
    users.upsert("aide@g.swu.ac.th", roles=["teacher"])
    assert c.delete(f"/api/roles/{gid}", headers=ADMIN).status_code == 204
    assert c.get(f"/api/roles/{gid}", headers=ADMIN).status_code == 404


def test_guards(env) -> None:
    c, _ = env
    assert c.delete("/api/roles/teacher", headers=ADMIN).status_code == 409, "built-in stays"
    # the administrators cannot remove their own way back into this page
    r = c.put("/api/roles/admin", json={"perms": {"u1": ["view"]}}, headers=ADMIN)
    assert r.status_code == 409 and "กำหนดกลุ่มสิทธิ์" in r.json()["detail"]
    # the faculty reviewer has no u1 at all
    assert c.post("/api/roles", json={"name": "x"}, headers=DEAN).status_code == 403
    assert c.put("/api/roles/teacher", json={"perms": {}}, headers=DEAN).status_code == 403


def test_role_switch_narrows_the_menus(env) -> None:
    c, _ = env
    svc = h_service()
    both = c.post("/api/auth/refresh", json={"email": "t1@g.swu.ac.th"}, headers=svc).json()
    assert both["active_role"] is None and "c1" in both["perms"] and "p2" in both["perms"]
    assert both["role_names"] == {"teacher": "อาจารย์ผู้สอน", "curator": "ผู้ตรวจสอบระดับหลักสูตร"}
    one = c.post(
        "/api/auth/refresh", json={"email": "t1@g.swu.ac.th", "role": "teacher"}, headers=svc
    ).json()
    assert one["active_role"] == "teacher" and "c1" not in one["perms"] and "p2" in one["perms"]
    # a group the user does not hold is ignored
    other = c.post(
        "/api/auth/refresh", json={"email": "t1@g.swu.ac.th", "role": "admin"}, headers=svc
    ).json()
    assert other["active_role"] is None and "u1" not in other["perms"]


def h_service() -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub='web', roles=['service'])}"}
