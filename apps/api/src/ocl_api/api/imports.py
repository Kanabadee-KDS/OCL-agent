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

from ocl_api.config import Settings, get_settings
from ocl_api.jobs import ALL_PARTS, PARTS, JobStore
from ocl_api.worker import process_job

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_UPLOAD = 50 * 1024 * 1024  # the mock promises 50 MB
ALLOWED = {".docx", ".pdf"}


def get_store(settings: Settings = Depends(get_settings)) -> JobStore:
    return JobStore(settings.data_dir)


def _job_view(job: dict[str, Any]) -> dict[str, Any]:
    confirmed = job.get("confirmed", {})
    return {
        **job,
        "confirmed_count": len(confirmed),
        "parts_total": len(job.get("parts", PARTS)),
        "all_parts": ALL_PARTS,
    }


@router.get("")
def list_imports(store: JobStore = Depends(get_store)) -> list[dict[str, Any]]:
    return [_job_view(j) for j in store.list()]


@router.post("", status_code=201)
async def create_import(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    provider: str = Form("ollama"),
    target: str | None = Form(None),
    store: JobStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
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
        background.add_task(_run_inline, store, job["id"], settings)
    return _job_view(job)


def _run_inline(store: JobStore, job_id: str, settings: Settings) -> None:
    # A thread so the HTTP response is not held while Ollama works (minutes).
    threading.Thread(target=process_job, args=(store, job_id, settings), daemon=True).start()


@router.get("/{job_id}")
def get_import(job_id: str, store: JobStore = Depends(get_store)) -> dict[str, Any]:
    try:
        return _job_view(store.read(job_id))
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e


@router.get("/{job_id}/parts/{key}")
def get_part(job_id: str, key: str, store: JobStore = Depends(get_store)) -> dict[str, Any]:
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
def put_part(job_id: str, key: str, body: PartUpdate, store: JobStore = Depends(get_store)) -> dict:
    try:
        if store.read_part(job_id, key) is None:
            raise HTTPException(404, "ส่วนนี้ยังไม่มีข้อมูลให้แก้")
        return store.save_part(job_id, key, body.data, confirm=body.confirm, by=body.by)
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานหรือส่วนที่ขอ") from e


@router.post("/{job_id}/finalize")
def finalize(job_id: str, store: JobStore = Depends(get_store)) -> dict[str, Any]:
    try:
        job = store.read(job_id)
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e
    if job["status"] not in ("review", "done"):
        raise HTTPException(409, f"งานอยู่ในสถานะ {job['status']} ยังบันทึกไม่ได้")
    if not job["confirmed"]:
        raise HTTPException(409, "ต้องยืนยันอย่างน้อย 1 ส่วนก่อนบันทึกเข้าระบบ")
    return _job_view(store.finalize(job_id))


@router.get("/{job_id}/checks")
def get_checks(job_id: str, store: JobStore = Depends(get_store)) -> list[dict[str, Any]]:
    try:
        p = store.dir(job_id) / "extract" / "checks.json"
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


@router.get("/{job_id}/source")
def get_source(
    job_id: str, page: int = Query(..., ge=1), store: JobStore = Depends(get_store)
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
def get_file(job_id: str, path: str, store: JobStore = Depends(get_store)):
    """Serve ingest/extract outputs (Markdown, assets) from the job folder; path-safe."""
    try:
        root = store.dir(job_id).resolve()
    except KeyError as e:
        raise HTTPException(404, "ไม่พบงานนำเข้า") from e
    target = (root / path).resolve()
    if root not in target.parents or not target.is_file():
        raise HTTPException(404, "ไม่พบไฟล์")
    if target.suffix.lower() in {".md", ".txt", ".json"}:
        return PlainTextResponse(
            target.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8"
        )
    return FileResponse(target)
