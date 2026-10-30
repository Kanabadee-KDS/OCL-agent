"""กำหนดผู้ใช้งาน (menu u3 · US-U-03): search, add staff from the HURIS copy, invite outside
evaluators, edit groups/units/end date, suspend or re-enable. No delete, no passwords (Q1 ข):
Buasri passwords stay with `ocl users set --ask-password` on the server."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import User, clear_user_cache, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.db import connect
from ocl_api.users import UserError, UserStore

router = APIRouter(prefix="/api/users", tags=["users"])

REQUIRE_VIEW = require_menu("u3")
REQUIRE_ADD = require_menu("u3", action="add")
REQUIRE_EDIT = require_menu("u3", action="edit")
WHOLE = "ทั้งมหาวิทยาลัย"


def get_users(settings: Settings = Depends(get_settings)) -> UserStore:
    if not settings.database_url:
        raise HTTPException(503, "ผู้ใช้งานต้องการ DATABASE_URL")
    return UserStore(settings.database_url, settings.database_schema)


class NewUser(BaseModel):
    pid: str | None = None  # a staff record of the HURIS copy; fills name and e-mail
    sid: str | None = None  # a student of the SUPREME copy (FS-5 Q2 ก); fills the name
    email: str | None = None
    name: str = ""
    roles: list[str] = []
    units: list[str] = []
    expires_at: date | None = None


class Invite(BaseModel):
    email: str
    name: str
    roles: list[str] = ["evaluator"]
    units: list[str] = []
    expires_at: date


class UserEdit(BaseModel):
    name: str | None = None
    roles: list[str] | None = None
    units: list[str] | None = None
    expires_at: date | None = None
    clear_expiry: bool = False


class Active(BaseModel):
    active: bool


def _run(fn, *args, **kwargs):
    try:
        out = fn(*args, **kwargs)
    except UserError as e:
        raise HTTPException(e.status, str(e)) from e
    clear_user_cache()  # sign-in checks in this process see the change now
    return out


@router.get("/options")
def options(
    settings: Settings = Depends(get_settings), _: User = Depends(REQUIRE_VIEW)
) -> dict[str, Any]:
    """Groups to tick and units to choose (faculties and programs of the SUPREME copy)."""
    with connect(settings.database_url or "", settings.database_schema) as conn:
        roles = conn.execute("SELECT id, name FROM role_groups ORDER BY ord, name").fetchall()
        progs = conn.execute(
            "SELECT faculty, short FROM ext_programs ORDER BY faculty, code"
        ).fetchall()
        src = conn.execute("SELECT adapter FROM ext_sources WHERE system = 'supreme'").fetchone()
    faculties = list(dict.fromkeys(p["faculty"] for p in progs if p["faculty"]))
    return {
        "roles": roles,
        "units": [WHOLE, *faculties, *[p["short"] for p in progs if p["short"]]],
        "units_sample": bool(src and src["adapter"] == "sample"),
    }


@router.get("")
def search(
    q: str = "",
    role: str = "",
    status: str = "",
    users: UserStore = Depends(get_users),
    _: User = Depends(REQUIRE_VIEW),
) -> dict[str, Any]:
    return {"items": users.search(q, role, status)}


@router.get("/{email}")
def get_user(
    email: str, users: UserStore = Depends(get_users), _: User = Depends(REQUIRE_VIEW)
) -> dict[str, Any]:
    u = users.get(email)
    if u is None:
        raise HTTPException(404, "ไม่พบผู้ใช้")
    return {**u, "events": users.events(email)}


@router.post("", status_code=201)
def add_user(
    body: NewUser,
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
    user: User = Depends(REQUIRE_ADD),
) -> dict[str, Any]:
    name, email = body.name, body.email
    if body.pid:
        with connect(settings.database_url or "", settings.database_schema) as conn:
            st = conn.execute("SELECT * FROM ext_staff WHERE pid = %s", (body.pid,)).fetchone()
        if st is None:
            raise HTTPException(404, "ไม่พบบุคลากรในข้อมูล HURIS")
        name = name or f"{st['title_short'] or ''}{st['name_th']}"
        email = email or st["email"]
    if body.sid:
        with connect(settings.database_url or "", settings.database_schema) as conn:
            st = conn.execute("SELECT * FROM ext_students WHERE sid = %s", (body.sid,)).fetchone()
        if st is None:
            raise HTTPException(404, "ไม่พบรหัสนิสิตในข้อมูล SUPREME")
        name = name or st["name_th"]
    if not email:
        raise HTTPException(400, "ต้องมีอีเมล หรือเลือกบุคลากรจาก HURIS")
    return _run(
        users.save, email, user.email, create=True, name=name, roles=body.roles,
        units=body.units, expires_at=body.expires_at and body.expires_at.isoformat(),
        pid=body.pid, sid=body.sid,
    )  # fmt: skip


@router.post("/invite", status_code=201)
def invite(
    body: Invite,
    users: UserStore = Depends(get_users),
    settings: Settings = Depends(get_settings),
    user: User = Depends(REQUIRE_ADD),
) -> dict[str, Any]:
    """Outside evaluator (US-U-02): an account with an end date, and the invitation e-mail."""
    from ocl_api.mail import Outbox

    if body.expires_at < datetime.now(timezone(timedelta(hours=7))).date():  # Thai day
        raise HTTPException(400, "วันสิ้นสุดสิทธิ์ต้องไม่ใช่วันที่ผ่านมาแล้ว")
    out = _run(
        users.save, body.email, user.email, create=True, name=body.name, roles=body.roles,
        units=body.units, expires_at=body.expires_at.isoformat(), kind="external",
    )  # fmt: skip
    Outbox(settings.database_url or "", settings.database_schema).send(
        out["email"],
        "คำเชิญเข้าใช้ระบบบริหารจัดการหลักสูตรและการรับรองสมรรถนะดิจิทัล มศว",
        f"เรียน {body.name}\n\nมหาวิทยาลัยศรีนครินทรวิโรฒเชิญท่านเข้าใช้ระบบเพื่อประเมินหลักสูตร "
        f"สิทธิ์ใช้งานถึงวันที่ {body.expires_at.isoformat()} "
        "วิธีเข้าสู่ระบบด้วยรหัสยืนยันทางอีเมลจะแจ้งให้ทราบในอีเมลฉบับถัดไป",
        kind="invite",
        by=user.email,
        ref=f"user:{out['email']}",
    )
    return out


@router.put("/{email}")
def edit_user(
    email: str,
    body: UserEdit,
    users: UserStore = Depends(get_users),
    user: User = Depends(REQUIRE_EDIT),
) -> dict[str, Any]:
    return _run(
        users.save, email, user.email, create=False, name=body.name, roles=body.roles,
        units=body.units, expires_at=body.expires_at and body.expires_at.isoformat(),
        clear_expiry=body.clear_expiry,
    )  # fmt: skip


@router.post("/{email}/active")
def set_active(
    email: str,
    body: Active,
    users: UserStore = Depends(get_users),
    user: User = Depends(REQUIRE_EDIT),
) -> dict[str, Any]:
    return _run(users.set_active_by, email, body.active, user.email)
