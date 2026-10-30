"""แผน/รายงานการจัดการเรียนรู้ (FS-4 · US-M2-01–07 · BR-M2-01–05)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.db import connect
from ocl_api.flows import today_th

SECRET = "m2-secret-for-tests-only-32bytes"
TERM, SLUG = "2/2569", "2-2569"
FAC = "คณะเทคโนโลยีและนวัตกรรมผลิตภัณฑ์การเกษตร"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, T1, T2, CUR, DEAN, EXEC = (h(x) for x in (
    "central@g.swu.ac.th", "t1@g.swu.ac.th", "t2@g.swu.ac.th", "cur@g.swu.ac.th", "dean@g.swu.ac.th", "exec@g.swu.ac.th"))  # fmt: skip
COURSE = {"code_en": "X", "name_en": "X", "transcript_th": "x", "transcript_en": "X",
          "course_type": "วิชาแกน", "credit_text": "3(2-2-5)", "status": "ใช้งาน"}  # fmt: skip
PLAN = {
    "s1": {"status_type": "วิชาบังคับ", "hours_week": "4", "mode": "ออนไซต์ 100%", "contact": "อีเมล",
           "appeal": "ยื่นคำร้องที่คณะ", "consult_hours": "2", "updated_on": "2569-10-30"},
    "s3": {"clos": [{"code": "CLO1", "criteria": "อธิบายได้", "pct": 60}, {"code": "CLO2", "criteria": "ทำได้", "pct": 40}]},
    "s4": {"weeks": [{"week": 1, "topic": "แนะนำรายวิชา", "hours": 4}]},
    "s5": {"texts": "ตำราหลัก"},
    "s6": {"participation": "ก", "verify_outcome": "ข", "verify_quality": "ค", "appeal_risk": "ง"},
}  # fmt: skip


@pytest.fixture
def env(pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from ocl_api.external import ExternalStore
    from ocl_api.external.sample import SampleAdapter
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    for k, v in {"DATA_DIR": str(tmp_path / "data"), "DATABASE_URL": pg_url,
                 "DATABASE_SCHEMA": schema, "AUTH_SECRET": SECRET}.items():  # fmt: skip
        monkeypatch.setenv(k, v)
    app = create_app()
    for system in ("huris", "supreme"):
        ExternalStore(pg_url, schema).load(SampleAdapter(), system)
    users = UserStore(pg_url, schema)
    for email, roles in (("central@g.swu.ac.th", ["central"]), ("t1@g.swu.ac.th", ["teacher"]),
                         ("t2@g.swu.ac.th", ["teacher"]), ("cur@g.swu.ac.th", ["curator"]),
                         ("exec@g.swu.ac.th", ["exec"])):  # fmt: skip
        users.upsert(email, roles=roles)
    users.upsert("dean@g.swu.ac.th", roles=["faculty"], unit="คณะอื่น")
    with connect(pg_url, schema) as conn:
        for email, pid in (("t1", "SWU01001"), ("t2", "SWU01002"), ("cur", "SWU01003")):
            conn.execute(
                "UPDATE users SET pid = %s WHERE email = %s", (pid, f"{email}@g.swu.ac.th")
            )
    clear_user_cache()
    c = TestClient(app)
    # two offered courses form one module in the central course database (FS-4 Q2 ก)
    for code in ("ทวพ111", "ทวพ121"):
        c.post("/api/courses", json={**COURSE, "code_th": code, "name_th": f"วิชา {code}",
                                     "module": "ชุดวิชาวัสดุ"}, headers=CENTRAL)  # fmt: skip
    c.post(
        "/api/courses", json={**COURSE, "code_th": "ทวพ131", "name_th": "วิชาเดี่ยว"}, headers=CENTRAL
    )
    assert c.post(f"/api/m2/terms/{SLUG}/sync", headers=CENTRAL).status_code == 200
    return c, pg_url, schema


def item(c: TestClient, key: str, h=CENTRAL) -> dict:
    return next(
        i
        for i in c.get(f"/api/m2/terms/{SLUG}/items", headers=h).json()["items"]
        if i["key"] == key
    )


def test_offerings_come_from_the_timetable(env) -> None:
    c, *_ = env
    d = c.get(f"/api/m2/terms/{SLUG}/items", headers=CENTRAL).json()
    keys = {i["key"]: i for i in d["items"]}
    mod = keys["M:ชุดวิชาวัสดุ"]
    assert (
        mod["kind"] == "module" and mod["courses"] == ["ทวพ111", "ทวพ121"] and mod["sections"] == 3
    )
    assert "C:ทวพ111" not in keys, "a course of a module is planned with its module"
    assert keys["C:ทวพ131"]["name_th"] == "วิชาเดี่ยว", "the central course database names it"
    assert (
        keys["C:ทวพ211"]["name_th"].startswith("[รายวิชาตัวอย่าง") and keys["C:ทวพ211"]["unit"] == FAC
    )
    assert d["synced_at"] and len(keys) == 102 - 1, "102 codes, 2 of them one module"
    assert c.get(f"/api/m2/terms/{SLUG}/items", headers=T1).json()["items"] == [], (
        "BR-M2-05: only assigned"
    )
    assert c.get(f"/api/m2/terms/{SLUG}/items", headers=DEAN).json()["items"] == [], (
        "another faculty"
    )


def test_recorders_copy_and_notify(env) -> None:
    from ocl_api.mail import Outbox

    c, pg_url, schema = env
    u = f"/api/m2/terms/{SLUG}/items/{'C:ทวพ131'}/assign"
    assert c.put(u, json={"doc": "plan", "pids": ["NOPE"]}, headers=CENTRAL).status_code == 400
    assert c.put(u, json={"doc": "plan", "pids": ["SWU01001"]}, headers=T1).status_code == 403, (
        "p1 edit only"
    )
    r = c.put(u, json={"doc": "plan", "pids": ["SWU01001", "SWU01002"]}, headers=CENTRAL).json()
    assert [a["pid"] for a in r["assign"]["plan"]] == ["SWU01001", "SWU01002"] and r["assign"][
        "report"
    ] == []
    c.put(u, json={"doc": "report", "pids": ["SWU01002"]}, headers=CENTRAL)
    mine = c.get(f"/api/m2/terms/{SLUG}/items", headers=T1).json()["items"]
    assert [(i["key"], i["mine"]) for i in mine] == [("C:ทวพ131", {"plan": True, "report": False})]
    assert not mine[0]["scoped"]
    doc = f"/api/m2/terms/{SLUG}/items/C:ทวพ131"
    assert c.get(f"{doc}/plan", headers=T1).status_code == 200
    assert c.get(f"{doc}/report", headers=T1).status_code == 403, "BR-M2-05: the document assigned"
    # คัดลอกจากภาคก่อน: rows of 1/2569 for items offered now
    with connect(pg_url, schema) as conn:
        conn.execute("INSERT INTO m2_assign (term, key, doc, pids) VALUES "
                     "('1/2569', 'C:ทวพ211', 'plan', '[\"SWU01001\"]'), ('1/2569', 'C:ทวพ131', 'plan', '[\"SWU01003\"]')")  # fmt: skip
    assert c.post(f"/api/m2/terms/{SLUG}/assign/copy", headers=CENTRAL).json() == {
        "copied": 1,
        "from": "1/2569",
    }
    assert [a["pid"] for a in item(c, "C:ทวพ131")["assign"]["plan"]] == ["SWU01001", "SWU01002"], (
        "kept"
    )
    n = c.post(f"/api/m2/terms/{SLUG}/assign/notify", headers=CENTRAL).json()
    assert n["recipients"] == 2 and n["sent"] == 2
    assert c.post(f"/api/m2/terms/{SLUG}/assign/notify", headers=CENTRAL).json()["sent"] == 0, (
        "once a day"
    )
    assert any("ทวพ211" in m["body"] for m in Outbox(pg_url, schema).list())


def test_plan_is_recorded_certified_and_published(env) -> None:
    c, pg_url, schema = env
    key = "C:ทวพ131"
    c.put(
        f"/api/m2/terms/{SLUG}/items/{key}/assign",
        json={"doc": "plan", "pids": ["SWU01001"]},
        headers=CENTRAL,
    )
    # the curator teaches in a verified curriculum that has the course (FS-4 Q4 ก, BR-M2-03)
    did = c.post("/api/curricula", json={"name_th": "วท.บ. วัสดุ"}, headers=CENTRAL).json()["id"]
    secs = c.get(f"/api/curricula/{did}/sections", headers=CENTRAL).json()
    s0, s3, s4 = secs["0"]["data"], secs["3"]["data"], secs["4"]["data"]
    s0["teachers"] = {"teachers": [{"name": "อ.ผู้ตรวจ", "pid": "SWU01003"}]}
    s3["plo"] = {"plos": [{"code": "PLO1", "text": "รู้วัสดุ"}]}
    s4["courses"] = {"courses": [{"code_th": "ทวพ131", "name_th": "วิชาเดี่ยว"}]}
    s4["mapping"] = {
        "ksec_rows": [{"course_code": "ทวพ131", "plos": ["PLO1"], "by_column": {"K1": ["K1-1"]}}]
    }
    for n, data in (("0", s0), ("3", s3), ("4", s4)):
        c.put(f"/api/curricula/{did}/sections/{n}", json={"data": data}, headers=CENTRAL)
    doc = f"/api/m2/terms/{SLUG}/items/{key}/plan"
    assert c.get(doc, headers=CENTRAL).json()["pulled"]["plos"] == [], (
        "only verified curricula (BR-M2-03)"
    )
    with connect(pg_url, schema) as conn:
        conn.execute("UPDATE curriculum_drafts SET status = 'verified' WHERE id = %s", (did,))
    d = c.get(doc, headers=T1).json()
    assert (
        d["status"] == "none"
        and d["can_edit"]
        and d["pulled"]["plos"][0]["rows"][0]["by_column"] == {"K1": ["K1-1"]}
    )
    assert c.get(doc, headers=T2).status_code == 403, "not assigned"

    c.put(doc, json={"data": {"s1": PLAN["s1"]}}, headers=T1)
    miss = c.post(f"{doc}/submit", headers=T1).json()["detail"]
    assert "หมวด 3" in miss and "หมวด 6" in miss
    bad = {**PLAN, "s3": {"clos": [{"code": "CLO1", "criteria": "x", "pct": 50}]}}
    c.put(doc, json={"data": bad}, headers=T1)
    assert "เท่ากับ 100" in c.post(f"{doc}/submit", headers=T1).json()["detail"]
    c.put(doc, json={"data": PLAN}, headers=T1)
    r = c.post(f"{doc}/submit", headers=T1).json()
    assert r["status"] == "sent" and not r["can_edit"]
    assert c.put(doc, json={"data": PLAN}, headers=T1).status_code == 403, "sent: locked"

    assert c.post(f"{doc}/certify", json={"ok": True}, headers=T1).status_code == 403
    assert c.post(f"{doc}/certify", json={"ok": False}, headers=CUR).status_code == 400, "a reason"
    r = c.post(f"{doc}/certify", json={"ok": False, "note": "เพิ่ม CLO3"}, headers=CUR).json()
    assert r["status"] == "returned" and r["can_edit"] is False, "the curator does not edit"
    assert c.get(doc, headers=T1).json()["can_edit"]
    c.post(f"{doc}/submit", headers=T1)
    assert c.post(f"{doc}/certify", json={"ok": True}, headers=CUR).json()["status"] == "approved"
    assert c.post(f"{doc}/publish", headers=CUR).status_code == 403, "central publishes"
    assert c.post(f"{doc}/publish", headers=CENTRAL).json()["status"] == "published"
    r = c.post(f"{doc}/publish?on=false", headers=CENTRAL).json()
    assert r["status"] == "approved"
    assert [e["action"] for e in r["events"]][-4:] == ["submit", "approve", "publish", "unpublish"]


def test_window_report_and_copy(env) -> None:
    c, *_ = env
    key = "C:ทวพ131"
    for d in ("plan", "report"):
        c.put(
            f"/api/m2/terms/{SLUG}/items/{key}/assign",
            json={"doc": d, "pids": ["SWU01001"]},
            headers=CENTRAL,
        )
    today = today_th()
    t = {
        "starts_on": (today + timedelta(days=10)).isoformat(),
        "ends_on": (today + timedelta(days=120)).isoformat(),
    }
    r = c.put(f"/api/m2/terms/{SLUG}", json=t, headers=CENTRAL).json()
    assert r["plan_close"] == (today - timedelta(days=4)).isoformat(), (
        "BR-M2-04: 2 weeks before the term"
    )
    plan = f"/api/m2/terms/{SLUG}/items/{key}/plan"
    d = c.get(plan, headers=T1).json()
    assert d["window"]["open"] is False and d["can_edit"] is False
    assert c.put(plan, json={"data": PLAN}, headers=T1).status_code == 403
    assert c.put(plan, json={"data": PLAN}, headers=CENTRAL).status_code == 200, (
        "central may still key it in"
    )

    rep = f"/api/m2/terms/{SLUG}/items/{key}/report"
    enrolled = c.get(rep, headers=T1).json()["pulled"]["enrolled"]
    too_many = {"r3": {"grades": {"A": enrolled + 1}, "achieved": "x", "not_achieved": "y"},
                "r4": {"critique": "a", "improvement": "b"}}  # fmt: skip
    c.put(rep, json={"data": too_many}, headers=T1)
    assert "เกินจำนวนลงทะเบียน" in c.post(f"{rep}/submit", headers=T1).json()["detail"]
    ok = {**too_many, "r3": {**too_many["r3"], "grades": {"A": 5, "B": 3}}}
    c.put(rep, json={"data": ok}, headers=T1)
    assert "หลังวันสุดท้ายของภาค" in c.post(f"{rep}/submit", headers=T1).json()["detail"]
    c.put(
        f"/api/m2/terms/{SLUG}",
        json={
            "starts_on": (today - timedelta(days=100)).isoformat(),
            "ends_on": (today - timedelta(days=1)).isoformat(),
        },
        headers=CENTRAL,
    )
    assert c.post(f"{rep}/submit", headers=T1).json()["status"] == "sent"
    # คัดลอกจากภาคก่อน: nothing in 1/2569 yet, then this term already has one
    assert (
        c.post(f"/api/m2/terms/{SLUG}/items/C:ทวพ211/plan/copy", headers=CENTRAL).status_code == 404
    )
    assert c.post(f"{plan}/copy", headers=CENTRAL).status_code == 409


def test_dashboard_late_and_reminders(env) -> None:
    c, *_ = env
    today = today_th()
    c.put(
        f"/api/m2/terms/{SLUG}/items/C:ทวพ131/assign",
        json={"doc": "plan", "pids": ["SWU01001"]},
        headers=CENTRAL,
    )
    c.put(
        f"/api/m2/terms/{SLUG}",
        json={"plan_close": (today - timedelta(days=3)).isoformat()},
        headers=CENTRAL,
    )
    d = c.get(f"/api/m2/terms/{SLUG}/dashboard", headers=CENTRAL).json()
    assert (
        d["offered"] == 101 and d["modules"] == 1 and d["unassigned"] == 101 and d["plan_pct"] == 0
    )
    assert d["late"][0]["days"] == 3 and all(x["doc"] == "plan" for x in d["late"])
    assert all(u["below"] for u in d["units"]), "0% is under the 70% target"
    assert c.get(f"/api/m2/terms/{SLUG}/dashboard", headers=EXEC).status_code == 200
    assert c.post(f"/api/m2/terms/{SLUG}/remind", json={}, headers=EXEC).status_code == 403
    one = c.post(
        f"/api/m2/terms/{SLUG}/remind", json={"key": "C:ทวพ131", "doc": "plan"}, headers=CENTRAL
    ).json()
    assert one == {"sent": 1, "late": 1}
    again = c.post(f"/api/m2/terms/{SLUG}/remind", json={}, headers=CENTRAL).json()
    assert again["sent"] == 0 and again["late"] == 101, (
        "the others have no recorder; ทวพ131 was reminded today"
    )
