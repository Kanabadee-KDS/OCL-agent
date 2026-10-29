"""สมอ.08 (FS-3c · US-M1-09 10 · BR-06): request, approve step by step, then หมวด 0.2 changes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.db import connect
from ocl_api.smo import changes

SECRET = "smo-secret-for-tests-only-32bytes"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, DEAN, CUR = h("central@g.swu.ac.th"), h("dean@g.swu.ac.th"), h("cur@g.swu.ac.th")
T = [{"name": "อ.หนึ่ง", "pid": "SWU1", "responsible": True, "group": "แขนง ก"},
     {"name": "อ.สอง", "pid": "SWU2", "responsible": True, "group": "แขนง ข"},
     {"name": "อ.สาม", "pid": "SWU3", "responsible": False, "group": "แขนง ก"}]  # fmt: skip
FIELDS = {"ack_date": "1 ต.ค. 2569", "council": "ครั้งที่ 9/2569 วันที่ 20 ต.ค. 2569",
          "start_term": "ภาคเรียนที่ 1", "start_year": "2570"}  # fmt: skip


@pytest.fixture
def env(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {"DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url,
                 "DATABASE_SCHEMA": schema, "AUTH_SECRET": SECRET}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    users = UserStore(pg_url, schema)
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    users.upsert("cur@g.swu.ac.th", roles=["curator"])
    with connect(pg_url, schema) as conn:
        conn.execute("UPDATE users SET pid = 'SWU1' WHERE email = 'cur@g.swu.ac.th'")
    clear_user_cache()
    c = TestClient(app)

    def curriculum(name: str, status: str = "verified") -> int:
        did = c.post(
            "/api/curricula", json={"name_th": name, "faculty": "คณะวิทยาศาสตร์"}, headers=CENTRAL
        ).json()["id"]
        s0 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
        s0["teachers"] = {"teachers": T}
        c.put(f"/api/curricula/{did}/sections/0", json={"data": s0}, headers=CENTRAL)
        with connect(pg_url, schema) as conn:
            conn.execute("UPDATE curriculum_drafts SET status = %s WHERE id = %s", (status, did))
        return did

    return c, curriculum, pg_url, schema


def teachers(c: TestClient, did: int) -> list[dict]:
    return c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]["teachers"][
        "teachers"
    ]


def test_request_runs_the_flow_and_changes_the_teachers(env) -> None:
    from ocl_api.mail import Outbox

    c, curriculum, pg_url, schema = env
    did, draft = curriculum("วท.บ. ก"), curriculum("วท.บ. ข", "import")
    opts = c.get("/api/smo/options", headers=CENTRAL).json()
    assert [x["id"] for x in opts["curricula"]] == [did] and opts["curricula"][0]["branches"] == [
        "แขนง ก",
        "แขนง ข",
    ]
    assert c.post("/api/smo", json={"draft_id": draft}, headers=CENTRAL).status_code == 409, (
        "a draft: not yet"
    )
    r = c.post("/api/smo", json={"draft_id": did}, headers=CENTRAL).json()
    rid = r["id"]
    assert (
        rid.startswith("S08-25")
        and rid.endswith("-001")
        and r["status"] == "draft"
        and r["changes"] == []
    )

    # one added, one edited, one removed
    after = [{**T[0], "rank": "ผศ."}, T[1], {"name": "อ.สี่", "pid": "SWU4", "responsible": True}]
    edit = {"types": ["teacher", "other"], "after": after, "details": {"other": "ปรับชื่อแขนง"}}
    assert c.post(f"/api/smo/{rid}/submit", headers=CENTRAL).status_code == 400
    r = c.put(f"/api/smo/{rid}", json=edit, headers=CENTRAL).json()
    assert sorted(x["change"] for x in r["changes"]) == ["นำออก", "เพิ่ม", "แก้ไข"]
    miss = c.post(f"/api/smo/{rid}/submit", headers=CENTRAL).json()["detail"]
    assert "วันที่ สป.อว. รับทราบ" in miss and "เหตุผล" in miss
    c.put(
        f"/api/smo/{rid}", json={**edit, "fields": FIELDS, "reason": "อาจารย์ลาออก"}, headers=CENTRAL
    )
    r = c.post(f"/api/smo/{rid}/submit", headers=CENTRAL).json()
    assert r["status"] == "pending" and r["step"] == 1 and r["start"] == "ภาคเรียนที่ 1/2570"
    assert c.put(f"/api/smo/{rid}", json=edit, headers=CENTRAL).status_code == 409, "sent: locked"
    assert any(m["subject"].startswith(f"สมอ.08 {rid}") for m in Outbox(pg_url, schema).list())

    # step 1 is an outside body (คณะกรรมการประจำคณะ): central keys it in, the faculty cannot
    assert c.post(f"/api/smo/{rid}/approve", json={}, headers=DEAN).status_code == 403
    assert c.post(f"/api/smo/{rid}/return", json={"note": ""}, headers=CENTRAL).status_code == 400
    r = c.post(f"/api/smo/{rid}/return", json={"note": "แนบมติคณะ"}, headers=CENTRAL).json()
    assert r["status"] == "returned" and r["step"] == 0
    c.post(f"/api/smo/{rid}/submit", headers=CENTRAL)
    for _ in range(4):
        assert teachers(c, did) == T, "nothing changes before the last step"
        r = c.post(f"/api/smo/{rid}/approve", json={"note": "เห็นชอบ"}, headers=CENTRAL).json()
    assert r["status"] == "approved" and r["step_label"] == "ครบทุกขั้นตอน"
    now = teachers(c, did)
    assert [t["name"] for t in now] == ["อ.หนึ่ง", "อ.สอง", "อ.สี่"] and now[0]["rank"] == "ผศ."
    d = c.get(f"/api/curricula/{did}", headers=CENTRAL).json()
    assert (
        d["events"][-1]["action"] == "smo08"
        and d["sections"]["0"]["updated_by"] == "central@g.swu.ac.th"
    )
    # BR-06: the verified curriculum itself stays locked
    s0 = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()["0"]["data"]
    assert (
        c.put(f"/api/curricula/{did}/sections/0", json={"data": s0}, headers=CENTRAL).status_code
        == 409
    )
    assert [e["action"] for e in r["events"]][:4] == ["create", "save", "save", "submit"]
    assert c.post("/api/smo", json={"draft_id": did}, headers=CENTRAL).json()["id"].endswith("-002")


def test_child_book_changes_only_its_branch_and_files(env) -> None:
    c, curriculum, *_ = env
    did = curriculum("วท.บ. ค")
    rid = c.post("/api/smo", json={"draft_id": did}, headers=CENTRAL).json()["id"]
    scope = {"kind": "child", "branch": "แขนง ก"}
    # rows of other branches sent along are ignored: only แขนง ก may change
    after = [T[0], {**T[1], "rank": "ศ."}, {"name": "อ.ห้า", "pid": "SWU5", "group": "แขนง ก"}]
    r = c.put(f"/api/smo/{rid}", json={"types": ["teacher"], "scope": scope, "after": after,
                                         "fields": FIELDS, "reason": "เพิ่มอาจารย์แขนง ก"}, headers=CENTRAL).json()  # fmt: skip
    assert [(x["change"], (x["after"] or x["before"])["name"]) for x in r["changes"]] == [
        ("เพิ่ม", "อ.ห้า"),
        ("นำออก", "อ.สาม"),
    ]
    ok = c.post(
        f"/api/smo/{rid}/files", files={"file": ("มติสภา.pdf", b"%PDF-1.4 x")}, headers=CENTRAL
    )
    assert ok.status_code == 200 and ok.json()["files"][0]["name"] == "มติสภา.pdf"
    bad = c.post(f"/api/smo/{rid}/files", files={"file": ("x.exe", b"MZ")}, headers=CENTRAL)
    assert bad.status_code == 400
    fid = ok.json()["files"][0]["id"]
    assert c.get(f"/api/smo/{rid}/files/{fid}", headers=CENTRAL).content == b"%PDF-1.4 x"
    c.post(f"/api/smo/{rid}/submit", headers=CENTRAL)
    for _ in range(4):
        c.post(f"/api/smo/{rid}/approve", json={}, headers=CENTRAL)
    assert [t["name"] for t in teachers(c, did)] == ["อ.สอง", "อ.หนึ่ง", "อ.ห้า"]
    assert (
        c.post(
            f"/api/smo/{rid}/files", files={"file": ("y.pdf", b"x")}, headers=CENTRAL
        ).status_code
        == 403
    )


def test_scope_and_the_curator(env) -> None:
    c, curriculum, *_ = env
    mine, other = curriculum("วท.บ. ของ curator"), curriculum("วท.บ. อื่น")
    with connect(env[2], env[3]) as conn:  # the curator teaches only in `mine`
        conn.execute(
            "UPDATE curriculum_sections SET data = jsonb_set(data, '{teachers,teachers}', '[]') "
            "WHERE draft_id = %s AND section = '0'",
            (other,),
        )
    assert [x["id"] for x in c.get("/api/smo/options", headers=CUR).json()["curricula"]] == [mine]
    rid = c.post("/api/smo", json={"draft_id": mine}, headers=CUR).json()["id"]
    assert c.post("/api/smo", json={"draft_id": other}, headers=CUR).status_code == 409
    other_rid = c.post("/api/smo", json={"draft_id": other}, headers=CENTRAL).json()["id"]
    assert [x["id"] for x in c.get("/api/smo", headers=CUR).json()["items"]] == [rid]
    assert c.get(f"/api/smo/{other_rid}", headers=CUR).status_code == 403


def test_changes_compare_by_hr_id() -> None:
    a = [{"name": "ก", "pid": "1"}, {"name": "ข"}]
    b = [{"name": "ก (ชื่อใหม่)", "pid": "1"}, {"name": "ข"}]
    assert [x["change"] for x in changes(a, b)] == ["แก้ไข"]
