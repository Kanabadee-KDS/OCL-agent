"""tools/test_round.py: the next round holds every case without a usable team result, and the
round file is regenerated from the answer key and the results, never edited by hand."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "test_round.py"
spec = importlib.util.spec_from_file_location("test_round", TOOL)
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)

ROW = {f: f"text of {f}" for f in tr.FIELDS}


def test_round_file_is_current() -> None:
    r = subprocess.run([sys.executable, str(TOOL), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_pass_on_the_same_row_stays_out() -> None:
    res = {"round": "R1-2", "status": "ผ่าน", "row": tr.fingerprint(ROW)}
    assert tr.reason(ROW, res) is None


def test_a_pass_on_an_older_row_comes_back_and_names_what_changed() -> None:
    res = {"round": "R1-2", "status": "ผ่าน", "row": tr.fingerprint(ROW)}
    new = {**ROW, "ผลที่คาดหวัง": "something else"}
    assert tr.reason(new, res) == "ผ่านในรอบ R1-2 แต่ผลที่คาดหวังเปลี่ยนหลังทดสอบ · ทดสอบกับสคริปต์ใหม่"


def test_a_pass_whose_code_changed_comes_back_as_a_retest() -> None:
    res = {"round": "R1", "status": "ผ่าน", "row": tr.fingerprint(ROW), "retest": "หน้าตรวจ"}
    assert tr.reason(ROW, res) == "ผ่านในรอบ R1 แต่โค้ดเปลี่ยนหลังทดสอบ: หน้าตรวจ · ทดสอบซ้ำ"


def test_no_result_failed_and_untested_cases_come_back() -> None:
    row = tr.fingerprint(ROW)
    assert tr.reason(ROW, None) == "ใหม่ · ยังไม่เคยทดสอบ"
    for status in ("ไม่ผ่าน", "ไม่ได้ทดสอบ", "ไม่มีในไฟล์ผล", "ผ่านแต่ไม่มีผลจริง"):
        assert tr.reason(ROW, {"round": "R1-2", "status": status, "row": row})


def test_results_name_real_cases_once() -> None:
    _, rows = tr.load_script()
    ids = {r["TC_ID"] for r in rows}
    cases = [e["case"] for e in tr.load_results().values()]
    raw = (ROOT / "docs/testing/results_ocl.json").read_text(encoding="utf-8")
    assert raw.count('"case"') == len(cases), "a case is listed twice"
    assert set(cases) <= ids, sorted(set(cases) - ids)
    for e in tr.load_results().values():
        assert len(e["row"].split()) == len(tr.FIELDS), e["case"]


def test_every_case_is_either_in_the_round_or_passed_on_its_current_row() -> None:
    _, rows = tr.load_script()
    results = tr.load_results()
    inside = set(tr.round_cases())
    for r in rows:
        if r["TC_ID"] == "EX-00" or r["TC_ID"] in inside:
            continue
        res = results[r["TC_ID"]]
        assert res["status"] == "ผ่าน" and res["row"] == tr.fingerprint(r), r["TC_ID"]
        assert not res.get("retest"), r["TC_ID"]
