"""แผนและรายงานการจัดการเรียนรู้ (FS-4 · M2): menus p1 (กำหนดผู้บันทึก) p2 (แผน) p4 (รายงาน) d2."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import User, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.m2 import DOCS, M2Error, M2Store

router = APIRouter(prefix="/api/m2", tags=["m2"])

ANY = require_menu("p1", "p2", "p4", "d2")
ASSIGN, ASSIGN_EDIT = require_menu("p1"), require_menu("p1", action="edit")
DASH, REMIND = require_menu("d2"), require_menu("d2", action="edit")


def get_m2(settings: Settings = Depends(get_settings)) -> M2Store:
    if not settings.database_url:
        raise HTTPException(503, "แผนการจัดการเรียนรู้ต้องการ DATABASE_URL")
    return M2Store(settings.database_url, settings.database_schema)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except M2Error as e:
        raise HTTPException(e.status, str(e)) from e


def _term(slug: str) -> str:
    return slug.replace("-", "/")


def _doc_menu(doc: str, user: User, action: str = "view") -> None:
    if doc not in DOCS:
        raise HTTPException(404, "ไม่มีเอกสารนี้")
    if not user.can_do("p2" if doc == "plan" else "p4", action):
        raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์ในเมนูนี้")


class TermBody(BaseModel):
    starts_on: str | None = None
    ends_on: str | None = None
    plan_open: str | None = None
    plan_close: str | None = None
    report_open: str | None = None
    report_close: str | None = None
    target_pct: int = 70


class AssignBody(BaseModel):
    doc: str
    pids: list[str]


class DocBody(BaseModel):
    data: dict[str, Any]


class CertifyBody(BaseModel):
    ok: bool
    note: str | None = None


class RemindBody(BaseModel):
    key: str | None = None
    doc: str | None = None


@router.get("/terms")
def terms(ms: M2Store = Depends(get_m2), _: User = Depends(ANY)) -> list[dict[str, Any]]:
    return ms.terms()


@router.put("/terms/{slug}")
def save_term(
    slug: str, body: TermBody, ms: M2Store = Depends(get_m2), user: User = Depends(ASSIGN_EDIT)
) -> dict[str, Any]:
    return _run(ms.save_term, _term(slug), body.model_dump(), user.email)


@router.post("/terms/{slug}/sync")
def sync(
    slug: str, ms: M2Store = Depends(get_m2), _: User = Depends(ASSIGN_EDIT)
) -> dict[str, Any]:
    return _run(ms.sync, _term(slug))


@router.get("/terms/{slug}/items")
def items(slug: str, ms: M2Store = Depends(get_m2), user: User = Depends(ANY)) -> dict[str, Any]:
    return _run(ms.items, _term(slug), user)


@router.put("/terms/{slug}/items/{key}/assign")
def assign(
    slug: str,
    key: str,
    body: AssignBody,
    ms: M2Store = Depends(get_m2),
    user: User = Depends(ASSIGN_EDIT),
) -> dict[str, Any]:
    return _run(ms.set_assign, _term(slug), key, body.doc, body.pids, user)


@router.post("/terms/{slug}/assign/copy")
def copy_assign(
    slug: str, ms: M2Store = Depends(get_m2), user: User = Depends(ASSIGN_EDIT)
) -> dict[str, Any]:
    return _run(ms.copy_assign, _term(slug), user)


@router.post("/terms/{slug}/assign/notify")
def notify(
    slug: str, ms: M2Store = Depends(get_m2), user: User = Depends(ASSIGN_EDIT)
) -> dict[str, Any]:
    return _run(ms.notify_assigned, _term(slug), user)


@router.get("/terms/{slug}/items/{key}/{doc}")
def get_doc(
    slug: str, key: str, doc: str, ms: M2Store = Depends(get_m2), user: User = Depends(ANY)
) -> dict[str, Any]:
    _doc_menu(doc, user)
    return _run(ms.doc, _term(slug), key, doc, user)


@router.put("/terms/{slug}/items/{key}/{doc}")
def save_doc(
    slug: str,
    key: str,
    doc: str,
    body: DocBody,
    ms: M2Store = Depends(get_m2),
    user: User = Depends(ANY),
) -> dict[str, Any]:
    _doc_menu(doc, user, "edit")
    return _run(ms.save, _term(slug), key, doc, body.data, user)


@router.post("/terms/{slug}/items/{key}/{doc}/copy")
def copy_doc(
    slug: str, key: str, doc: str, ms: M2Store = Depends(get_m2), user: User = Depends(ANY)
) -> dict[str, Any]:
    _doc_menu(doc, user, "edit")
    return _run(ms.copy_previous, _term(slug), key, doc, user)


@router.post("/terms/{slug}/items/{key}/{doc}/submit")
def submit(
    slug: str, key: str, doc: str, ms: M2Store = Depends(get_m2), user: User = Depends(ANY)
) -> dict[str, Any]:
    _doc_menu(doc, user, "edit")
    return _run(ms.submit, _term(slug), key, doc, user)


@router.post("/terms/{slug}/items/{key}/{doc}/certify")
def certify(
    slug: str,
    key: str,
    doc: str,
    body: CertifyBody,
    ms: M2Store = Depends(get_m2),
    user: User = Depends(ANY),
) -> dict[str, Any]:
    _doc_menu(doc, user, "approve")
    return _run(ms.certify, _term(slug), key, doc, user, body.ok, body.note)


@router.post("/terms/{slug}/items/{key}/{doc}/publish")
def publish(
    slug: str,
    key: str,
    doc: str,
    on: bool = True,
    ms: M2Store = Depends(get_m2),
    user: User = Depends(ANY),
) -> dict[str, Any]:
    _doc_menu(doc, user, "approve")
    return _run(ms.publish, _term(slug), key, doc, user, on)


@router.get("/terms/{slug}/dashboard")
def dashboard(
    slug: str, ms: M2Store = Depends(get_m2), user: User = Depends(DASH)
) -> dict[str, Any]:
    return _run(ms.dashboard, _term(slug), user)


@router.post("/terms/{slug}/remind")
def remind(
    slug: str, body: RemindBody, ms: M2Store = Depends(get_m2), user: User = Depends(REMIND)
) -> dict[str, Any]:
    return _run(ms.remind, _term(slug), user, body.key, body.doc)
