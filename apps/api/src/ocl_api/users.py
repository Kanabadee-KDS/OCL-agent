"""Users and roles in Postgres (table `users`); needs DATABASE_URL."""

from __future__ import annotations

from typing import Any

import psycopg

from ocl_api.auth import ROLES, hash_password, verify_password
from ocl_api.db import Jsonb, connect

# `usable` = may sign in now: not suspended and not past the end date (Thai calendar day).
# Every sign-in path and the per-request check read `usable`, never `active` alone.
COLUMNS = (
    "email, name, buasri_id, roles, active, unit, units, kind, pid, sid, expires_at, created_at, "
    "last_login_at, updated_by, updated_at, password_hash IS NOT NULL AS has_password, "
    "(active AND (expires_at IS NULL OR "
    "expires_at >= (now() AT TIME ZONE 'Asia/Bangkok')::date)) AS usable"
)


class UserError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _row(r: dict[str, Any] | None) -> dict[str, Any] | None:
    if r is None:
        return None
    out = dict(r)
    for k in ("created_at", "last_login_at", "updated_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat(timespec="seconds")
    if out.get("expires_at") is not None:
        out["expires_at"] = out["expires_at"].isoformat()
    return out


def _known_roles(conn) -> list[str]:
    """Group ids users may hold: the role_groups table (FS-1b), else the nine built-in ones."""
    try:
        with conn.transaction():
            return [r["id"] for r in conn.execute("SELECT id FROM role_groups ORDER BY ord")]
    except psycopg.errors.UndefinedTable:
        return list(ROLES)


class UserStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema

    def _conn(self):
        return connect(self.url, self.schema)

    def list(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            return [_row(r) for r in conn.execute(f"SELECT {COLUMNS} FROM users ORDER BY email")]

    def search(self, q: str = "", role: str = "", status: str = "") -> list[dict[str, Any]]:
        """The users page: name or e-mail (spaces ignored), one group, active/suspended/expired."""
        needle = "%" + "".join(q.split()).lower() + "%"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM (SELECT {COLUMNS} FROM users) u WHERE "
                "lower(replace(concat_ws(' ', name, email, buasri_id), ' ', '')) LIKE %s "
                "AND (%s = '' OR roles ? %s) "
                "AND (%s = '' OR (%s = 'active' AND usable) OR (%s = 'suspended' AND NOT active) "
                "OR (%s = 'expired' AND active AND NOT usable)) ORDER BY name, email",
                (needle, role, role, status, status, status, status),
            ).fetchall()
        return [_row(r) for r in rows]

    def events(self, email: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT ts, by, action, detail FROM user_events WHERE lower(email) = lower(%s) "
                "ORDER BY id DESC LIMIT %s",
                (email, limit),
            ).fetchall()
        return [{**r, "ts": r["ts"].isoformat(timespec="seconds")} for r in rows]

    def save(
        self,
        email: str,
        by: str,
        *,
        create: bool,
        name: str | None = None,
        roles: list[str] | None = None,
        units: list[str] | None = None,
        expires_at: str | None = None,
        kind: str = "internal",
        pid: str | None = None,
        buasri_id: str | None = None,
        clear_expiry: bool = False,
        sid: str | None = None,
    ) -> dict[str, Any]:
        """Add or edit an account from the users page; passwords are never set here (Q1 ข)."""
        email = email.strip().lower()
        if "@" not in email:
            raise UserError("อีเมลไม่ถูกต้อง")
        with self._conn() as conn, conn.transaction():
            old = conn.execute(
                f"SELECT {COLUMNS} FROM users WHERE email = %s FOR UPDATE", (email,)
            ).fetchone()
            if create and old is not None:
                raise UserError("มีบัญชีอีเมลนี้แล้ว", 409)
            if not create and old is None:
                raise UserError("ไม่พบผู้ใช้", 404)
            if roles is not None:
                known = _known_roles(conn)
                bad = [r for r in roles if r not in known]
                if bad:
                    raise UserError(f"ไม่รู้จักกลุ่มสิทธิ์ {', '.join(bad)}")
            if old is not None and old["email"] == by.lower():
                if roles is not None and sorted(roles) != sorted(old["roles"]):
                    raise UserError("แก้กลุ่มสิทธิ์ของบัญชีตัวเองไม่ได้ ให้ผู้ดูแลอีกคนแก้", 409)
                if expires_at or clear_expiry:
                    raise UserError("แก้วันสิ้นสุดสิทธิ์ของบัญชีตัวเองไม่ได้", 409)
            if old is not None and roles is not None and "admin" in old["roles"]:
                if "admin" not in roles:
                    self._keep_an_admin(conn, email)
            if create:
                conn.execute(
                    "INSERT INTO users (email, name, buasri_id, roles, units, kind, pid, sid, "
                    "expires_at, updated_by, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
                    (
                        email, (name or "").strip(), buasri_id, Jsonb(roles or []),
                        Jsonb(units or []), kind, pid, sid, expires_at, by,
                    ),
                )  # fmt: skip
                detail: dict[str, Any] = {"roles": roles or [], "units": units or [], "kind": kind}
                if sid:
                    detail["sid"] = sid
                action = "invite" if kind == "external" else "create"
            else:
                detail = {}
                new = {"name": (name or "").strip() or None, "roles": roles, "units": units}
                for k, v in new.items():
                    if v is not None and v != old[k]:
                        detail[k] = [old[k], v]
                old_exp = old["expires_at"].isoformat() if old["expires_at"] else None
                new_exp = None if clear_expiry else (expires_at or old_exp)
                if new_exp != old_exp:
                    detail["expires_at"] = [old_exp, new_exp]
                if not detail:
                    return self.get(email) or {}
                conn.execute(
                    "UPDATE users SET name = coalesce(%s, name), roles = coalesce(%s, roles), "
                    "units = coalesce(%s, units), "
                    "expires_at = CASE WHEN %s THEN NULL ELSE coalesce(%s::date, expires_at) END, "
                    "updated_by = %s, updated_at = now() WHERE email = %s",
                    (
                        new["name"],
                        Jsonb(roles) if roles is not None else None,
                        Jsonb(units) if units is not None else None,
                        clear_expiry,
                        expires_at,
                        by,
                        email,
                    ),
                )
                action = "update"
            conn.execute(
                "INSERT INTO user_events (by, email, action, detail) VALUES (%s, %s, %s, %s)",
                (by, email, action, Jsonb(detail)),
            )
        return self.get(email) or {}

    def log(self, email: str, by: str, action: str, detail: dict[str, Any]) -> None:
        """A change made outside the users page (the `ocl users` command), for NFR-15."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO user_events (by, email, action, detail) VALUES (%s, %s, %s, %s)",
                (by, email.strip().lower(), action, Jsonb(detail)),
            )

    @staticmethod
    def _keep_an_admin(conn, email: str) -> None:
        others = conn.execute(
            f"SELECT count(*) AS n FROM (SELECT {COLUMNS} FROM users) u "
            "WHERE usable AND roles ? 'admin' AND email <> %s",
            (email,),
        ).fetchone()["n"]
        if not others:
            raise UserError("ต้องมีผู้ดูแลระบบที่ใช้งานได้อย่างน้อย 1 คน", 409)

    def set_active_by(self, email: str, active: bool, by: str) -> dict[str, Any]:
        """Suspend or re-enable from the users page; accounts are never deleted (US-U-03)."""
        email = email.strip().lower()
        if email == by.lower() and not active:
            raise UserError("ระงับบัญชีตัวเองไม่ได้", 409)
        with self._conn() as conn, conn.transaction():
            u = conn.execute(
                f"SELECT {COLUMNS} FROM users WHERE email = %s FOR UPDATE", (email,)
            ).fetchone()
            if u is None:
                raise UserError("ไม่พบผู้ใช้", 404)
            if u["active"] == active:
                return _row(u) or {}
            if not active and "admin" in u["roles"]:
                self._keep_an_admin(conn, email)
            conn.execute(
                "UPDATE users SET active = %s, updated_by = %s, updated_at = now() "
                "WHERE email = %s",
                (active, by, email),
            )
            conn.execute(
                "INSERT INTO user_events (by, email, action, detail) VALUES (%s, %s, %s, '{}')",
                (by, email, "enable" if active else "suspend"),
            )
        return self.get(email) or {}

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
        email = email.strip().lower()
        with self._conn() as conn:
            known = _known_roles(conn)
            bad = [r for r in roles if r not in known]
            if bad:
                raise ValueError(f"unknown roles: {', '.join(bad)} (valid: {', '.join(known)})")
            conn.execute(
                """
                INSERT INTO users (email, name, buasri_id, roles, password_hash, unit, units)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO UPDATE SET
                    name = CASE WHEN EXCLUDED.name <> '' THEN EXCLUDED.name ELSE users.name END,
                    buasri_id = COALESCE(EXCLUDED.buasri_id, users.buasri_id),
                    roles = CASE WHEN EXCLUDED.roles <> '[]'::jsonb
                                 THEN EXCLUDED.roles ELSE users.roles END,
                    password_hash = COALESCE(EXCLUDED.password_hash, users.password_hash),
                    unit = COALESCE(EXCLUDED.unit, users.unit),
                    units = CASE WHEN EXCLUDED.unit IS NULL OR users.units ? EXCLUDED.unit
                                 THEN users.units ELSE users.units || EXCLUDED.units END
                """,
                (
                    email,
                    name,
                    buasri_id,
                    Jsonb(roles),
                    hash_password(password) if password else None,
                    unit,
                    Jsonb([unit] if unit else []),
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
        if r is None or not r["usable"] or not verify_password(password, r.get("password_hash")):
            return None
        out = _row(r) or {}
        out.pop("password_hash", None)
        return out
