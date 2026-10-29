"""Auth: password hashing, tokens, permission guards and the web-facing endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import PERM_MENU, ROLES, User, hash_password, sign_token, verify_password
from ocl_api.main import create_app
from tests.test_ingest_docx import build_docx

SECRET = "test-secret-not-for-prod"


def test_password_and_permissions() -> None:
    h = hash_password("บัวศรี123")
    assert h.startswith("scrypt$") and verify_password("บัวศรี123", h)
    assert not verify_password("wrong", h) and not verify_password("x", None)
    assert PERM_MENU["import_write"] == ("c3", "add")
    assert User(email="a", roles=["faculty"]).can("import_read")
    assert not User(email="a", roles=["faculty"]).can("import_write")
    assert not User(email="a", roles=["student"]).can("import_read")


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **env: str) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", env.pop("DATABASE_URL", ""))
    monkeypatch.setenv("AUTH_SECRET", env.pop("AUTH_SECRET", ""))
    monkeypatch.setenv("INLINE_WORKER", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "32768")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return TestClient(create_app())


def _bearer(roles: list[str], sub: str = "u@g.swu.ac.th") -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, name='ทดสอบ', roles=roles)}"}


def test_guards_without_and_with_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # auth disabled: anonymous admin
    c = _client(tmp_path, monkeypatch)
    assert c.get("/health").json()["auth"] == "disabled"
    assert c.get("/api/imports").status_code == 200
    assert c.get("/api/auth/me").json()["roles"] == ["admin"]

    # auth enabled: token required, roles enforced
    c = _client(tmp_path, monkeypatch, AUTH_SECRET=SECRET)
    assert c.get("/health").json()["auth"] == "enabled"
    assert c.get("/api/imports").status_code == 401
    assert c.get("/api/imports", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/api/imports", headers=_bearer(["student"])).status_code == 403
    assert c.get("/api/imports", headers=_bearer(["faculty"])).status_code == 200
    book = tmp_path / "b.docx"
    build_docx(book)
    files = {"file": ("x.docx", book.read_bytes())}
    r = c.post("/api/imports", files=files, data={"provider": "none"}, headers=_bearer(["faculty"]))
    assert r.status_code == 403, "faculty reads but does not import"
    r = c.post("/api/imports", files=files, data={"provider": "none"}, headers=_bearer(["curator"]))
    assert r.status_code == 201
    me = c.get("/api/auth/me", headers=_bearer(["curator", "teacher"])).json()
    assert me["permissions"]["import_write"] and not me["permissions"]["users_manage"]
    assert "c3" in me["menus"] and "p2" in me["menus"] and "u1" not in me["menus"]
    # the service endpoints refuse ordinary users
    assert (
        c.post(
            "/api/auth/lookup", json={"email": "a@g.swu.ac.th"}, headers=_bearer(["admin"])
        ).status_code
        == 403
    )


def test_users_and_web_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pg_url: str, schema: str
) -> None:
    from ocl_api.users import UserStore

    c = _client(
        tmp_path, monkeypatch, AUTH_SECRET=SECRET, DATABASE_URL=pg_url, DATABASE_SCHEMA=schema
    )
    assert c.get("/health").json()["database"] == "postgres"
    users = UserStore(pg_url, schema)
    u = users.upsert(
        "Somchai@g.swu.ac.th",
        name="สมชาย",
        roles=["central"],
        buasri_id="somchai",
        password="pw-1234",
    )
    assert (
        u["email"] == "somchai@g.swu.ac.th"
        and u["roles"] == ["central"]
        and "password_hash" not in u
    )
    with pytest.raises(ValueError):
        users.upsert("x@g.swu.ac.th", roles=["boss"])
    users.upsert("ext@example.com", name="ผู้ประเมิน", roles=["evaluator"])

    svc = _bearer(["service"], sub="web")
    # Google lookup: domain rule and unknown users
    assert c.post("/api/auth/lookup", json={"email": "somchai@g.swu.ac.th"}, headers=svc).json()[
        "roles"
    ] == ["central"]
    assert (
        c.post("/api/auth/lookup", json={"email": "nobody@g.swu.ac.th"}, headers=svc).status_code
        == 404
    )
    assert (
        c.post("/api/auth/lookup", json={"email": "ext@example.com"}, headers=svc).status_code
        == 403
    )
    # Buasri credentials
    ok = c.post(
        "/api/auth/credentials", json={"username": "somchai", "password": "pw-1234"}, headers=svc
    )
    assert ok.status_code == 200 and ok.json()["email"] == "somchai@g.swu.ac.th"
    assert (
        c.post(
            "/api/auth/credentials", json={"username": "somchai", "password": "bad"}, headers=svc
        ).status_code
        == 401
    )
    users.set_active("somchai@g.swu.ac.th", False)
    assert (
        c.post(
            "/api/auth/credentials",
            json={"username": "somchai", "password": "pw-1234"},
            headers=svc,
        ).status_code
        == 401
    )
    assert users.get("somchai@g.swu.ac.th")["last_login_at"] is not None
    # an edit is attributed to the signed-in user, not the body
    users.set_active("somchai@g.swu.ac.th", True)
    book = tmp_path / "b.docx"
    build_docx(book)
    jid = c.post(
        "/api/imports",
        files={"file": ("x.docx", book.read_bytes())},
        data={"provider": "none"},
        headers=_bearer(["central"], sub="somchai@g.swu.ac.th"),
    ).json()["id"]
    import time

    for _ in range(100):
        if c.get(
            f"/api/imports/{jid}", headers=_bearer(["central"], sub="somchai@g.swu.ac.th")
        ).json()["status"] in (
            "review",
            "failed",
        ):
            break
        time.sleep(0.1)
    plo = c.get(
        f"/api/imports/{jid}/parts/plo", headers=_bearer(["central"], sub="somchai@g.swu.ac.th")
    ).json()
    c.put(
        f"/api/imports/{jid}/parts/plo",
        json={"data": plo["data"], "confirm": False, "by": "spoof"},
        headers=_bearer(["central"], sub="somchai@g.swu.ac.th"),
    )
    from ocl_api.db import connect

    with connect(pg_url, schema) as conn:
        hist = conn.execute(
            "SELECT history FROM import_parts WHERE job_id = %s AND key = 'plo'", (jid,)
        ).fetchone()["history"]
    assert hist[0]["by"] == "somchai@g.swu.ac.th"


def test_table_decides_roles_and_suspension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pg_url: str, schema: str
) -> None:
    """A web session lives 8 hours; the API must not trust the roles it was signed with."""
    from ocl_api.auth import clear_user_cache
    from ocl_api.users import UserStore

    c = _client(
        tmp_path, monkeypatch, AUTH_SECRET=SECRET, DATABASE_URL=pg_url, DATABASE_SCHEMA=schema
    )
    users = UserStore(pg_url, schema)
    users.upsert("t@g.swu.ac.th", name="อาจารย์", roles=["teacher"])
    claims_admin = _bearer(["admin"], sub="t@g.swu.ac.th")
    # the token says admin, the table says teacher
    assert c.get("/api/imports", headers=claims_admin).status_code == 403
    assert c.get("/api/auth/me", headers=claims_admin).json()["roles"] == ["teacher"]
    # a user who is not in the table gets nothing, whatever the token says
    assert c.get("/api/imports", headers=_bearer(["admin"], sub="ghost@x")).status_code == 401
    # a role change applies once the short cache expires
    users.upsert("t@g.swu.ac.th", name="อาจารย์", roles=["curator"])
    clear_user_cache()
    assert c.get("/api/imports", headers=claims_admin).status_code == 200
    # suspension ends access at the API and at the web's refresh
    svc = _bearer(["service"], sub="web")
    assert c.post("/api/auth/refresh", json={"email": "T@g.swu.ac.th"}, headers=svc).json()[
        "roles"
    ] == ["curator"]
    users.set_active("t@g.swu.ac.th", False)
    clear_user_cache()
    assert c.get("/api/imports", headers=claims_admin).status_code == 401
    r = c.post("/api/auth/refresh", json={"email": "t@g.swu.ac.th"}, headers=svc)
    assert r.status_code == 404
    assert (
        c.post(
            "/api/auth/refresh", json={"email": "t@g.swu.ac.th"}, headers=claims_admin
        ).status_code
        == 401
    ), "refresh is for the web's service token only"


def test_menu_ids_match_the_web() -> None:
    """perms.py mirrors the menus of apps/web/src/lib/nav.ts; a menu added on one side fails."""
    import re

    from ocl_api.perms import MENU_INHERITS, MENUS

    nav = (Path(__file__).parents[3] / "apps/web/src/lib/nav.ts").read_text(encoding="utf-8")
    web_menus: dict[str, list[str]] = {}
    mod = ""
    for m in re.finditer(r'k: "([a-z])"|\{ id: "([a-z0-9]+)"', nav):
        if m.group(1):
            mod = m.group(1)
        else:
            web_menus.setdefault(mod, []).append(m.group(2))
    assert web_menus == MENUS
    assert dict(re.findall(r'id: "([a-z0-9]+)"[^}]*inherits: "([a-z0-9]+)"', nav)) == MENU_INHERITS
    assert "ROLE_ACCESS" not in nav, "who sees what lives in the database now (FS-1a)"


def test_default_permissions_follow_brd_roles() -> None:
    """The seed reproduces BRD 00 §3 (modules per role) and the mock's role-edit defaults."""
    from ocl_api.auth import can_menu
    from ocl_api.perms import MENUS, default_table

    def mods(roles: list[str]) -> str:
        return " ".join(k for k, ids in MENUS.items() if any(can_menu(roles, m) for m in ids))

    # d = แดชบอร์ด, which the mock adds for these five roles (NAV.unshift · FS-2f)
    assert mods(["admin"]) == mods(["central"]) == "d c p s q r u"
    assert mods(["curator"]) == mods(["faculty"]) == "d c p s q r"
    assert mods(["evaluator"]) == "q" and mods(["exec"]) == "d r" and mods(["student"]) == "m"
    assert mods(["teacher"]) == "p s r" and mods(["advisor"]) == "s r" and mods([]) == ""
    assert mods(["teacher", "student"]) == "p s r m", "several roles add up"
    assert User(email="a", roles=["teacher"]).menus() == ["p2", "p4", "s4", "s5", "r0", "r7", "r8"]
    assert User(email="a", roles=["advisor"]).menus() == ["s5", "r0", "r8"]
    assert set(default_table()) == set(ROLES)
    # actions: the mock's defaults, except that the faculty reviewer does not import
    assert can_menu(["faculty"], "c3h") and not can_menu(["faculty"], "c3", "add")
    assert can_menu(["curator"], "c3", "add") and not can_menu(["curator"], "c1", "delete")
    assert can_menu(["teacher"], "p2", "edit") and not can_menu(["teacher"], "p2", "approve")
    assert not can_menu(["exec"], "r1", "edit") and can_menu(["exec"], "r1", "print")
    assert can_menu(["admin"], "u3", "delete")


