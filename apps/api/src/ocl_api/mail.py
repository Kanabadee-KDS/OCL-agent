"""E-mail outbox (migration 005).

Notifications (approval steps, report reminders, sign-in codes for external evaluators) are
written to `email_outbox` with status `queued`. No mail server is agreed yet, so nothing is
sent: a sender added later takes queued rows and marks them `sent` or `failed`. Until then
the outbox is also the record of who would have been told what (`ocl outbox list`).
"""

from __future__ import annotations

import re
from typing import Any

import psycopg

from ocl_api.db import Jsonb, connect

ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COLUMNS = (
    "id, created_at, created_by, kind, ref, to_addrs, subject, body, dedupe_key, status, "
    "sent_at, error"
)


def _row(r: dict[str, Any] | None) -> dict[str, Any] | None:
    if r is None:
        return None
    out = dict(r)
    for k in ("created_at", "sent_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat(timespec="seconds")
    return out


class Outbox:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema

    def _conn(self):
        return connect(self.url, self.schema)

    def send(
        self,
        to: str | list[str],
        subject: str,
        body: str,
        *,
        kind: str,
        by: str | None = None,
        ref: str | None = None,
        dedupe_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Queue one message to all `to`; None when `dedupe_key` was queued before."""
        addrs = list(
            dict.fromkeys(a.strip().lower() for a in ([to] if isinstance(to, str) else to))
        )
        bad = [a for a in addrs if not ADDRESS.match(a)]
        if not addrs or bad:
            raise ValueError(f"อีเมลผู้รับไม่ถูกต้อง: {', '.join(bad) or '(ว่าง)'}")
        if not subject.strip() or not body.strip():
            raise ValueError("ต้องมีหัวเรื่องและเนื้อความ")
        with self._conn() as conn:
            try:
                r = conn.execute(
                    "INSERT INTO email_outbox (created_by, kind, ref, to_addrs, subject, body, "
                    f"dedupe_key) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING {COLUMNS}",
                    (by, kind, ref, Jsonb(addrs), subject.strip(), body, dedupe_key),
                ).fetchone()
            except psycopg.errors.UniqueViolation:
                return None
        return _row(r)

    def list(self, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {COLUMNS} FROM email_outbox WHERE (%s::text IS NULL OR status = %s) "
                "ORDER BY id DESC LIMIT %s",
                (status, status, limit),
            ).fetchall()
        return [_row(r) for r in rows]

    def get(self, id: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            return _row(
                conn.execute(f"SELECT {COLUMNS} FROM email_outbox WHERE id = %s", (id,)).fetchone()
            )
