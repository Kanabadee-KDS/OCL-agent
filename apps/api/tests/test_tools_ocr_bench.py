"""tools/ocr_bench.py (OCR-0): CER is fair to both engines, the shared-server rules hold, and a
run against a stand-in Ollama writes the per-page outputs and the summary."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools" / "ocr_bench.py"
spec = importlib.util.spec_from_file_location("ocr_bench", TOOL)
bench = importlib.util.module_from_spec(spec)
sys.modules["ocr_bench"] = bench
spec.loader.exec_module(bench)


def test_typhoon_markdown_and_plain_text_compare_equal() -> None:
    truth = "หมวดที่ 1 ข้อมูลทั่วไป\nรหัสหลักสูตร  25290091100204\nสารบัญ ........ 92\nหน่วยกิต 3 "
    md = (
        "```markdown\n# หมวดที่ 1 ข้อมูลทั่วไป\n\n<table><tr><td>รหัสหลักสูตร</td>"
        "<td>25290091100204</td></tr></table>\n\n**สารบัญ** … 92\n\nหน่วยกิต 3\n"
        "<figure>ภาพตราสัญลักษณ์มหาวิทยาลัย</figure>\n<page_number></page_number>\n```"
    )
    assert bench.cer(truth, bench.md_to_text(md))[0] == 0.0
    assert bench.normalise("กํา") == bench.normalise("กำ"), "nikhahit + aa is sara am"
    assert bench.cer("", "anything") == (None, 0, 0)
    assert bench.edit_distance("kitten", "sitting") == 3
    rate, edits, n = bench.cer("abcd", "abxd e")
    assert (edits, n) == (2, 4) and rate == 0.5


def test_shared_server_rules() -> None:
    at = lambda h, m: dt.datetime(2026, 10, 30, h, m, tzinfo=bench.TH)  # noqa: E731
    assert bench.in_quiet_hours(at(3, 0)) and bench.in_quiet_hours(at(2, 30))
    assert not bench.in_quiet_hours(at(2, 29)) and not bench.in_quiet_hours(at(4, 0))
    assert bench.main(["--scan", "x.pdf", "--out", "o", "--model", "gemma4:12b"]) == 2
    assert bench.parse_pages("1-3,7", 5) == [0, 1, 2]
    assert bench.parse_pages(None, 3) == [0, 1, 2]


@pytest.fixture
def fake_ollama():
    seen: list[dict] = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._send(
                {"models": [{"name": "gemma4:12b", "expires_at": "2319-02-09T13:57:18+07:00"}]}
            )

        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self._send({"message": {"content": "## Hello OCR 123"}, "eval_count": 9,
                        "prompt_eval_count": 2900, "load_duration": 1.5e9, "done_reason": "stop"})  # fmt: skip

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", seen
    srv.shutdown()


def test_run_against_a_stand_in_ollama(tmp_path: Path, fake_ollama, monkeypatch) -> None:
    import pymupdf

    url, seen = fake_ollama
    truth = pymupdf.open()
    truth.new_page().insert_text((72, 100), "Hello OCR 123", fontsize=24)
    truth.save(tmp_path / "truth.pdf")
    scan = pymupdf.open()  # the same page as an image only, like a scanner makes it
    pix = truth[0].get_pixmap(dpi=100)
    scan.new_page(width=truth[0].rect.width, height=truth[0].rect.height).insert_image(
        truth[0].rect, pixmap=pix
    )
    scan.save(tmp_path / "scan.pdf")
    monkeypatch.setattr(bench, "in_quiet_hours", lambda now=None: False)
    out = tmp_path / "out"
    rc = bench.main(["--scan", str(tmp_path / "scan.pdf"), "--truth", str(tmp_path / "truth.pdf"),
                     "--engines", "typhoon", "--base-url", url, "--out", str(out)])  # fmt: skip
    assert rc == 0
    body = seen[0]
    assert body["keep_alive"] == "10m" and body["options"]["num_ctx"] == bench.NUM_CTX
    assert body["model"] == bench.DEFAULT_MODEL and body["options"]["temperature"] == 0.1
    assert body["messages"][0]["content"] == bench.PROMPT_V15 and body["messages"][0]["images"]
    r = json.loads((out / "results.json").read_text(encoding="utf-8"))
    page = r["pages"][0]
    assert page["typhoon_cer"] == 0.0 and page["typhoon_prompt_tokens"] == 2900
    assert r["ps_before"][0]["expires_at"].startswith("2319"), "/api/ps is recorded"
    assert (out / "page-01.typhoon.md").read_text(encoding="utf-8") == "## Hello OCR 123"
    assert "CER รวม 0.0%" in (out / "summary.md").read_text(encoding="utf-8")
