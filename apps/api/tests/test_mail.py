"""E-mail outbox: queued rows instead of sending, de-duplication, `ocl outbox`."""

from __future__ import annotations

import pytest

from ocl_api.db import migrate
from ocl_api.mail import Outbox


def test_outbox_queues_and_never_sends(pg_url: str, schema: str) -> None:
    migrate(pg_url, schema)
    box = Outbox(pg_url, schema)
    m = box.send(
        ["Dean@g.swu.ac.th", "dean@g.swu.ac.th", "cur@g.swu.ac.th"],
        " มีคู่มือหลักสูตรรอตรวจ ",
        "เนื้อความ",
        kind="workflow",
        by="central@g.swu.ac.th",
        ref="curriculum:7",
    )
    assert m["to_addrs"] == ["dean@g.swu.ac.th", "cur@g.swu.ac.th"], "lower-cased, no repeats"
    assert m["status"] == "queued" and m["sent_at"] is None and m["subject"] == "มีคู่มือหลักสูตรรอตรวจ"
    assert box.get(m["id"])["ref"] == "curriculum:7"

    # a reminder may go once per key (US-M5-03: once a day per item)
    key = "R01:plan:42:2026-10-29"
    assert box.send("t@g.swu.ac.th", "เตือน", "ยังไม่ส่งแผน", kind="reminder", dedupe_key=key)
    assert box.send("t@g.swu.ac.th", "เตือน", "ยังไม่ส่งแผน", kind="reminder", dedupe_key=key) is None

    for to in ([], "not-an-address", ["ok@x.th", "bad@"]):
        with pytest.raises(ValueError):
            box.send(to, "s", "b", kind="test")
    with pytest.raises(ValueError):
        box.send("ok@x.th", " ", "b", kind="test")

    rows = box.list()
    assert [r["kind"] for r in rows] == ["reminder", "workflow"], "newest first"
    assert box.list(status="sent") == [] and len(box.list(limit=1)) == 1


def test_outbox_command(pg_url: str, schema: str, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from ocl_api.cli import main

    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    assert main(["outbox", "test"]) == 1
    assert main(["outbox", "test", "--to", "bad"]) == 1
    assert "ไม่ถูกต้อง" in capsys.readouterr().out
    assert main(["outbox", "test", "--to", "pm@sample.invalid"]) == 0
    assert '"status": "queued"' in capsys.readouterr().out
    assert main(["outbox", "list"]) == 0
    out = capsys.readouterr().out
    assert "queued" in out and "pm@sample.invalid" in out
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today_bkk = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d")
    assert today_bkk in out, "listed in Thai time"
    assert main(["outbox", "show", "--id", "1"]) == 0
    assert main(["outbox", "show", "--id", "999"]) == 1
