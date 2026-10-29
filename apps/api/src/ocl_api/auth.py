"""Identity and permissions.

The web app (Auth.js: Google @g.swu.ac.th or Buasri ID credentials) is the only login
surface. It calls this API with a short-lived HS256 JWT signed with the shared
AUTH_SECRET: `sub` = email, `name`, `roles`. Users and their roles live in the `users`
table (migration 002); roles follow the 9 groups of the customer's mock, and a user may
hold several. With a database, every request takes the roles from that table and the
per-menu actions of those roles from `role_perms` (both cached USER_CACHE_TTL seconds), so a
suspended user or a permission change does not wait for the web session to expire. When
AUTH_SECRET is not set (file-mode dev, tests) every request acts as an anonymous admin and
/health reports auth=disabled.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request

from ocl_api.config import Settings, get_settings
from ocl_api.perms import (  # MENUS, MENU_INHERITS and ROLES are re-exported
    ALL_MENUS,
    Table,
    default_table,
    perms_for,
)
from ocl_api.perms import MENU_INHERITS as MENU_INHERITS
from ocl_api.perms import MENUS as MENUS
from ocl_api.perms import ROLES as ROLES

# Older permission names, now a menu and an action in `role_perms` (FS-1a).
PERM_MENU: dict[str, tuple[str, str]] = {
    "import_read": ("c3", "view"),
    "import_write": ("c3", "add"),
    "users_manage": ("u3", "edit"),
}
SERVICE_ROLE = "service"
TOKEN_TTL = 300  # seconds; the web signs a fresh token per request
USER_CACHE_TTL = 30  # seconds a looked-up user or the permission table is trusted

DEFAULT_TABLE = default_table()


def can_menu(roles: list[str], menu: str, action: str = "view", table: Table | None = None) -> bool:
    return action in perms_for(roles, DEFAULT_TABLE if table is None else table).get(menu, [])


@dataclass
class User:
    email: str
    name: str = ""
    roles: list[str] = field(default_factory=list)
    active: bool = True
    # menu -> actions from the database; None = the built-in defaults (no database)
    perms: dict[str, list[str]] | None = None

    def menu_perms(self) -> dict[str, list[str]]:
        return self.perms if self.perms is not None else perms_for(self.roles, DEFAULT_TABLE)

    def can_do(self, menu: str, action: str = "view") -> bool:
        return action in self.menu_perms().get(menu, [])

    def can(self, perm: str) -> bool:
        """An older permission name; workflow steps live in the approval flows (flows.py)."""
        return perm in PERM_MENU and self.can_do(*PERM_MENU[perm])

    def menus(self) -> list[str]:
        return [m for m in ALL_MENUS if self.can_do(m)]

    def to_dict(self) -> dict[str, Any]:
        return {"email": self.email, "name": self.name, "roles": self.roles, "active": self.active}


ANONYMOUS_ADMIN = User(email="dev@local", name="ผู้ดูแล (auth ปิด)", roles=["admin"])


# ---------- passwords (stdlib scrypt; replaced by Buasri ID / SWU directory later) ----------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, digest_b64 = stored.split("$", 2)
    salt = base64.b64decode(salt_b64)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return secrets.compare_digest(digest, base64.b64decode(digest_b64))


# ---------- tokens ----------


def sign_token(
    secret: str, *, sub: str, name: str = "", roles: list[str], ttl: int = TOKEN_TTL
) -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": sub, "name": name, "roles": roles, "iat": now, "exp": now + ttl},
        secret,
        algorithm="HS256",
    )


def verify_token(secret: str, token: str) -> User:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"token ไม่ถูกต้อง: {e.__class__.__name__}") from e
    roles = [r for r in claims.get("roles", []) if isinstance(r, str)]
    return User(email=str(claims.get("sub", "")), name=str(claims.get("name", "")), roles=roles)


# ---------- FastAPI dependencies ----------


_user_cache: dict[tuple[str, str | None, str], tuple[float, dict[str, Any] | None]] = {}
_table_cache: dict[tuple[str, str | None], tuple[float, Table]] = {}


def clear_user_cache() -> None:
    _user_cache.clear()
    _table_cache.clear()


def permission_table(settings: Settings) -> Table:
    """role -> menu -> actions from `role_perms`, or the defaults without a database."""
    if not settings.database_url:
        return DEFAULT_TABLE
    from ocl_api.db import connect

    key = (settings.database_url, settings.database_schema)
    hit = _table_cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    table: Table = {}
    with connect(settings.database_url, settings.database_schema) as conn:
        for r in conn.execute("SELECT role_id, menu, action FROM role_perms"):
            table.setdefault(r["role_id"], {}).setdefault(r["menu"], set()).add(r["action"])
    _table_cache[key] = (time.monotonic() + USER_CACHE_TTL, table)
    return table


def user_perms(settings: Settings, roles: list[str]) -> dict[str, list[str]]:
    return perms_for(roles, permission_table(settings))


def _stored_user(settings: Settings, email: str) -> dict[str, Any] | None:
    from ocl_api.users import UserStore  # users imports this module

    key = (settings.database_url or "", settings.database_schema, email.lower())
    hit = _user_cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    u = UserStore(settings.database_url or "", settings.database_schema).get(email)
    _user_cache[key] = (time.monotonic() + USER_CACHE_TTL, u)
    return u


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> User:
    if not settings.auth_secret:
        return ANONYMOUS_ADMIN
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "ต้องเข้าสู่ระบบก่อน")
    user = verify_token(settings.auth_secret, header[7:].strip())
    if SERVICE_ROLE in user.roles or not settings.database_url:
        return user
    # The users table, not the token, decides: a suspended user is refused and a role
    # change applies within USER_CACHE_TTL, although the web session lives for 8 hours.
    stored = _stored_user(settings, user.email)
    if stored is None or not stored["usable"]:
        raise HTTPException(401, "บัญชีนี้ถูกระงับหรือไม่มีในระบบ")
    roles = list(stored["roles"])
    return User(
        email=stored["email"],
        name=stored["name"] or user.name,
        roles=roles,
        perms=user_perms(settings, roles),
    )


def require(perm: str):
    def dep(user: User = Depends(current_user)) -> User:
        if perm == SERVICE_ROLE:
            if SERVICE_ROLE not in user.roles:
                raise HTTPException(403, "เฉพาะบริการภายใน")
            return user
        if not user.can(perm):
            raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์ในเมนูนี้")
        return user

    return dep


def require_menu(*menus: str, action: str = "view"):
    """Endpoint guard by menu id (lib/nav.ts): the user holds `action` on at least one."""

    def dep(user: User = Depends(current_user)) -> User:
        if not any(user.can_do(m, action) for m in menus):
            raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์ในเมนูนี้")
        return user

    return dep


# module-level singletons so endpoints can use them as defaults (ruff B008)
REQUIRE_SERVICE = require(SERVICE_ROLE)
REQUIRE_IMPORT_READ = require("import_read")
REQUIRE_IMPORT_WRITE = require("import_write")
