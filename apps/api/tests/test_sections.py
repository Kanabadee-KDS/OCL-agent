"""คู่มือหลักสูตร sections (FS-2a): conversion, who edits what when, blank drafts, backfill."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.sections import from_parts, to_parts, with_part
from tests.test_workflow import _import_and_finalize, curator_teaches

SECRET = "sections-secret-for-tests-only-32b"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, CUR, DEAN = h("central@g.swu.ac.th"), h("cur@g.swu.ac.th"), h("dean@g.swu.ac.th")

INFO = {
    "values": {"name_th": "หลักสูตร ก", "level": "ปริญญาตรี", "faculty": "คณะ ก",
               "language": "ไทย", "study_mode": "เต็มเวลา", "program_type": "วิชาการ"},
    "meta": {"name_th": {"page": 1}, "language": {"page": 3}},
    "fields": [{"key": "name_th"}], "careers": [{"title": "นักวิจัย"}], "majors": [],
    "collaborations": [], "count": 14,
}  # fmt: skip


def test_parts_and_sections_convert_both_ways() -> None:
    parts = {"info": INFO, "teachers": {"teachers": [1, 2]}, "plo": {"plos": [1]},
             "ksec": {"codes": []}, "mapping": {"rows": []}, "courses": {"courses": [1]},
             "plan": {"years": []}, "appr": {"approvals": []}}  # fmt: skip
    s = from_parts(parts)
    assert sorted(s) == ["0", "1", "2", "3", "4", "5"]
    assert s["0"]["info"]["values"] == {
        "name_th": "หลักสูตร ก",
        "level": "ปริญญาตรี",
        "faculty": "คณะ ก",
    }
    assert s["1"]["info"]["values"] == {
        "language": "ไทย",
        "study_mode": "เต็มเวลา",
        "program_type": "วิชาการ",
    }
    assert s["1"]["info"]["careers"] and "careers" not in s["0"]["info"]
    assert sorted(s["3"]) == ["ksec", "plo"] and sorted(s["4"]) == ["courses", "mapping"]
    assert to_parts(s) == parts, "nothing lost on the way back"
    edited = {**INFO, "values": {**INFO["values"], "language": "อังกฤษ"}}
    assert with_part(s["1"], "info", edited, "1")["info"]["values"]["language"] == "อังกฤษ"
    assert "language" not in with_part(s["0"], "info", edited, "0")["info"]["values"]


@pytest.fixture
def client(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {
        "DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url, "DATABASE_SCHEMA": schema,
        "AUTH_SECRET": SECRET, "INLINE_WORKER": "true", "OLLAMA_MODEL": "gemma4:26b",
        "OLLAMA_KEEP_ALIVE": "10m", "OLLAMA_NUM_CTX": "32768",
    }.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    users = UserStore(pg_url, schema)
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("cur@g.swu.ac.th", roles=["curator"])
    curator_teaches(pg_url, schema)
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    clear_user_cache()
    return TestClient(app)


def _draft(c: TestClient, d: Path) -> tuple[str, int]:
    d.mkdir(parents=True, exist_ok=True)
    jid = _import_and_finalize(c, d, CENTRAL)
    return jid, c.get(f"/api/curricula/by-job/{jid}", headers=CENTRAL).json()["id"]


def test_import_fills_sections_and_the_rules_follow_the_status(
    client: TestClient, tmp_path: Path
) -> None:
    c = client
    jid, did = _draft(c, tmp_path / "a")
    secs = c.get(f"/api/curricula/{did}/sections", headers=DEAN).json()
    assert sorted(secs) == ["0", "1", "2", "3", "4", "5"]
    assert sorted(secs["3"]["data"]) == ["ksec", "plo"] and secs["3"]["updated_by"] == "import"
    d = c.get(f"/api/curricula/{did}", headers=CENTRAL).json()
    assert "plo" in d["parts"] and d["sections"]["4"]["label"].startswith("หมวด 4")
    assert d["editable"] == ["0", "1", "2", "3", "4", "5"]

    sec = f"/api/curricula/{did}/sections"
    s2 = secs["2"]["data"]
    s2_new = {**s2, "plan": {**(s2.get("plan") or {}), "intake_per_year": 99}}
    assert c.put(f"{sec}/2", json={"data": s2_new}, headers=DEAN).status_code == 403, (
        "draft: step 1"
    )
    r = c.put(f"{sec}/2", json={"data": s2_new}, headers=CUR)
    assert r.status_code == 200 and r.json()["data"]["plan"]["intake_per_year"] == 99
    assert c.put(f"{sec}/9", json={"data": {}}, headers=CUR).status_code == 404

    c.post(f"/api/curricula/{did}/transition", json={"action": "submit"}, headers=CUR)
    assert c.get(f"/api/curricula/{did}", headers=DEAN).json()["editable"] == ["3", "4"]
    s3 = c.get(sec, headers=DEAN).json()["3"]["data"]
    assert c.put(f"{sec}/3", json={"data": s3}, headers=CUR).status_code == 403, "review: step 2"
    assert c.put(f"{sec}/1", json={"data": {}}, headers=DEAN).status_code == 403
    two = [{"code": "PLO1", "text": "ก"}, {"code": "PLO2", "text": "ข"}]
    s3_new = {**s3, "plo": {**s3["plo"], "plos": two[:1]}}
    assert c.put(f"{sec}/3", json={"data": s3_new}, headers=DEAN).status_code == 200
    s4 = c.get(sec, headers=DEAN).json()["4"]["data"]
    mapped = {**s4, "mapping": {**s4["mapping"], "rows": s4["mapping"]["rows"][:2]}}
    assert c.put(f"{sec}/4", json={"data": mapped}, headers=DEAN).status_code == 200
    no_courses = {**s4, "courses": {"courses": []}}
    r = c.put(f"{sec}/4", json={"data": no_courses}, headers=DEAN)
    assert r.status_code == 403 and "Mapping" in r.json()["detail"]

    # the import's review page is closed once saved into the system: edits go here
    plo = c.get(f"/api/imports/{jid}/parts/plo", headers=DEAN).json()
    plo["data"]["plos"] = two
    assert (
        c.put(f"/api/imports/{jid}/parts/plo", json={"data": plo["data"]}, headers=DEAN).status_code
        == 409
    )
    assert c.get(sec, headers=DEAN).json()["3"]["data"]["plo"]["plos"] == two[:1], "unchanged"
    assert c.get(f"/api/curricula/{did}", headers=DEAN).json()["limited"] == {"4": ["mapping"]}
    # finalizing the job again would overwrite the review
    assert c.post(f"/api/imports/{jid}/finalize", headers=CENTRAL).status_code == 409

    ev = c.get(f"/api/curricula/{did}", headers=CENTRAL).json()["events"]
    # 4 = the setup (curator into 0.2) + three edits above
    assert [e["action"] for e in ev].count("edit") == 4 and any(
        "หมวด 3" in (e["note"] or "") for e in ev
    )

    t = f"/api/curricula/{did}/transition"
    for n in ("3", "4"):
        c.post(t, json={"action": "check", "section": n}, headers=DEAN)
    c.post(t, json={"action": "verify"}, headers=DEAN)
    assert c.put(f"{sec}/3", json={"data": s3}, headers=DEAN).status_code == 409
    assert c.get(f"/api/curricula/{did}", headers=DEAN).json()["editable"] == []


def test_blank_draft_and_backfill(client: TestClient, pg_url: str, schema: str) -> None:
    from ocl_api.db import Jsonb, connect
    from ocl_api.sections import backfill

    c = client
    body = {"name_th": "หลักสูตรใหม่ ก", "level": "ปริญญาโท", "faculty": "คณะ ข"}
    assert c.post("/api/curricula", json=body, headers=DEAN).status_code == 403, "not step 1"
    r = c.post("/api/curricula", json=body, headers=CENTRAL)
    assert r.status_code == 201
    d = r.json()
    assert d["job_id"] is None and d["status"] == "import" and d["faculty"] == "คณะ ข"
    assert d["events"][0]["action"] == "create" and d["parts"] == {
        "info": {"count": None, "confirmed_at": None, "edited": None}
    }
    item = c.get("/api/curricula", headers=CENTRAL).json()["items"][0]
    assert item["name_th"] == "หลักสูตรใหม่ ก" and item["faculty"] == "คณะ ข"
    # หมวด 0 renames the list entry
    sec = f"/api/curricula/{d['id']}/sections"
    s0 = c.get(sec, headers=CENTRAL).json()["0"]["data"]
    s0["info"]["values"].update(name_th="หลักสูตรใหม่ ข", program_code="25690000000001")
    c.put(f"{sec}/0", json={"data": s0}, headers=CENTRAL)
    item = c.get("/api/curricula", headers=CENTRAL).json()["items"][0]
    assert item["name_th"] == "หลักสูตรใหม่ ข" and item["program_code"] == "25690000000001"

    # a draft from before migration 010 (snapshot only) gets its sections at start-up
    with connect(pg_url, schema) as conn:
        old = conn.execute(
            "INSERT INTO curriculum_drafts (name_th, data) VALUES ('เก่า', %s) RETURNING id",
            (Jsonb({"parts": {"info": {"data": INFO}, "plo": {"data": {"plos": [1, 2]}}}}),),
        ).fetchone()["id"]
    assert backfill(pg_url, schema) == 1 and backfill(pg_url, schema) == 0
    s = c.get(f"/api/curricula/{old}/sections", headers=CENTRAL).json()
    assert (
        s["3"]["data"]["plo"]["plos"] == [1, 2]
        and s["1"]["data"]["info"]["values"]["language"] == "ไทย"
    )
