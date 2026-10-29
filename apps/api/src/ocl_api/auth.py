"""Identity and permissions.

The web app (Auth.js: Google @g.swu.ac.th or Buasri ID credentials) is the only login
surface. It calls this API with a short-lived HS256 JWT signed with the shared
AUTH_SECRET: `sub` = email, `name`, `roles`. Users and their roles live in the `users`
table (migration 002); roles follow the 9 groups of the customer's mock, and a user may
hold several. With a database, every request takes the roles from that table (cached
USER_CACHE_TTL seconds), so a suspended user or a role change does not wait for the web
session to expire. When AUTH_SECRET is not set (file-mode dev, tests) every request acts as
an anonymous admin and /health reports auth=disabled.
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

ROLES: dict[str, str] = {
    "admin": "ผู้ดูแลระบบ",
    "central": "ผู้ดูแลส่วนกลาง",
    "curator": "ผู้ตรวจสอบระดับหลักสูตร",
    "faculty": "ผู้ตรวจสอบระดับส่วนงาน",
    "evaluator": "ผู้ประเมินหลักสูตร",
    "teacher": "อาจารย์ผู้สอน",
    "advisor": "อาจารย์ที่ปรึกษา",
    "student": "นิสิต",
    "exec": "ผู้บริหาร",
}
# Menu-level permissions of the AI import feature (BRD 00 §3: M1 is open to admin,
# central, curator and faculty; the faculty reviewer reads but does not import).
PERMISSIONS: dict[str, set[str]] = {
    "import_read": {"admin", "central", "curator", "faculty"},
    "import_write": {"admin", "central", "curator"},
    "users_manage": {"admin", "central"},
    # คู่มือหลักสูตร workflow (BRD 01 §2)
    "curriculum_submit": {"admin", "central", "curator"},
    "curriculum_verify": {"admin", "faculty"},
    "curriculum_publish": {"admin", "central"},
}
# Menu-level visibility, mirrored from the web's apps/web/src/lib/nav.ts (the mock's NAV and
# ROLES.mods/only, BRD 00 §3); tests/test_auth.py fails when the two drift apart.
MENUS: dict[str, list[str]] = {
    "c": ["c1", "c1b", "c2", "c3", "c3h", "c5", "c4"],
    "p": ["p1", "p2", "p4"],
    "s": ["s1", "s2", "s2b", "s3", "s4", "s5", "s6"],
    "q": ["q1", "q2", "q1b", "q3", "q4"],
    "r": ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "ra", "rb", "rc"],
    "u": ["u1", "u2", "u3"],
    "m": ["m1", "m2"],
}
MENU_INHERITS: dict[str, str] = {"c3h": "c3"}  # pages beyond the mock follow their parent menu
ROLE_ACCESS: dict[str, tuple[list[str], list[str] | None]] = {  # role: (modules, only these menus)
    "admin": (["c", "p", "s", "q", "r", "u"], None),
    "central": (["c", "p", "s", "q", "r", "u"], None),
    "curator": (["c", "p", "s", "q", "r"], None),
    "faculty": (["c", "p", "s", "q", "r"], None),
    "evaluator": (["q"], None),
    "teacher": (["p", "s", "r"], ["p2", "p4", "s4", "s5", "r0", "r7", "r8"]),
    "advisor": (["s", "r"], ["s5", "r0", "r8"]),
    "student": (["m"], None),
    "exec": (["r"], None),
}
SERVICE_ROLE = "service"
TOKEN_TTL = 300  # seconds; the web signs a fresh token per request
USER_CACHE_TTL = 30  # seconds a looked-up user is trusted before the table is read again


def can_menu(roles: list[str], menu: str) -> bool:
    menu = MENU_INHERITS.get(menu, menu)
    mod = next((k for k, ids in MENUS.items() if menu in ids), None)
    for r in roles:
        mods, only = ROLE_ACCESS.get(r, ([], None))
        if mod in mods and (only is None or menu in only):
            return True
    return False


@dataclass
class User:
    email: str
    name: str = ""
    roles: list[str] = field(default_factory=list)
    active: bool = True

    def can(self, perm: str) -> bool:
        return bool(PERMISSIONS.get(perm, set()) & set(self.roles))

    def menus(self) -> list[str]:
        return [m for ids in MENUS.values() for m in ids if can_menu(self.roles, m)]

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


def clear_user_cache() -> None:
    _user_cache.clear()


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
    if stored is None or not stored["active"]:
        raise HTTPException(401, "บัญชีนี้ถูกระงับหรือไม่มีในระบบ")
    return User(
        email=stored["email"], name=stored["name"] or user.name, roles=list(stored["roles"])
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


def require_menu(menu: str):
    """Endpoint guard by menu id (lib/nav.ts), for the pages FS-1..FS-7 add."""

    def dep(user: User = Depends(current_user)) -> User:
        if not can_menu(user.roles, menu):
            raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์ในเมนูนี้")
        return user

    return dep


# module-level singletons so endpoints can use them as defaults (ruff B008)
REQUIRE_SERVICE = require(SERVICE_ROLE)
REQUIRE_IMPORT_READ = require("import_read")
REQUIRE_IMPORT_WRITE = require("import_write")
