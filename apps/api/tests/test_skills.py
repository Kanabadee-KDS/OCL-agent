"""Skill Transcript (FS-5 · US-M3-01–10 · BR-M3-01–06)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.db import connect
from ocl_api.skill_defaults import LEVELS
from ocl_api.skills import level_of

SECRET = "skills-secret-for-tests-only-32b"
TERM, SLUG = "2/2569", "2-2569"
FAC = "คณะเทคโนโลยีและนวัตกรรมผลิตภัณฑ์การเกษตร"
PROG = "25500091010001"  # the sample's first programme: courses ทวพ111 ทวพ121 ทวพ131
CORE = ["GS1", "GS2", "GS3", "GS4", "GS5", "E1", "E3", "E4", "C1", "C2"]
MAP = {"ทวพ111": CORE[:5], "ทวพ121": CORE[5:], "ทวพ131": ["SS1"]}


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, CHAIR, TCH, FACU, TEACHER, ADVISOR, STUDENT, OTHER = (h(f"{x}@g.swu.ac.th") for x in (
    "central", "chair", "tch", "fac", "teacher", "advisor", "student", "other"))  # fmt: skip


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
    with connect(pg_url, schema) as conn:
        sec = {
            r["course_code"]: r["teachers"]
            for r in conn.execute(
                "SELECT course_code, teachers FROM ext_sections WHERE program_code = %s "
                "AND section = '1'",
                (PROG,),
            )
        }
        grads = [r["sid"] for r in conn.execute(
            "SELECT sid FROM ext_students WHERE program_code = %s AND graduated IS NOT NULL "
            "ORDER BY sid", (PROG,))]  # fmt: skip
        advisor = conn.execute("SELECT advisor_pid FROM ext_students WHERE sid = %s",
                               (grads[0],)).fetchone()["advisor_pid"]  # fmt: skip
    users = UserStore(pg_url, schema)
    people = {  # email -> (roles, unit, pid, sid)
        "central": (["central"], None, None, None),
        "chair": (["curator"], None, "SWU01002", None),
        "tch": (["curator"], None, "SWU01003", None),
        "fac": (["faculty"], FAC, None, None),
        "teacher": (["teacher"], None, sec["ทวพ111"][0], None),
        "advisor": (["advisor"], None, advisor, None),
        "student": (["student"], None, None, grads[0]),
        "other": (["curator"], None, "SWU02001", None),
    }
    for name, (roles, unit, _, _) in people.items():
        users.upsert(f"{name}@g.swu.ac.th", roles=roles, unit=unit)
    with connect(pg_url, schema) as conn:
        for name, (_, _, pid, sid) in people.items():
            conn.execute("UPDATE users SET pid = %s, sid = %s WHERE email = %s",
                         (pid, sid, f"{name}@g.swu.ac.th"))  # fmt: skip
    clear_user_cache()
    c = TestClient(app)
    # a curriculum of the sample programme; SWU01001 teaches in its 0.2 (scope หลักสูตร)
    cid = c.post("/api/curricula", json={"name_th": "วท.บ. วัสดุพอลิเมอร์"}, headers=CENTRAL).json()[
        "id"
    ]
    s0 = c.get(f"/api/curricula/{cid}/sections", headers=CENTRAL).json()["0"]["data"]
    s0["info"]["values"] |= {"program_code": PROG, "faculty": FAC}
    s0["teachers"] = {"teachers": [{"name": "อ.ประธาน", "pid": "SWU01002"},
                                   {"name": "อ.ผู้สอน", "pid": "SWU01003"}]}  # fmt: skip
    c.put(f"/api/curricula/{cid}/sections/0", json={"data": s0}, headers=CENTRAL)
    return {"c": c, "url": pg_url, "schema": schema, "cid": cid, "grads": grads, "sec": sec}


def test_levels_follow_the_table() -> None:
    assert [level_of(x, LEVELS)["en"] for x in (0, 1.49, 1.5, 2.495, 3.5, 4.5, 5)] == [
        "Novice", "Novice", "Advanced Beginner", "Competent", "Proficient", "Expert", "Expert"]  # fmt: skip
    assert level_of(None, LEVELS) is None


def test_skill_database(env) -> None:
    c = env["c"]
    d = c.get("/api/skills", headers=CENTRAL).json()
    assert len(d["items"]) == 14 and {
        s["code"] for s in d["items"] if s["scope"] == "central"
    } == set(CORE)
    assert d["settings"]["ethics_pass"] == 2.5 and len(d["settings"]["levels"]) == 5
    new = {"code": "SS9", "cat": "SS", "name_th": "ทักษะใหม่", "scope": "program"}
    assert c.post("/api/skills", json=new, headers=CENTRAL).status_code == 201
    assert c.post("/api/skills", json=new, headers=CENTRAL).status_code == 409
    # a curator adds SS/E/C of a curriculum, not GS nor a skill of the whole university
    assert c.get("/api/skills", headers=CHAIR).json()["rights"] == {
        "cats": ["SS", "E", "C"], "central": False}  # fmt: skip
    bad = {**new, "code": "GS9", "cat": "GS"}
    assert c.post("/api/skills", json=bad, headers=CHAIR).status_code == 403
    assert c.post("/api/skills", json={**new, "code": "E9", "cat": "E", "scope": "central"},
                  headers=CHAIR).status_code == 403  # fmt: skip
    assert c.put("/api/skills/GS1", json={"code": "GS1", "cat": "GS", "name_th": "x"},
                 headers=CHAIR).status_code == 403  # fmt: skip
    assert c.post("/api/skills/SS9/active?on=false", headers=CENTRAL).json()["active"] is False
    # the levels table: five ranges in order (BR-M3-02)
    lv = d["settings"]["levels"]
    bad_lv = [dict(lv[0], max=2.0), *lv[1:]]
    assert (
        c.put("/api/skills/settings/levels", json={"data": bad_lv}, headers=CENTRAL).status_code
        == 400
    )
    assert (
        c.put("/api/skills/settings/ethics_pass", json={"data": 3}, headers=CHAIR).status_code
        == 403
    )
    # import from Excel: the template's own row is added, a bad row is reported
    from openpyxl import load_workbook

    t = c.get("/api/skills/template.xlsx", headers=CENTRAL)
    wb = load_workbook(io.BytesIO(t.content))
    wb.active.append(["C9", "X", "ผิดด้าน", "", "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    out = c.post("/api/skills/import", files={"file": ("s.xlsx", buf.getvalue())},
                 headers=CENTRAL).json()  # fmt: skip
    assert out["added"] == 1 and out["errors"][0]["row"] == 3


def _set_up(env) -> int:
    """Chair and a course-only teacher assigned, the set approved, the mapping approved."""
    c, cid = env["c"], env["cid"]
    rows = [{"pid": "SWU01002", "role": "chair", "perms": ["add", "map", "send", "appr"]},
            {"pid": "SWU01003", "role": "tch", "perms": ["map"], "scope": "courses",
             "courses": ["ทวพ111"]}]  # fmt: skip
    assert c.put(f"/api/skills/assign/{cid}", json=rows, headers=CENTRAL).status_code == 200
    c.post(f"/api/skills/sets/{cid}/own",
           json={"code": "SS1", "cat": "SS", "name_th": "การออกแบบผลิตภัณฑ์"}, headers=CHAIR)  # fmt: skip
    c.post(f"/api/skills/sets/{cid}/submit", headers=CHAIR)
    c.post(f"/api/skills/sets/{cid}/certify", json={"ok": True}, headers=FACU)
    c.put(f"/api/skills/map/{SLUG}/{cid}", json={"cells": MAP}, headers=CHAIR)
    c.post(f"/api/skills/map/{SLUG}/{cid}/submit", headers=CHAIR)
    assert c.post(f"/api/skills/map/{SLUG}/{cid}/certify", json={"ok": True},
                  headers=FACU).json()["status"] == "approved"  # fmt: skip
    return cid


def test_assign_and_skill_set(env) -> None:
    from ocl_api.mail import Outbox

    c, cid = env["c"], env["cid"]
    rows = [{"pid": "SWU01002", "role": "chair", "perms": ["add", "map", "send", "appr"]},
            {"pid": "SWU01003", "role": "tch", "perms": ["map"], "scope": "courses"}]  # fmt: skip
    r = c.put(f"/api/skills/assign/{cid}", json=rows, headers=CENTRAL)
    assert r.status_code == 400, "a course-only person needs courses"
    rows[1]["courses"] = ["ทวพ111"]
    assert c.put(f"/api/skills/assign/{cid}", json=rows, headers=TEACHER).status_code == 403
    assert len(c.put(f"/api/skills/assign/{cid}", json=rows, headers=CENTRAL).json()) == 2
    assert sum(1 for m in Outbox(env["url"], env["schema"]).list() if m["kind"] == "skill") == 1
    ov = c.get("/api/skills/assign", headers=CENTRAL).json()
    assert ov["kpi"]["assigned"] == 1 and ov["kpi"]["people"] == 2
    # the set starts with the core, which cannot be taken out (BR-M3-03)
    d = c.get(f"/api/skills/sets/{cid}", headers=CHAIR).json()
    assert d["set"]["status"] == "none" and d["set"]["skills"] == CORE and d["can_edit"]
    assert not c.get(f"/api/skills/sets/{cid}", headers=TCH).json()["can_edit"], "no right add"
    assert c.get(f"/api/skills/sets/{cid}", headers=OTHER).status_code == 403, "out of scope"
    assert c.get("/api/skills/sets", headers=TEACHER).status_code == 403
    d = c.put(f"/api/skills/sets/{cid}", json={"skills": ["C3"], "cohort_from": 66},
              headers=CHAIR).json()  # fmt: skip
    assert d["set"]["skills"] == [*CORE, "C3"], "the core stays"
    d = c.post(f"/api/skills/sets/{cid}/own", json={"code": "SS1", "cat": "SS", "name_th": "ออกแบบ"},
               headers=CHAIR).json()  # fmt: skip
    assert "SS1" in d["set"]["skills"]
    own = next(
        s for s in c.get("/api/skills", headers=CENTRAL).json()["items"] if s["code"] == "SS1"
    )
    assert own["scope"] == "program" and own["curriculum_id"] == cid
    assert c.post(f"/api/skills/sets/{cid}/own", json={"code": "GS7", "cat": "GS", "name_th": "x"},
                  headers=CHAIR).status_code == 400  # fmt: skip
    # ส่ง → คณะอนุมัติ (flow skill_set)
    assert c.post(f"/api/skills/sets/{cid}/submit", headers=CHAIR).json()["set"]["status"] == "sent"
    assert c.put(f"/api/skills/sets/{cid}", json={"skills": []}, headers=CHAIR).status_code == 403
    assert (
        c.post(f"/api/skills/sets/{cid}/certify", json={"ok": False}, headers=FACU).status_code
        == 400
    )
    d = c.post(f"/api/skills/sets/{cid}/certify", json={"ok": False, "note": "เพิ่ม E2"},
               headers=FACU).json()  # fmt: skip
    assert d["set"]["status"] == "returned"
    c.post(f"/api/skills/sets/{cid}/submit", headers=CHAIR)
    assert c.post(f"/api/skills/sets/{cid}/certify", json={"ok": True},
                  headers=FACU).json()["set"]["status"] == "approved"  # fmt: skip
    ov = c.get("/api/skills/sets", headers=CENTRAL).json()
    assert ov["kpi"]["approved"] == 1 and ov["items"][0]["counts"]["SS"] == 1
    # ขอแก้ไข (สร้างฉบับใหม่) for a later cohort; the approved one stays for the earlier
    d = c.post(f"/api/skills/sets/{cid}/revise", json={"cohort_from": 68}, headers=CHAIR).json()
    assert d["set"]["version"] == 2 and d["set"]["status"] == "draft"
    from ocl_api.skills import SkillStore

    assert SkillStore(env["url"], env["schema"]).approved_set(cid, 67)["version"] == 1


def test_mapping(env) -> None:
    c, cid = env["c"], env["cid"]
    rows = [{"pid": "SWU01002", "role": "chair", "perms": ["add", "map", "send", "appr"]},
            {"pid": "SWU01003", "role": "tch", "perms": ["map"], "scope": "courses",
             "courses": ["ทวพ111"]}]  # fmt: skip
    c.put(f"/api/skills/assign/{cid}", json=rows, headers=CENTRAL)
    d = c.get(f"/api/skills/map/{SLUG}/{cid}", headers=CHAIR).json()
    assert d["set"] is None and not d["can_edit"], "only an approved set maps (US-M3-04)"
    c.post(f"/api/skills/sets/{cid}/own", json={"code": "SS1", "cat": "SS", "name_th": "x"},
           headers=CHAIR)  # fmt: skip
    c.post(f"/api/skills/sets/{cid}/submit", headers=CHAIR)
    c.post(f"/api/skills/sets/{cid}/certify", json={"ok": True}, headers=FACU)
    d = c.get(f"/api/skills/map/{SLUG}/{cid}", headers=CHAIR).json()
    assert [x["code"] for x in d["courses"] if x["offered"]] == ["ทวพ111", "ทวพ121", "ทวพ131"]
    assert d["kpi"]["gaps"] == [*CORE, "SS1"]
    bad = c.put(f"/api/skills/map/{SLUG}/{cid}", json={"cells": {"ทวพ999": ["GS1"]}}, headers=CHAIR)
    assert bad.status_code == 400, "a course not offered cannot be mapped"
    d = c.put(f"/api/skills/map/{SLUG}/{cid}", json={"cells": {**MAP, "ทวพ111": [*CORE[:5], "ZZ"]}},
              headers=CHAIR).json()  # fmt: skip
    assert d["kpi"]["points"] == 11 and d["kpi"]["gaps"] == [] and d["kpi"]["mapped"] == 3
    # a course-only teacher changes only their course
    r = c.put(f"/api/skills/map/{SLUG}/{cid}", json={"cells": {**MAP, "ทวพ131": []}}, headers=TCH)
    assert r.status_code == 403
    r = c.put(f"/api/skills/map/{SLUG}/{cid}", json={"cells": {**MAP, "ทวพ111": ["GS1"]}},
              headers=TCH)  # fmt: skip
    assert r.status_code == 200
    assert c.post(f"/api/skills/map/{SLUG}/{cid}/submit", headers=TCH).status_code == 403
    c.put(f"/api/skills/map/{SLUG}/{cid}", json={"cells": MAP}, headers=CHAIR)
    assert c.post(f"/api/skills/map/{SLUG}/{cid}/copy", headers=CHAIR).status_code == 404
    d = c.post(f"/api/skills/map/{SLUG}/{cid}/submit", headers=CHAIR).json()
    assert d["status"] == "sent" and not d["can_edit"]
    assert c.post(f"/api/skills/map/{SLUG}/{cid}/certify", json={"ok": True},
                  headers=FACU).json()["status"] == "approved"  # fmt: skip
    # คัดลอกจากภาคก่อน into a later term: courses not offered then are skipped
    with connect(env["url"], env["schema"]) as conn:
        conn.execute("INSERT INTO ext_sections (term, course_code, section, program_code, "
                     "teachers) VALUES ('1/2570', 'ทวพ111', '1', %s, '[]')", (PROG,))  # fmt: skip
    d = c.post(f"/api/skills/map/1-2570/{cid}/copy", headers=CHAIR).json()
    assert d["copied_from"] == TERM and sorted(d["skipped"]) == ["ทวพ121", "ทวพ131"]
    assert d["kpi"]["points"] == 5


def _score_all(c, code: str, sec: str, scores: dict[str, float], who=CENTRAL) -> dict:
    d = c.get(f"/api/skills/assess/{SLUG}/{code}/{sec}", headers=who).json()
    body = {s["sid"]: {k: scores.get(s["sid"], 4.0) for k in d["skills"]} for s in d["students"]}
    c.put(f"/api/skills/assess/{SLUG}/{code}/{sec}", json={"scores": body}, headers=who)
    return c.post(f"/api/skills/assess/{SLUG}/{code}/{sec}/confirm", headers=who).json()


def test_assessment_portfolio_and_transcript(env) -> None:
    from openpyxl import load_workbook

    c, grads = env["c"], env["grads"]
    _set_up(env)
    # US-M3-05: a teacher sees the sections they teach, with the mapped skills (BR-M3-06)
    mine = c.get(f"/api/skills/assess/{SLUG}", headers=TEACHER).json()["items"]
    assert ("ทวพ111", "1") in [(i["course_code"], i["section"]) for i in mine]
    assert all(i["mine"] for i in mine) and len(mine) < 4, "only the sections they teach"
    first = next(i for i in mine if i["course_code"] == "ทวพ111")
    assert first["skills"] == CORE[:5] and first["status"] == "todo" and first["n"] == 30
    assert len(c.get(f"/api/skills/assess/{SLUG}", headers=CENTRAL).json()["items"]) == 4
    url = f"/api/skills/assess/{SLUG}/ทวพ111/1"
    d = c.get(url, headers=TEACHER).json()
    sid = d["students"][0]["sid"]
    assert c.put(url, json={"scores": {sid: {"GS1": 6}}}, headers=TEACHER).status_code == 400
    assert c.put(url, json={"scores": {"999": {"GS1": 3}}}, headers=TEACHER).status_code == 400
    assert c.put(url, json={"scores": {sid: {"SS1": 3}}}, headers=TEACHER).status_code == 400
    d = c.put(url, json={"scores": {sid: {"GS1": 3.5}}}, headers=TEACHER).json()
    assert d["status"] == "doing" and d["scores"][sid] == {"GS1": 3.5}
    assert c.post(f"{url}/confirm", headers=TEACHER).status_code == 400, "not complete"
    # แบบฟอร์ม Excel: download, fill every cell, import
    wb = load_workbook(io.BytesIO(c.get(f"{url}/form.xlsx", headers=TEACHER).content))
    ws = wb.worksheets[0]
    for row in ws.iter_rows(min_row=2):
        for cell in row[2:]:
            cell.value = 4.5 if row[0].value in grads else 3
    buf = io.BytesIO()
    wb.save(buf)
    d = c.post(f"{url}/import", files={"file": ("f.xlsx", buf.getvalue())}, headers=TEACHER).json()
    assert d["imported"] == 30 and d["status"] == "wait"
    d = c.post(f"{url}/confirm", headers=TEACHER).json()
    assert d["status"] == "ok" and not d["can_edit"]
    assert c.put(url, json={"scores": {sid: {"GS1": 1}}}, headers=TEACHER).status_code == 403
    assert c.post(f"{url}/reopen", json={"note": ""}, headers=CENTRAL).status_code == 400
    assert c.post(f"{url}/reopen", json={"note": "x"}, headers=TEACHER).status_code == 403
    # the other courses: one graduate fails E1 (Ethics U), the others pass
    _score_all(c, "ทวพ121", "1", {grads[1]: 2.0})
    _score_all(c, "ทวพ131", "1", {grads[0]: 5.0})
    # BR-M3-01: the average of the courses that assessed the skill
    p = c.get(f"/api/skills/portfolio/{grads[0]}", headers=CENTRAL).json()
    gs1 = next(s for s in p["skills"] if s["code"] == "GS1")
    assert (
        gs1["avg"] == 4.5
        and gs1["level"] == "Expert"
        and gs1["sources"][0]["course_code"] == "ทวพ111"
    )
    assert p["cats"]["SS"] == 5.0 and p["by_term"][0]["label"] == "ปี 4/2"
    assert p["readiness"]["ready"]
    # อาจารย์ที่ปรึกษาเห็นเฉพาะนิสิตในความดูแล · the student sees their own only
    adv = c.get("/api/skills/portfolio", headers=ADVISOR).json()["items"]
    assert grads[0] in {s["sid"] for s in adv} and len(adv) < 40
    other = next(s["sid"] for s in c.get("/api/skills/portfolio", headers=CENTRAL).json()["items"]
                 if s["sid"] not in {a["sid"] for a in adv})  # fmt: skip
    assert c.get(f"/api/skills/portfolio/{other}", headers=ADVISOR).status_code == 403
    assert c.get("/api/skills/me", headers=STUDENT).json()["student"]["sid"] == grads[0]
    assert c.get("/api/skills/portfolio", headers=STUDENT).status_code == 403
    assert c.get("/api/skills/me", headers=TEACHER).status_code == 403
    draft = c.get("/api/skills/me/transcript", headers=STUDENT).json()
    assert draft["draft"] and draft["no"] is None
    # ออกเอกสาร (BR-M3-04): groups, only the ready ones
    g = c.get("/api/skills/issue", headers=CENTRAL).json()
    groups = {i["sid"]: i["group"] for i in g["items"]}
    assert groups[grads[0]] == "ready" and groups[grads[1]] == "ethics"
    assert (
        c.post("/api/skills/issue", json={"sids": [grads[1]]}, headers=CENTRAL).status_code == 400
    )
    out = c.post("/api/skills/issue", json={"sids": [grads[0], grads[2]]}, headers=CENTRAL).json()
    assert out["issued"][0].startswith("ST-25") and out["issued"][0].endswith("-000001")
    no = out["issued"][0]
    doc = c.get("/api/skills/me/transcript", headers=STUDENT).json()
    assert not doc["draft"] and doc["no"] == no and doc["signer"]["sample"]
    # หน้าตรวจสอบ QR: no sign-in, counted (R09)
    v = c.get(f"/api/public/transcripts/{no}").json()
    assert v["name_th"] and v["signature"]["valid"] and v["checks"] == 1
    assert c.get(f"/api/public/transcripts/{no.lower()}").json()["checks"] == 2
    assert c.get("/api/public/transcripts/ST-0000-000000").status_code == 404
    with connect(env["url"], env["schema"]) as conn:
        conn.execute("UPDATE skill_transcripts SET data = jsonb_set(data, '{overall}', '1') "
                     "WHERE no = %s", (no,))  # fmt: skip
    assert not c.get(f"/api/public/transcripts/{no}").json()["signature"]["valid"], "tampered"
    reg = c.get("/api/skills/register", headers=CENTRAL).json()
    assert next(r for r in reg if r["no"] == no)["checks"] == 3 and len(reg) == 2
    svg = c.get(f"/api/skills/transcripts/{no}/qr.svg?origin=https://x.test", headers=STUDENT)
    assert svg.status_code == 200 and 'xmlns="http://www.w3.org/2000/svg"' in svg.text
    assert c.get(f"/api/skills/transcripts/{no}/qr.svg?origin=javascript:x",
                 headers=STUDENT).status_code == 400  # fmt: skip
    assert c.get(f"/api/skills/transcripts/{no}/qr.svg?origin=https://x.test",
                 headers=ADVISOR).status_code == 200, "the advisor of the student"  # fmt: skip


def test_dashboard_and_reminders(env) -> None:
    c = env["c"]
    _set_up(env)
    _score_all(c, "ทวพ131", "1", {})
    d = c.get(f"/api/skills/dashboard/{SLUG}", headers=CENTRAL).json()
    assert d["sections"] == 4 and d["status"]["ok"] == 1 and d["status"]["todo"] == 3
    assert d["units"][0]["faculty"] == FAC and d["units"][0]["below"]
    assert d["late"][0]["status"] == "todo" and d["graduates"] > 0
    r = c.post(f"/api/skills/dashboard/{SLUG}/remind", json={}, headers=CENTRAL).json()
    assert r["late"] == 3 and r["sent"] == 3
    again = c.post(f"/api/skills/dashboard/{SLUG}/remind", json={}, headers=CENTRAL).json()
    assert again["sent"] == 0, "once a day"
    assert c.get(f"/api/skills/dashboard/{SLUG}", headers=TEACHER).status_code == 403
