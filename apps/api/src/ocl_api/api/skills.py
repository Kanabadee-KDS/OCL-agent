"""Skill Transcript (FS-5 · M3): menus s1 s2 s2b s3 s4 s5 s6, d3, and m1 m2 for students;
plus the public check of an issued document (BR-M3-05), which needs no sign-in."""

from __future__ import annotations

import io
import re
from typing import Any
from urllib.parse import quote

import segno
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel

from ocl_api.assess import AssessStore
from ocl_api.auth import User, current_user, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.skills import SkillError, SkillStore

router = APIRouter(prefix="/api/skills", tags=["skills"])
public = APIRouter(prefix="/api/public", tags=["public"])

ANY = require_menu("s1", "s2", "s2b", "s3", "s4", "s5", "s6", "d3", "m1", "m2")
DB, DB_ADD, DB_EDIT = (require_menu("s1", action=a) for a in ("view", "add", "edit"))
ASSIGN, ASSIGN_EDIT = require_menu("s2"), require_menu("s2", action="edit")
SETS, SETS_EDIT = require_menu("s2b", "s3"), require_menu("s2b", action="edit")
MAP, MAP_EDIT = require_menu("s3"), require_menu("s3", action="edit")
ASSESS, ASSESS_EDIT = require_menu("s4"), require_menu("s4", action="edit")
PORT = require_menu("s5", "s6")
ISSUE, ISSUE_ADD = require_menu("s6"), require_menu("s6", action="add")
DASH, REMIND = require_menu("d3"), require_menu("d3", action="edit")
ME, MY_DOC = require_menu("m1"), require_menu("m2")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_XLSX = 5 * 1024 * 1024


def _db(settings: Settings) -> tuple[str, str | None]:
    if not settings.database_url:
        raise HTTPException(503, "Skill Transcript ต้องการ DATABASE_URL")
    return settings.database_url, settings.database_schema


def get_skills(settings: Settings = Depends(get_settings)) -> SkillStore:
    return SkillStore(*_db(settings))


def get_assess(settings: Settings = Depends(get_settings)) -> AssessStore:
    return AssessStore(*_db(settings))


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except SkillError as e:
        raise HTTPException(e.status, str(e)) from e


def _term(slug: str) -> str:
    return slug.replace("-", "/")


def _xlsx(data: bytes, name: str) -> Response:
    # a Thai course code in the name needs RFC 5987; the plain name is for old browsers
    cd = f"attachment; filename=\"skill.xlsx\"; filename*=UTF-8''{quote(name)}"
    return Response(data, media_type=XLSX, headers={"content-disposition": cd})


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > MAX_XLSX:
        raise HTTPException(413, "ไฟล์ใหญ่เกิน 5 MB")
    return data


class SkillBody(BaseModel):
    code: str
    cat: str
    name_th: str
    name_en: str | None = None
    definition: str | None = None
    scope: str = "program"
    tools: list[str] = []
    sources: list[str] = []
    rubric: list[str] = []


class DbPermBody(BaseModel):
    who: str
    cats: list[str]
    unit_scope: str = "program"


class AssignRow(BaseModel):
    pid: str
    role: str
    perms: list[str] = []
    scope: str = "all"
    courses: list[str] = []


class SetBody(BaseModel):
    skills: list[str]
    cohort_from: int | None = None


class ReviseBody(BaseModel):
    cohort_from: int | None = None


class CertifyBody(BaseModel):
    ok: bool
    note: str = ""


class CellsBody(BaseModel):
    cells: dict[str, list[str]]


class ScoresBody(BaseModel):
    scores: dict[str, dict[str, float | None]]


class NoteBody(BaseModel):
    note: str = ""


class IssueBody(BaseModel):
    sids: list[str]


class RemindBody(BaseModel):
    course_code: str | None = None
    section: str | None = None


# ---------- FS-5a ฐานข้อมูล Skill ----------


@router.get("")
def skills(ss: SkillStore = Depends(get_skills), user: User = Depends(ANY)) -> dict[str, Any]:
    return {"items": ss.skills(), "settings": ss.settings(), "rights": ss.db_rights(user)}


@router.post("", status_code=201)
def add_skill(
    body: SkillBody, ss: SkillStore = Depends(get_skills), user: User = Depends(DB_ADD)
) -> dict[str, Any]:
    return _run(ss.save_skill, body.model_dump(), user, create=True)


