"""ฐานข้อมูลรายวิชากลาง (FS-3a · US-M1-18): menu c5 บริหารรายวิชา."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import User, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.courses import CourseError, CourseStore

router = APIRouter(prefix="/api/courses", tags=["courses"])

VIEW, ADD = require_menu("c5"), require_menu("c5", action="add")
EDIT, DELETE = require_menu("c5", action="edit"), require_menu("c5", action="delete")


def get_courses(settings: Settings = Depends(get_settings)) -> CourseStore:
    if not settings.database_url:
        raise HTTPException(503, "ฐานข้อมูลรายวิชากลางต้องการ DATABASE_URL")
    return CourseStore(settings.database_url, settings.database_schema)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except CourseError as e:
        raise HTTPException(e.status, str(e)) from e


class CourseBody(BaseModel):
    code_th: str | None = None
    code_en: str | None = None
    name_th: str | None = None
    name_en: str | None = None
    transcript_th: str | None = None
    transcript_en: str | None = None
    credit_text: str | None = None
    course_type: str | None = None
    module: str | None = None
    unit: str | None = None
    major: str | None = None
    reg_no: str | None = None
    telebank: str | None = None
    status: str | None = None
    note: str | None = None
    description_th: str | None = None
    description_en: str | None = None
    new_version: bool = False  # PUT: keep the current Version for the curricula that use it


@router.get("")
def list_courses(cs: CourseStore = Depends(get_courses), _: User = Depends(VIEW)) -> dict[str, Any]:
    return cs.list()


@router.get("/{code}")
def get_course(
    code: str, cs: CourseStore = Depends(get_courses), _: User = Depends(VIEW)
) -> dict[str, Any]:
    return _run(cs.get, code)


@router.post("", status_code=201)
def create_course(
    body: CourseBody,
    cs: CourseStore = Depends(get_courses),
    user: User = Depends(ADD),
) -> dict[str, Any]:
    return _run(cs.create, body.model_dump(exclude={"new_version"}), user.email)


@router.put("/{code}")
def update_course(
    code: str, body: CourseBody, cs: CourseStore = Depends(get_courses),
    user: User = Depends(EDIT),
) -> dict[str, Any]:  # fmt: skip
    return _run(
        cs.update,
        code,
        body.model_dump(exclude={"new_version", "code_th"}),
        user.email,
        body.new_version,
    )


@router.delete("/{code}", status_code=204)
def delete_course(
    code: str,
    cs: CourseStore = Depends(get_courses),
    _: User = Depends(DELETE),
) -> None:
    _run(cs.delete, code)
