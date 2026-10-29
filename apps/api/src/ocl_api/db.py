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

from ocl_api.flow_defaults import seed_sql as flow_seed_sql
from ocl_api.perms import menu_seed_sql, scope_kind_sql, seed_sql

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
    (
        "005_email_outbox",
        """
        -- every e-mail the system would send (ocl_api.mail); nothing leaves until a sender exists
        CREATE TABLE IF NOT EXISTS email_outbox (
            id         bigserial PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            created_by text,
            kind       text NOT NULL,
            ref        text,
            to_addrs   jsonb NOT NULL,
            subject    text NOT NULL,
            body       text NOT NULL,
            dedupe_key text,
            status     text NOT NULL DEFAULT 'queued',
            sent_at    timestamptz,
            error      text
        );
        CREATE UNIQUE INDEX IF NOT EXISTS email_outbox_dedupe_uidx
            ON email_outbox (dedupe_key) WHERE dedupe_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS email_outbox_status_idx ON email_outbox (status, created_at);
        """,
    ),
    (
        "006_role_perms",
        """
        -- permission groups and their per-menu actions (ocl_api.perms seeds the 9 of the mock)
        CREATE TABLE IF NOT EXISTS role_groups (
            id         text PRIMARY KEY,
            name       text NOT NULL,
            scope      text NOT NULL DEFAULT '',
            builtin    boolean NOT NULL DEFAULT false,
            ord        integer NOT NULL DEFAULT 0,
            updated_by text,
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS role_perms (
            role_id text NOT NULL REFERENCES role_groups (id) ON DELETE CASCADE,
            menu    text NOT NULL,
            action  text NOT NULL,
            PRIMARY KEY (role_id, menu, action)
        );
        """
        + seed_sql(),
    ),
    (
        "007_role_admin",
        """
        -- what the role-edit page sets besides the menu actions, and who changed a group (NFR-15)
        ALTER TABLE role_groups
            ADD COLUMN IF NOT EXISTS scope_kind text NOT NULL DEFAULT 'all',
            ADD COLUMN IF NOT EXISTS auto_from_teachers boolean NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS notify_on_change boolean NOT NULL DEFAULT true;
        CREATE TABLE IF NOT EXISTS role_events (
            id      bigserial PRIMARY KEY,
            ts      timestamptz NOT NULL DEFAULT now(),
            by      text,
            role_id text NOT NULL,
            action  text NOT NULL,
            detail  jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS role_events_role_idx ON role_events (role_id, ts);
        """
        + scope_kind_sql(),
    ),
    (
        "008_users_admin",
        """
        -- what the users page manages (US-U-03): several units, external invitees with an end
        -- date, the HURIS record a staff account came from, and who changed what (NFR-15)
        ALTER TABLE users
            ADD COLUMN IF NOT EXISTS units      jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS kind       text NOT NULL DEFAULT 'internal',
            ADD COLUMN IF NOT EXISTS pid        text,
            ADD COLUMN IF NOT EXISTS expires_at date,
            ADD COLUMN IF NOT EXISTS updated_by text,
            ADD COLUMN IF NOT EXISTS updated_at timestamptz;
        UPDATE users SET units = jsonb_build_array(unit)
            WHERE unit IS NOT NULL AND unit <> '' AND units = '[]'::jsonb;
        CREATE TABLE IF NOT EXISTS user_events (
            id     bigserial PRIMARY KEY,
            ts     timestamptz NOT NULL DEFAULT now(),
            by     text,
            email  text NOT NULL,
            action text NOT NULL,
            detail jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS user_events_email_idx ON user_events (email, ts);
        """,
    ),
    (
        "009_flows",
        """
        -- approval flows (ocl_api.flows): every save is a new version, started work keeps its own
        CREATE TABLE IF NOT EXISTS flows (
            id             text PRIMARY KEY,
            name           text NOT NULL,
            version        integer NOT NULL DEFAULT 1,
            fixed_steps    integer,
            ord            integer NOT NULL DEFAULT 0,
            notify_next    boolean NOT NULL DEFAULT true,
            notify_sender  boolean NOT NULL DEFAULT true,
            remind_overdue boolean NOT NULL DEFAULT true,
            updated_by     text,
            updated_at     timestamptz
        );
        CREATE TABLE IF NOT EXISTS flow_steps (
            flow_id   text NOT NULL REFERENCES flows (id) ON DELETE CASCADE,
            version   integer NOT NULL,
            ord       integer NOT NULL,
            roles     jsonb NOT NULL DEFAULT '[]'::jsonb,
            position  text,
            label     text NOT NULL,
            action    text NOT NULL,
            days      integer NOT NULL DEFAULT 0,
            on_reject text NOT NULL DEFAULT 'sender',
            PRIMARY KEY (flow_id, version, ord)
        );
        CREATE TABLE IF NOT EXISTS flow_versions (
            flow_id text NOT NULL REFERENCES flows (id) ON DELETE CASCADE,
            version integer NOT NULL,
            by      text,
            ts      timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (flow_id, version)
        );
        ALTER TABLE curriculum_drafts ADD COLUMN IF NOT EXISTS flow_version integer;
        """
        + flow_seed_sql(),
    ),
    (
        "010_curriculum_sections",
        """
        -- the คู่มือหลักสูตร's own data (ocl_api.sections): หมวด 0–5, filled by import or by hand
        ALTER TABLE curriculum_drafts ALTER COLUMN job_id DROP NOT NULL;
        ALTER TABLE curriculum_drafts
            ADD COLUMN IF NOT EXISTS faculty    text,
            ADD COLUMN IF NOT EXISTS created_by text;
        UPDATE curriculum_drafts
            SET faculty = data->'parts'->'info'->'data'->'values'->>'faculty'
            WHERE faculty IS NULL;
        CREATE TABLE IF NOT EXISTS curriculum_sections (
            draft_id   bigint NOT NULL REFERENCES curriculum_drafts (id) ON DELETE CASCADE,
            section    text NOT NULL,
            data       jsonb NOT NULL DEFAULT '{}'::jsonb,
            updated_by text,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (draft_id, section)
        );
        CREATE TABLE IF NOT EXISTS curriculum_section_history (
            id       bigserial PRIMARY KEY,
            draft_id bigint NOT NULL REFERENCES curriculum_drafts (id) ON DELETE CASCADE,
            section  text NOT NULL,
            ts       timestamptz NOT NULL DEFAULT now(),
            by       text,
            why      text,
            data     jsonb NOT NULL
        );
        CREATE INDEX IF NOT EXISTS curriculum_section_history_idx
            ON curriculum_section_history (draft_id, section, ts);
        """,
    ),
    (
        "011_lookups",
        """
        -- options the administrators add to the form's lists (curriculum_form.lookup_keys)
        CREATE TABLE IF NOT EXISTS lookups (
            field    text NOT NULL,
            value    text NOT NULL,
            added_by text,
            added_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (field, value)
        );
        """,
    ),
    (
        "012_dashboard_menu",
        "-- แดชบอร์ดหลักสูตร (FS-2f): the menu d1 for the groups the mock shows it to\n"
        + menu_seed_sql("d1"),
    ),
    (
        "013_courses",
        """
        -- ฐานข้อมูลรายวิชากลาง (FS-3a · US-M1-18, mock CUR23): one row per course code, its
        -- content per Version (code shown as รหัส-Version); a curriculum keeps the Version it uses
        CREATE TABLE IF NOT EXISTS courses (
            code_th       text PRIMARY KEY,
            code_en       text,
            transcript_th text,
            transcript_en text,
            course_type   text,
            module        text,
            unit          text,
            major         text,
            reg_no        text,
            telebank      text,
            status        text NOT NULL DEFAULT 'ใช้งาน',
            note          text,
            latest        int NOT NULL DEFAULT 1,
            created_by    text,
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_by    text,
            updated_at    timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS course_versions (
            code_th        text NOT NULL REFERENCES courses (code_th) ON DELETE CASCADE,
            version        int NOT NULL,
            kind           text NOT NULL,
            year           int,
            name_th        text NOT NULL,
            name_en        text,
            credits        int,
            credit_text    text,
            description_th text,
            description_en text,
            source         text,
            created_by     text,
            created_at     timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (code_th, version)
        );
        """,
    ),
    (
        "014_ext_persons",
        """
        -- ทะเบียนบุคคลภายนอก (FS-3b · US-M1-19): people not in HURIS whom curricula list as
        -- teachers (หมวด 0.2 rows carry `xid`); edited here once, copied to every curriculum
        CREATE TABLE IF NOT EXISTS ext_persons (
            id          text PRIMARY KEY,
            kind        text NOT NULL,
            title_full  text,
            title_short text,
            position    text,
            name_th     text NOT NULL,
            name_en     text,
            national_id text,
            org         text,
            email       text,
            tel         text,
            education   jsonb NOT NULL DEFAULT '[]'::jsonb,
            works       jsonb NOT NULL DEFAULT '[]'::jsonb,
            active      boolean NOT NULL DEFAULT true,
            created_by  text,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_by  text,
            updated_at  timestamptz NOT NULL DEFAULT now()
        );
        """,
    ),
    (
        "015_smo08",
        """
        -- งานปรับปรุงแก้ไขหลักสูตร สมอ.08 (FS-3c · US-M1-09 10): a request on a verified
        -- curriculum, approved step by step by the flow smo08; once approved its teacher list
        -- replaces หมวด 0.2 (BR-06: the only way to change a verified curriculum)
        CREATE TABLE IF NOT EXISTS smo_requests (
            id           text PRIMARY KEY,
            draft_id     bigint NOT NULL REFERENCES curriculum_drafts (id),
            status       text NOT NULL DEFAULT 'draft',
            step         int NOT NULL DEFAULT 0,
            flow_version int,
            types        jsonb NOT NULL DEFAULT '[]'::jsonb,
            scope        jsonb NOT NULL DEFAULT '{"kind": "mother"}'::jsonb,
            fields       jsonb NOT NULL DEFAULT '{}'::jsonb,
            teachers     jsonb NOT NULL DEFAULT '{}'::jsonb,
            details      jsonb NOT NULL DEFAULT '{}'::jsonb,
            reason       text,
            created_by   text NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            submitted_at timestamptz,
            approved_at  timestamptz
        );
        CREATE TABLE IF NOT EXISTS smo_events (
            id         bigserial PRIMARY KEY,
            request_id text NOT NULL REFERENCES smo_requests (id) ON DELETE CASCADE,
            ts         timestamptz NOT NULL DEFAULT now(),
            by         text,
            action     text NOT NULL,
            step       int,
            note       text
        );
        CREATE TABLE IF NOT EXISTS smo_files (
            id         bigserial PRIMARY KEY,
            request_id text NOT NULL REFERENCES smo_requests (id) ON DELETE CASCADE,
            name       text NOT NULL,
            path       text NOT NULL,
            size       bigint NOT NULL,
            by         text,
            ts         timestamptz NOT NULL DEFAULT now()
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