@router.put("/{code}")
def save_skill(
    code: str, body: SkillBody, ss: SkillStore = Depends(get_skills), user: User = Depends(DB_EDIT)
) -> dict[str, Any]:
    if body.code.strip().upper() != code.upper():
        raise HTTPException(400, "เปลี่ยนรหัส Skill ไม่ได้")
    return _run(ss.save_skill, body.model_dump(), user, create=False)


@router.post("/{code}/active")
def set_active(
    code: str, on: bool, ss: SkillStore = Depends(get_skills), user: User = Depends(DB_EDIT)
) -> dict[str, Any]:
    return _run(ss.set_active, code, on, user)


@router.get("/template.xlsx")
def template(ss: SkillStore = Depends(get_skills), _: User = Depends(DB)) -> Response:
    return _xlsx(ss.template_xlsx(), "skill-template.xlsx")


@router.post("/import")
async def import_skills(
    file: UploadFile = File(...), ss: SkillStore = Depends(get_skills), user: User = Depends(DB_ADD)
) -> dict[str, Any]:
    return _run(ss.import_xlsx, await _read(file), user)


@router.put("/settings/{key}")
def save_setting(
    key: str,
    body: dict[str, Any],
    ss: SkillStore = Depends(get_skills),
    user: User = Depends(DB_EDIT),
) -> dict[str, Any]:
    if not user.sees_all():
        raise HTTPException(403, "เกณฑ์ของมหาวิทยาลัยแก้ได้เฉพาะส่วนกลาง")
    return _run(ss.save_setting, key, body.get("data"), user.email)


@router.get("/db-perms")
def db_perms(ss: SkillStore = Depends(get_skills), _: User = Depends(ASSIGN)) -> dict[str, Any]:
    return {"items": ss.db_perms(), "groups": ss.groups()}


def _staff_only(user: User) -> None:
    if not user.sees_all():
        raise HTTPException(403, "สิทธิ์เพิ่ม Skill ในฐานข้อมูลกำหนดได้เฉพาะส่วนกลาง")


@router.post("/db-perms")
def add_db_perm(
    body: DbPermBody, ss: SkillStore = Depends(get_skills), user: User = Depends(ASSIGN_EDIT)
) -> list[dict]:
    _staff_only(user)
    return _run(ss.save_db_perm, None, body.who, body.cats, body.unit_scope, user.email)


@router.put("/db-perms/{pid}")
def save_db_perm(
    pid: int,
    body: DbPermBody,
    ss: SkillStore = Depends(get_skills),
    user: User = Depends(ASSIGN_EDIT),
) -> list[dict]:
    _staff_only(user)
    return _run(ss.save_db_perm, pid, body.who, body.cats, body.unit_scope, user.email)


@router.delete("/db-perms/{pid}")
def delete_db_perm(
    pid: int, ss: SkillStore = Depends(get_skills), user: User = Depends(ASSIGN_EDIT)
) -> list[dict]:
    _staff_only(user)
    return ss.delete_db_perm(pid)


# ---------- FS-5b ผู้รับผิดชอบ และชุด Skill ----------


@router.get("/assign")
def assign_overview(
    ss: SkillStore = Depends(get_skills), user: User = Depends(ASSIGN)
) -> dict[str, Any]:
    return ss.assign_overview(user)


@router.put("/assign/{cid}")
def set_assign(
    cid: int,
    body: list[AssignRow],
    ss: SkillStore = Depends(get_skills),
    user: User = Depends(ASSIGN_EDIT),
) -> list[dict]:
    return _run(ss.set_assign, cid, [r.model_dump() for r in body], user)


@router.get("/sets")
def sets(ss: SkillStore = Depends(get_skills), user: User = Depends(SETS)) -> dict[str, Any]:
    return ss.sets_overview(user)


@router.get("/sets/{cid}")
def skill_set(
    cid: int, ss: SkillStore = Depends(get_skills), user: User = Depends(SETS)
) -> dict[str, Any]:
    return _run(ss.skill_set, cid, user)


@router.put("/sets/{cid}")
def save_set(
    cid: int, body: SetBody, ss: SkillStore = Depends(get_skills), user: User = Depends(SETS_EDIT)
) -> dict[str, Any]:
    return _run(ss.save_set, cid, body.skills, body.cohort_from, user)


@router.post("/sets/{cid}/own")
def add_own(
    cid: int, body: SkillBody, ss: SkillStore = Depends(get_skills), user: User = Depends(SETS_EDIT)
) -> dict[str, Any]:
    return _run(ss.add_own_skill, cid, body.model_dump(), user)


@router.post("/sets/{cid}/submit")
def submit_set(
    cid: int, ss: SkillStore = Depends(get_skills), user: User = Depends(SETS_EDIT)
) -> dict[str, Any]:
    return _run(ss.submit_set, cid, user)


