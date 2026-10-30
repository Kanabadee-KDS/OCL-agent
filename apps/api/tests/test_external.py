"""External systems (SUPREME / HURIS): sample adapter, local copies, API and `ocl seed`."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocl_api.auth import sign_token
from ocl_api.external import ExternalStore, Snapshot
from ocl_api.external.base import COLUMNS, SYSTEMS
from ocl_api.external.sample import SampleAdapter
from ocl_api.external.signature import SampleSigner

SECRET = "ext-secret"
TODAY = date(2026, 10, 29)


def test_sample_is_fixed_complete_and_made_up() -> None:
    a, b = SampleAdapter(TODAY), SampleAdapter(TODAY)
    for system in SYSTEMS:
        snap = a.fetch(system)
        assert snap == b.fetch(system), "same input, same rows"
        assert snap.as_of == date(2026, 10, 28), "Data Warehouse lags one day"
        assert set(snap.rows) == set(SYSTEMS[system]["tables"])
        for table, rows in snap.rows.items():
            assert rows and all(set(r) == set(COLUMNS[table]) for r in rows), table
    staff = a.fetch("huris").rows["ext_staff"]
    sup = a.fetch("supreme").rows
    assert len(staff) == 48 and len({s["pid"] for s in staff}) == 48
    assert all(s["name_th"].startswith("[") and s["email"].endswith(".invalid") for s in staff)
    assert all(st["name_th"].startswith("[นิสิต") for st in sup["ext_students"])
    programs = {p["code"]: p for p in sup["ext_programs"]}
    assert len(programs) == len(sup["ext_programs"]) == 42
    keys = [(s["term"], s["course_code"], s["section"]) for s in sup["ext_sections"]]
    assert len(keys) == len(set(keys))
    by_pid = {s["pid"]: s for s in staff}
    for sec in sup["ext_sections"]:
        fac = programs[sec["program_code"]]["faculty"]
        assert sec["teachers"] and all(by_pid[t]["faculty"] == fac for t in sec["teachers"])
    assert len({s["sid"] for s in sup["ext_students"]}) == len(sup["ext_students"]) == 1020
    # FS-5 Q1 ก: each section's roster is as large as its `enrolled`, from its programme
    students = {s["sid"]: s for s in sup["ext_students"]}
    for sec in sup["ext_sections"]:
        roster = [e["sid"] for e in sup["ext_enrollments"]
                  if (e["course_code"], e["section"]) == (sec["course_code"], sec["section"])]  # fmt: skip
        assert len(roster) == sec["enrolled"] > 0
        assert all(students[x]["program_code"] == sec["program_code"] for x in roster)
    grads = [s for s in sup["ext_students"] if s["graduated"]]
    assert grads and all(s["advisor_pid"] in by_pid for s in sup["ext_students"])
    with pytest.raises(ValueError):
        a.fetch("nope")


def test_sample_signer_marks_itself() -> None:
    sig = SampleSigner().sign(b"pdf bytes", "S01")
    assert sig["sample"] is True and sig["signer_id"] == "S01" and len(sig["sha256"]) == 64


class _Feed:
    """A stand-in for a real feed: one staff row, adapter name not 'sample'."""

    name = "datawarehouse"

    def fetch(self, system: str) -> Snapshot:
        row = dict.fromkeys(COLUMNS["ext_staff"]) | {"pid": "SWU99999", "name_th": "จริง"}
        return Snapshot({"ext_staff": [row | {"education": [], "works": []}]}, TODAY)


def test_store_replaces_a_whole_system(pg_url: str, schema: str) -> None:
    from ocl_api.db import migrate

    migrate(pg_url, schema)
    store = ExternalStore(pg_url, schema)
    assert [s["adapter"] for s in store.status()] == [None, None]
    first = store.load(SampleAdapter(TODAY), "supreme")
    assert store.load(SampleAdapter(TODAY), "supreme") == first, "seeding twice adds nothing"
    store.load(SampleAdapter(TODAY), "huris")
    src = store.source("huris")
    assert src["sample"] and src["as_of"] == "2026-10-28" and src["counts"] == {"ext_staff": 48}
    found = store.staff("ชื่อ นามสกุล 7")
    assert [s["pid"] for s in found["items"]] == ["SWU02001"] and found["source"]["sample"]
    assert store.staff("ชื่อนามสกุล7")["items"][0]["pid"] == "SWU02001", "spaces ignored"
    assert store.staff("", faculty="คณะวิทยาศาสตร์", limit=100)["items"][0]["pid"] == "SWU03001"
    store.load(_Feed(), "huris")
    assert store.staff("")["items"][0]["name_th"] == "จริง" and not store.source("huris")["sample"]
    with pytest.raises(ValueError):
        store.load(SampleAdapter(TODAY), "nope")


def test_api_and_seed_command(
    pg_url: str, schema: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from ocl_api.cli import main
    from ocl_api.main import create_app
    from ocl_api.users import UserStore

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    c = TestClient(create_app())
    users = UserStore(pg_url, schema)
    users.upsert("cur@g.swu.ac.th", roles=["curator"])
    users.upsert("t@g.swu.ac.th", roles=["teacher"])

    def h(sub: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {sign_token(SECRET, sub=sub, roles=[])}"}

    assert c.get("/api/external/status").status_code == 401
    assert c.get("/api/external/status", headers=h("t@g.swu.ac.th")).json()[0]["adapter"] is None

    assert main(["seed", "sample"]) == 0
    assert '"sample": true' in capsys.readouterr().out
    st = c.get("/api/external/status", headers=h("t@g.swu.ac.th")).json()
    assert [s["system"] for s in st] == ["huris", "supreme"] and all(s["sample"] for s in st)
    assert st[1]["counts"]["ext_programs"] == 42

    assert c.get("/api/external/staff", headers=h("t@g.swu.ac.th")).status_code == 403
    r = c.get("/api/external/staff?q=SWU01&limit=3", headers=h("cur@g.swu.ac.th")).json()
    assert len(r["items"]) == 3 and r["source"]["adapter_label"] == "ข้อมูลตัวอย่าง"

    # a real feed is never overwritten by the sample unless asked
    ExternalStore(pg_url, schema).load(_Feed(), "huris")
    main(["seed", "sample", "--system", "huris"])
    assert "not replaced" in capsys.readouterr().out
    assert not ExternalStore(pg_url, schema).source("huris")["sample"]
    main(["seed", "sample", "--system", "huris", "--replace-real"])
    assert ExternalStore(pg_url, schema).source("huris")["sample"]
