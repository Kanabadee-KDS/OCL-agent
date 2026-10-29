"""สกัดใหม่ (FS-3e · US-M1-12): some parts again, without reading the book again."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_ingest_docx import build_docx
from tests.test_workflow import CENTRAL, client  # noqa: F401 - the fixture

__all__ = ["client"]


def _wait(c: TestClient, jid: str) -> dict:
    for _ in range(150):
        j = c.get(f"/api/imports/{jid}", headers=CENTRAL).json()
        if j["status"] in ("review", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError(j)


def test_reextract_some_parts(client: TestClient, tmp_path: Path) -> None:  # noqa: F811
    c = client
    book = tmp_path / "b.docx"
    build_docx(book)
    jid = c.post("/api/imports", files={"file": ("x.docx", book.read_bytes())},
                 data={"provider": "none"}, headers=CENTRAL).json()["id"]  # fmt: skip
    first = _wait(c, jid)
    assert first["status"] == "review"
    part = lambda k: c.get(f"/api/imports/{jid}/parts/{k}", headers=CENTRAL).json()  # noqa: E731
    plo, info = part("plo"), part("info")
    plo_edit = {**plo["data"], "plos": [{"code": "PLO1", "text": "แก้ด้วยมือ"}]}
    c.put(
        f"/api/imports/{jid}/parts/plo", json={"data": plo_edit, "confirm": True}, headers=CENTRAL
    )
    c.put(
        f"/api/imports/{jid}/parts/info",
        json={"data": info["data"], "confirm": True},
        headers=CENTRAL,
    )
    assert part("plo")["confirmed"] and part("plo")["edited"]

    bad = c.post(
        f"/api/imports/{jid}/reextract",
        json={"parts": ["nope"], "provider": "none"},
        headers=CENTRAL,
    )
    assert bad.status_code == 400
    r = c.post(
        f"/api/imports/{jid}/reextract",
        json={"parts": ["plo"], "provider": "none"},
        headers=CENTRAL,
    )
    assert r.status_code == 200 and r.json()["status"] in ("queued", "extracting", "review")
    j = _wait(c, jid)
    assert (
        j["status"] == "review" and j.get("timings", {}).get("ingest") == first["timings"]["ingest"]
    ), "not read again"
    p = part("plo")
    assert not p["confirmed"] and not p["edited"] and p["data"] == plo["extracted"], (
        "back to what was extracted"
    )
    assert p["edit_count"] == 2, "the history keeps the edit and the re-extraction"
    assert part("info")["confirmed"], "the other parts keep their confirmation"

    # once in the system the import is read-only (FS-2c): no re-extraction
    c.put(
        f"/api/imports/{jid}/parts/plo", json={"data": p["data"], "confirm": True}, headers=CENTRAL
    )
    assert c.post(f"/api/imports/{jid}/finalize", headers=CENTRAL).json()["status"] == "done"
    again = c.post(f"/api/imports/{jid}/reextract", json={"provider": "none"}, headers=CENTRAL)
    assert again.status_code == 409


def test_markdown_editor(client: TestClient, tmp_path: Path) -> None:  # noqa: F811
    """US-M1-17 (FS-3f): the book, its chapters and the 10 parts as Markdown, edited by hand."""
    from tests.test_workflow import FACULTY

    c = client
    book = tmp_path / "b.docx"
    build_docx(book)
    jid = c.post("/api/imports", files={"file": ("x.docx", book.read_bytes())},
                 data={"provider": "none"}, headers=CENTRAL).json()["id"]  # fmt: skip
    _wait(c, jid)
    files = [
        f["path"] for f in c.get(f"/api/imports/{jid}/markdown", headers=CENTRAL).json()["files"]
    ]
    assert files[0] == "ingest/book.md" and any(f.startswith("ingest/sections/") for f in files)
    assert sum(f.startswith("extract/md/") for f in files) == 10

    def put(path: str, text: str, h: dict = CENTRAL):
        return c.put(
            f"/api/imports/{jid}/markdown", json={"path": path, "content": text}, headers=h
        )

    assert (
        put("job.json", "x").status_code == 400
        and put("ingest/../job.json", "x").status_code == 400
    )
    assert put("ingest/book.md", "x", FACULTY).status_code == 403, "the faculty only reads imports"
    r = put("ingest/book.md", "# เล่มที่แก้ด้วยมือ\n")
    assert r.status_code == 200 and r.json()["log"][-1]["by"] == "central@g.swu.ac.th"
    assert (
        c.get(f"/api/imports/{jid}/files/ingest/book.md", headers=CENTRAL).text == "# เล่มที่แก้ด้วยมือ\n"
    )
    put("extract/md/4-plos.md", "# PLO แก้ด้วยมือ\n")
    assert c.get(f"/api/imports/{jid}/files/extract/md/4-plos.md", headers=CENTRAL).text.startswith(
        "# PLO แก้"
    )
    # สกัดใหม่ of that part brings back its own Markdown; the book's edit stays
    c.post(
        f"/api/imports/{jid}/reextract",
        json={"parts": ["plo"], "provider": "none"},
        headers=CENTRAL,
    )
    _wait(c, jid)
    assert not c.get(
        f"/api/imports/{jid}/files/extract/md/4-plos.md", headers=CENTRAL
    ).text.startswith("# PLO แก้")
    assert c.get(f"/api/imports/{jid}/files/ingest/book.md", headers=CENTRAL).text.startswith(
        "# เล่มที่แก้"
    )
    for k in ("info", "plo"):
        p = c.get(f"/api/imports/{jid}/parts/{k}", headers=CENTRAL).json()
        c.put(
            f"/api/imports/{jid}/parts/{k}",
            json={"data": p["data"], "confirm": True},
            headers=CENTRAL,
        )
    c.post(f"/api/imports/{jid}/finalize", headers=CENTRAL)
    assert put("ingest/book.md", "y").status_code == 409, "in the system: read-only"