@router.post("/sets/{cid}/certify")
def certify_set(
    cid: int, body: CertifyBody, ss: SkillStore = Depends(get_skills), user: User = Depends(SETS)
) -> dict[str, Any]:
    return _run(ss.certify_set, cid, body.ok, body.note, user)


@router.post("/sets/{cid}/revise")
def revise_set(
    cid: int,
    body: ReviseBody,
    ss: SkillStore = Depends(get_skills),
    user: User = Depends(SETS_EDIT),
) -> dict[str, Any]:
    return _run(ss.revise_set, cid, body.cohort_from, user)


# ---------- FS-5c Skill Mapping ----------


@router.get("/terms")
def terms(ss: SkillStore = Depends(get_skills), _: User = Depends(ANY)) -> list[str]:
    return ss.terms()


@router.get("/map/{slug}")
def map_curricula(
    slug: str, ss: SkillStore = Depends(get_skills), user: User = Depends(MAP)
) -> list[dict]:
    return [
        {"id": c["id"], "name_th": c["name_th"], "faculty": c["faculty"]}
        for c in ss.curricula(user)
    ]


@router.get("/map/{slug}/{cid}")
def mapping(
    slug: str, cid: int, ss: SkillStore = Depends(get_skills), user: User = Depends(MAP)
) -> dict[str, Any]:
    return _run(ss.mapping, _term(slug), cid, user)


@router.put("/map/{slug}/{cid}")
def save_mapping(
    slug: str,
    cid: int,
    body: CellsBody,
    ss: SkillStore = Depends(get_skills),
    user: User = Depends(MAP_EDIT),
) -> dict[str, Any]:
    return _run(ss.save_mapping, _term(slug), cid, body.cells, user)


@router.post("/map/{slug}/{cid}/copy")
def copy_mapping(
    slug: str, cid: int, ss: SkillStore = Depends(get_skills), user: User = Depends(MAP_EDIT)
) -> dict[str, Any]:
    return _run(ss.copy_mapping, _term(slug), cid, user)


@router.post("/map/{slug}/{cid}/submit")
def submit_mapping(
    slug: str, cid: int, ss: SkillStore = Depends(get_skills), user: User = Depends(MAP_EDIT)
) -> dict[str, Any]:
    return _run(ss.submit_mapping, _term(slug), cid, user)


@router.post("/map/{slug}/{cid}/certify")
def certify_mapping(
    slug: str,
    cid: int,
    body: CertifyBody,
    ss: SkillStore = Depends(get_skills),
    user: User = Depends(MAP),
) -> dict[str, Any]:
    return _run(ss.certify_mapping, _term(slug), cid, body.ok, body.note, user)


# ---------- FS-5d บันทึกประเมิน ----------


@router.get("/assess/{slug}")
def sections(
    slug: str, st: AssessStore = Depends(get_assess), user: User = Depends(ASSESS)
) -> dict[str, Any]:
    return _run(st.sections, _term(slug), user)


@router.get("/assess/{slug}/{code}/{sec}")
def section(
    slug: str,
    code: str,
    sec: str,
    st: AssessStore = Depends(get_assess),
    user: User = Depends(ASSESS),
) -> dict[str, Any]:
    return _run(st.section, _term(slug), code, sec, user)


@router.put("/assess/{slug}/{code}/{sec}")
def save_scores(
    slug: str,
    code: str,
    sec: str,
    body: ScoresBody,
    st: AssessStore = Depends(get_assess),
    user: User = Depends(ASSESS_EDIT),
) -> dict[str, Any]:
    return _run(st.save_scores, _term(slug), code, sec, body.scores, user)


@router.post("/assess/{slug}/{code}/{sec}/confirm")
def confirm(
    slug: str,
    code: str,
    sec: str,
    st: AssessStore = Depends(get_assess),
    user: User = Depends(ASSESS_EDIT),
) -> dict[str, Any]:
    return _run(st.confirm, _term(slug), code, sec, user)


@router.post("/assess/{slug}/{code}/{sec}/reopen")
def reopen(
    slug: str,
    code: str,
    sec: str,
    body: NoteBody,
    st: AssessStore = Depends(get_assess),
    user: User = Depends(ASSESS_EDIT),
) -> dict[str, Any]:
    return _run(st.reopen, _term(slug), code, sec, body.note, user)


