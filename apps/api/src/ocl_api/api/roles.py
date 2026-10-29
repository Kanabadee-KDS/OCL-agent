"""กำหนดกลุ่มสิทธิ์การใช้งาน (menu u1): list, create by copying, edit the matrix, delete."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import User, clear_user_cache, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.perms import ACTIONS, SCOPE_KINDS
from ocl_api.roles import RoleError, RoleStore

router = APIRouter(prefix="/api/roles", tags=["roles"])

REQUIRE_VIEW = require_menu("u1")
REQUIRE_ADD = require_menu("u1", action="add")
REQUIRE_EDIT = require_menu("u1", action="edit")
REQUIRE_DELETE = require_menu("u1", action="delete")


def get_roles(settings: Settings = Depends(get_settings)) -> RoleStore:
    if not settings.database_url:
        raise HTTPException(503, "กลุ่มสิทธิ์ต้องการ DATABASE_URL")
    return RoleStore(settings.database_url, settings.database_schema)


class NewRole(BaseModel):
    name: str
    copy_from: str | None = None


class RoleEdit(BaseModel):
    name: str | None = None
    scope_kind: str | None = None
    perms: dict[str, list[str]] | None = None
    auto_from_teachers: bool | None = None
    notify_on_change: bool | None = None


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except RoleError as e:
        raise HTTPException(e.status, str(e)) from e


def _detail(group: dict[str, Any]) -> dict[str, Any]:
    """One group as the role-edit page reads it, from GET, POST and PUT alike."""
    return {**group, "actions": ACTIONS, "scopes": SCOPE_KINDS}


@router.get("")
def list_roles(rs: RoleStore = Depends(get_roles), _: User = Depends(REQUIRE_VIEW)) -> dict:
    return {"items": rs.list(), "actions": ACTIONS, "scopes": SCOPE_KINDS}


@router.get("/{role_id}")
def get_role(
    role_id: str, rs: RoleStore = Depends(get_roles), _: User = Depends(REQUIRE_VIEW)
) -> dict[str, Any]:
    return _detail(_run(rs.get, role_id))


@router.post("", status_code=201)
def create_role(
    body: NewRole, rs: RoleStore = Depends(get_roles), user: User = Depends(REQUIRE_ADD)
) -> dict[str, Any]:
    out = _run(rs.create, body.name, body.copy_from, user.email)
    clear_user_cache()
    return _detail(out)


@router.put("/{role_id}")
def update_role(
    role_id: str,
    body: RoleEdit,
    rs: RoleStore = Depends(get_roles),
    user: User = Depends(REQUIRE_EDIT),
) -> dict[str, Any]:
    out = _run(rs.update, role_id, user.email, **body.model_dump())
    clear_user_cache()  # this process applies it now; others within USER_CACHE_TTL
    return _detail(out)


@router.delete("/{role_id}", status_code=204)
def delete_role(
    role_id: str, rs: RoleStore = Depends(get_roles), user: User = Depends(REQUIRE_DELETE)
) -> None:
    _run(rs.delete, role_id, user.email)
    clear_user_cache()
