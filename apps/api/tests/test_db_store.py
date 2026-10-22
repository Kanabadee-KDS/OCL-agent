"""The Postgres-backed store, end to end through the API.

Runs against DATABASE_URL when set (CI: a postgres service; dev: Neon), otherwise
against an embedded server from the `pgserver` dev dependency, and is skipped when
neither is available. Every run works in its own throw-away schema."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.db import connect, migrate, status
from ocl_api.main import create_app
from tests.test_ingest_docx import build_docx


@pytest.fixture
def client(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("AUTH_SECRET", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")  # the developer's .env may hold a real key
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    monkeypatch.setenv("INLINE_WORKER", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "32768")
    return TestClient(create_app())


def _wait(client: TestClient, job_id: str, want: str, timeout: float = 30.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/api/imports/{job_id}").json()
        if job["status"] in (want, "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError(f"job did not reach {want}: {job}")


def test_migrate_is_idempotent(pg_url: str, schema: str) -> None:
    assert migrate(pg_url, schema) == ["001_import_jobs", "002_users", "003_curriculum_workflow"]
    assert migrate(pg_url, schema) == []
    st = status(pg_url, schema)
    assert st["migrations"] == ["001_import_jobs", "002_users", "003_curriculum_workflow"]
    assert st["pending"] == [] and st["jobs"] == 0


def test_import_flow_on_postgres(
    client: TestClient, tmp_path: Path, pg_url: str, schema: str
) -> None:
    assert client.get("/health").json()["database"] == "postgres"
    book = tmp_path / "sample.docx"
    build_docx(book)
    r = client.post(
        "/api/imports",
        files={"file": ("เล่มทดสอบ.docx", book.read_bytes())},
        data={"provider": "none"},
    )
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    job_dir = tmp_path / "data" / "imports" / jid
    assert not (job_dir / "job.json").exists(), "job state lives in the database, not job.json"

    job = _wait(client, jid, "review")
    assert job["status"] == "review", job.get("error")
    assert client.get("/api/imports").json()[0]["id"] == jid
    assert (job_dir / "extract" / "plo.json").exists(), "pipeline files are still written"

    with connect(pg_url, schema) as conn:
        n = conn.execute(
            "SELECT count(*) AS n FROM import_parts WHERE job_id = %s", (jid,)
        ).fetchone()
        assert n["n"] == len(job["parts"]), "every part is copied into import_parts"
        assert conn.execute(
            "SELECT extracted FROM import_checks WHERE job_id = %s", (jid,)
        ).fetchone()

    # edit + confirm: history and recomputed checks live in the database
    plo = client.get(f"/api/imports/{jid}/parts/plo").json()
    data = plo["data"]
    data["plos"] = [{"code": "PLO1", "text": "แก้โดยผู้ตรวจ", "sub_plos": [], "meta": {}}]
    saved = client.put(
        f"/api/imports/{jid}/parts/plo", json={"data": data, "confirm": True, "by": "admin"}
    ).json()
    assert saved["edited"] and saved["confirmed"] and saved["edit_count"] == 1
    assert saved["extracted"] != saved["data"]
    assert not (job_dir / "edits" / "plo.json").exists(), "edits are rows, not files"
    checks = {c["key"]: c for c in client.get(f"/api/imports/{jid}/checks").json()}
    assert "1 ข้อ" in checks["plo_present"]["message"]
    assert "แก้โดยผู้ตรวจ" in client.get(f"/api/imports/{jid}/files/extract/md/4-plos.md").text
    j2 = client.get(f"/api/imports/{jid}").json()
    assert j2["confirmed_count"] == 1 and j2["edited_parts"] == ["plo"]

    # unconfirm keeps the history
    again = client.put(
        f"/api/imports/{jid}/parts/plo", json={"data": data, "confirm": False}
    ).json()
    assert again["confirmed"] is False and again["edit_count"] == 2

    # finalize writes the curriculum draft row
    client.put(f"/api/imports/{jid}/parts/plo", json={"data": data, "confirm": True})
    done = client.post(f"/api/imports/{jid}/finalize").json()
    assert done["status"] == "done"
    with connect(pg_url, schema) as conn:
        row = conn.execute(
            "SELECT job_id, name_th, data FROM curriculum_drafts WHERE job_id = %s", (jid,)
        ).fetchone()
    assert row and row["data"]["parts"]["plo"]["data"]["plos"][0]["text"] == "แก้โดยผู้ตรวจ"
    assert client.get("/api/imports/nope00000000").status_code == 404
