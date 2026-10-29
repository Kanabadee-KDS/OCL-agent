"""Local copies of the external systems in Postgres (`ext_*`, migration 004)."""

from __future__ import annotations

from typing import Any

from ocl_api.db import Jsonb, connect
from ocl_api.external.base import ADAPTER_LABELS, COLUMNS, JSONB, SYSTEMS, Adapter


def _source(r: dict[str, Any] | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "system": r["system"],
        "label": SYSTEMS.get(r["system"], {}).get("label", r["system"]),
        "adapter": r["adapter"],
        "adapter_label": ADAPTER_LABELS.get(r["adapter"], r["adapter"]),
        "sample": r["adapter"] == "sample",
        "synced_at": r["synced_at"].isoformat(timespec="seconds"),
        "as_of": r["as_of"].isoformat() if r["as_of"] else None,
        "counts": r["counts"],
    }


class ExternalStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema

    def _conn(self):
        return connect(self.url, self.schema)

    def load(self, adapter: Adapter, system: str) -> dict[str, int]:
        """Replace everything one system supplies with what the adapter returns, atomically."""
        if system not in SYSTEMS:
            raise ValueError(f"ไม่รู้จักระบบ {system} (มี {', '.join(SYSTEMS)})")
        snap = adapter.fetch(system)
        tables = SYSTEMS[system]["tables"]
        counts: dict[str, int] = {}
        with self._conn() as conn, conn.transaction():
            for t in tables:
                cols = COLUMNS[t]
                conn.execute(f"DELETE FROM {t}")
                rows = [
                    tuple(Jsonb(r.get(c)) if c in JSONB else r.get(c) for c in cols)
                    for r in snap.rows.get(t, [])
                ]
                if rows:
                    marks = ", ".join(["%s"] * len(cols))
                    with conn.cursor() as cur:
                        cur.executemany(
                            f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({marks})", rows
                        )
                counts[t] = len(rows)
            conn.execute(
                "INSERT INTO ext_sources (system, adapter, synced_at, as_of, counts) "
                "VALUES (%s, %s, now(), %s, %s) ON CONFLICT (system) DO UPDATE SET "
                "adapter = EXCLUDED.adapter, synced_at = EXCLUDED.synced_at, "
                "as_of = EXCLUDED.as_of, counts = EXCLUDED.counts",
                (system, adapter.name, snap.as_of, Jsonb(counts)),
            )
        return counts

    def status(self) -> list[dict[str, Any]]:
        """Every known system, loaded or not."""
        with self._conn() as conn:
            got = {r["system"]: r for r in conn.execute("SELECT * FROM ext_sources")}
        return [
            _source(got.get(s)) or {"system": s, "label": v["label"], "adapter": None}
            for s, v in SYSTEMS.items()
        ]

    def source(self, system: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            r = conn.execute("SELECT * FROM ext_sources WHERE system = %s", (system,)).fetchone()
        return _source(r)

    def staff(self, q: str = "", faculty: str = "", limit: int = 20) -> dict[str, Any]:
        """HURIS staff by name, Buasri-style id or e-mail (spaces ignored), for pickers."""
        needle = "%" + "".join(q.split()).lower() + "%"
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ext_staff WHERE "
                "(lower(replace(concat_ws(' ', name_th, name_en, pid, email), ' ', '')) "
                "LIKE %s) AND (%s = '' OR faculty = %s) ORDER BY pid LIMIT %s",
                (needle, faculty, faculty, limit),
            ).fetchall()
        return {"items": rows, "source": self.source("huris")}
