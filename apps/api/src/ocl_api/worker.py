"""Worker: takes queued import jobs one at a time and runs ingest -> extract.

One job at a time by design: the shared Ollama server must never see parallel OCL
requests (docs/server-constraints.md). `ocl worker` runs the loop as its own process
(compose service); in dev the API can run jobs inline in a background thread.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from ocl_api.config import Settings, get_settings
from ocl_api.extract.pipeline import extract
from ocl_api.ingest.pipeline import EmptyDocumentError, ingest
from ocl_api.ingest.typhoon import from_settings as typhoon_ocr
from ocl_api.jobs import JobStore, make_store, now_iso

_LOCK = threading.Lock()

PROGRESS = {
    "ingest": "กำลังแปลงไฟล์และอ่านโครงสร้างเล่ม…",
    "info": "กำลังอ่านหมวดที่ 1 ข้อมูลทั่วไปและหน้าปก…",
    "teachers": "กำลังอ่านตารางอาจารย์ผู้รับผิดชอบ/ประจำหลักสูตร…",
    "plan": "กำลังอ่านแผนการรับนิสิตและรูปแบบการสอน…",
    "structure": "กำลังค้นหาหมวดที่ 4 โครงสร้างหลักสูตร…",
    "plo": "กำลังสกัด PLO จากหมวดที่ 3…",
    "ksec": "กำลังอ่านตาราง KSEC (K/S/E/C) ตาม PLO…",
    "modules": "กำลังอ่านชุดวิชาและคำอธิบายชุดวิชา…",
    "courses": "กำลังสกัดรายวิชาและคำอธิบายรายวิชา…",
    "mapping": "กำลังอ่านตาราง Curriculum Mapping…",
    "appr": "กำลังอ่านสถานภาพและมติอนุมัติ (ข้อ 13)…",
}


def _gateway(provider: str, settings: Settings):
    if provider in ("none", "parser"):
        return None
    from ocl_api.llm.gateway import LLMGateway

    s = settings
    if provider != s.llm_provider:
        s = s.model_copy(update={"llm_provider": provider})
    return LLMGateway(s)


def process_job(store: JobStore, job_id: str, settings: Settings | None = None) -> dict[str, Any]:
    """Run one job to the review state. Serialized with a process-wide lock."""
    settings = settings or get_settings()
    with _LOCK:
        job = store.read(job_id)
        if job["status"] != "queued":
            return job
        d = store.dir(job_id)
        t_all = time.perf_counter()
        # สกัดใหม่ (FS-3e): the book was read already; extract only the chosen parts again
        again = job.get("reextract") if (d / "ingest").exists() else None
        if again is None:
            store.set_status(job_id, "ingesting", PROGRESS["ingest"], started_at=now_iso())
        try:
            t0 = time.perf_counter()
            rep = (
                None
                if again
                else ingest(
                    d / job["source"],
                    d / "ingest",
                    ocr=settings.ocr,
                    ocr_language=settings.ocr_language,
                    typhoon=typhoon_ocr(settings),
                    progress=lambda msg: store.set_status(job_id, "ingesting", msg),
                )
            )
            job = store.read(job_id)
            if rep is not None:
                job["timings"]["ingest"] = round(time.perf_counter() - t0, 2)
                job["counts"]["ingest"] = {
                    k: rep[k]
                    for k in (
                        "pages",
                        "tables",
                        "images",
                        "chapters",
                        "appendices",
                        "scanned_pages",
                        "ocr_pages",
                        "ocr_flags",
                        "ocr_hard_pages",
                    )
                }
            store.write(job)

            gateway = _gateway(job["provider"], settings)
            store.set_status(job_id, "extracting", PROGRESS["structure"])
            # run part by part so the progress line follows the mock's messages
            parts = job["parts"]
            run = [k for k in (again or {}).get("parts") or parts if k in parts]
            for key in run:
                store.set_status(job_id, "extracting", PROGRESS.get(key, key))
                t0 = time.perf_counter()
                extract(
                    d / "ingest",
                    parts=[key],
                    gateway=gateway,
                    out_dir=d / "extract",
                    mode=settings.extract_mode if gateway is not None else "parser_first",
                    fewshot=settings.fewshot,
                )
                job = store.read(job_id)
                job["timings"][key] = round(time.perf_counter() - t0, 2)
                store.write(job)
            # final combined checks/report over all parts
            report = extract(d / "ingest", parts=parts, gateway=None, out_dir=d / "extract-parser")
            _merge_checks(d, parts)
            store.sync_parts_from_files(job_id, run)
            if again:
                # the parts read again go back to unconfirmed; the other parts keep their edits
                store.reset_parts(job_id, run, again.get("by", ""))
                store.recompute(job_id)
            job = store.read(job_id)
            if again:
                job.setdefault("reextracts", []).append({**again, "done_at": now_iso()})
                job.pop("reextract", None)
            job["counts"]["parts"] = {k: v.get("count") for k, v in report["parts"].items()}
            job["llm"] = _sum_llm(d, parts)
            job["timings"]["total"] = round(time.perf_counter() - t_all, 2)
            store.write(job)
            return store.set_status(job_id, "review", "สกัดข้อมูลแล้ว รอตรวจสอบและยืนยันทีละส่วน")
        except EmptyDocumentError as e:  # a user problem, not a crash: no traceback
            return store.set_status(job_id, "failed", "ไม่พบเนื้อหาในไฟล์", error=str(e))
        except Exception as e:  # noqa: BLE001 - the job must record any failure
            tb = traceback.format_exc(limit=5)
            return store.set_status(job_id, "failed", "เกิดข้อผิดพลาด", error=f"{e}\n{tb}")


def _merge_checks(d: Path, parts: list[str]) -> None:
    """Re-run validators over the LLM-assisted parts (extract/) so checks.json matches them."""
    from ocl_api.extract.base import Check  # noqa: F401 - type only
    from ocl_api.extract.validators import run_checks

    data = {}
    for key in parts:
        p = d / "extract" / f"{key}.json"
        if p.exists():
            data[key] = json.loads(p.read_text(encoding="utf-8"))["data"]
    checks = run_checks(data)
    (d / "extract" / "checks.json").write_text(
        json.dumps([c.to_dict() for c in checks], ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _sum_llm(d: Path, parts: list[str]) -> dict[str, Any] | None:
    total: dict[str, Any] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "seconds": 0.0}
    seen = False
    for key in parts:
        p = d / "extract" / f"{key}.json"
        if not p.exists():
            continue
        llm = json.loads(p.read_text(encoding="utf-8")).get("llm")
        if llm:
            seen = True
            for k in total:
                total[k] += llm.get(k, 0)
            total["model"] = llm.get("model")
            total["provider"] = llm.get("provider")
    total["seconds"] = round(total["seconds"], 1)
    return total if seen else None


REMINDER_EVERY = 3600  # seconds; each overdue item is e-mailed at most once a day (dedupe)


def _remind(settings: Settings) -> None:
    """Overdue reviews of the approval flows (US-U-05): queue the daily reminders."""
    from ocl_api.curricula import CurriculumStore

    try:
        store = CurriculumStore(settings.database_url or "", settings.database_schema, None)
        sent = store.remind_overdue()
        if sent:
            print(f"worker: {sent} overdue reminder(s) queued")
    except Exception as e:  # a reminder must never stop the import queue
        print(f"worker: reminders skipped ({e.__class__.__name__}: {e})")


def run_loop(
    settings: Settings | None = None, *, poll_seconds: float = 2.0, once: bool = False
) -> int:
    settings = settings or get_settings()
    store = make_store(settings)
    print(
        f"worker: watching {store.root} ({'postgres' if settings.database_url else 'files'}) "
        f"· provider={settings.llm_provider} "
        f"· model={settings.ollama_model}"
    )
    handled = 0
    next_reminder = 0.0
    while True:
        if settings.database_url and time.monotonic() >= next_reminder:
            next_reminder = time.monotonic() + REMINDER_EVERY
            _remind(settings)
        job = store.next_queued()
        if job:
            print(f"worker: job {job['id']} {job['filename']}")
            res = process_job(store, job["id"], settings)
            print(f"worker: job {job['id']} -> {res['status']} ({res['timings'].get('total')} s)")
            handled += 1
            continue
        if once:
            return handled
        time.sleep(poll_seconds)
