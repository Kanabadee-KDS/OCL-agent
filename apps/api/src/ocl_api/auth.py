"""Identity and permissions.

The web app (Auth.js: Google @g.swu.ac.th or Buasri ID credentials) is the only login
surface. It calls this API with a short-lived HS256 JWT signed with the shared
AUTH_SECRET: `sub` = email, `name`, `roles`. Users and their roles live in the `users`
table (migration 002); roles follow the 9 groups of the customer's mock, and a user may
hold several. When AUTH_SECRET is not set (file-mode dev, tests) every request acts as
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
}
SERVICE_ROLE = "service"
TOKEN_TTL = 300  # seconds; the web signs a fresh token per request


@dataclass
class User:
    email: str
    name: str = ""
    roles: list[str] = field(default_factory=list)
    active: bool = True

    def can(self, perm: str) -> bool:
        return bool(PERMISSIONS.get(perm, set()) & set(self.roles))

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


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> User:
    if not settings.auth_secret:
        return ANONYMOUS_ADMIN
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "ต้องเข้าสู่ระบบก่อน")
    return verify_token(settings.auth_secret, header[7:].strip())


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


# module-level singletons so endpoints can use them as defaults (ruff B008)
REQUIRE_SERVICE = require(SERVICE_ROLE)
REQUIRE_IMPORT_READ = require("import_read")
REQUIRE_IMPORT_WRITE = require("import_write")
