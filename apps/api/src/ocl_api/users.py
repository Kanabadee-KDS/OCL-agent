"""Users and roles in Postgres (table `users`); needs DATABASE_URL."""

from __future__ import annotations

from typing import Any

from ocl_api.auth import ROLES, hash_password, verify_password
from ocl_api.db import Jsonb, connect

COLUMNS = "email, name, buasri_id, roles, active, unit, created_at, last_login_at"


def _row(r: dict[str, Any] | None) -> dict[str, Any] | None:
    if r is None:
        return None
    out = dict(r)
    for k in ("created_at", "last_login_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat(timespec="seconds")
    return out


class UserStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema

    def _conn(self):
        return connect(self.url, self.schema)

    def list(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return [_row(r) for r in conn.execute(f"SELECT {COLUMNS} FROM users ORDER BY email")]

    def get(self, email: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            return _row(
                conn.execute(
                    f"SELECT {COLUMNS} FROM users WHERE lower(email) = lower(%s)", (email,)
                ).fetchone()
            )

    def upsert(
        self,
        email: str,
        *,
        name: str = "",
        roles: list[str] | None = None,
        buasri_id: str | None = None,
        password: str | None = None,
        unit: str | None = None,
    ) -> dict[str, Any]:
        roles = roles or []
        bad = [r for r in roles if r not in ROLES]
        if bad:
            raise ValueError(f"unknown roles: {', '.join(bad)} (valid: {', '.join(ROLES)})")
        email = email.strip().lower()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO users (email, name, buasri_id, roles, password_hash, unit)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    name = CASE WHEN EXCLUDED.name <> '' THEN EXCLUDED.name ELSE users.name END,
                    buasri_id = COALESCE(EXCLUDED.buasri_id, users.buasri_id),
                    roles = CASE WHEN EXCLUDED.roles <> '[]'::jsonb
                                 THEN EXCLUDED.roles ELSE users.roles END,
                    password_hash = COALESCE(EXCLUDED.password_hash, users.password_hash),
                    unit = COALESCE(EXCLUDED.unit, users.unit)
                """,
                (
                    email,
                    name,
                    buasri_id,
                    Jsonb(roles),
                    hash_password(password) if password else None,
                    unit,
                ),
            )
        return self.get(email) or {}

    def set_active(self, email: str, active: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET active = %s WHERE lower(email) = lower(%s)", (active, email)
            )

    def touch_login(self, email: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE users SET last_login_at = now() WHERE lower(email) = lower(%s)", (email,)
            )

    def check_credentials(self, username: str, password: str) -> dict[str, Any] | None:
        """Buasri ID (or email) + password; None when unknown, inactive or wrong."""
        with self._conn() as conn:
            r = conn.execute(
                f"SELECT {COLUMNS}, password_hash FROM users "
                "WHERE lower(buasri_id) = lower(%s) OR lower(email) = lower(%s)",
                (username, username),
            ).fetchone()
        if r is None or not r["active"] or not verify_password(password, r.get("password_hash")):
            return None
        out = _row(r) or {}
        out.pop("password_hash", None)
        return out
