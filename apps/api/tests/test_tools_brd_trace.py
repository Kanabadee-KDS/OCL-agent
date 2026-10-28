"""tools/brd_trace.py: user stories, their pages and AC are read the way the BRD writes them."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools" / "brd_trace.py"
spec = importlib.util.spec_from_file_location("brd_trace", TOOL)
trace = importlib.util.module_from_spec(spec)
sys.modules["brd_trace"] = trace  # @dataclass looks its module up while the file runs
spec.loader.exec_module(trace)

BRD = """# 01 M1

### 3.1 แดชบอร์ดหลักสูตร [mock: dash-cur]

- **US-M1-01** ในฐานะผู้ดูแล ฉันต้องการเห็นจำนวนหลักสูตร
  - AC: KPI 4 ค่า
- **US-M1-02** ฉันต้องการแท็บ "วิเคราะห์เชิงสถิติ" `[รายละเอียดยังไม่เห็นใน mock — ถาม]`

### 3.2 อื่น ๆ

- **US-M1-03** ฉันต้องการรายการ [mock: cur, cur-edit]
  - รายละเอียดเพิ่ม
  - AC: ค้นหาได้
  - AC: กรองได้
"""


def test_stories_take_pages_from_heading_or_inline(tmp_path):
    f = tmp_path / "01-m1.md"
    f.write_text(BRD, encoding="utf-8")
    s = {x.id: x for x in trace.parse_stories([f])}
    assert s["US-M1-01"].pages == ["dash-cur"] and s["US-M1-01"].ac == 1
    assert s["US-M1-02"].ac == 0 and s["US-M1-02"].open_q
    # inline [mock: ...] wins over a heading without one; every AC line counts
    assert s["US-M1-03"].pages == ["cur", "cur-edit"] and s["US-M1-03"].ac == 2


def test_test_ids_collapse_to_ranges():
    assert trace.ranges(["K-03", "K-01", "K-02", "B-04", "B-06"]) == "B-04 · B-06 · K-01–K-03"


def test_nfr_rows_name_their_test_cases(tmp_path):
    f = tmp_path / "06-nfr.md"
    f.write_text(
        "| รหัส | requirement | เกณฑ์ | วิธีวัด | ผล | กรณีทดสอบ |\n|---|---|---|---|---|---|\n"
        "| NFR-01 | ไม่สร้างรหัส | 0 **[ยืนยันแล้ว]** | นับ | 0 | M-01–M-03 · G-05 |\n"
        "| NFR-02 | เวลา | ≤ 5 นาที **[เสนอ]** | จับเวลา | 1 นาที | – |\n",
        encoding="utf-8",
    )
    a, b = trace.parse_nfrs(f)
    assert (a.id, a.proposed, a.tests) == ("NFR-01", False, ["M-01", "M-02", "M-03", "G-05"])
    assert (b.id, b.proposed, b.tests) == ("NFR-02", True, [])


def test_every_test_category_is_mapped():
    cats = {tc.split("-")[0] for tc, _ in trace.test_cases(trace.TESTS)}
    assert cats <= set(trace.TEST_MAP), cats - set(trace.TEST_MAP)


@pytest.mark.skipif(not trace.MOCK.exists(), reason="samples/ui-mock.html is not in git")
def test_traceability_file_is_current():
    r = subprocess.run([sys.executable, str(TOOL), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
