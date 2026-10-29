from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from ocl_api.auth import REQUIRE_IMPORT_READ, REQUIRE_IMPORT_WRITE, User, current_user
from ocl_api.config import Settings, get_settings
from ocl_api.curricula import CurriculumStore
from ocl_api.jobs import ALL_PARTS, PARTS, JobStore, make_store
from ocl_api.worker import process_job

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_UPLOAD = 50 * 1024 * 1024  # the mock promises 50 MB
ALLOWED = {".docx", ".pdf"}


def get_store(settings: Settings = Depends(get_settings)):
    store = make_store(settings)
    try:
        yield store
    finally:
        close = getattr(store, "close", None)
        if close:
            close()


def _job_view(job: dict[str, Any]) -> dict[str, Any]:
    confirmed = job.get("confirmed", {})
    return {
        **job,
        "confirmed_count": len(confirmed),
        "parts_total": len(job.get("parts", PARTS)),
        "all_parts": ALL_PARTS,
    }


@router.get("")
def list_imports(
    store: JobStore = Depends(get_store), _: User = Depends(REQUIRE_IMPORT_READ)
) -> list[dict[str, Any]]:
    return [_job_view(j) for j in store.list()]


@router.post("", status_code=201)
async def create_import(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    provider: str = Form("ollama"),
    target: str | None = Form(None),
    store: JobStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    _: User = Depends(REQUIRE_IMPORT_WRITE),
) -> dict[str, Any]:
    name = file.filename or "book"
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(400, "รองรับเฉพาะ .docx และ .pdf")
    if provider not in ("ollama", "gemini", "none"):
        raise HTTPException(400, "provider ต้องเป็น ollama, gemini หรือ none")
    if provider == "gemini" and not settings.gemini_api_key:
        raise HTTPException(400, "Gemini ยังไม่ได้ตั้งค่า API key ในระบบนี้")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "ไฟล์ใหญ่เกิน 50 MB")
    if not data:
        raise HTTPException(400, "ไฟล์ว่าง")
    job = store.create(name, data, provider=provider, target=target or None)
    if settings.inline_worker:
        background.add_task(_run_inline, job["id"], settings)
    return _job_view(job)


def _run_inline(job_id: str, settings: Settings) -> None:
    # A thread so the HTTP response is not held while Ollama works (minutes). The thread
    # gets its own store: the request's one (and its DB connection) closes with the request.
    def run() -> None:
        store = make_store(settings)
        try:
            process_job(store, job_id, settings)
        finally:
            close = getattr(store, "close", None)
            if close:
                close()

    threading.Thread(target=run, daemon=True).start()


@router.get("/{job_id}")
def get_import(
    job_id: str, store: JobStore = Depends(get_store), _: User = Depends(REQUIRE_IMPORT_READ)
) -> dict[str, Any]:
    try:
        return _job_view(store.read(job_id))
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e


@router.get("/{job_id}/parts/{key}")
def get_part(
    job_id: str,
    key: str,
    store: JobStore = Depends(get_store),
    _: User = Depends(REQUIRE_IMPORT_READ),
) -> dict[str, Any]:
    try:
        part = store.read_part(job_id, key)
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานหรือส่วนที่ขอ") from e
    if part is None:
        if key in ALL_PARTS:
            return {"part": key, "data": None, "available": False, "note": "ส่วนนี้อยู่ใน R1"}
        raise HTTPException(404, "ไม่พบส่วนที่ขอ")
    return {**part, "available": True}


class PartUpdate(BaseModel):
    data: dict[str, Any]
    confirm: bool = False
    by: str = ""


@router.put("/{job_id}/parts/{key}")
def put_part(
    job_id: str,
    key: str,
    body: PartUpdate,
    store: JobStore = Depends(get_store),
    user: User = Depends(current_user),
) -> dict:
    try:
        if store.read_part(job_id, key) is None:
            raise HTTPException(404, "ส่วนนี้ยังไม่มีข้อมูลให้แก้")
        cs = _curricula()
        _check_edit_allowed(store, job_id, key, user, cs)
        saved = store.save_part(
            job_id, key, body.data, confirm=body.confirm, by=user.email or body.by
        )
        if cs is not None:
            cs.sync_part(job_id, key, body.data, user)  # after finalize the sections hold it
        return saved
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานหรือส่วนที่ขอ") from e


