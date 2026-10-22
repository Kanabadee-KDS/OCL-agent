"""Import jobs stored as one folder each under DATA_DIR/imports/<id>/ (file mode).

With DATABASE_URL set, `ocl_api.jobs_pg.PgJobStore` keeps job state, parts, edits and
checks in Postgres instead (see `make_store`); the folder layout below is still used for
the uploaded book, ingest output and Markdown.

Layout:
  job.json          status, step, progress, timings, confirmations, counts
  source.<ext>      the uploaded book
  ingest/           ocl ingest output (book.md, sections/, assets/, document.json, report.json)
  extract/          ocl extract output (parts JSON, checks.json, report.json, md/)
  edits/<part>.json user-edited data + history of every save (evidence for "learns from edits")
"""

from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any

STATUSES = ("queued", "ingesting", "extracting", "review", "done", "failed")
# Steps as the customer's mock shows them: 1 upload · 2 AI reads · 3 review · 4 saved
STEP_OF = {"queued": 1, "ingesting": 2, "extracting": 2, "review": 3, "done": 4, "failed": 2}
ALL_PARTS = [
    "info",
    "teachers",
    "plan",
    "plo",
    "ksec",
    "structure",
    "modules",
    "courses",
    "mapping",
    "appr",
]
PARTS = list(ALL_PARTS)  # all 10 parts are implemented

_SAFE = re.compile(r"[^0-9A-Za-zก-๙._ -]+")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def safe_filename(name: str) -> str:
    name = _SAFE.sub("_", Path(name).name).strip("._ ") or "book"
    return name[:120]


class JobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root) / "imports"
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------- paths ----------

    @staticmethod
    def _valid_id(job_id: str) -> bool:
        return re.fullmatch(r"[0-9a-f]{12}", job_id) is not None

    def dir(self, job_id: str) -> Path:
        if not self._valid_id(job_id):
            raise KeyError(job_id)
        d = self.root / job_id
        if not (d / "job.json").exists():
            raise KeyError(job_id)
        return d

    def read(self, job_id: str) -> dict[str, Any]:
        return json.loads((self.dir(job_id) / "job.json").read_text(encoding="utf-8"))

    def write(self, job: dict[str, Any]) -> None:
        d = self.root / job["id"]
        d.mkdir(parents=True, exist_ok=True)
        job["updated_at"] = now_iso()
        tmp = d / "job.json.tmp"
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / "job.json")

    # ---------- lifecycle ----------

    def create(self, filename: str, data: bytes, *, provider: str, target: str | None) -> dict:
        job_id = secrets.token_hex(6)
        d = self.root / job_id
        d.mkdir(parents=True)
        fname = safe_filename(filename)
        ext = Path(fname).suffix.lower() or ".bin"
        (d / f"source{ext}").write_bytes(data)
        job = self._new_job(job_id, fname, f"source{ext}", len(data), provider, target)
        self.write(job)
        return job

    @staticmethod
    def _new_job(
        job_id: str, fname: str, source: str, size: int, provider: str, target: str | None
    ) -> dict[str, Any]:
        return {
            "id": job_id,
            "filename": fname,
            "source": source,
            "size": size,
            "provider": provider,
            "target": target,  # existing curriculum id, or None = create new from the book
            "status": "queued",
            "step": 1,
            "progress": "รอคิว",
            "error": None,
            "created_at": now_iso(),
            "started_at": None,
            "finished_at": None,
            "timings": {},
            "parts": PARTS,
            "confirmed": {},
            "counts": {},
            "llm": None,
        }

    def sync_parts_from_files(self, job_id: str, parts: list[str] | None = None) -> None:
        """File mode reads extract/<part>.json directly; nothing to copy."""

    def draft_state(self, job_id: str) -> dict[str, Any] | None:
        """File mode has no workflow."""
        return None

    def list(self) -> list[dict[str, Any]]:
        out = []
        for p in self.root.glob("*/job.json"):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        out.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        return out

    def next_queued(self) -> dict[str, Any] | None:
        queued = [j for j in self.list() if j["status"] == "queued"]
        queued.sort(key=lambda j: j.get("created_at", ""))
        return queued[0] if queued else None

    def set_status(
        self, job_id: str, status: str, progress: str | None = None, **extra: Any
    ) -> dict:
        job = self.read(job_id)
        job["status"] = status
        job["step"] = STEP_OF[status]
        if progress is not None:
            job["progress"] = progress
        job.update(extra)
        self.write(job)
        return job

    # ---------- parts ----------

    def part_path(self, job_id: str, key: str) -> Path:
        if key not in ALL_PARTS:
            raise KeyError(key)
        return self.dir(job_id) / "extract" / f"{key}.json"

    def edit_path(self, job_id: str, key: str) -> Path:
        if key not in ALL_PARTS:
            raise KeyError(key)
        return self.dir(job_id) / "edits" / f"{key}.json"

    def read_part(self, job_id: str, key: str) -> dict[str, Any] | None:
        """Extracted data with any user edits applied; None if the part does not exist."""
        p = self.part_path(job_id, key)
        if not p.exists():
            return None
        extracted = json.loads(p.read_text(encoding="utf-8"))
        edit = self.edit_path(job_id, key)
        edited = json.loads(edit.read_text(encoding="utf-8")) if edit.exists() else None
        job = self.read(job_id)
        return {
            "part": key,
            "data": edited["data"] if edited else extracted["data"],
            "extracted": extracted["data"],
            "notes": extracted.get("notes", []),
            "llm": extracted.get("llm"),
            "edited": bool(edited),
            "edit_count": len(edited["history"]) if edited else 0,
            "confirmed": bool(job["confirmed"].get(key)),
            "confirmed_at": job["confirmed"].get(key),
        }

    def save_part(
        self, job_id: str, key: str, data: dict[str, Any], *, confirm: bool, by: str = ""
    ) -> dict:
        p = self.edit_path(job_id, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        prev = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"history": []}
        before = (
            prev.get("data")
            if "data" in prev
            else (
                json.loads(self.part_path(job_id, key).read_text(encoding="utf-8"))["data"]
                if self.part_path(job_id, key).exists()
                else None
            )
        )
        prev["history"].append(
            {
                "ts": now_iso(),
                "by": by,
                "confirm": confirm,
                "changed": _changed_fields(before, data),
            }
        )
        prev["data"] = data
        p.write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
        job = self.read(job_id)
        if confirm:
            job["confirmed"][key] = now_iso()
        else:
            job["confirmed"].pop(key, None)
        self.write(job)
        self.recompute(job_id)
        return self.read_part(job_id, key) or {}

    def recompute(self, job_id: str) -> list[dict[str, Any]]:
        """Re-run the validators over every part *with the user's edits applied* and
        re-render the Markdown of the edited parts, so the checks tab and the preview
        follow what the reviewer sees instead of the original extraction."""
        from ocl_api.extract.render import RENDERERS
        from ocl_api.extract.validators import run_checks

        job = self.read(job_id)
        data: dict[str, Any] = {}
        edited: list[str] = []
        for key in job.get("parts", []):
            part = self.read_part(job_id, key)
            if part and part.get("data") is not None:
                data[key] = part["data"]
                if part.get("edited"):
                    edited.append(key)
        checks = [c.to_dict() for c in run_checks(data)]
        self._write_checks(job_id, checks)
        out = self.dir(job_id) / "edits"
        (out / "md").mkdir(parents=True, exist_ok=True)
        for key in edited:
            if key in RENDERERS:
                name, render = RENDERERS[key]
                (out / "md" / name).write_text(render(data[key]), encoding="utf-8")
        job = self.read(job_id)
        job["checks_recomputed_at"] = now_iso()
        job["edited_parts"] = edited
        self.write(job)
        return checks

    def _write_checks(self, job_id: str, checks: list[dict[str, Any]]) -> None:
        out = self.dir(job_id) / "edits"
        out.mkdir(parents=True, exist_ok=True)
        (out / "checks.json").write_text(
            json.dumps(checks, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def checks(self, job_id: str) -> list[dict[str, Any]]:
        """Effective checks: recomputed after edits when present, else the extraction's."""
        d = self.dir(job_id)
        for p in (d / "edits" / "checks.json", d / "extract" / "checks.json"):
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        return []

    def finalize(self, job_id: str) -> dict[str, Any]:
        job = self.read(job_id)
        job["status"] = "done"
        job["step"] = 4
        job["progress"] = "บันทึกข้อมูลเข้าระบบแล้ว (ร่างนำเข้าหลักสูตร)"
        job["finished_at"] = now_iso()
        self.write(job)
        return job


def _changed_fields(before: Any, after: Any, path: str = "") -> list[str]:
    """Paths of leaves that differ (bounded; enough to show 'what the reviewer changed')."""
    out: list[str] = []
    if isinstance(before, dict) and isinstance(after, dict):
        for k in sorted(set(before) | set(after)):
            if k == "meta":
                continue
            out.extend(_changed_fields(before.get(k), after.get(k), f"{path}.{k}" if path else k))
    elif isinstance(before, list) and isinstance(after, list):
        n = max(len(before), len(after))
        for i in range(n):
            b = before[i] if i < len(before) else None
            a = after[i] if i < len(after) else None
            label = (
                a.get("code_th") or a.get("code") or a.get("number")
                if isinstance(a, dict)
                else None
            )
            out.extend(_changed_fields(b, a, f"{path}[{label or i}]"))
    elif before != after:
        out.append(path or "$")
    return out[:200]


def elapsed_since(t0: float) -> float:
    return round(time.perf_counter() - t0, 2)


def make_store(settings) -> JobStore:
    """Postgres-backed store when DATABASE_URL is set, else the file store."""
    if getattr(settings, "database_url", None):
        from ocl_api.jobs_pg import PgJobStore

        return PgJobStore(settings.data_dir, settings.database_url, settings.database_schema)
    return JobStore(settings.data_dir)
