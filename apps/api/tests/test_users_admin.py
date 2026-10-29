"""กำหนดผู้ใช้งาน (US-U-03): add from HURIS, invite, edit, suspend, end dates, self-lockout."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token

SECRET = "users-secret-for-tests-only-32bytes"


@pytest.fixture
def env(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.external import ExternalStore
    from ocl_api.external.sample import SampleAdapter
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    app = create_app()
    for system in ("huris", "supreme"):
        ExternalStore(pg_url, schema).load(SampleAdapter(), system)
    users = UserStore(pg_url, schema)
    users.upsert("admin@g.swu.ac.th", name="ผู้ดูแล", roles=["admin"])
    users.upsert("central@g.swu.ac.th", roles=["central"], unit="ฝ่ายวิชาการ")
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    clear_user_cache()
    return TestClient(app), users


def h(sub: str, roles: list[str] | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=roles or [])}"}


ADMIN, CENTRAL, DEAN = h("admin@g.swu.ac.th"), h("central@g.swu.ac.th"), h("dean@g.swu.ac.th")
SVC = h("web", ["service"])


def test_options_search_and_who_may_open(env) -> None:
    c, _ = env
    o = c.get("/api/users/options", headers=ADMIN).json()
    assert o["roles"][0] == {"id": "admin", "name": "ผู้ดูแลระบบ"} and o["units_sample"]
    assert o["units"][0] == "ทั้งมหาวิทยาลัย" and "คณะวิทยาศาสตร์" in o["units"]
    items = c.get("/api/users?q=central", headers=CENTRAL).json()["items"]
    assert [u["email"] for u in items] == ["central@g.swu.ac.th"]
    assert items[0]["units"] == ["ฝ่ายวิชาการ"], "the old single unit carried into units"
    assert items[0]["has_password"] is False and "password_hash" not in items[0]
    assert len(c.get("/api/users?role=faculty", headers=ADMIN).json()["items"]) == 1
    assert c.get("/api/users", headers=DEAN).status_code == 403


def test_add_from_huris_edit_and_suspend(env) -> None:
    c, users = env
    r = c.post(
        "/api/users",
        json={"pid": "SWU03001", "roles": ["teacher", "advisor"], "units": ["คณะวิทยาศาสตร์"]},
        headers=CENTRAL,
    )
    assert r.status_code == 201
    u = r.json()
    assert u["email"] == "staff013@sample.invalid" and u["name"].startswith("ผศ.ดร.[ชื่อ")
    assert u["pid"] == "SWU03001" and u["usable"] and not u["has_password"]
    assert c.post("/api/users", json={"pid": "SWU03001"}, headers=CENTRAL).status_code == 409
    assert c.post("/api/users", json={"pid": "NOPE"}, headers=CENTRAL).status_code == 404
    bad = c.post("/api/users", json={"email": "x@y.th", "roles": ["boss"]}, headers=CENTRAL)
    assert bad.status_code == 400

    who = "staff013@sample.invalid"
    r = c.put(f"/api/users/{who}", json={"roles": ["teacher"], "units": []}, headers=CENTRAL)
    assert r.json()["roles"] == ["teacher"] and r.json()["updated_by"] == "central@g.swu.ac.th"
    ev = c.get(f"/api/users/{who}", headers=ADMIN).json()["events"]
    assert [e["action"] for e in ev] == ["update", "create"]
    assert ev[0]["detail"]["roles"] == [["teacher", "advisor"], ["teacher"]]

    # suspended: refused by the API and by the web's re-check; back after enable
    users.upsert(who, password="pw")  # the PM sets the Buasri password on the server
    me = h(who)
    assert c.get("/api/auth/me", headers=me).status_code == 200
    assert (
        c.post(f"/api/users/{who}/active", json={"active": False}, headers=CENTRAL).json()["usable"]
        is False
    )
    assert c.get("/api/auth/me", headers=me).status_code == 401
    assert c.post("/api/auth/refresh", json={"email": who}, headers=SVC).status_code == 404
    login = {"username": who, "password": "pw"}
    assert c.post("/api/auth/credentials", json=login, headers=SVC).status_code == 401
    assert c.get("/api/users?status=suspended", headers=ADMIN).json()["items"][0]["email"] == who
    c.post(f"/api/users/{who}/active", json={"active": True}, headers=CENTRAL)
    assert c.post("/api/auth/credentials", json=login, headers=SVC).status_code == 200
    assert c.delete(f"/api/users/{who}", headers=ADMIN).status_code == 405, "no delete"


def test_invite_with_end_date(env, pg_url: str, schema: str) -> None:
    from ocl_api.mail import Outbox

    c, _ = env
    end = (date.today() + timedelta(days=30)).isoformat()
    r = c.post(
        "/api/users/invite",
        json={"email": "Expert@Company.co.th", "name": "ผู้ทรงคุณวุฒิ", "expires_at": end},
        headers=ADMIN,
    )
    assert r.status_code == 201
    u = r.json()
    assert u["kind"] == "external" and u["roles"] == ["evaluator"] and u["expires_at"] == end
    mail = Outbox(pg_url, schema).list()[0]
    assert mail["to_addrs"] == ["expert@company.co.th"] and mail["kind"] == "invite"
    past = (date.today() - timedelta(days=1)).isoformat()
    again = {"email": "late@x.th", "name": "x", "expires_at": past}
    assert c.post("/api/users/invite", json=again, headers=ADMIN).status_code == 400

    # an end date that has passed works like a suspension
    who = "expert@company.co.th"
    assert c.get("/api/auth/me", headers=h(who)).status_code == 200
    c.put(f"/api/users/{who}", json={"expires_at": past}, headers=ADMIN)
    clear_user_cache()
    assert c.get("/api/auth/me", headers=h(who)).status_code == 401
    assert c.get("/api/users?status=expired", headers=ADMIN).json()["items"][0]["email"] == who
    c.put(f"/api/users/{who}", json={"clear_expiry": True}, headers=ADMIN)
    assert c.get("/api/auth/me", headers=h(who)).status_code == 200


def test_nobody_locks_the_administrators_out(env) -> None:
    c, _ = env
    me = "admin@g.swu.ac.th"
    assert (
        c.post(f"/api/users/{me}/active", json={"active": False}, headers=ADMIN).status_code == 409
    )
    r = c.put(f"/api/users/{me}", json={"roles": ["teacher"]}, headers=ADMIN)
    assert r.status_code == 409 and "ตัวเอง" in r.json()["detail"]
    # central cannot remove or suspend the only administrator either
    r = c.put(f"/api/users/{me}", json={"roles": ["central"]}, headers=CENTRAL)
    assert r.status_code == 409 and "อย่างน้อย 1 คน" in r.json()["detail"]
    assert (
        c.post(f"/api/users/{me}/active", json={"active": False}, headers=CENTRAL).status_code
        == 409
    )
    # with a second administrator it is allowed
    c.post("/api/users", json={"email": "admin2@g.swu.ac.th", "roles": ["admin"]}, headers=CENTRAL)
    assert (
        c.put(f"/api/users/{me}", json={"roles": ["central"]}, headers=CENTRAL).status_code == 200
    )


def test_server_command_is_recorded(env, pg_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Passwords are set on the server (Q1 ข); the users page still shows who did it."""
    from ocl_api.cli import main

    c, _ = env
    assert main(["users", "set", "--email", "dean@g.swu.ac.th", "--password", "pw"]) == 0
    assert main(["users", "disable", "--email", "dean@g.swu.ac.th"]) == 0
    ev = c.get("/api/users/dean@g.swu.ac.th", headers=ADMIN).json()["events"]
    assert [e["action"] for e in ev] == ["cli_disable", "cli_set"]
    assert ev[1]["detail"]["password_set"] is True and ev[1]["by"].startswith("cli:")
    assert "pw" not in str(ev), "the password itself is never logged"
