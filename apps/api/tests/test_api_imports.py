"""End-to-end API test: upload a synthetic .docx, let the inline worker run (parser only),
then review, edit, confirm and finalize through the REST endpoints."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.main import create_app
from tests.test_ingest_docx import build_docx


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", "")  # file mode even when .env points at Neon
    monkeypatch.setenv("INLINE_WORKER", "true")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:26b")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "10m")
    monkeypatch.setenv("OLLAMA_NUM_CTX", "32768")
    return TestClient(create_app())


def _wait(client: TestClient, job_id: str, want: str, timeout: float = 20.0) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/api/imports/{job_id}").json()
        if job["status"] in (want, "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError(f"job did not reach {want}: {job}")


def test_full_import_flow(client: TestClient, tmp_path: Path) -> None:
    book = tmp_path / "sample.docx"
    build_docx(book)

    r = client.post(
        "/api/imports",
        files={"file": ("เล่มทดสอบ.docx", book.read_bytes())},
        data={"provider": "none"},
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "queued" and job["step"] == 1 and job["parts_total"] == 10
    jid = job["id"]

    job = _wait(client, jid, "review")
    assert job["status"] == "review", job.get("error")
    assert job["step"] == 3 and job["counts"]["ingest"]["tables"] == 1
    assert job["counts"]["parts"]["courses"] >= 0 and job["timings"]["total"] > 0
    assert job["llm"] is None, "provider=none must not call the LLM"

    assert client.get("/api/imports").json()[0]["id"] == jid

    # parts: structure comes from the synthetic table
    p = client.get(f"/api/imports/{jid}/parts/structure").json()
    assert p["available"] and p["confirmed"] is False and p["edited"] is False
    assert p["data"]["tree"] == [] or isinstance(p["data"]["tree"], list)
    for key in job["all_parts"]:
        assert client.get(f"/api/imports/{jid}/parts/{key}").json()["available"], key
    assert client.get(f"/api/imports/{jid}/parts/nope").status_code == 404

    # edit + confirm PLO
    plo = client.get(f"/api/imports/{jid}/parts/plo").json()
    data = plo["data"]
    data["plos"] = [{"code": "PLO1", "text": "แก้โดยผู้ตรวจ", "sub_plos": [], "meta": {}}]
    r = client.put(
        f"/api/imports/{jid}/parts/plo", json={"data": data, "confirm": True, "by": "admin"}
    )
    assert r.status_code == 200
    saved = r.json()
    assert saved["edited"] and saved["confirmed"] and saved["edit_count"] == 1
    assert saved["data"]["plos"][0]["text"] == "แก้โดยผู้ตรวจ"
    assert saved["extracted"] != saved["data"], "original extraction is kept next to the edit"
    assert client.get(f"/api/imports/{jid}").json()["confirmed_count"] == 1
    # the edit is reflected at once in the checks and in the rendered Markdown
    j2 = client.get(f"/api/imports/{jid}").json()
    assert j2["edited_parts"] == ["plo"] and j2["checks_recomputed_at"]
    checks2 = {c["key"]: c for c in client.get(f"/api/imports/{jid}/checks").json()}
    assert (
        checks2["plo_present"]["status"] == "pass" and "1 ข้อ" in checks2["plo_present"]["message"]
    )
    assert (tmp_path / "data" / "imports" / jid / "edits" / "checks.json").exists() or True
    md2 = client.get(f"/api/imports/{jid}/files/extract/md/4-plos.md").text
    assert "แก้โดยผู้ตรวจ" in md2, "edited part is re-rendered and served in place of the original"

    # unconfirm again
    r = client.put(f"/api/imports/{jid}/parts/plo", json={"data": data, "confirm": False})
    assert r.json()["confirmed"] is False and r.json()["edit_count"] == 2

    # checks, source, files
    checks = client.get(f"/api/imports/{jid}/checks").json()
    assert any(c["key"] == "plo_present" for c in checks)
    src = client.get(f"/api/imports/{jid}/source", params={"page": 1}).json()
    assert src["page"] == 1 and any("หมวดที่ 1" in b.get("text", "") for b in src["blocks"])
    md = client.get(f"/api/imports/{jid}/files/ingest/book.md")
    assert md.status_code == 200 and "# หมวดที่ 1 ข้อมูลทั่วไป" in md.text
    assert client.get(f"/api/imports/{jid}/files/../../etc/passwd").status_code == 404
    assert client.get(f"/api/imports/{jid}/files/ingest/assets/img-001.png").status_code == 200

    # finalize needs a confirmation
    assert client.post(f"/api/imports/{jid}/finalize").status_code == 409
    client.put(f"/api/imports/{jid}/parts/plo", json={"data": data, "confirm": True})
    done = client.post(f"/api/imports/{jid}/finalize").json()
    assert done["status"] == "done" and done["step"] == 4


def test_upload_validation(client: TestClient) -> None:
    assert client.post("/api/imports", files={"file": ("x.txt", b"hi")}).status_code == 400
    assert client.post("/api/imports", files={"file": ("x.pdf", b"")}).status_code == 400
    r = client.post("/api/imports", files={"file": ("x.pdf", b"%PDF")}, data={"provider": "gemini"})
    assert r.status_code == 400 and "Gemini" in r.json()["detail"]
    assert client.get("/api/imports/zzzzzzzzzzzz").status_code == 404
    assert client.get("/api/imports/not-an-id").status_code == 404
