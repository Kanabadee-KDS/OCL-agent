"""คู่มือหลักสูตร workflow: submit → faculty checks → verify → publish, locks and roles."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import sign_token
from ocl_api.curricula import business_days_after
from ocl_api.main import create_app
from tests.test_ingest_docx import build_docx

SECRET = "wf-secret"


def _h(roles: list[str], sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=roles)}"}


CENTRAL = _h(["central"], "central@g.swu.ac.th")
FACULTY = _h(["faculty"], "dean@g.swu.ac.th")
CURATOR = _h(["curator"], "cur@g.swu.ac.th")


def test_business_days() -> None:
    assert business_days_after(date(2026, 10, 22), 5) == date(2026, 10, 29)  # Thu -> next Thu
    assert business_days_after(date(2026, 10, 23), 1) == date(2026, 10, 26)  # Fri -> Mon


@pytest.fixture
def client(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    monkeypatch.setenv("INLINE_WORKER", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "32768")
    return TestClient(create_app())


def _import_and_finalize(c: TestClient, tmp_path: Path, headers: dict[str, str]) -> str:
    book = tmp_path / "b.docx"
    build_docx(book)
    jid = c.post(
        "/api/imports",
        files={"file": ("x.docx", book.read_bytes())},
        data={"provider": "none"},
        headers=headers,
    ).json()["id"]
    for _ in range(100):
        if c.get(f"/api/imports/{jid}", headers=headers).json()["status"] in ("review", "failed"):
            break
        time.sleep(0.1)
    plo = c.get(f"/api/imports/{jid}/parts/plo", headers=headers).json()
    c.put(
        f"/api/imports/{jid}/parts/plo",
        json={"data": plo["data"], "confirm": True},
        headers=headers,
    )
    assert c.post(f"/api/imports/{jid}/finalize", headers=headers).json()["status"] == "done"
    return jid


def test_workflow_end_to_end(client: TestClient, tmp_path: Path) -> None:
    c = client
    jid = _import_and_finalize(c, tmp_path, CENTRAL)
    draft = c.get(f"/api/curricula/by-job/{jid}", headers=FACULTY).json()
    did = draft["id"]
    assert draft["status"] == "import"
    lst = c.get("/api/curricula", headers=FACULTY).json()
    assert (
        lst["counts"]["import"] == 1
        and lst["items"][0]["id"] == did
        and lst["items"][0]["status_th"] == "ร่างนำเข้าหลักสูตร"
    )

    # finalize again does not create a second draft
    c.post(f"/api/imports/{jid}/finalize", headers=CENTRAL)
    assert c.get("/api/curricula", headers=CENTRAL).json()["counts"]["import"] == 1

    t = f"/api/curricula/{did}/transition"
    # faculty cannot submit; verify before review is refused
    assert c.post(t, json={"action": "submit"}, headers=FACULTY).status_code == 403
    assert c.post(t, json={"action": "verify"}, headers=FACULTY).status_code == 409
    r = c.post(t, json={"action": "submit", "note": "ขอให้ตรวจหมวด 3–4"}, headers=CURATOR).json()
    assert (
        r["status"] == "review"
        and r["review_due_at"] == business_days_after(date.today(), 5).isoformat()
    )

    # while in review the faculty may edit หมวด 3–4 only; central still can; courses are off-limits to faculty
    plo = c.get(f"/api/imports/{jid}/parts/plo", headers=FACULTY).json()
    assert (
        c.put(
            f"/api/imports/{jid}/parts/plo",
            json={"data": plo["data"], "confirm": False},
            headers=FACULTY,
        ).status_code
        == 200
    )
    crs = c.get(f"/api/imports/{jid}/parts/courses", headers=FACULTY).json()
    assert (
        c.put(
            f"/api/imports/{jid}/parts/courses",
            json={"data": crs["data"], "confirm": False},
            headers=FACULTY,
        ).status_code
        == 403
    )

    # verify needs both sections checked
    assert c.post(t, json={"action": "verify"}, headers=FACULTY).status_code == 409
    c.post(t, json={"action": "check", "section": "3"}, headers=FACULTY)
    assert c.post(t, json={"action": "check", "section": "5"}, headers=FACULTY).status_code == 400
    r = c.post(t, json={"action": "check", "section": "4"}, headers=FACULTY).json()
    assert r["faculty_checked"] == {"3": True, "4": True}
    assert c.post(t, json={"action": "publish"}, headers=CENTRAL).status_code == 409, (
        "publish only from verified"
    )
    r = c.post(t, json={"action": "verify"}, headers=FACULTY).json()
    assert r["status"] == "verified" and r["verified_at"]

    # locked after verification, for everyone
    assert (
        c.put(
            f"/api/imports/{jid}/parts/plo",
            json={"data": plo["data"], "confirm": False},
            headers=CENTRAL,
        ).status_code
        == 409
    )
    assert c.post(t, json={"action": "publish"}, headers=FACULTY).status_code == 403
    r = c.post(t, json={"action": "publish"}, headers=CENTRAL).json()
    assert r["status"] == "published" and r["published_at"]
    r = c.post(t, json={"action": "unpublish"}, headers=CENTRAL).json()
    assert r["status"] == "verified"
    actions = [e["action"] for e in r["events"]]
    assert actions == ["submit", "check", "check", "verify", "publish", "unpublish"]
    assert (
        r["events"][0]["by"] == "cur@g.swu.ac.th" and r["events"][0]["note"] == "ขอให้ตรวจหมวด 3–4"
    )
    assert r["parts"]["plo"]["count"] >= 0 and "checks" in r


def test_return_to_draft(client: TestClient, tmp_path: Path) -> None:
    c = client
    jid = _import_and_finalize(c, tmp_path, CENTRAL)
    did = c.get(f"/api/curricula/by-job/{jid}", headers=CENTRAL).json()["id"]
    t = f"/api/curricula/{did}/transition"
    c.post(t, json={"action": "submit"}, headers=CENTRAL)
    c.post(t, json={"action": "check", "section": "3"}, headers=FACULTY)
    r = c.post(t, json={"action": "return", "note": "หมวด 1 ชื่อปริญญาผิด"}, headers=FACULTY).json()
    assert r["status"] == "import" and r["review_due_at"] is None
    # resubmitting clears the previous ticks
    r = c.post(t, json={"action": "submit"}, headers=CENTRAL).json()
    assert r["faculty_checked"] == {}
    assert c.get("/api/curricula/9999", headers=CENTRAL).status_code == 404
    assert c.get("/api/curricula/by-job/000000000000", headers=CENTRAL).status_code == 404
