"""Endpoints the web's Auth.js config calls with a service token, plus /me for debugging."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import (
    PERM_MENU,
    REQUIRE_SERVICE,
    ROLES,
    User,
    current_user,
    user_perms,
)
from ocl_api.config import Settings, get_settings
from ocl_api.roles import RoleStore
from ocl_api.users import UserStore

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_users(settings: Settings = Depends(get_settings)) -> UserStore:
    if not settings.database_url:
        raise HTTPException(503, "ระบบผู้ใช้ต้องการ DATABASE_URL")
    return UserStore(settings.database_url, settings.database_schema)


class Lookup(BaseModel):
    email: str
    role: str | None = None  # refresh only: the one group the user is acting as (role switch)


class Credentials(BaseModel):
    username: str
    password: str


def _public(u: dict[str, Any], settings: Settings, role: str | None = None) -> dict[str, Any]:
    """What the web keeps in its session: who, group names, and menu -> actions for the nav.

    With `role` (one of the user's groups) the menus are those of that group only: the role
    switch of the top bar narrows what the pages show; the API still allows all the groups."""
    out = {k: u.get(k) for k in ("email", "name", "roles", "active", "units", "buasri_id")}
    roles = list(u.get("roles") or [])
    active = role if role in roles else None
    out["active_role"] = active
    out["perms"] = user_perms(settings, [active] if active else roles)
    names = RoleStore(settings.database_url, settings.database_schema).names(roles)
    out["role_names"] = {r: names.get(r) or ROLES.get(r, r) for r in roles}
    return out


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
    if u is None or not u["usable"]:
        raise HTTPException(404, "ไม่พบผู้ใช้ในระบบ หรือถูกระงับ ติดต่อผู้ดูแลเพื่อกำหนดสิทธิ์")
    users.touch_login(email)
    return _public(u, settings)


@router.post("/credentials")
def credentials(
    body: Credentials,
    _: User = Depends(REQUIRE_SERVICE),
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Buasri ID sign-in (POC: password stored in our table; later SWU's directory)."""
    u = users.check_credentials(body.username, body.password)
    if u is None:
        raise HTTPException(401, "บัวศรีไอดีหรือรหัสผ่านไม่ถูกต้อง")
    users.touch_login(u["email"])
    return _public(u, settings)


class OtpRequest(BaseModel):
    email: str


class OtpVerify(BaseModel):
    email: str
    code: str


def _otp(settings: Settings):
    from ocl_api.otp import OtpStore

    if not settings.database_url or not settings.auth_secret:
        raise HTTPException(503, "การเข้าสู่ระบบด้วยรหัสต้องการฐานข้อมูลและ AUTH_SECRET")
    return OtpStore(settings.database_url, settings.database_schema, settings.auth_secret)


@router.post("/otp/request")
def otp_request(
    body: OtpRequest,
    _: User = Depends(REQUIRE_SERVICE),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """US-U-02: a one-time code by e-mail, for invited outside evaluators only."""
    from ocl_api.otp import OtpError

    try:
        return _otp(settings).request(body.email)
    except OtpError as e:
        raise HTTPException(e.status, str(e)) from e


@router.post("/otp/verify")
def otp_verify(
    body: OtpVerify,
    _: User = Depends(REQUIRE_SERVICE),
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    from ocl_api.otp import OtpError

    try:
        u = _otp(settings).verify(body.email, body.code)
    except OtpError as e:
        raise HTTPException(e.status, str(e)) from e
    users.touch_login(u["email"])
    return _public(u, settings)


@router.post("/refresh")
def refresh(
    body: Lookup,
    _: User = Depends(REQUIRE_SERVICE),
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The web re-reads a signed-in user every minute: roles and menus, or 404 to end it."""
    u = users.get(body.email.strip())
    if u is None or not u["usable"]:
        raise HTTPException(404, "บัญชีนี้ถูกระงับหรือไม่มีในระบบ")
    return _public(u, settings, body.role)


@router.get("/me")
def me(user: User = Depends(current_user), settings: Settings = Depends(get_settings)) -> dict:
    return {
        **user.to_dict(),
        "auth": "enabled" if settings.auth_secret else "disabled",
        "role_names": {r: ROLES.get(r, r) for r in user.roles},
        "permissions": {p: user.can(p) for p in PERM_MENU},
        "menus": user.menus(),
        "perms": user.menu_perms(),
    }
