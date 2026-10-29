"""คู่มือหลักสูตร list/detail and the workflow transitions (needs Postgres)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ocl_api.auth import REQUIRE_IMPORT_READ, User, current_user, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.curricula import ACTIONS, BOOK_MAX, STATUSES, CurriculumStore
from ocl_api.curriculum_form import spec
from ocl_api.jobs import make_store
from ocl_api.sections import SECTIONS

router = APIRouter(prefix="/api/curricula", tags=["curricula"])

REQUIRE_VIEW = require_menu("c1")  # คู่มือหลักสูตร
REQUIRE_ADD = require_menu("c1", action="add")
REQUIRE_LOOKUPS = require_menu("u1", action="edit")  # the administrators' basic data


def get_curricula(settings: Settings = Depends(get_settings)) -> CurriculumStore:
    if not settings.database_url:
        raise HTTPException(503, "workflow คู่มือหลักสูตรต้องการ DATABASE_URL")
    return CurriculumStore(settings.database_url, settings.database_schema, make_store(settings))


class Transition(BaseModel):
    action: str
    note: str | None = None
    section: str | None = None
    checked: bool = True


def scoped(
    draft_id: int, cs: CurriculumStore = Depends(get_curricula), user: User = Depends(REQUIRE_VIEW)
) -> User:
    """REQUIRE_VIEW plus the user's ขอบเขตข้อมูล for this curriculum (FS-2e)."""
    cs.check_visible(draft_id, user)
    return user


@router.get("")
def list_curricula(
    cs: CurriculumStore = Depends(get_curricula), user: User = Depends(REQUIRE_VIEW)
) -> dict[str, Any]:
    out = cs.list(user)
    out["statuses"] = STATUSES
    out["actions"] = ACTIONS
    return out


@router.get("/form")
def form_spec(
    cs: CurriculumStore = Depends(get_curricula), _: User = Depends(REQUIRE_VIEW)
) -> dict[str, Any]:
    """The cur-edit form (หมวด 0 1 2 5) with the options the administrators added."""
    return {"sections": spec(cs.options()), "labels": SECTIONS}


class NewOption(BaseModel):
    key: str
    value: str


@router.post("/form/options")
def add_option(
    body: NewOption,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(REQUIRE_LOOKUPS),
) -> dict[str, Any]:
    """BRD 01 US-M1-04: list options come from basic data the administrators can extend."""
    cs.add_option(body.key, body.value, user)
    return {"sections": spec(cs.options()), "labels": SECTIONS}


REQUIRE_DASH = require_menu("d1")  # แดชบอร์ดหลักสูตร
REQUIRE_REMIND = require_menu("d1", action="edit")


@router.get("/dashboard")
def dashboard(
    faculty: str = "",
    level: str = "",
    year: int | None = None,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(REQUIRE_DASH),
) -> dict[str, Any]:
    """แดชบอร์ดหลักสูตร (US-M1-01 02): counts within the user's ขอบเขตข้อมูล."""
    return cs.dashboard(user, faculty, level, year)


@router.post("/{draft_id}/remind")
def remind(
    draft_id: int,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(REQUIRE_REMIND),
) -> dict[str, Any]:
    """ปุ่ม "แจ้งเตือน" of the longest-pending list: once a day per curriculum (outbox dedupe)."""
    cs.check_visible(draft_id, user)
    return cs.remind(draft_id, user)


@router.get("/courses/catalog")
def course_catalog(
    q: str = "",
    exclude: int | None = None,
    cs: CurriculumStore = Depends(get_curricula),
    _: User = Depends(REQUIRE_VIEW),
) -> list[dict[str, Any]]:
    """เลือกรายวิชาจากฐานข้อมูลกลาง (US-M1-20): courses of the other curricula."""
    return cs.course_catalog(q, exclude)


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
    draft_id: int, cs: CurriculumStore = Depends(get_curricula), _: User = Depends(scoped)
) -> dict[str, Any]:
    return cs.sections(draft_id)


@router.put("/{draft_id}/sections/{n}")
def put_section(
    draft_id: int,
    n: str,
    body: SectionEdit,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(scoped),
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
    cs.check_visible(draft_id, user)
    return cs.transition(
        draft_id, body.action, user, note=body.note, section=body.section, checked=body.checked
    )


@router.post("/{draft_id}/book")
async def upload_book(
    draft_id: int,
    file: UploadFile = File(...),
    cs: CurriculumStore = Depends(get_curricula),
    settings: Settings = Depends(get_settings),
    user: User = Depends(scoped),
) -> dict[str, Any]:
    """ไฟล์เล่มหลักสูตรที่อนุมัติแล้ว (หมวด 0): same rights as editing หมวด 0."""
    content = await file.read(BOOK_MAX + 1)
    return cs.save_book(draft_id, file.filename or "book.pdf", content, user, settings.data_dir)


@router.get("/{draft_id}/book")
def download_book(
    draft_id: int,
    cs: CurriculumStore = Depends(get_curricula),
    settings: Settings = Depends(get_settings),
    _: User = Depends(scoped),
) -> FileResponse:
    path, name = cs.book_path(draft_id, settings.data_dir)
    return FileResponse(path, media_type="application/pdf", filename=name)


@router.get("/{draft_id}/teachers/check")
def teacher_check(
    draft_id: int, cs: CurriculumStore = Depends(get_curricula), _: User = Depends(scoped)
) -> dict[str, Any]:
    return cs.teacher_check(draft_id)