def _curricula() -> CurriculumStore | None:
    s = get_settings()
    return CurriculumStore(s.database_url, s.database_schema, None) if s.database_url else None


def _check_edit_allowed(
    store: JobStore, job_id: str, key: str, user: User, cs: CurriculumStore | None
) -> None:
    """Before finalize: who may import. After it the คู่มือหลักสูตร's rules apply (BRD 01 §2):
    the draft is edited by step 1 of its flow, the review by step 2 (หมวด 3–4, inside หมวด 4
    the Mapping only), and after 'ตรวจสอบสำเร็จ' nobody (สมอ.08)."""
    if store.draft_state(job_id) is not None and cs is not None:
        cs.check_part(job_id, key, user)
        return
    if not user.can("import_write"):
        raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์แก้ไขส่วนนี้")


@router.post("/{job_id}/finalize")
def finalize(
    job_id: str, store: JobStore = Depends(get_store), _: User = Depends(REQUIRE_IMPORT_WRITE)
) -> dict[str, Any]:
    try:
        job = store.read(job_id)
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e
    if job["status"] not in ("review", "done"):
        raise HTTPException(409, f"งานอยู่ในสถานะ {job['status']} ยังบันทึกไม่ได้")
    if not job["confirmed"]:
        raise HTTPException(409, "ต้องยืนยันอย่างน้อย 1 ส่วนก่อนบันทึกเข้าระบบ")
    state = store.draft_state(job_id)
    if state is not None and state["status"] != "import":
        # finalizing again would overwrite what the faculty is reviewing or has verified
        raise HTTPException(409, "คู่มือหลักสูตรจากงานนี้ส่งตรวจแล้ว บันทึกทับไม่ได้")
    return _job_view(store.finalize(job_id))


@router.get("/{job_id}/checks")
def get_checks(
    job_id: str, store: JobStore = Depends(get_store), _: User = Depends(REQUIRE_IMPORT_READ)
) -> list[dict[str, Any]]:
    try:
        return store.checks(job_id)
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e


@router.get("/{job_id}/source")
def get_source(
    job_id: str,
    page: int = Query(..., ge=1),
    store: JobStore = Depends(get_store),
    _: User = Depends(REQUIRE_IMPORT_READ),
) -> dict[str, Any]:
    """Blocks of the ingested document on one page, for the 'ต้นฉบับ' panel."""
    try:
        p = store.dir(job_id) / "ingest" / "document.json"
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e
    if not p.exists():
        raise HTTPException(409, "ยังไม่ได้แปลงไฟล์")
    doc = json.loads(p.read_text(encoding="utf-8"))
    blocks: list[dict[str, Any]] = []
    for sec in doc["sections"]:
        if sec.get("kind") != "front" and sec.get("page") == page:
            blocks.append({"kind": "paragraph", "text": sec["title"], "level": 1, "page": page})
        for b in sec["blocks"]:
            if b.get("page") == page:
                blocks.append(b)
    image = None
    for b in blocks:
        if b.get("kind") == "image" and str(b.get("path", "")).startswith("assets/page-"):
            image = b["path"]
    return {"page": page, "pages": doc.get("pages"), "blocks": blocks, "page_image": image}


@router.get("/{job_id}/files/{path:path}")
def get_file(
    job_id: str,
    path: str,
    store: JobStore = Depends(get_store),
    _: User = Depends(REQUIRE_IMPORT_READ),
):
    """Serve ingest/extract outputs (Markdown, assets) from the job folder; path-safe."""
    try:
        root = store.dir(job_id).resolve()
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e
    target = (root / path).resolve()
    # Markdown of a part the reviewer edited is re-rendered under edits/md/ and wins
    if path.startswith("extract/md/"):
        edited = (root / "edits" / "md" / path[len("extract/md/") :]).resolve()
        if root in edited.parents and edited.is_file():
            target = edited
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, "ไม่พบไฟล์")
    if target.suffix.lower() in {".md", ".txt", ".json"}:
        return PlainTextResponse(
            target.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8"
        )
    return FileResponse(target)
