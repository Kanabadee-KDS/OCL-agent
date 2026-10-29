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
    (
        "003_curriculum_workflow",
        """
        DELETE FROM curriculum_drafts a USING curriculum_drafts b
            WHERE a.job_id = b.job_id AND a.id < b.id;
        CREATE UNIQUE INDEX IF NOT EXISTS curriculum_drafts_job_uidx ON curriculum_drafts (job_id);
        ALTER TABLE curriculum_drafts
            ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'import',
            ADD COLUMN IF NOT EXISTS faculty_checked jsonb NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS review_due_at date,
            ADD COLUMN IF NOT EXISTS submitted_at timestamptz,
            ADD COLUMN IF NOT EXISTS verified_at timestamptz,
            ADD COLUMN IF NOT EXISTS published_at timestamptz,
            ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
        CREATE TABLE IF NOT EXISTS curriculum_events (
            id          bigserial PRIMARY KEY,
            draft_id    bigint NOT NULL REFERENCES curriculum_drafts (id) ON DELETE CASCADE,
            ts          timestamptz NOT NULL DEFAULT now(),
            by          text,
            action      text NOT NULL,
            from_status text,
            to_status   text,
            note        text
        );
        CREATE INDEX IF NOT EXISTS curriculum_events_draft_idx ON curriculum_events (draft_id, ts);
        """,
    ),
    (
        "004_external",
        """
        -- copies of SUPREME / HURIS data (ocl_api.external): filled by an adapter, read-only here
        CREATE TABLE IF NOT EXISTS ext_sources (
            system    text PRIMARY KEY,
            adapter   text NOT NULL,
            synced_at timestamptz NOT NULL DEFAULT now(),
            as_of     date,
            counts    jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE TABLE IF NOT EXISTS ext_staff (
            pid         text PRIMARY KEY,
            title_full  text,
            title_short text,
            position    text,
            name_th     text NOT NULL,
            name_en     text,
            faculty     text,
            department  text,
            email       text,
            education   jsonb NOT NULL DEFAULT '[]'::jsonb,
            works       jsonb NOT NULL DEFAULT '[]'::jsonb
        );
        CREATE TABLE IF NOT EXISTS ext_programs (
            code    text PRIMARY KEY,
            name_th text NOT NULL,
            name_en text,
            short   text,
            level   text,
            faculty text,
            version text
        );
        CREATE TABLE IF NOT EXISTS ext_sections (
            term         text NOT NULL,
            course_code  text NOT NULL,
            section      text NOT NULL,
            course_name  text,
            program_code text,
            teachers     jsonb NOT NULL DEFAULT '[]'::jsonb,
            schedule     text,
            room         text,
            enrolled     integer,
            PRIMARY KEY (term, course_code, section)
        );
        CREATE TABLE IF NOT EXISTS ext_students (
            sid          text PRIMARY KEY,
            name_th      text NOT NULL,
            program_code text,
            entry_year   integer,
            status       text,
            graduated    text
        );
        CREATE TABLE IF NOT EXISTS ext_signers (
            id       text PRIMARY KEY,
            name_th  text NOT NULL,
            position text,
            scope    text
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
