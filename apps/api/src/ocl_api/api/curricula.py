"""คู่มือหลักสูตร list/detail and the workflow transitions (needs Postgres)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import REQUIRE_IMPORT_READ, User, current_user, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.curricula import ACTIONS, STATUSES, CurriculumStore
from ocl_api.jobs import make_store

router = APIRouter(prefix="/api/curricula", tags=["curricula"])

REQUIRE_VIEW = require_menu("c1")  # คู่มือหลักสูตร
REQUIRE_ADD = require_menu("c1", action="add")


def get_curricula(settings: Settings = Depends(get_settings)) -> CurriculumStore:
    if not settings.database_url:
        raise HTTPException(503, "workflow คู่มือหลักสูตรต้องการ DATABASE_URL")
    return CurriculumStore(settings.database_url, settings.database_schema, make_store(settings))


class Transition(BaseModel):
    action: str
    note: str | None = None
    section: str | None = None
    checked: bool = True


@router.get("")
def list_curricula(
    cs: CurriculumStore = Depends(get_curricula), _: User = Depends(REQUIRE_VIEW)
) -> dict[str, Any]:
    out = cs.list()
    out["statuses"] = STATUSES
    out["actions"] = ACTIONS
    return out


@router.get("/by-job/{job_id}")
def by_job(
    job_id: str,
    cs: CurriculumStore = Depends(get_curricula),
    _: User = Depends(REQUIRE_IMPORT_READ),
) -> dict[str, Any]:
    d = cs.by_job(job_id)
    if d is None:
        raise HTTPException(404, "งานนี้ยังไม่ได้บันทึกเข้าระบบ")
    return d


@router.get("/{draft_id}")
def get_curriculum(
    draft_id: int,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(REQUIRE_VIEW),
) -> dict[str, Any]:
    return cs.get(draft_id, user)


class NewCurriculum(BaseModel):
    name_th: str
    level: str | None = None
    faculty: str | None = None


class SectionEdit(BaseModel):
    data: dict[str, Any]


@router.post("", status_code=201)
def create_curriculum(
    body: NewCurriculum,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(REQUIRE_ADD),
) -> dict[str, Any]:
    """เพิ่มหลักสูตร: a blank draft (US-M1-03); the form fills it (FS-2b)."""
    return cs.create(body.name_th, body.level, body.faculty, user)


@router.get("/{draft_id}/sections")
def get_sections(
    draft_id: int, cs: CurriculumStore = Depends(get_curricula), _: User = Depends(REQUIRE_VIEW)
) -> dict[str, Any]:
    return cs.sections(draft_id)


@router.put("/{draft_id}/sections/{n}")
def put_section(
    draft_id: int,
    n: str,
    body: SectionEdit,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(REQUIRE_VIEW),
) -> dict[str, Any]:
    """Replace one หมวด; who may do it depends on the status and the approval flow."""
    return cs.save_section(draft_id, n, body.data, user)


@router.post("/{draft_id}/transition")
def transition(
    draft_id: int,
    body: Transition,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    return cs.transition(
        draft_id, body.action, user, note=body.note, section=body.section, checked=body.checked
    )
