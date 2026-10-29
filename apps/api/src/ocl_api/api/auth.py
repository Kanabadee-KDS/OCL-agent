"""Endpoints the web's Auth.js config calls with a service token, plus /me for debugging."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import PERMISSIONS, REQUIRE_SERVICE, ROLES, User, current_user
from ocl_api.config import Settings, get_settings
from ocl_api.users import UserStore

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_users(settings: Settings = Depends(get_settings)) -> UserStore:
    if not settings.database_url:
        raise HTTPException(503, "ระบบผู้ใช้ต้องการ DATABASE_URL")
    return UserStore(settings.database_url, settings.database_schema)


class Lookup(BaseModel):
    email: str


class Credentials(BaseModel):
    username: str
    password: str


def _public(u: dict[str, Any]) -> dict[str, Any]:
    return {k: u.get(k) for k in ("email", "name", "roles", "active", "unit", "buasri_id")}


@router.post("/lookup")
def lookup(
    body: Lookup,
    _: User = Depends(REQUIRE_SERVICE),
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Google sign-in: who is this @domain address in our user table?"""
    email = body.email.strip().lower()
    domain = (settings.auth_allowed_domain or "").strip().lower()
    if domain and not email.endswith("@" + domain):
        raise HTTPException(403, f"อนุญาตเฉพาะบัญชี @{domain}")
    u = users.get(email)
    if u is None or not u["active"]:
        raise HTTPException(404, "ไม่พบผู้ใช้ในระบบ หรือถูกระงับ ติดต่อผู้ดูแลเพื่อกำหนดสิทธิ์")
    users.touch_login(email)
    return _public(u)


@router.post("/credentials")
def credentials(
    body: Credentials,
    _: User = Depends(REQUIRE_SERVICE),
    users: UserStore = Depends(get_users),
) -> dict[str, Any]:
    """Buasri ID sign-in (POC: password stored in our table; later SWU's directory)."""
    u = users.check_credentials(body.username, body.password)
    if u is None:
        raise HTTPException(401, "บัวศรีไอดีหรือรหัสผ่านไม่ถูกต้อง")
    users.touch_login(u["email"])
    return _public(u)


@router.post("/refresh")
def refresh(
    body: Lookup, _: User = Depends(REQUIRE_SERVICE), users: UserStore = Depends(get_users)
) -> dict[str, Any]:
    """The web re-reads a signed-in user every minute: current roles, or 404 to end the session."""
    u = users.get(body.email.strip())
    if u is None or not u["active"]:
        raise HTTPException(404, "บัญชีนี้ถูกระงับหรือไม่มีในระบบ")
    return _public(u)


@router.get("/me")
def me(user: User = Depends(current_user), settings: Settings = Depends(get_settings)) -> dict:
    return {
        **user.to_dict(),
        "auth": "enabled" if settings.auth_secret else "disabled",
        "role_names": {r: ROLES.get(r, r) for r in user.roles},
        "permissions": {p: user.can(p) for p in PERMISSIONS},
        "menus": user.menus(),
    }
