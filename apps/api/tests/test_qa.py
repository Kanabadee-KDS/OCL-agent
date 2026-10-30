"""ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน (FS-6 · US-M4-01–08 · BR-M4-01–05)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import clear_user_cache, sign_token
from ocl_api.db import connect
from ocl_api.qa import NO_THESIS, final_of, set_of

SECRET = "qa-secret-for-tests-only-32bytes"
FAC = "คณะเทคโนโลยีและนวัตกรรมผลิตภัณฑ์การเกษตร"
PROG = "25500091010001"


def h(sub: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}


CENTRAL, REC, CONF, EV, EV2, OTHER = (h(f"{x}@g.swu.ac.th") for x in (
    "central", "rec", "conf", "ev", "ev2", "other"))  # fmt: skip


def _curriculum(c, name: str, level: str, standard: str, n_resp: int, approved: str, fac=1):
    cid = c.post("/api/curricula", json={"name_th": name}, headers=CENTRAL).json()["id"]
    secs = c.get(f"/api/curricula/{cid}/sections", headers=CENTRAL).json()
    s0, s5 = secs["0"]["data"], secs["5"]["data"]
    s0["info"]["values"] |= {"level": level, "faculty": FAC, "standard_criteria": standard,
                             "program_code": PROG if "ตรี" in level else None}  # fmt: skip
    s0["teachers"] = {"teachers": [
        {"name": f"อาจารย์ {fac}.{i}", "pid": f"SWU0{fac}00{i}", "responsible": i <= n_resp,
         "highest_level": "เอก", "rank": "อาจารย์"} for i in range(1, 7)
    ] + [{"name": "อาจารย์ ภายนอก", "responsible": False, "highest_level": "โท"}]}  # fmt: skip
    s5["appr"] = {"approvals": [{"level_key": "university_council",
                                 "date": {"iso": approved, "text": approved}}]}  # fmt: skip
    for n, data in (("0", s0), ("5", s5)):
        r = c.put(f"/api/curricula/{cid}/sections/{n}", json={"data": data}, headers=CENTRAL)
        assert r.status_code == 200, r.text
    return cid


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
    for email, roles, pid in (("central", ["central"], None), ("rec", ["curator"], "SWU02001"),
                              ("conf", ["curator"], "SWU02002"), ("ev", ["evaluator"], None),
                              ("ev2", ["evaluator"], None), ("other", ["curator"], "SWU03001")):  # fmt: skip
        users.upsert(f"{email}@g.swu.ac.th", roles=roles)
        with connect(pg_url, schema) as conn:
            conn.execute(
                "UPDATE users SET pid = %s WHERE email = %s", (pid, f"{email}@g.swu.ac.th")
            )
    clear_user_cache()
    c = TestClient(app)
    bsc = _curriculum(c, "วท.บ. วัสดุ", "ปริญญาตรี", "ประกาศ อว. 2565 (ตรี)", 5, "2023-01-10")
    msc = _curriculum(c, "วท.ม. วัสดุ", "ปริญญาโท", "ประกาศ ศธ. 2558", 3, "2019-06-01", fac=4)
    return {"c": c, "url": pg_url, "schema": schema, "bsc": bsc, "msc": msc}


def test_set_and_final_rules() -> None:
    assert [set_of(x) for x in ("ประกาศ อว. 2565 (ตรี)", "เกณฑ์ 2558", "", None, "2560")] == [
        2565, 2558, 2565, 2565, 2565]  # fmt: skip
    items = [{"no": 1, "applies": True}, {"no": 2, "applies": True}, {"no": 5, "applies": False}]
    assert final_of(items, {"1": {"result": "pass"}, "2": {"result": "pass"}}) == "pass"
    assert final_of(items, {"1": {"result": "fail"}}) == "fail"
    assert final_of(items, {"1": {"result": "pass"}, "2": {"result": "pending"}}) == "pending"


def test_criteria(env) -> None:
    c = env["c"]
    d = c.get("/api/qa/criteria", headers=CENTRAL).json()
    assert len(d["items"]) == 30 and d["sets"] == [2548, 2558, 2565]
    c10 = next(i for i in d["items"] if i["set_year"] == 2565 and i["no"] == 10)
    assert c10["rule"] == "revision_age" and "สมมติ" not in c10["detail"]
    assert "สมมติ" in next(i for i in d["items"] if i["set_year"] == 2548)["detail"]
    body = {**{k: c10[k] for k in ("set_year", "no", "title", "detail", "sources", "level",
                                   "rule")}, "title": "ปรับปรุงหลักสูตร (แก้)"}  # fmt: skip
    assert c.put(f"/api/qa/criteria/{c10['id']}", json=body, headers=OTHER).status_code == 403
    assert c.put(f"/api/qa/criteria/{c10['id']}", json=body, headers=CENTRAL).status_code == 200
    assert c.post("/api/qa/criteria", json={**body, "no": 9}, headers=CENTRAL).status_code == 409


def _round(c, programs, year=2569):
    r = c.post("/api/qa/rounds", json={"year": year, "starts_on": "2026-11-01",
                                       "ends_on": "2027-01-31", "programs": programs},
               headers=CENTRAL)  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()


def test_round_lifecycle(env) -> None:
    c, bsc, msc = env["c"], env["bsc"], env["msc"]
    cand = {x["id"]: x for x in c.get("/api/qa/candidates", headers=CENTRAL).json()}
    assert cand[bsc]["set_year"] == 2565 and cand[msc]["set_year"] == 2558, "BR-M4-05"
    bad = [{"curriculum_id": bsc, "set_year": 2565, "evaluators": ["rec@g.swu.ac.th"]}]
    assert c.post("/api/qa/rounds", json={"year": 2569, "programs": bad},
                  headers=CENTRAL).status_code == 400, "evaluators come from the group"  # fmt: skip
    progs = [{"curriculum_id": bsc, "set_year": 2565, "evaluators": ["ev@g.swu.ac.th"]},
             {"curriculum_id": msc, "set_year": 2558, "evaluators": []}]  # fmt: skip
    r = _round(c, progs)
    assert r["status"] == "draft" and r["programs"] == 2 and r["sets"] == [2558, 2565]
    assert c.post("/api/qa/rounds", json={"year": 2569}, headers=OTHER).status_code == 403
    assert c.post(f"/api/qa/rounds/{r['id']}/open", headers=CENTRAL).json()["status"] == "open"
    second = _round(c, progs[:1], 2570)
    assert c.post(f"/api/qa/rounds/{second['id']}/open", headers=CENTRAL).status_code == 409, (
        "one open round at a time"
    )
    # the criteria were copied into the round: a later edit does not change it
    crit = c.get("/api/qa/criteria", headers=CENTRAL).json()["items"]
    c1 = next(i for i in crit if i["set_year"] == 2565 and i["no"] == 1)
    c.put(f"/api/qa/criteria/{c1['id']}", json={**{k: c1[k] for k in (
        "set_year", "no", "detail", "sources", "level", "rule")}, "title": "แก้ทีหลัง"},
        headers=CENTRAL)  # fmt: skip
    d = c.get(f"/api/qa/rounds/{r['id']}/programs/{bsc}", headers=CENTRAL).json()
    assert d["items"][0]["title"] == c1["title"] != "แก้ทีหลัง"
    cp = c.post(f"/api/qa/rounds/{r['id']}/copy", headers=CENTRAL).json()
    assert cp["year"] == 2570 and cp["programs"] == 2 and cp["status"] == "draft"
    assert c.post(f"/api/qa/rounds/{r['id']}/close", json={}, headers=CENTRAL).json()["status"] == (
        "closed"
    )
    assert (
        c.put(f"/api/qa/rounds/{r['id']}", json={"year": 2569}, headers=CENTRAL).status_code == 409
    )


def test_record_confirm_evaluate(env) -> None:
    from ocl_api.mail import Outbox

    c, bsc = env["c"], env["bsc"]
    r = _round(c, [{"curriculum_id": bsc, "set_year": 2565, "evaluators": ["ev@g.swu.ac.th"]}])
    rid = r["id"]
    c.post(f"/api/qa/rounds/{rid}/open", headers=CENTRAL)
    url = f"/api/qa/rounds/{rid}/programs/{bsc}"
    d = c.get(url, headers=CENTRAL).json()
    assert not d["complete"] and not d["can_note"], "no recorder and confirmer yet"
    # evidence and what the system computes (BR-M4-02 · FS-6 Q2 ก)
    ev = {str(i["no"]): i["evidence"] for i in d["items"]}
    assert ev["1"]["result"] == "pass" and "5 คน" in ev["1"]["text"]
    assert ev["2"]["result"] == "pass" and all(x["works"] for x in ev["2"]["rows"])
    assert ev["3"]["result"] == "pending" and "ยังไม่จับคู่กับ HURIS" in ev["3"]["text"]
    assert ev["4"]["rows"] and ev["5"]["result"] == "na" and ev["10"]["result"] == "pass"
    assert d["dates"]["huris"] and d["dates"]["supreme"]
    # US-M4-03
    a = c.put(f"/api/qa/rounds/{rid}/assign/{bsc}", json={"recorders": ["SWU02001"],
              "confirmer": "SWU02002"}, headers=CENTRAL).json()  # fmt: skip
    assert a["kpi"] == {"complete": 1, "incomplete": 0, "confirmed": 0}
    assert c.post(f"/api/qa/rounds/{rid}/assign/notify", headers=CENTRAL).json()["sent"] == 2
    # BR-M4-03: someone outside the round reads only; an evaluator sees assigned curricula only
    assert c.get(f"/api/qa/rounds/{rid}/programs", headers=EV2).json()["items"] == []
    assert [i["curriculum_id"] for i in c.get(f"/api/qa/rounds/{rid}/programs",
            headers=EV).json()["items"]] == [bsc]  # fmt: skip
    assert c.put(f"{url}/notes", json={"notes": {"1": "x"}}, headers=CONF).status_code == 403
    d = c.put(f"{url}/notes", json={"notes": {"1": "ครบ 5 คน", "99": "x"}}, headers=REC).json()
    assert d["status"] == "doing" and d["items"][0]["note"] == "ครบ 5 คน"
    assert c.post(f"{url}/evaluate", json={"results": {}}, headers=EV).status_code == 403
    assert c.post(f"{url}/send", headers=REC).json()["status"] == "sent"
    assert c.put(f"{url}/notes", json={"notes": {}}, headers=REC).status_code == 403, "locked"
    assert c.post(f"{url}/confirm", json={"ok": False}, headers=CONF).status_code == 400
    d = c.post(f"{url}/confirm", json={"ok": False, "note": "เพิ่มหมายเหตุข้อ 4"}, headers=CONF).json()
    assert d["status"] == "doing"
    c.post(f"{url}/send", headers=REC)
    assert c.post(f"{url}/confirm", json={"ok": True}, headers=CONF).json()["status"] == "confirmed"
    assert any(m["kind"] == "qa" and "ev@g.swu.ac.th" in m["to_addrs"]
               for m in Outbox(env["url"], env["schema"]).list())  # fmt: skip
    # US-M4-06: results per item, the final by BR-M4-01, the round locks when all have one
    bad = c.post(f"{url}/evaluate", json={"results": {"5": {"result": "pass"}}}, headers=EV)
    assert bad.status_code == 400, "item 5 does not apply to a bachelor"
    bad = c.post(f"{url}/evaluate", json={"results": {"1": {"result": "x"}}}, headers=EV)
    assert bad.status_code == 400
    applies = [str(i["no"]) for i in d["items"] if i["applies"]]
    d = c.post(f"{url}/evaluate", json={"results": {n: {"result": "pass"} for n in applies[:-1]}},
               headers=EV).json()  # fmt: skip
    assert d["final"] == "pending"
    d = c.post(f"{url}/evaluate", json={"results": {applies[-1]: {"result": "pass", "note": "ok"}}},
               headers=EV).json()  # fmt: skip
    assert d["final"] == "pass" and d["round"]["status"] == "closed", "BR-M4-04"
    s = c.get(f"/api/qa/rounds/{rid}/summary", headers=CENTRAL).json()
    assert s["kpi"] == {"programs": 1, "pass": 1, "fail": 0, "pending": 0}
    assert s["items"][0]["passed"] == s["items"][0]["total"] == 5
    pv = c.get(f"/api/qa/rounds/{rid}/preview", headers=CENTRAL).json()
    assert len(pv) == 1 and pv[0]["complete"]


def test_graduate_items_and_a_failure(env) -> None:
    c, msc = env["c"], env["msc"]
    rid = _round(c, [{"curriculum_id": msc, "set_year": 2558, "evaluators": ["ev@g.swu.ac.th"]}])[
        "id"
    ]
    c.post(f"/api/qa/rounds/{rid}/open", headers=CENTRAL)
    c.put(f"/api/qa/rounds/{rid}/assign/{msc}", json={"recorders": ["SWU02001"],
          "confirmer": "SWU02002"}, headers=CENTRAL)  # fmt: skip
    url = f"/api/qa/rounds/{rid}/programs/{msc}"
    d = c.get(url, headers=REC).json()
    ev = {str(i["no"]): i["evidence"] for i in d["items"]}
    assert ev["1"]["result"] == "pass" and "อย่างน้อย 3" in ev["1"]["text"], "graduate: 3"
    # a responsible teacher of another curriculum too: ไม่ซ้ำหลักสูตรอื่น fails
    secs = c.get(f"/api/curricula/{env['bsc']}/sections", headers=CENTRAL).json()
    s0 = secs["0"]["data"]
    s0["teachers"]["teachers"][0]["pid"] = "SWU04001"
    c.put(f"/api/curricula/{env['bsc']}/sections/0", json={"data": s0}, headers=CENTRAL)
    ev = {str(i["no"]): i["evidence"] for i in c.get(url, headers=REC).json()["items"]}
    assert ev["1"]["result"] == "fail" and "ซ้ำกับหลักสูตรอื่น" in ev["1"]["text"]
    assert ev["5"]["result"] == "pending" and ev["5"]["text"] == NO_THESIS, "FS-6 Q4 ก"
    assert ev["10"]["result"] == "fail", "approved more than 5 years ago"
    assert all(i["applies"] for i in d["items"]) and "สมมติ" in d["items"][0]["detail"]
    c.post(f"{url}/send", headers=REC)
    c.post(f"{url}/confirm", json={"ok": True}, headers=CONF)
    assert c.post(f"{url}/return", json={"note": ""}, headers=EV).status_code == 400
    d = c.post(f"{url}/evaluate", json={"results": {"10": {"result": "fail", "note": "เกิน 5 ปี"}}},
               headers=EV).json()  # fmt: skip
    assert d["final"] == "fail" and d["round"]["status"] == "open"
    d = c.post(f"{url}/return", json={"note": "ขอหลักฐานการปรับปรุง"}, headers=EV).json()
    assert d["status"] == "doing" and d["can_note"] is False and d["roles"] == ["evaluator"]
    s = c.get(f"/api/qa/rounds/{rid}/summary", headers=CENTRAL).json()
    assert s["kpi"]["fail"] == 1
    assert (
        c.get(f"/api/qa/rounds/{rid}/preview?cid={msc}", headers=CENTRAL).json()[0]["complete"]
        is False
    ), "ฉบับร่าง"
