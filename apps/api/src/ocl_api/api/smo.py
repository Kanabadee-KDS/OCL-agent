"""งานปรับปรุงแก้ไขหลักสูตร สมอ.08 (FS-3c · US-M1-09 10): menu c2."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ocl_api.auth import User, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.smo import FILE_MAX, SmoError, SmoStore

router = APIRouter(prefix="/api/smo", tags=["smo"])

VIEW = require_menu("c2")


def get_smo(settings: Settings = Depends(get_settings)) -> SmoStore:
    if not settings.database_url:
        raise HTTPException(503, "สมอ.08 ต้องการ DATABASE_URL")
    return SmoStore(settings.database_url, settings.database_schema, settings.data_dir)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except SmoError as e:
        raise HTTPException(e.status, str(e)) from e


class NewRequest(BaseModel):
    draft_id: int


class RequestEdit(BaseModel):
    types: list[str] = []
    scope: dict[str, Any] = {"kind": "mother"}
    fields: dict[str, Any] = {}
    after: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    reason: str | None = None


class Note(BaseModel):
    note: str | None = None


@router.get("")
def list_requests(ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)) -> dict[str, Any]:
    return ss.list(user)


@router.get("/options")
def options(ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)) -> dict[str, Any]:
    return ss.options(user)


@router.post("", status_code=201)
def create(
    body: NewRequest, ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)
) -> dict[str, Any]:
    return _run(ss.create, body.draft_id, user)


@router.get("/{rid}")
def get_request(
    rid: str, ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)
) -> dict[str, Any]:
    return _run(ss.get, rid, user)


@router.put("/{rid}")
def update(
    rid: str, body: RequestEdit, ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)
) -> dict[str, Any]:
    return _run(ss.update, rid, body.model_dump(), user)


@router.post("/{rid}/submit")
def submit(rid: str, ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)) -> dict[str, Any]:
    return _run(ss.submit, rid, user)


@router.post("/{rid}/approve")
def approve(
    rid: str, body: Note, ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)
) -> dict[str, Any]:
    return _run(ss.approve, rid, user, body.note)


@router.post("/{rid}/return")
def send_back(
    rid: str, body: Note, ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)
) -> dict[str, Any]:
    return _run(ss.send_back, rid, user, body.note)


@router.post("/{rid}/files")
async def add_file(
    rid: str,
    file: UploadFile = File(...),
    ss: SmoStore = Depends(get_smo),
    user: User = Depends(VIEW),
) -> dict[str, Any]:
    content = await file.read(FILE_MAX + 1)
    return _run(ss.add_file, rid, file.filename or "file", content, user)


@router.get("/{rid}/files/{fid}")
def get_file(
    rid: str, fid: int, ss: SmoStore = Depends(get_smo), user: User = Depends(VIEW)
) -> FileResponse:
    path, name = _run(ss.file, rid, fid, user)
    return FileResponse(path, filename=name)
