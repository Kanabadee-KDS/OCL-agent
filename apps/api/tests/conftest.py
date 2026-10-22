"""Shared fixtures: a Postgres for the DB-backed tests (DATABASE_URL, else the embedded
pgserver dev dependency) and a throw-away schema per test."""

from __future__ import annotations

import os
import secrets

import pytest

from ocl_api.db import drop_schema


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory: pytest.TempPathFactory):
    url = os.environ.get("DATABASE_URL")
    if url:
        yield url
        return
    try:
        import pgserver
    except ImportError:  # pragma: no cover - dev machines without the extra
        pytest.skip("no DATABASE_URL and no pgserver")
    server = pgserver.get_server(str(tmp_path_factory.mktemp("pg")))
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


@pytest.fixture
def schema(pg_url: str):
    name = "t_" + secrets.token_hex(4)
    yield name
    drop_schema(pg_url, name)
