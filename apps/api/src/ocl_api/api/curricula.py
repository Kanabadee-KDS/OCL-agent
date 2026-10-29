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


@router.get("/persons")
def person_search(
    q: str = "", cs: CurriculumStore = Depends(get_curricula), _: User = Depends(REQUIRE_VIEW)
) -> list[dict[str, Any]]:
    """หมวด 0.2: pick an external person from the register (FS-3b), not typed in a curriculum."""
    from ocl_api.persons import PersonStore

    return PersonStore(cs.url, cs.schema).search(q)


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


class NewCourse(BaseModel):
    code_th: str
    name_th: str
    code_en: str | None = None
    name_en: str | None = None
    credit_text: str | None = None


@router.post("/{draft_id}/courses", status_code=201)
def new_course(
    draft_id: int,
    body: NewCourse,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(scoped),
) -> dict[str, Any]:
    """สร้างรายวิชาใหม่ from a group of หมวด 4 (US-M1-20): a ร่างรายวิชา in the central database
    (FS-3a), by whoever may change this curriculum's courses now."""
    from ocl_api.courses import CourseError, CourseStore

    d = cs.get(draft_id, user)
    if "4" not in d["editable"] or d["limited"].get("4"):
        raise HTTPException(403, "สถานะนี้เพิ่มรายวิชาในหลักสูตรไม่ได้")
    try:
        c = CourseStore(cs.url, cs.schema).create(body.model_dump(), user.email, status="ร่างรายวิชา")
    except CourseError as e:
        raise HTTPException(e.status, str(e)) from e
    return {
        k: c.get(k)
        for k in ("code_th", "code_en", "name_th", "name_en", "credits", "credit_text", "label")
    } | {"version": 1}


@router.get("/{draft_id}/courses/versions")
def course_versions(
    draft_id: int, cs: CurriculumStore = Depends(get_curricula), _: User = Depends(scoped)
) -> dict[str, Any]:
    """Each course of หมวด 4 against the central database: the latest Version, and its content
    so a draft can take it (FS-3 Q2 ก: a verified curriculum keeps its Version)."""
    from ocl_api.courses import CourseStore

    rows = (cs.sections(draft_id).get("4", {}).get("data", {}).get("courses") or {}).get(
        "courses"
    ) or []
    store = CourseStore(cs.url, cs.schema)
    latest = store.latest([str(c.get("code_th") or "") for c in rows if c.get("code_th")])
    out = {}
    for code, x in latest.items():
        v = store.version(code, x["latest"]) or {}
        out[code] = x | {
            k: v.get(k)
            for k in (
                "name_th",
                "name_en",
                "credits",
                "credit_text",
                "description_th",
                "description_en",
            )
        }
    return out


class MatchChoices(BaseModel):
    choices: list[dict[str, Any]]


@router.get("/{draft_id}/match")
def match_proposals(
    draft_id: int, cs: CurriculumStore = Depends(get_curricula), user: User = Depends(scoped)
) -> dict[str, Any]:
    """จับคู่ (US-M1-13): proposals only; nothing is stored until a person confirms."""
    from ocl_api.matching import Matcher

    d = cs.get(draft_id, user)
    secs = cs.sections(draft_id)
    m = Matcher(cs.url, cs.schema)
    return {
        "teachers": m.teachers(secs["0"]["data"]),
        "courses": m.courses(secs["4"]["data"]),
        "editable": {
            "0": "0" in d["editable"],
            "4": "4" in d["editable"] and not d["limited"].get("4"),
        },
    }


@router.post("/{draft_id}/match/teachers")
def match_teachers(
    draft_id: int,
    body: MatchChoices,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(scoped),
) -> dict[str, Any]:
    from ocl_api.matching import Matcher

    s0, n = Matcher(cs.url, cs.schema).apply_teachers(
        cs.sections(draft_id)["0"]["data"], body.choices
    )
    if n:
        cs.save_section(draft_id, "0", s0, user, why=f"จับคู่อาจารย์กับ HURIS/ทะเบียน {n} คน")
    return {"matched": n} | match_proposals(draft_id, cs, user)


@router.post("/{draft_id}/match/courses")
def match_courses(
    draft_id: int,
    body: MatchChoices,
    cs: CurriculumStore = Depends(get_curricula),
    user: User = Depends(scoped),
) -> dict[str, Any]:
    from ocl_api.matching import Matcher

    d = cs.get(draft_id, user)
    if "4" not in d["editable"] or d["limited"].get("4"):  # before the central database changes
        raise HTTPException(403, "สถานะนี้แก้รายวิชาในหลักสูตรไม่ได้")
    s4, n = Matcher(cs.url, cs.schema).apply_courses(
        cs.sections(draft_id)["4"]["data"], body.choices, user
    )
    if n:
        cs.save_section(draft_id, "4", s4, user, why=f"จับคู่รายวิชากับฐานข้อมูลกลาง {n} วิชา")
    return {"matched": n} | match_proposals(draft_id, cs, user)


@router.get("/{draft_id}/teachers/check")
def teacher_check(
    draft_id: int, cs: CurriculumStore = Depends(get_curricula), _: User = Depends(scoped)
) -> dict[str, Any]:
    return cs.teacher_check(draft_id)
