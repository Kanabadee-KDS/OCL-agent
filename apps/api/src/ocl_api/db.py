"""Postgres access (psycopg 3) and the schema migrations, used when DATABASE_URL is set.

Dev points at a Neon project (pooled URL, sslmode=require); prod at the `db` service of
the compose stack. Heavy artefacts (the uploaded book, ingest output, Markdown, page
images) stay on the DATA_DIR volume; the database holds what the main system needs to
query: jobs, each part's extracted and edited data with its history, the checks, and the
curriculum draft a finalised job produces. Plain SQL, no ORM: five tables are not worth
a dependency the team would have to learn.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_import_jobs",
        """
        CREATE TABLE IF NOT EXISTS import_jobs (
            id          text PRIMARY KEY,
            status      text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            data        jsonb NOT NULL
        );
        CREATE INDEX IF NOT EXISTS import_jobs_status_idx ON import_jobs (status, created_at);

        CREATE TABLE IF NOT EXISTS import_parts (
            job_id       text NOT NULL REFERENCES import_jobs (id) ON DELETE CASCADE,
            key          text NOT NULL,
            extracted    jsonb,
            notes        jsonb NOT NULL DEFAULT '[]'::jsonb,
            llm          jsonb,
            edited       jsonb,
            history      jsonb NOT NULL DEFAULT '[]'::jsonb,
            confirmed_at timestamptz,
            updated_at   timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (job_id, key)
        );

        CREATE TABLE IF NOT EXISTS import_checks (
            job_id        text PRIMARY KEY REFERENCES import_jobs (id) ON DELETE CASCADE,
            extracted     jsonb NOT NULL DEFAULT '[]'::jsonb,
            recomputed    jsonb,
            recomputed_at timestamptz
        );

        CREATE TABLE IF NOT EXISTS curriculum_drafts (
            id           bigserial PRIMARY KEY,
            job_id       text NOT NULL REFERENCES import_jobs (id) ON DELETE CASCADE,
            program_code text,
            name_th      text,
            level        text,
            start_year   integer,
            finalized_at timestamptz NOT NULL DEFAULT now(),
            data         jsonb NOT NULL
        );
        CREATE INDEX IF NOT EXISTS curriculum_drafts_job_idx ON curriculum_drafts (job_id);
        """,
    ),
    (
        "002_users",
        """
        CREATE TABLE IF NOT EXISTS users (
            email         text PRIMARY KEY,
            name          text NOT NULL DEFAULT '',
            buasri_id     text UNIQUE,
            roles         jsonb NOT NULL DEFAULT '[]'::jsonb,
            password_hash text,
            active        boolean NOT NULL DEFAULT true,
            unit          text,
            created_at    timestamptz NOT NULL DEFAULT now(),
            last_login_at timestamptz
        );
        """,
    ),
]


def connect(url: str, schema: str | None = None) -> psycopg.Connection[dict[str, Any]]:
    """Autocommit connection; `schema` (tests) puts every table into its own namespace."""
    kwargs: dict[str, Any] = {"row_factory": dict_row, "autocommit": True}
    if schema:
        kwargs["options"] = f"-c search_path={schema},public"
    conn = psycopg.connect(url, **kwargs)
    if schema:
        # a pooled endpoint (PgBouncer) may drop the `options` startup parameter, so the
        # search_path is set again on the session
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        conn.execute(f'SET search_path TO "{schema}", public')
    return conn


def migrate(url: str, schema: str | None = None) -> list[str]:
    """Apply the migrations that are not yet recorded; returns the names applied."""
    applied: list[str] = []
    with connect(url, schema) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()}
        for name, sql in MIGRATIONS:
            if name in done:
                continue
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (name,))
            applied.append(name)
    return applied


def status(url: str, schema: str | None = None) -> dict[str, Any]:
    with connect(url, schema) as conn:
        ver = conn.execute("SELECT version()").fetchone()
        try:
            mig = [r["name"] for r in conn.execute("SELECT name FROM schema_migrations ORDER BY 1")]
            jobs = conn.execute("SELECT count(*) AS n FROM import_jobs").fetchone()
        except psycopg.errors.UndefinedTable:
            mig, jobs = [], {"n": 0}
        return {
            "server": (ver or {}).get("version"),
            "migrations": mig,
            "pending": [n for n, _ in MIGRATIONS if n not in mig],
            "jobs": (jobs or {}).get("n", 0),
        }


def drop_schema(url: str, schema: str) -> None:
    """Tests only: remove a throw-away schema."""
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


__all__ = ["Jsonb", "connect", "drop_schema", "migrate", "status"]