@router.get("/assess/{slug}/{code}/{sec}/form.xlsx")
def form_xlsx(
    slug: str,
    code: str,
    sec: str,
    st: AssessStore = Depends(get_assess),
    user: User = Depends(ASSESS),
) -> Response:
    return _xlsx(_run(st.form_xlsx, _term(slug), code, sec, user), f"skill-{code}-{sec}.xlsx")


@router.post("/assess/{slug}/{code}/{sec}/import")
async def import_scores(
    slug: str,
    code: str,
    sec: str,
    file: UploadFile = File(...),
    st: AssessStore = Depends(get_assess),
    user: User = Depends(ASSESS_EDIT),
) -> dict[str, Any]:
    return _run(st.import_xlsx, _term(slug), code, sec, await _read(file), user)


# ---------- FS-5e Portfolio และหน้านิสิต ----------


@router.get("/portfolio")
def portfolio_list(st: AssessStore = Depends(get_assess), user: User = Depends(PORT)) -> dict:
    return st.portfolio_list(user)


@router.get("/portfolio/{sid}")
def portfolio(
    sid: str, st: AssessStore = Depends(get_assess), user: User = Depends(PORT)
) -> dict[str, Any]:
    return _run(st.portfolio, sid, user)


@router.get("/portfolio/{sid}/transcript")
def student_transcript(
    sid: str, st: AssessStore = Depends(get_assess), user: User = Depends(PORT)
) -> dict[str, Any]:
    return _run(st.transcript, sid, user)


def _own(user: User) -> str:
    if not user.sid:
        raise HTTPException(404, "บัญชีนี้ยังไม่ได้ผูกกับรหัสนิสิต")
    return user.sid


@router.get("/me")
def my_portfolio(st: AssessStore = Depends(get_assess), user: User = Depends(ME)) -> dict:
    return _run(st.portfolio, _own(user), None)


@router.get("/me/transcript")
def my_transcript(st: AssessStore = Depends(get_assess), user: User = Depends(MY_DOC)) -> dict:
    return _run(st.transcript, _own(user), None)


ORIGIN_RE = re.compile(r"^https?://[A-Za-z0-9.\-:\[\]]+$")


@router.get("/transcripts/{no}/qr.svg")
def qr(
    no: str,
    origin: str,
    st: AssessStore = Depends(get_assess),
    user: User = Depends(current_user),
) -> Response:
    """QR of the public check page of an issued document, for the document itself."""
    if not ORIGIN_RE.match(origin):
        raise HTTPException(400, "origin ไม่ถูกต้อง")
    with st._conn() as conn:
        r = conn.execute("SELECT sid FROM skill_transcripts WHERE no = %s", (no,)).fetchone()
    if r is None:
        raise HTTPException(404, "ไม่พบเอกสารเลขที่นี้")
    own = user.sid == r["sid"] and user.can_do("m2")
    if not own and not any(user.can_do(m) for m in ("s5", "s6")):
        raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์ในเมนูนี้")
    if not own:
        _run(st.portfolio, r["sid"], user)  # in the user's scope
    buf = io.BytesIO()  # a standalone file (with xmlns), so an <img> can show it
    segno.make(f"{origin}/verify/{no}", error="m").save(buf, kind="svg", scale=4, border=2)
    return Response(buf.getvalue(), media_type="image/svg+xml")


# ---------- FS-5f ออกเอกสาร ----------


@router.get("/issue")
def graduates(st: AssessStore = Depends(get_assess), user: User = Depends(ISSUE)) -> dict:
    return st.graduates(user)


@router.post("/issue")
def issue(
    body: IssueBody, st: AssessStore = Depends(get_assess), user: User = Depends(ISSUE_ADD)
) -> dict[str, Any]:
    return _run(st.issue, body.sids, user)


@router.get("/register")
def register(st: AssessStore = Depends(get_assess), user: User = Depends(ISSUE)) -> list[dict]:
    return st.register(user)


@public.get("/transcripts/{no}")
def verify(no: str, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """BR-M3-05: anyone may check a document by its number (QR) without signing in."""
    return _run(AssessStore(*_db(settings)).verify, no)


# ---------- FS-5g แดชบอร์ด ----------


@router.get("/dashboard/{slug}")
def dashboard(
    slug: str, st: AssessStore = Depends(get_assess), user: User = Depends(DASH)
) -> dict[str, Any]:
    return _run(st.dashboard, _term(slug), user)


@router.post("/dashboard/{slug}/remind")
def remind(
    slug: str,
    body: RemindBody,
    st: AssessStore = Depends(get_assess),
    user: User = Depends(REMIND),
) -> dict[str, Any]:
    return _run(st.remind, _term(slug), user, body.course_code, body.section)
