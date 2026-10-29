"""ทะเบียนบุคคลภายนอก (FS-3b · US-M1-19): menu c4 บริหารบุคคลภายนอก."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import User, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.persons import PersonError, PersonStore

router = APIRouter(prefix="/api/persons", tags=["persons"])

VIEW, ADD = require_menu("c4"), require_menu("c4", action="add")
EDIT, DELETE = require_menu("c4", action="edit"), require_menu("c4", action="delete")


def get_persons(settings: Settings = Depends(get_settings)) -> PersonStore:
    if not settings.database_url:
        raise HTTPException(503, "ทะเบียนบุคคลภายนอกต้องการ DATABASE_URL")
    return PersonStore(settings.database_url, settings.database_schema)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PersonError as e:
        raise HTTPException(e.status, str(e)) from e


class Work(BaseModel):
    title: str = ""
    type: str = "ผลงานวิชาการ"
    year: str | None = None


class PersonBody(BaseModel):
    kind: str
    title_full: str | None = None
    title_short: str | None = None
    position: str | None = None
    name_th: str | None = None
    name_en: str | None = None
    national_id: str | None = None
    org: str | None = None
    email: str | None = None
    tel: str | None = None
    education: list[list[str]] = []  # [level, degree, major, school, country, year]
    works: list[Work] = []
    active: bool = True


@router.get("")
def list_persons(ps: PersonStore = Depends(get_persons), _: User = Depends(VIEW)) -> dict[str, Any]:
    return ps.list()


@router.get("/{pid}")
def get_person(
    pid: str, ps: PersonStore = Depends(get_persons), _: User = Depends(VIEW)
) -> dict[str, Any]:
    return _run(ps.get, pid)


@router.post("", status_code=201)
def add_person(
    body: PersonBody, ps: PersonStore = Depends(get_persons), user: User = Depends(ADD)
) -> dict[str, Any]:
    return _run(ps.save, None, body.model_dump(), user.email)


@router.put("/{pid}")
def edit_person(
    pid: str, body: PersonBody, ps: PersonStore = Depends(get_persons), user: User = Depends(EDIT)
) -> dict[str, Any]:
    return _run(ps.save, pid, body.model_dump(), user.email)


@router.delete("/{pid}", status_code=204)
def delete_person(
    pid: str, ps: PersonStore = Depends(get_persons), _: User = Depends(DELETE)
) -> None:
    _run(ps.delete, pid)
