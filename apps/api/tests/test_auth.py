"""Auth: password hashing, tokens, permission guards and the web-facing endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import PERMISSIONS, ROLES, User, hash_password, sign_token, verify_password
from ocl_api.main import create_app
from tests.test_ingest_docx import build_docx

SECRET = "test-secret-not-for-prod"


def test_password_and_permissions() -> None:
    h = hash_password("บัวศรี123")
    assert h.startswith("scrypt$") and verify_password("บัวศรี123", h)
    assert not verify_password("wrong", h) and not verify_password("x", None)
    assert set(PERMISSIONS["import_write"]) <= set(ROLES)
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
    assert me["permissions"] == {"import_read": True, "import_write": True, "users_manage": False}
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
        if c.get(f"/api/imports/{jid}", headers=_bearer(["central"])).json()["status"] in (
            "review",
            "failed",
        ):
            break
        time.sleep(0.1)
    plo = c.get(f"/api/imports/{jid}/parts/plo", headers=_bearer(["central"])).json()
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
