"""tools/ocr_report.py (OCR-3a): the OCR report is regenerated from its data, and the figures
06-nfr.md quotes are the report's, so a new measurement cannot leave either behind."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "ocr_report.py"
spec = importlib.util.spec_from_file_location("ocr_report", TOOL)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_report_is_current() -> None:
    r = subprocess.run([sys.executable, str(TOOL), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _row(nfr: str) -> str:
    text = (ROOT / "docs/brd/06-nfr.md").read_text(encoding="utf-8")
    m = re.search(rf"^\| {nfr} \|.*$", text, re.M)
    assert m, nfr
    return m.group(0)


def test_nfr_rows_quote_the_report() -> None:
    n = report.summary_numbers()
    nfr04, nfr08 = _row("NFR-04"), _row("NFR-08")
    for v in (n["typhoon_same"], n["typhoon_cer"], n["tesseract_cer"]):
        assert v in nfr04, f"NFR-04 should say {v}"
    for v in (f"{n['typhoon_s']} วินาทีต่อหน้า", f"สูงสุด {n['typhoon_max_s']}", f"{n['book_s']} วินาที",
              f"Tesseract อย่างเดียว {n['tesseract_s']}"):  # fmt: skip
        assert v in nfr08, f"NFR-08 should say {v}"


def test_every_listed_misread_has_a_check() -> None:
    """NFR-04 says the system points at every misread found; the data must back that."""
    errs = report.load("errors.json")["errors"]
    assert errs and all(e["caught_by"] for e in errs)
    assert {c for e in errs for c in e["caught_by"]} <= set(report.CHECKS)