def test_permissions_live_in_the_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pg_url: str, schema: str
) -> None:
    from ocl_api.auth import clear_user_cache
    from ocl_api.db import connect
    from ocl_api.perms import default_table
    from ocl_api.users import UserStore

    c = _client(
        tmp_path, monkeypatch, AUTH_SECRET=SECRET, DATABASE_URL=pg_url, DATABASE_SCHEMA=schema
    )
    with connect(pg_url, schema) as conn:
        rows = conn.execute("SELECT role_id, menu, action FROM role_perms").fetchall()
        groups = conn.execute("SELECT id, builtin FROM role_groups ORDER BY ord").fetchall()
    seeded: dict = {}
    for r in rows:
        seeded.setdefault(r["role_id"], {}).setdefault(r["menu"], set()).add(r["action"])
    assert seeded == default_table(), "migration 006 seeds exactly the defaults"
    assert [g["id"] for g in groups] == list(ROLES) and all(g["builtin"] for g in groups)

    UserStore(pg_url, schema).upsert(
        "f@g.swu.ac.th", roles=["faculty"], buasri_id="f", password="pw"
    )
    fac = _bearer(["faculty"], sub="f@g.swu.ac.th")
    svc = _bearer(["service"], sub="web")
    login = c.post("/api/auth/credentials", json={"username": "f", "password": "pw"}, headers=svc)
    assert login.json()["perms"]["c3"] == ["view", "print"], "the web gets menus at sign-in"
    assert c.get("/api/imports", headers=fac).status_code == 200

    # an administrator takes the import menu away from the faculty group
    with connect(pg_url, schema) as conn:
        conn.execute("DELETE FROM role_perms WHERE role_id = 'faculty' AND menu = 'c3'")
    clear_user_cache()
    assert c.get("/api/imports", headers=fac).status_code == 403
    me = c.get("/api/auth/me", headers=fac).json()
    assert "c3" not in me["menus"] and "c3h" not in me["perms"] and "c1" in me["menus"]
    r = c.post("/api/auth/refresh", json={"email": "f@g.swu.ac.th"}, headers=svc).json()
    assert "c3" not in r["perms"], "and the web's next re-check drops the menu"
    # ... and gives it "add": now faculty may import
    with connect(pg_url, schema) as conn:
        conn.execute(
            "INSERT INTO role_perms VALUES ('faculty', 'c3', 'view'), ('faculty', 'c3', 'add')"
        )
    clear_user_cache()
    assert c.get("/api/auth/me", headers=fac).json()["permissions"]["import_write"] is True
