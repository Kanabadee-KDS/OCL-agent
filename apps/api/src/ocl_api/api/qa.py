"""ประเมินผลหลักสูตรตามเกณฑ์มาตรฐาน (FS-6 · M4): menus q1 (รอบ) q2 (เกณฑ์) q1b (ผู้บันทึก/
ผู้ยืนยัน) q3 (ตรวจสอบข้อมูล) q4 (สรุปผล). Rounds, criteria and assignments are set by the
central office (ฝ่ายพัฒนาคุณภาพ); recorders, confirmers and evaluators act on their curricula."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import User, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.qa import QaError, QaStore

router = APIRouter(prefix="/api/qa", tags=["qa"])

ANY = require_menu("q1", "q2", "q1b", "q3", "q4")
ROUNDS, ROUNDS_ADD, ROUNDS_EDIT = (require_menu("q1", action=a) for a in ("view", "add", "edit"))
CRIT, CRIT_ADD, CRIT_EDIT = (require_menu("q2", action=a) for a in ("view", "add", "edit"))
ASSIGN, ASSIGN_EDIT = require_menu("q1b"), require_menu("q1b", action="edit")
CHECK, CHECK_EDIT = require_menu("q3"), require_menu("q3", action="edit")
RESULT = require_menu("q4")
READ_DOC = require_menu("q3", "q4")


def get_qa(settings: Settings = Depends(get_settings)) -> QaStore:
    if not settings.database_url:
        raise HTTPException(503, "การประเมินหลักสูตรต้องการ DATABASE_URL")
    return QaStore(settings.database_url, settings.database_schema)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except QaError as e:
        raise HTTPException(e.status, str(e)) from e


def _staff(user: User) -> None:
    if not user.sees_all():
        raise HTTPException(403, "ตั้งค่าการประเมินได้เฉพาะส่วนกลาง (ฝ่ายพัฒนาคุณภาพ)")


class CriterionBody(BaseModel):
    set_year: int
    no: int
    title: str
    detail: str | None = None
    sources: list[str] = []
    level: str = "all"
    rule: str = "none"
    active: bool = True


class ProgramRow(BaseModel):
    curriculum_id: int
    set_year: int
    evaluators: list[str] = []


class RoundBody(BaseModel):
    year: int
    name: str | None = None
    starts_on: str | None = None
    ends_on: str | None = None
    programs: list[ProgramRow] = []


class NoteBody(BaseModel):
    note: str = ""


class AssignBody(BaseModel):
    recorders: list[str] = []
    confirmer: str | None = None


class NotesBody(BaseModel):
    notes: dict[str, str]


class ConfirmBody(BaseModel):
    ok: bool
    note: str = ""


class EvaluateBody(BaseModel):
    results: dict[str, dict[str, str]]


# ---------- FS-6a เกณฑ์และรอบ ----------


@router.get("/criteria")
def criteria(qa: QaStore = Depends(get_qa), _: User = Depends(ANY)) -> dict[str, Any]:
    return qa.criteria()


@router.post("/criteria", status_code=201)
def add_criterion(
    body: CriterionBody, qa: QaStore = Depends(get_qa), user: User = Depends(CRIT_ADD)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.save_criterion, None, body.model_dump(), user.email)


@router.put("/criteria/{cid}")
def save_criterion(
    cid: int, body: CriterionBody, qa: QaStore = Depends(get_qa), user: User = Depends(CRIT_EDIT)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.save_criterion, cid, body.model_dump(), user.email)


@router.get("/evaluators")
def evaluators(qa: QaStore = Depends(get_qa), _: User = Depends(ROUNDS)) -> list[dict]:
    return qa.evaluators()


@router.get("/rounds")
def rounds(qa: QaStore = Depends(get_qa), _: User = Depends(ANY)) -> list[dict]:
    return qa.rounds()


@router.get("/candidates")
def candidates(qa: QaStore = Depends(get_qa), _: User = Depends(ROUNDS)) -> list[dict]:
    return qa.candidates()


@router.get("/rounds/{rid}")
def round_(rid: int, qa: QaStore = Depends(get_qa), _: User = Depends(ANY)) -> dict[str, Any]:
    return _run(qa.round, rid)


@router.post("/rounds", status_code=201)
def add_round(
    body: RoundBody, qa: QaStore = Depends(get_qa), user: User = Depends(ROUNDS_ADD)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.save_round, None, body.model_dump(), user)


@router.put("/rounds/{rid}")
def save_round(
    rid: int, body: RoundBody, qa: QaStore = Depends(get_qa), user: User = Depends(ROUNDS_EDIT)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.save_round, rid, body.model_dump(), user)


@router.post("/rounds/{rid}/copy", status_code=201)
def copy_round(
    rid: int, qa: QaStore = Depends(get_qa), user: User = Depends(ROUNDS_ADD)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.copy_round, rid, user)


@router.post("/rounds/{rid}/open")
def open_round(
    rid: int, qa: QaStore = Depends(get_qa), user: User = Depends(ROUNDS_EDIT)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.open_round, rid, user)


@router.post("/rounds/{rid}/close")
def close_round(
    rid: int, body: NoteBody, qa: QaStore = Depends(get_qa), user: User = Depends(ROUNDS_EDIT)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.close_round, rid, user.email, body.note or None)


# ---------- FS-6b ผู้บันทึกและผู้ยืนยัน ----------


@router.get("/rounds/{rid}/assign")
def assign(rid: int, qa: QaStore = Depends(get_qa), _: User = Depends(ASSIGN)) -> dict[str, Any]:
    return _run(qa.assign_overview, rid)


@router.put("/rounds/{rid}/assign/{cid}")
def set_assign(
    rid: int,
    cid: int,
    body: AssignBody,
    qa: QaStore = Depends(get_qa),
    user: User = Depends(ASSIGN_EDIT),
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.set_assign, rid, cid, body.recorders, body.confirmer, user)


@router.post("/rounds/{rid}/assign/copy")
def copy_assign(
    rid: int, qa: QaStore = Depends(get_qa), user: User = Depends(ASSIGN_EDIT)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.copy_assign, rid, user)


@router.post("/rounds/{rid}/assign/notify")
def notify(
    rid: int, qa: QaStore = Depends(get_qa), user: User = Depends(ASSIGN_EDIT)
) -> dict[str, Any]:
    _staff(user)
    return _run(qa.notify, rid, user)


# ---------- FS-6c FS-6d ตรวจสอบ ประเมิน สรุป ----------


@router.get("/rounds/{rid}/programs")
def programs(rid: int, qa: QaStore = Depends(get_qa), user: User = Depends(CHECK)) -> dict:
    return _run(qa.programs, rid, user)


@router.get("/rounds/{rid}/programs/{cid}")
def detail(
    rid: int, cid: int, qa: QaStore = Depends(get_qa), user: User = Depends(READ_DOC)
) -> dict[str, Any]:
    return _run(qa.detail, rid, cid, user)


@router.put("/rounds/{rid}/programs/{cid}/notes")
def save_notes(
    rid: int,
    cid: int,
    body: NotesBody,
    qa: QaStore = Depends(get_qa),
    user: User = Depends(CHECK_EDIT),
) -> dict[str, Any]:
    return _run(qa.save_notes, rid, cid, body.notes, user)


@router.post("/rounds/{rid}/programs/{cid}/send")
def send(
    rid: int, cid: int, qa: QaStore = Depends(get_qa), user: User = Depends(CHECK_EDIT)
) -> dict[str, Any]:
    return _run(qa.send, rid, cid, user)


@router.post("/rounds/{rid}/programs/{cid}/confirm")
def confirm(
    rid: int,
    cid: int,
    body: ConfirmBody,
    qa: QaStore = Depends(get_qa),
    user: User = Depends(CHECK),
) -> dict[str, Any]:
    return _run(qa.confirm, rid, cid, body.ok, body.note, user)


@router.post("/rounds/{rid}/programs/{cid}/evaluate")
def evaluate(
    rid: int,
    cid: int,
    body: EvaluateBody,
    qa: QaStore = Depends(get_qa),
    user: User = Depends(CHECK),
) -> dict[str, Any]:
    return _run(qa.evaluate, rid, cid, body.results, user)


@router.post("/rounds/{rid}/programs/{cid}/return")
def eval_return(
    rid: int, cid: int, body: NoteBody, qa: QaStore = Depends(get_qa), user: User = Depends(CHECK)
) -> dict[str, Any]:
    return _run(qa.eval_return, rid, cid, body.note, user)


@router.get("/rounds/{rid}/summary")
def summary(rid: int, qa: QaStore = Depends(get_qa), user: User = Depends(RESULT)) -> dict:
    return _run(qa.summary, rid, user)


@router.get("/rounds/{rid}/preview")
def preview(
    rid: int,
    cid: int | None = None,
    qa: QaStore = Depends(get_qa),
    user: User = Depends(READ_DOC),
) -> list[dict]:
    return _run(qa.preview, rid, cid, user)
