"""JobStore backed by Postgres for job state, parts, edits, checks and the final draft.

Files keep their place: the uploaded book, ingest output, extracted JSON written by the
pipeline and every Markdown stay under DATA_DIR/imports/<id>/ exactly as in file mode.
After extraction the worker copies the part JSON into `import_parts` so the database is
the system of record for review; edits and their history never touch edits/*.json here.
"""

from __future__ import annotations

import contextlib
import json
import secrets
from pathlib import Path
from typing import Any

import psycopg

from ocl_api.db import Jsonb, connect
from ocl_api.jobs import PARTS, JobStore, _changed_fields, now_iso, safe_filename


class PgJobStore(JobStore):
    def __init__(self, root: str | Path, url: str, schema: str | None = None):
        super().__init__(root)
        self.url = url
        self.schema = schema
        self._c: psycopg.Connection[dict[str, Any]] | None = None

    def _conn(self):
        """One connection per store instance (per API request / per worker process):
        a remote database such as Neon costs ~0.3 s per connect, and a job walks
        through dozens of status writes. Reconnects once when the server dropped it."""
        if self._c is None or self._c.closed:
            self._c = connect(self.url, self.schema)
        else:
            try:
                self._c.execute("SELECT 1")
            except psycopg.OperationalError:
                self._c = connect(self.url, self.schema)
        return contextlib.nullcontext(self._c)

    def close(self) -> None:
        if self._c is not None and not self._c.closed:
            self._c.close()
        self._c = None

    # ---------- job rows ----------

    def dir(self, job_id: str) -> Path:
        if not JobStore._valid_id(job_id):
            raise KeyError(job_id)
        with self._conn() as conn:
            if (
                conn.execute("SELECT 1 FROM import_jobs WHERE id = %s", (job_id,)).fetchone()
                is None
            ):
                raise KeyError(job_id)
        d = self.root / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def read(self, job_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute("SELECT data FROM import_jobs WHERE id = %s", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return row["data"]

    def write(self, job: dict[str, Any]) -> None:
        job["updated_at"] = now_iso()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO import_jobs (id, status, data, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE
                    SET status = EXCLUDED.status, data = EXCLUDED.data, updated_at = now()
                """,
                (job["id"], job["status"], Jsonb(job)),
            )

    def create(self, filename: str, data: bytes, *, provider: str, target: str | None) -> dict:
        job_id = secrets.token_hex(6)
        d = self.root / job_id
        d.mkdir(parents=True)
        fname = safe_filename(filename)
        ext = Path(fname).suffix.lower() or ".bin"
        (d / f"source{ext}").write_bytes(data)
        job = self._new_job(job_id, fname, f"source{ext}", len(data), provider, target)
        self.write(job)
        return job

    def list(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT data FROM import_jobs ORDER BY created_at DESC").fetchall()
        return [r["data"] for r in rows]

    def next_queued(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM import_jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
        return row["data"] if row else None

    # ---------- parts ----------

    def sync_parts_from_files(self, job_id: str, parts: list[str] | None = None) -> None:
        """Copy the pipeline's extract/<part>.json and checks.json into the database."""
        job = self.read(job_id)
        d = self.dir(job_id)
        with self._conn() as conn:
            for key in parts or job.get("parts", PARTS):
                p = d / "extract" / f"{key}.json"
                if not p.exists():
                    continue
                ex = json.loads(p.read_text(encoding="utf-8"))
                conn.execute(
                    """
                    INSERT INTO import_parts (job_id, key, extracted, notes, llm)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (job_id, key) DO UPDATE
                        SET extracted = EXCLUDED.extracted, notes = EXCLUDED.notes,
                            llm = EXCLUDED.llm, updated_at = now()
                    """,
                    (
                        job_id,
                        key,
                        Jsonb(ex["data"]),
                        Jsonb(ex.get("notes", [])),
                        Jsonb(ex.get("llm")),
                    ),
                )
            cp = d / "extract" / "checks.json"
            if cp.exists():
                conn.execute(
                    """
                    INSERT INTO import_checks (job_id, extracted) VALUES (%s, %s)
                    ON CONFLICT (job_id) DO UPDATE SET extracted = EXCLUDED.extracted
                    """,
                    (job_id, Jsonb(json.loads(cp.read_text(encoding="utf-8")))),
                )

    def read_part(self, job_id: str, key: str) -> dict[str, Any] | None:
        self.part_path(job_id, key)  # validates the key
        with self._conn() as conn:
            row = conn.execute(
                "SELECT extracted, notes, llm, edited, history, confirmed_at "
                "FROM import_parts WHERE job_id = %s AND key = %s",
                (job_id, key),
            ).fetchone()
        if row is None or row["extracted"] is None:
            return None
        edited = row["edited"]
        return {
            "part": key,
            "data": edited if edited is not None else row["extracted"],
            "extracted": row["extracted"],
            "notes": row["notes"] or [],
            "llm": row["llm"],
            "edited": edited is not None,
            "edit_count": len(row["history"] or []),
            "confirmed": row["confirmed_at"] is not None,
            "confirmed_at": row["confirmed_at"].isoformat(timespec="seconds")
            if row["confirmed_at"]
            else None,
        }

    def save_part(
        self, job_id: str, key: str, data: dict[str, Any], *, confirm: bool, by: str = ""
    ) -> dict:
        self.part_path(job_id, key)
        current = self.read_part(job_id, key)
        before = current["data"] if current else None
        entry = {
            "ts": now_iso(),
            "by": by,
            "confirm": confirm,
            "changed": _changed_fields(before, data),
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO import_parts (job_id, key, edited, history, confirmed_at)
                VALUES (%s, %s, %s, %s, CASE WHEN %s THEN now() END)
                ON CONFLICT (job_id, key) DO UPDATE
                    SET edited = EXCLUDED.edited,
                        history = import_parts.history || EXCLUDED.history,
                        confirmed_at = CASE WHEN %s THEN now() ELSE NULL END,
                        updated_at = now()
                """,
                (job_id, key, Jsonb(data), Jsonb([entry]), confirm, confirm),
            )
        job = self.read(job_id)
        if confirm:
            job["confirmed"][key] = now_iso()
        else:
            job["confirmed"].pop(key, None)
        self.write(job)
        self.recompute(job_id)
        return self.read_part(job_id, key) or {}

    # ---------- checks ----------

    def _write_checks(self, job_id: str, checks: list[dict[str, Any]]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO import_checks (job_id, recomputed, recomputed_at)
                VALUES (%s, %s, now())
                ON CONFLICT (job_id) DO UPDATE
                    SET recomputed = EXCLUDED.recomputed, recomputed_at = now()
                """,
                (job_id, Jsonb(checks)),
            )

    def checks(self, job_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT extracted, recomputed FROM import_checks WHERE job_id = %s", (job_id,)
            ).fetchone()
        if row is None:
            return []
        return row["recomputed"] if row["recomputed"] is not None else row["extracted"]

    # ---------- finalize ----------

    def finalize(self, job_id: str) -> dict[str, Any]:
        job = super().finalize(job_id)
        snapshot = {}
        for key in job.get("parts", PARTS):
            part = self.read_part(job_id, key)
            if part:
                snapshot[key] = {
                    "data": part["data"],
                    "confirmed_at": part["confirmed_at"],
                    "edited": part["edited"],
                }
        iv = ((snapshot.get("info") or {}).get("data") or {}).get("values") or {}
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO curriculum_drafts
                    (job_id, program_code, name_th, level, start_year, data)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    iv.get("program_code"),
                    iv.get("name_th"),
                    iv.get("level"),
                    iv.get("start_year"),
                    Jsonb({"job": job, "parts": snapshot, "checks": self.checks(job_id)}),
                ),
            )
        return job
