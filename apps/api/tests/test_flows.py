"""Approval flows (US-U-05): versions, rules, and how they drive the คู่มือหลักสูตร workflow."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.curricula import business_days_after
from ocl_api.flows import today_th
from tests.test_workflow import _import_and_finalize

SECRET = "flows-secret-for-tests-only-32bytes"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


ADMIN, CENTRAL, CUR, DEAN, OTHER = (
    h("admin@g.swu.ac.th"),
    h("central@g.swu.ac.th"),
    h("cur@g.swu.ac.th"),
    h("dean@g.swu.ac.th"),
    h("far@g.swu.ac.th"),
)


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
    users.upsert("admin@g.swu.ac.th", roles=["admin"])
    users.upsert("central@g.swu.ac.th", roles=["central"])
    users.upsert("cur@g.swu.ac.th", roles=["curator"])
    users.upsert("dean@g.swu.ac.th", roles=["faculty"])
    # a faculty reviewer of another faculty: never e-mailed about this curriculum
    users.upsert("far@g.swu.ac.th", roles=["faculty"], unit="คณะอื่น")
    clear_user_cache()
    return TestClient(app)


def _steps(c: TestClient) -> list[dict]:
    return c.get("/api/flows/curriculum", headers=ADMIN).json()["steps"]


def test_seeded_flows_and_rules(client: TestClient) -> None:
    c = client
    items = c.get("/api/flows", headers=CENTRAL).json()["items"]
    assert [f["id"] for f in items] == [
        "curriculum", "smo08", "skill_mapping", "learning_plan", "skill_transcript",
    ]  # fmt: skip
    cur = items[0]
    assert [s["roles"] for s in cur["steps"]] == [["curator", "central"], ["faculty"], ["central"]]
    assert cur["steps"][1]["days"] == 5 and cur["fixed_steps"] == 3 and cur["version"] == 1
    assert items[1]["steps"][3]["position"] == "สภาวิชาการ"
    assert c.get("/api/flows", headers=DEAN).status_code == 403

    steps = _steps(c)
    put = lambda fid, body: c.put(f"/api/flows/{fid}", json=body, headers=ADMIN)  # noqa: E731
    assert put("curriculum", {"steps": steps[:2]}).status_code == 409, "three steps, fixed"
    bad_last = [*steps[:2], {**steps[2], "action": "review"}]
    assert put("curriculum", {"steps": bad_last}).status_code == 400, "last step approves"
    nobody = [steps[0], {**steps[1], "roles": [], "position": None}, steps[2]]
    assert put("curriculum", {"steps": nobody}).status_code == 400
    assert (
        put("curriculum", {"steps": [{**steps[0], "roles": ["boss"]}, *steps[1:]]}).status_code
        == 400
    )

    # a free flow may grow; unchanged steps keep the version, only the switches change
    smo = c.get("/api/flows/smo08", headers=ADMIN).json()["steps"]
    extra = {"roles": ["central"], "label": "บันทึกผล", "action": "review", "days": 2}
    r = put("smo08", {"steps": [*smo[:-1], extra, smo[-1]]}).json()
    assert (
        r["version"] == 2 and len(r["steps"]) == 6 and r["history"][0]["by"] == "admin@g.swu.ac.th"
    )
    r = put("smo08", {"steps": r["steps"], "remind_overdue": False}).json()
    assert r["version"] == 2 and r["remind_overdue"] is False
    assert len(c.get("/api/flows/smo08?version=1", headers=ADMIN).json()["steps"]) == 5


def test_flow_drives_the_curriculum_workflow(
    client: TestClient, tmp_path: Path, pg_url, schema
) -> None:
    from ocl_api.mail import Outbox

    c = client
    # draft A is submitted under version 1 (faculty reviews within 5 business days)
    a = _draft(c, tmp_path / "a")
    r = c.post(f"/api/curricula/{a}/transition", json={"action": "submit"}, headers=CUR).json()
    assert r["review_due_at"] == business_days_after(today_th(), 5).isoformat()
    assert r["flow"]["version"] == 1 and r["allowed"] == {
        "submit": True,
        "review": False,
        "publish": False,
    }

    mail = Outbox(pg_url, schema).list()
    assert mail[0]["to_addrs"] == ["dean@g.swu.ac.th"], "the next step, of this faculty only"
    assert mail[0]["subject"].startswith("คู่มือหลักสูตรรอตรวจสอบ")

    # the administrators hand the review to the curator group with 2 days
    steps = _steps(c)
    steps[1] = {**steps[1], "roles": ["curator"], "days": 2}
    assert (
        c.put("/api/flows/curriculum", json={"steps": steps}, headers=CENTRAL).json()["version"]
        == 2
    )

    # draft A keeps version 1: the faculty still verifies it
    t = f"/api/curricula/{a}/transition"
    for sec in ("3", "4"):
        assert c.post(t, json={"action": "check", "section": sec}, headers=DEAN).status_code == 200
    v = c.post(t, json={"action": "verify"}, headers=DEAN).json()
    assert v["status"] == "verified" and v["flow"]["version"] == 1
    mail = Outbox(pg_url, schema).list()
    assert {tuple(m["to_addrs"]) for m in mail[:2]} == {
        ("central@g.swu.ac.th",),
        ("cur@g.swu.ac.th",),
    }, "central is told to publish, the sender hears the result"

    # draft B starts on version 2: 2 days, the curator reviews, the faculty may not
    b = _draft(c, tmp_path / "b")
    tb = f"/api/curricula/{b}/transition"
    r = c.post(tb, json={"action": "submit"}, headers=CENTRAL).json()
    assert r["flow"]["version"] == 2
    assert r["review_due_at"] == business_days_after(today_th(), 2).isoformat()
    assert c.post(tb, json={"action": "check", "section": "3"}, headers=DEAN).status_code == 403
    assert c.post(tb, json={"action": "check", "section": "3"}, headers=CUR).status_code == 200
    ret = c.post(tb, json={"action": "return", "note": "แก้หมวด 1"}, headers=CUR).json()
    assert ret["status"] == "import"
    assert Outbox(pg_url, schema).list()[0]["to_addrs"] == ["central@g.swu.ac.th"]
    assert "แก้หมวด 1" in Outbox(pg_url, schema).list()[0]["body"]


def test_overdue_reviews_are_reminded_once_a_day(
    client: TestClient, tmp_path: Path, pg_url, schema
) -> None:
    from ocl_api.cli import main
    from ocl_api.db import connect
    from ocl_api.mail import Outbox

    c = client
    d = _draft(c, tmp_path / "d")
    c.post(f"/api/curricula/{d}/transition", json={"action": "submit"}, headers=CUR)
    with connect(pg_url, schema) as conn:
        conn.execute(
            "UPDATE curriculum_drafts SET review_due_at = %s WHERE id = %s",
            (today_th() - timedelta(days=1), d),
        )
    assert main(["flows", "remind"]) == 0
    assert main(["flows", "remind"]) == 0
    reminders = [m for m in Outbox(pg_url, schema).list() if m["kind"] == "reminder"]
    assert len(reminders) == 1 and reminders[0]["to_addrs"] == ["dean@g.swu.ac.th"]
    # switched off on the approval page: no reminder
    steps = _steps(c)
    c.put("/api/flows/curriculum", json={"steps": steps, "remind_overdue": False}, headers=ADMIN)
    with connect(pg_url, schema) as conn:
        conn.execute("DELETE FROM email_outbox WHERE kind = 'reminder'")
    main(["flows", "remind"])
    assert not [m for m in Outbox(pg_url, schema).list() if m["kind"] == "reminder"]


def _draft(c: TestClient, d: Path) -> int:
    d.mkdir(parents=True, exist_ok=True)
    jid = _import_and_finalize(c, d, CENTRAL)
    return c.get(f"/api/curricula/by-job/{jid}", headers=CENTRAL).json()["id"]
