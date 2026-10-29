"""คู่มือหลักสูตร workflow over `curriculum_drafts` (BRD 01 §2 state machine).

    import ──submit──▶ review ──verify──▶ verified ──publish──▶ published
      ▲                  │ return                                  │ unpublish
      └──────────────────┘                                         ▼ (back to verified)

Who acts comes from the approval flow `curriculum` (flows.py, set on the approval page):
* submit     ส่งให้คณะตรวจสอบ      step 1 · due date = step 2's business days; the draft keeps
                                    the flow version it was submitted with (C13)
* check      ติ๊ก "ตรวจสอบหมวดนี้แล้ว" step 2, sections 3 and 4 only, while in review
* return     ส่งคืนเป็นร่าง          step 2 or step 1, while in review
* verify     ตรวจสอบสำเร็จ          step 2, both sections checked
* publish    เปิดเผยแพร่             step 3, from verified; unpublish goes back
The administrators may act on any step. E-mails (outbox) follow the flow's switches: the next
step is told, the sender hears of each outcome, and an overdue review is reminded once a day.
After "verified" the data is locked: edits only through สมอ.08 (BR-06), not in this POC.
Every transition is a row in `curriculum_events`. The data itself lives in the draft's
sections (sections.py, หมวด 0–5) and is edited there under the same rules; the import job's
from the import job's parts (with the reviewer's edits applied).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from ocl_api.auth import User
from ocl_api.curriculum_form import get_path, lookup_keys, progress
from ocl_api.db import Jsonb, connect
from ocl_api.flows import FlowStore, can_act, covers, today_th
from ocl_api.jobs import PARTS
from ocl_api.mail import Outbox
from ocl_api.sections import (
    REVIEW_EDITABLE,
    SECTIONS,
    master_columns,
    normalized,
    to_parts,
    write_all,
)

FLOW = "curriculum"
BOOK_MAX = 50 * 1024 * 1024  # the mock's limit for the approved book
COURSE_KEYS = (
    "code_th",
    "code_en",
    "name_th",
    "name_en",
    "credits",
    "credit_text",
    "description_th",
)
SUBMIT, REVIEW, PUBLISH = 0, 1, 2  # step index in the flow

STATUSES: dict[str, str] = {
    "import": "ร่างนำเข้าหลักสูตร",
    "review": "คณะตรวจสอบ",
    "verified": "ตรวจสอบสำเร็จ",
    "published": "เผยแพร่แล้ว",
}
FACULTY_SECTIONS = ("3", "4")  # หมวด 3 PLO/KSEC · หมวด 4 Curriculum Mapping
ACTIONS = {
    "submit": "ส่งให้คณะตรวจสอบ",
    "return": "ส่งคืนเป็นร่าง",
    "check": "ตรวจสอบหมวดนี้แล้ว",
    "verify": "ตรวจสอบสำเร็จ",
    "publish": "เปิดเผยแพร่",
    "unpublish": "ปิดการเผยแพร่",
}


def business_days_after(start: date, days: int) -> date:
    d = start
    left = days
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    return v.isoformat() if isinstance(v, date) else v


# ขอบเขตข้อมูล (FS-2e · US-M1-06 07): the curriculum's faculty (หมวด 0, else the draft's own)
# and the HURIS ids of the teachers in 0.2
SCOPE_COLUMNS = (
    "coalesce((SELECT s.data->'info'->'values'->>'faculty' FROM curriculum_sections s "
    "WHERE s.draft_id = d.id AND s.section = '0'), d.faculty) AS scope_faculty, "
    "coalesce((SELECT jsonb_agg(t->>'pid') FROM curriculum_sections s, "
    "jsonb_array_elements(coalesce(s.data->'teachers'->'teachers', '[]'::jsonb)) t "
    "WHERE s.draft_id = d.id AND s.section = '0' AND t->>'pid' IS NOT NULL), '[]'::jsonb) "
    "AS scope_pids"
)
OUT_OF_SCOPE = "หลักสูตรนี้อยู่นอกขอบเขตข้อมูลของบัญชีนี้"
BANGKOK = timezone(timedelta(hours=7))  # fixed offset: the slim image has no tz database


def _pct(a: int, b: int) -> int:
    return round(a * 100 / b) if b else 0


def visible(user: User | None, r: dict[str, Any]) -> bool:
    """ทั้งมหาวิทยาลัย: all · ส่วนงาน: the units cover the curriculum's faculty · หลักสูตร and
    รายบุคคล: the user's HURIS id is among the teachers in 0.2 (the mock's automatic rule)."""
    if user is None or user.sees_all():
        return True
    kinds = user.scope_kinds()
    if "faculty" in kinds and covers(user.units, r.get("scope_faculty")):
        return True
    return bool(
        kinds & {"program", "self"} and user.pid and user.pid in (r.get("scope_pids") or [])
    )


class CurriculumStore:
    def __init__(self, url: str, schema: str | None, job_store):
        self.url = url
        self.schema = schema
        self.jobs = job_store  # PgJobStore, for the parts snapshot
        self.flows = FlowStore(url, schema)

    def _conn(self):
        return connect(self.url, self.schema)

    # ---------- queries ----------

    def list(self, user: User | None = None) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT d.id, d.job_id, d.program_code, d.name_th, d.level, d.start_year, d.status,
                       d.faculty_checked, d.review_due_at, d.finalized_at, d.updated_at,
                       d.faculty, d.created_by, d.submitted_at, {SCOPE_COLUMNS},
                       (SELECT s.data->'info'->'values'->>'revision_type'
                          FROM curriculum_sections s
                          WHERE s.draft_id = d.id AND s.section = '0') AS revision_type,
                       (SELECT jsonb_build_object('ts', e.ts, 'by', e.by,
                                                  'action', e.action, 'note', e.note)
                          FROM curriculum_events e WHERE e.draft_id = d.id
                          ORDER BY e.ts DESC LIMIT 1) AS last_event,
                       (SELECT e.by FROM curriculum_events e
                          WHERE e.draft_id = d.id AND e.action = 'submit'
                          ORDER BY e.ts DESC LIMIT 1) AS submitted_by
                FROM curriculum_drafts d ORDER BY d.updated_at DESC
                """
            ).fetchall()
        items = [self._row(r) for r in rows if visible(user, r)]
        counts = {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}
        return {"counts": counts, "items": items}

    def get(self, draft_id: int, user: User | None = None) -> dict[str, Any]:
        with self._conn() as conn:
            r = conn.execute(
                "SELECT d.*, (SELECT s.data->'info'->'values'->>'revision_type' "
                "FROM curriculum_sections s WHERE s.draft_id = d.id AND s.section = '0') "
                f"AS revision_type, {SCOPE_COLUMNS} FROM curriculum_drafts d WHERE d.id = %s",
                (draft_id,),
            ).fetchone()
            if r is None:
                raise HTTPException(404, "ไม่พบคู่มือหลักสูตร")
            if not visible(user, r):
                raise HTTPException(403, OUT_OF_SCOPE)
            events = conn.execute(
                "SELECT ts, by, action, from_status, to_status, note FROM curriculum_events "
                "WHERE draft_id = %s ORDER BY ts, id",
                (draft_id,),
            ).fetchall()
            srows = conn.execute(
                "SELECT section, data, updated_by, updated_at FROM curriculum_sections "
                "WHERE draft_id = %s",
                (draft_id,),
            ).fetchall()
        out = self._row(r)
        data = r["data"] or {}
        imported = data.get("parts") or {}  # finalize snapshot: when each part was confirmed
        by_n = normalized({x["section"]: x["data"] for x in srows})
        current = to_parts(by_n)
        out["progress"] = progress(by_n)
        out["parts"] = {
            k: {
                "count": _count(current.get(k) or {}),
                "confirmed_at": (imported.get(k) or {}).get("confirmed_at"),
                "edited": (imported.get(k) or {}).get("edited"),
            }
            for k in PARTS
            if k in current
        }
        out["sections"] = {
            x["section"]: {
                "label": SECTIONS[x["section"]],
                "parts": sorted(x["data"]),
                "updated_by": x["updated_by"],
                "updated_at": _iso(x["updated_at"]),
            }
            for x in sorted(srows, key=lambda x: x["section"])
        }
        checks = data.get("checks") or []
        out["checks"] = {
            "pass": sum(c["status"] == "pass" for c in checks),
            "warn": sum(c["status"] == "warn" for c in checks),
            "fail": sum(c["status"] == "fail" for c in checks),
        }
        out["events"] = [{k: _iso(v) for k, v in e.items()} for e in events]
        version, steps, _ = self.flows.steps(FLOW, r.get("flow_version"))
        out["flow"] = {"version": version, "steps": steps}
        if user is not None:
            roles = user.roles
            out["allowed"] = {
                "submit": can_act(roles, steps[SUBMIT]),
                "review": can_act(roles, steps[REVIEW]),
                "publish": can_act(roles, steps[PUBLISH]),
            }
            out["editable"] = [
                n for n in SECTIONS if _edit_problem(r["status"], steps, user, n, None) is None
            ]
            # in review only some parts of a section may change (หมวด 4: the Mapping)
            out["limited"] = (
                {n: sorted(p) for n, p in REVIEW_EDITABLE.items() if p and n in out["editable"]}
                if r["status"] == "review"
                else {}
            )
        return out

    # ---------- sections (หมวด 0–5) ----------

    def create(self, name_th: str, level: str | None, faculty: str | None, user: User) -> dict:
        """เพิ่มหลักสูตร: a blank draft, filled on the form instead of from a book."""
        name_th = name_th.strip()
        if not name_th:
            raise HTTPException(400, "ต้องมีชื่อหลักสูตร")
        _, steps, _ = self.flows.steps(FLOW)
        _need(user, steps[SUBMIT])
        blank: dict[str, dict[str, Any]] = {n: {} for n in SECTIONS}
        blank["0"] = {"info": {"values": {"name_th": name_th, "level": level, "faculty": faculty}}}
        with self._conn() as conn, conn.transaction():
            r = conn.execute(
                "INSERT INTO curriculum_drafts (job_id, name_th, level, faculty, data, created_by) "
                "VALUES (NULL, %s, %s, %s, '{}'::jsonb, %s) RETURNING id",
                (name_th, level, faculty, user.email),
            ).fetchone()
            write_all(conn, r["id"], blank, user.email, "เพิ่มหลักสูตร")
            conn.execute(
                "INSERT INTO curriculum_events "
                "(draft_id, by, action, from_status, to_status, note) "
                "VALUES (%s, %s, 'create', NULL, 'import', %s)",
                (r["id"], user.email, "เพิ่มหลักสูตรโดยไม่นำเข้าจากเล่ม"),
            )
        return self.get(r["id"], user)

    def check_visible(self, draft_id: int, user: User) -> None:
        """403 for a curriculum outside the user's ขอบเขตข้อมูล (US-M1-06 07), 404 if none."""
        if user.sees_all():
            return
        with self._conn() as conn:
            r = conn.execute(
                f"SELECT {SCOPE_COLUMNS} FROM curriculum_drafts d WHERE d.id = %s", (draft_id,)
            ).fetchone()
        if r is None:
            raise HTTPException(404, "ไม่พบคู่มือหลักสูตร")
        if not visible(user, r):
            raise HTTPException(403, OUT_OF_SCOPE)

    def sections(self, draft_id: int) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT section, data, updated_by, updated_at FROM curriculum_sections "
                "WHERE draft_id = %s ORDER BY section",
                (draft_id,),
            ).fetchall()
        if not rows:
            raise HTTPException(404, "ไม่พบคู่มือหลักสูตร")
        data = normalized({x["section"]: x["data"] for x in rows})
        return {
            x["section"]: {
                "label": SECTIONS[x["section"]],
                "data": data[x["section"]],
                "updated_by": x["updated_by"],
                "updated_at": _iso(x["updated_at"]),
            }
            for x in rows
        }

    def save_section(
        self, draft_id: int, n: str, data: dict[str, Any], user: User, why: str | None = None
    ) -> dict[str, Any]:
        """Replace one section, if this user may change it in the draft's current state."""
        if n not in SECTIONS:
            raise HTTPException(404, "ไม่มีหมวดนี้")
        with self._conn() as conn, conn.transaction():
            d = conn.execute(
                "SELECT id, status, flow_version FROM curriculum_drafts WHERE id = %s FOR UPDATE",
                (draft_id,),
            ).fetchone()
            if d is None:
                raise HTTPException(404, "ไม่พบคู่มือหลักสูตร")
            old = conn.execute(
                "SELECT data FROM curriculum_sections WHERE draft_id = %s AND section = %s",
                (draft_id, n),
            ).fetchone()
            old_data = old["data"] if old else {}
            _, steps, _ = self.flows.steps(FLOW, d["flow_version"])
            problem = _edit_problem(d["status"], steps, user, n, (old_data, data))
            if problem:
                raise HTTPException(*problem)
            if data == old_data:
                return self.sections(draft_id)[n]
            conn.execute(
                "INSERT INTO curriculum_sections (draft_id, section, data, updated_by) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (draft_id, section) DO UPDATE SET "
                "data = EXCLUDED.data, updated_by = EXCLUDED.updated_by, updated_at = now()",
                (draft_id, n, Jsonb(data), user.email),
            )
            conn.execute(
                "INSERT INTO curriculum_section_history (draft_id, section, by, why, data) "
                "VALUES (%s, %s, %s, %s, %s)",
                (draft_id, n, user.email, why or "แก้ไข", Jsonb(data)),
            )
            conn.execute(
                "INSERT INTO curriculum_events "
                "(draft_id, by, action, from_status, to_status, note) "
                "VALUES (%s, %s, 'edit', %s, %s, %s)",
                (draft_id, user.email, d["status"], d["status"], f"แก้{SECTIONS[n]}"),
            )
            if n == "0":
                cols = master_columns({"0": data})
                conn.execute(
                    "UPDATE curriculum_drafts SET program_code = %s, "
                    "name_th = coalesce(%s, name_th), "
                    "level = %s, start_year = %s, faculty = %s, updated_at = now() WHERE id = %s",
                    (cols["program_code"], cols["name_th"], cols["level"], cols["start_year"],
                     cols["faculty"], draft_id),
                )  # fmt: skip
            else:
                conn.execute(
                    "UPDATE curriculum_drafts SET updated_at = now() WHERE id = %s", (draft_id,)
                )
        return self.sections(draft_id)[n]

    # ---------- form helpers ----------

    def options(self) -> dict[str, list[str]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT field, value FROM lookups ORDER BY added_at").fetchall()
        out: dict[str, list[str]] = {}
        for r in rows:
            out.setdefault(r["field"], []).append(r["value"])
        return out

    def add_option(self, key: str, value: str, user: User) -> dict[str, list[str]]:
        value = value.strip()
        if key not in lookup_keys():
            raise HTTPException(400, "ตัวเลือกของช่องนี้เพิ่มไม่ได้")
        if not value:
            raise HTTPException(400, "ต้องมีข้อความ")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO lookups (field, value, added_by) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (key, value, user.email),
            )
        return self.options()

    def save_book(self, draft_id: int, name: str, content: bytes, user: User, root) -> dict:
        """The approved book (PDF ≤ 50 MB) on the data volume; หมวด 0 records who and when."""
        if not content.startswith(b"%PDF"):
            raise HTTPException(400, "ต้องเป็นไฟล์ PDF")
        if len(content) > BOOK_MAX:
            raise HTTPException(413, "ไฟล์ใหญ่เกิน 50 MB")
        s0 = self.sections(draft_id)["0"]["data"]
        # check the right to edit หมวด 0 before anything is written
        with self._conn() as conn:
            d = conn.execute(
                "SELECT status, flow_version FROM curriculum_drafts WHERE id = %s", (draft_id,)
            ).fetchone()
        _, steps, _ = self.flows.steps(FLOW, d["flow_version"])
        problem = _edit_problem(d["status"], steps, user, "0", None)
        if problem:
            raise HTTPException(*problem)
        stamp = datetime.now(BANGKOK)
        folder = root / "curricula" / str(draft_id)
        folder.mkdir(parents=True, exist_ok=True)
        file = f"approved-{stamp:%Y%m%d-%H%M%S}.pdf"
        (folder / file).write_bytes(content)
        info = dict(s0.get("info") or {})
        info["values"] = {
            **(info.get("values") or {}),
            "approved_book": {
                "file": file, "name": name, "size": len(content), "by": user.email,
                "at": stamp.isoformat(timespec="seconds"), "label": "ฉบับอนุมัติ",
            },
        }  # fmt: skip
        return self.save_section(draft_id, "0", {**s0, "info": info}, user, why="แนบเล่มอนุมัติ")

    def book_path(self, draft_id: int, root):
        s0 = self.sections(draft_id)["0"]["data"]
        book = ((s0.get("info") or {}).get("values") or {}).get("approved_book") or {}
        path = root / "curricula" / str(draft_id) / str(book.get("file") or "")
        if not book.get("file") or not path.is_file() or path.parent.name != str(draft_id):
            raise HTTPException(404, "ยังไม่มีไฟล์เล่มอนุมัติ")
        return path, book.get("name") or path.name

    def teacher_check(self, draft_id: int) -> dict[str, Any]:
        """A first check of หมวด 0.2 (BRD 04 criteria 1–2) and responsible teachers shared
        with other curricula; the full criteria come with M4 (FS-6)."""
        secs = self.sections(draft_id)
        values = ((secs["0"]["data"].get("info") or {}).get("values")) or {}
        teachers = get_path(secs["0"]["data"], "teachers.teachers") or []
        resp = [t for t in teachers if t.get("responsible")]
        bachelor = str(values.get("level") or "").startswith(("ป.ตรี", "ปริญญาตรี"))
        need = 5 if bachelor else 3  # [สมมติ] เกณฑ์ อว. 2565 ตามระดับ
        issues = []
        if len(resp) < need:
            issues.append(f"อาจารย์ผู้รับผิดชอบ {len(resp)} คน ต้องอย่างน้อย {need} คน")
        for t in resp:
            if not _qualified(t, bachelor):
                issues.append(f"{t.get('name')}: คุณวุฒิ/ตำแหน่งต่ำกว่าเกณฑ์ขั้นต่ำ")
        key = lambda n: "".join(str(n or "").split())  # noqa: E731
        mine = {key(t.get("name")) for t in resp} | {t.get("pid") for t in resp if t.get("pid")}
        dups = []
        with self._conn() as conn:
            for r in conn.execute(
                "SELECT d.id, d.name_th, s.data->'teachers'->'teachers' AS t "
                "FROM curriculum_sections s JOIN curriculum_drafts d ON d.id = s.draft_id "
                "WHERE s.section = '0' AND s.draft_id <> %s",
                (draft_id,),
            ):
                for t in r["t"] or []:
                    if t.get("responsible") and (
                        key(t.get("name")) in mine or t.get("pid") in mine
                    ):
                        dups.append(
                            {"name": t.get("name"), "curriculum": r["name_th"], "id": r["id"]}
                        )
        return {"responsible": len(resp), "required": need, "issues": issues, "duplicates": dups}

    def course_catalog(self, q: str = "", exclude: int | None = None) -> list[dict[str, Any]]:
        """Courses already in the system's curricula, the stand-in for the central course
        database (CUR23) until FS-3 builds it with versions (plan FS-2, answer Q3 ก)."""
        needle = "".join(q.split()).lower()
        seen: dict[str, dict[str, Any]] = {}
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT s.draft_id, d.name_th, s.data->'courses'->'courses' AS courses "
                "FROM curriculum_sections s JOIN curriculum_drafts d ON d.id = s.draft_id "
                "WHERE s.section = '4' ORDER BY s.draft_id"
            ).fetchall()
        mine = set()
        for r in rows:
            for c in r["courses"] or []:
                code = str(c.get("code_th") or "").strip()
                if not code:
                    continue
                if r["draft_id"] == exclude:
                    mine.add(code)
                    continue
                text = "".join(f"{code}{c.get('code_en') or ''}{c.get('name_th') or ''}".split())
                if needle and needle not in text.lower():
                    continue
                seen.setdefault(code, {k: c.get(k) for k in COURSE_KEYS} | {"from": r["name_th"]})
        return [c for code, c in sorted(seen.items()) if code not in mine][:50]

    def by_job(self, job_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            r = conn.execute(
                "SELECT id, status, faculty_checked FROM curriculum_drafts WHERE job_id = %s",
                (job_id,),
            ).fetchone()
        return dict(r) if r else None

    @staticmethod
    def _row(r: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "id", "job_id", "program_code", "name_th", "level", "start_year", "status",
            "faculty_checked", "review_due_at", "finalized_at", "updated_at", "faculty",
            "revision_type", "last_event", "submitted_at", "verified_at", "published_at",
            "submitted_by",
        )  # fmt: skip
        out = {k: _iso(r[k]) for k in keys if k in r}
        out["status_th"] = STATUSES.get(out.get("status", ""), out.get("status"))
        if out.get("last_event") and isinstance(out["last_event"], dict):
            out["last_event"] = {k: _iso(v) for k, v in out["last_event"].items()}
        return out

    # ---------- transitions ----------

    def transition(
        self,
        draft_id: int,
        action: str,
        user: User,
        *,
        note: str | None = None,
        section: str | None = None,
        checked: bool = True,
    ) -> dict[str, Any]:
        if action not in ACTIONS:
            raise HTTPException(400, f"action ต้องเป็น {', '.join(ACTIONS)}")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, job_id, status, faculty_checked, flow_version, name_th, faculty "
                "FROM curriculum_drafts WHERE id = %s",
                (draft_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(404, "ไม่พบคู่มือหลักสูตร")
        status: str = row["status"]
        # submit starts on the current flow; later steps keep the version it started with
        version, steps, flow = self.flows.steps(
            FLOW, None if action == "submit" else row["flow_version"]
        )
        checked_map: dict[str, Any] = dict(row["faculty_checked"] or {})
        due: str | None = None
        new_status = status
        extra_sql = ""
        if action == "submit":
            _need(user, steps[SUBMIT])
            _from(status, "import", action)
            new_status = "review"
            checked_map = {}
            days = steps[REVIEW]["days"]
            due = business_days_after(today_th(), days).isoformat() if days else None
            extra_sql = (
                f", submitted_at = now(), flow_version = {int(version)}, review_due_at = "
                + (f"'{due}'" if due else "NULL")
            )
        elif action == "check":
            _need(user, steps[REVIEW])
            _from(status, "review", action)
            if section not in FACULTY_SECTIONS:
                raise HTTPException(400, "section ต้องเป็น 3 หรือ 4")
            checked_map[section] = bool(checked)
            note = note or f"หมวด {section}: {'ตรวจแล้ว' if checked else 'ยกเลิกการติ๊ก'}"
        elif action == "return":
            if not (can_act(user.roles, steps[REVIEW]) or can_act(user.roles, steps[SUBMIT])):
                raise HTTPException(403, "ส่งคืนได้เฉพาะผู้ตรวจสอบหรือผู้ส่ง")
            _from(status, "review", action)
            new_status = "import"
            extra_sql = ", review_due_at = NULL"
        elif action == "verify":
            _need(user, steps[REVIEW])
            _from(status, "review", action)
            missing = [s for s in FACULTY_SECTIONS if not checked_map.get(s)]
            if missing:
                raise HTTPException(
                    409,
                    "ต้องติ๊ก 'ตรวจสอบหมวดนี้แล้ว' ให้ครบหมวด 3 และ 4 ก่อน (ยังขาดหมวด "
                    + ", ".join(missing)
                    + ")",
                )
            new_status = "verified"
            extra_sql = ", verified_at = now()"
        elif action == "publish":
            _need(user, steps[PUBLISH])
            _from(status, "verified", action)
            new_status = "published"
            extra_sql = ", published_at = now()"
        elif action == "unpublish":
            _need(user, steps[PUBLISH])
            _from(status, "published", action)
            new_status = "verified"
            extra_sql = ", published_at = NULL"
        with self._conn() as conn:
            with conn.transaction():
                conn.execute(
                    f"UPDATE curriculum_drafts SET status = %s, faculty_checked = %s, "
                    f"updated_at = now(){extra_sql} WHERE id = %s",
                    (new_status, Jsonb(checked_map), draft_id),
                )
                conn.execute(
                    "INSERT INTO curriculum_events "
                    "(draft_id, by, action, from_status, to_status, note) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (draft_id, user.email, action, status, new_status, note),
                )
        self._notify(row, action, user.email, steps, flow, due, note)
        return self.get(draft_id, user)

    # ---------- e-mail (outbox) ----------

    def _sender(self, draft_id: int) -> str | None:
        with self._conn() as conn:
            r = conn.execute(
                "SELECT by FROM curriculum_events WHERE draft_id = %s AND action = 'submit' "
                "ORDER BY ts DESC, id DESC LIMIT 1",
                (draft_id,),
            ).fetchone()
        return r["by"] if r else None

    def _notify(self, row, action, by, steps, flow, due, note) -> None:
        name = row["name_th"] or "คู่มือหลักสูตร"
        ref = f"curriculum:{row['id']}"
        box = Outbox(self.url, self.schema)
        mails: list[tuple[list[str], str, str]] = []
        if flow["notify_next"] and action in ("submit", "verify"):
            step = steps[REVIEW] if action == "submit" else steps[PUBLISH]
            to = self.flows.recipients(step["roles"], row["faculty"])
            if action == "submit":
                when = f" ภายในวันที่ {due}" if due else ""
                mails.append((to, f"คู่มือหลักสูตรรอตรวจสอบ: {name}",
                              f"{by} ส่ง{name}ให้ตรวจสอบหมวด 3–4{when}"))  # fmt: skip
            else:
                mails.append((to, f"คู่มือหลักสูตรตรวจสอบสำเร็จ รอเผยแพร่: {name}",
                              f"{name} ตรวจสอบสำเร็จแล้ว ขั้นถัดไป: {step['label']}"))  # fmt: skip
        if flow["notify_sender"] and action in ("verify", "return", "publish"):
            sender = self._sender(row["id"])
            if sender and sender != by:
                what = {"verify": "ตรวจสอบสำเร็จแล้ว", "return": "ถูกส่งคืนเป็นร่าง",
                        "publish": "เผยแพร่แล้ว"}[action]  # fmt: skip
                body = f"{name} {what} โดย {by}" + (f"\nหมายเหตุ: {note}" if note else "")
                mails.append(([sender], f"{name}: {what}", body))
        for to, subject, body in mails:
            if to:
                box.send(to, subject, body, kind="workflow", by=by, ref=ref)

    # ---------- แดชบอร์ดหลักสูตร (FS-2f · US-M1-01 02) ----------

    def dashboard(
        self, user: User, faculty: str = "", level: str = "", year: int | None = None
    ) -> dict[str, Any]:
        """Every number from the curricula this user may see (ขอบเขตข้อมูล), after the filters."""
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT d.id, d.name_th, d.level, d.start_year, d.status, d.faculty_checked,
                       d.review_due_at, {SCOPE_COLUMNS},
                       coalesce((SELECT max(e.ts) FROM curriculum_events e
                                  WHERE e.draft_id = d.id AND e.to_status = d.status
                                    AND e.action <> 'edit'),
                                d.finalized_at, d.updated_at) AS since
                FROM curriculum_drafts d
                """
            ).fetchall()
            secs = conn.execute(
                "SELECT draft_id, section, data FROM curriculum_sections"
            ).fetchall()
        by_draft: dict[int, dict[str, Any]] = {}
        for x in secs:
            by_draft.setdefault(x["draft_id"], {})[x["section"]] = x["data"]
        today = today_th()
        seen = [r for r in rows if visible(user, r)]
        options = {
            "faculties": sorted({r["scope_faculty"] for r in seen if r["scope_faculty"]}),
            "levels": sorted({r["level"] for r in seen if r["level"]}),
            "years": sorted({r["start_year"] for r in seen if r["start_year"]}),
        }
        items = []
        for r in seen:
            if (faculty and r["scope_faculty"] != faculty) or (level and r["level"] != level):
                continue
            if year and r["start_year"] != year:
                continue
            data = normalized(by_draft.get(r["id"], {}))
            prog = progress(data)
            v = get_path(data.get("0"), "info.values") or {}
            ksec = get_path(data.get("3"), "ksec.plos") or []
            cats = [i.get("category") for k in ksec for i in (k.get("items") or [])]
            since = r["since"].astimezone(BANGKOK).date() if r["since"] else today
            items.append({
                "id": r["id"], "name_th": r["name_th"], "faculty": r["scope_faculty"],
                "level": r["level"], "start_year": r["start_year"], "status": r["status"],
                "status_th": STATUSES[r["status"]], "review_due_at": _iso(r["review_due_at"]),
                "days": (today - since).days if r["status"] in ("import", "review") else None,
                "missing": [n for n, x in prog.items() if x["done"] < x["total"]],
                "complete": {n: x["done"] >= x["total"] for n, x in prog.items()},
                "revision_type": v.get("revision_type"),
                "total_credits": v.get("total_credits"),
                "plo_count": len(get_path(data.get("3"), "plo.plos") or []),
                "course_count": len(get_path(data.get("4"), "courses.courses") or []),
                "ksec": {c: cats.count(c) for c in "KSEC"},
            })  # fmt: skip
        n = len(items)
        counts = {st: sum(i["status"] == st for i in items) for st in STATUSES}
        facs: dict[str, list[dict[str, Any]]] = {}
        for i in items:
            facs.setdefault(i["faculty"] or "ไม่ระบุคณะ", []).append(i)
        by_faculty = [
            {
                "faculty": f,
                "count": len(xs),
                "counts": {st: sum(x["status"] == st for x in xs) for st in STATUSES},
                "verified_pct": _pct(
                    sum(x["status"] in ("verified", "published") for x in xs), len(xs)
                ),
                "longest_days": max((x["days"] or 0 for x in xs), default=0),
            }
            for f, xs in sorted(facs.items(), key=lambda kv: -len(kv[1]))
        ]
        completeness = {
            k: _pct(sum(i["complete"].get(k, False) for i in items), n) for k in SECTIONS
        }
        stuck = sorted((i for i in items if i["days"] is not None), key=lambda i: -i["days"])[:8]
        return {
            "options": options,
            "total": n,
            "counts": counts,
            "by_faculty": by_faculty,
            "completeness": completeness,
            "stuck": stuck,
            "items": items,
            "today": today.isoformat(),
            "this_year": today.year + 543,
        }

    def remind(self, draft_id: int, user: User) -> dict[str, Any]:
        """The dashboard's แจ้งเตือน: to whoever holds the current step, once a day."""
        with self._conn() as conn:
            r = conn.execute(
                "SELECT id, name_th, status, faculty, flow_version, review_due_at "
                "FROM curriculum_drafts WHERE id = %s",
                (draft_id,),
            ).fetchone()
        if r is None:
            raise HTTPException(404, "ไม่พบคู่มือหลักสูตร")
        if r["status"] not in ("import", "review"):
            raise HTTPException(409, "หลักสูตรนี้ไม่ได้ค้างอยู่ในขั้นใด")
        _, steps, _ = self.flows.steps(FLOW, r["flow_version"])
        step = steps[SUBMIT] if r["status"] == "import" else steps[REVIEW]
        to = self.flows.recipients(step["roles"], r["faculty"])
        if not to:
            raise HTTPException(409, f"ไม่พบผู้รับผิดชอบขั้น '{step['label']}' ของคณะนี้")
        name = r["name_th"] or "คู่มือหลักสูตร"
        what = "ยังเป็นร่าง รอส่งให้คณะตรวจสอบ" if r["status"] == "import" else "รอคณะตรวจสอบหมวด 3–4"
        due = f" (กำหนด {r['review_due_at'].isoformat()})" if r["review_due_at"] else ""
        today = today_th().isoformat()
        m = Outbox(self.url, self.schema).send(
            to,
            f"แจ้งเตือนจากแดชบอร์ดหลักสูตร: {name}",
            f"{name} {what}{due}\nแจ้งโดย {user.email}",
            kind="reminder",
            by=user.email,
            ref=f"curriculum:{draft_id}",
            dedupe_key=f"dashboard:curriculum:{draft_id}:{today}",
        )
        return {"sent": m is not None, "to": len(to), "step": step["label"]}

    def remind_overdue(self) -> int:
        """Reviews past their due date: remind step 2 once a day (outbox dedupe). Count sent."""
        flow = self.flows.get(FLOW)
        if not flow["remind_overdue"]:
            return 0
        today = today_th()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, name_th, review_due_at, flow_version, faculty "
                "FROM curriculum_drafts WHERE status = 'review' AND review_due_at < %s",
                (today,),
            ).fetchall()
        box = Outbox(self.url, self.schema)
        sent = 0
        for r in rows:
            _, steps, _ = self.flows.steps(FLOW, r["flow_version"])
            to = self.flows.recipients(steps[REVIEW]["roles"], r["faculty"])
            if not to:
                continue
            m = box.send(
                to,
                f"เกินกำหนดตรวจสอบ: {r['name_th'] or 'คู่มือหลักสูตร'}",
                f"กำหนดตรวจสอบวันที่ {r['review_due_at'].isoformat()} ผ่านมาแล้ว",
                kind="reminder",
                ref=f"curriculum:{r['id']}",
                dedupe_key=f"overdue:curriculum:{r['id']}:{today.isoformat()}",
            )
            sent += m is not None
        return sent


_ASSOC_UP = ("รองศาสตราจารย์", "ศาสตราจารย์", "รศ.", "ศ.")
_ASSIST_UP = ("ผู้ช่วยศาสตราจารย์", "ผศ.", *_ASSOC_UP)


def _qualified(t: dict[str, Any], bachelor: bool) -> bool:
    """[สมมติ] BRD 04 criterion 2: bachelor's — a master's or assistant professor and up;
    graduate — a doctorate or associate professor and up."""
    level, rank = t.get("highest_level") or "", t.get("rank") or ""
    if bachelor:
        return level in ("โท", "เอก") or rank.startswith(_ASSIST_UP)
    return level == "เอก" or rank.startswith(_ASSOC_UP)


def _need(user: User, step: dict[str, Any]) -> None:
    if not can_act(user.roles, step):
        raise HTTPException(403, "บทบาทของคุณทำขั้นตอนนี้ไม่ได้ (ดูการตั้งค่าการอนุมัติ)")


def _edit_problem(
    status: str,
    steps: list[dict[str, Any]],
    user: User,
    n: str,
    change: tuple[dict, dict] | None,
    part: str | None = None,
) -> tuple[int, str] | None:
    """Why `user` may not change section `n` now (status code, message), or None.

    ร่าง: step 1 of the flow (who prepares and submits) · คณะตรวจสอบ: step 2, หมวด 3–4 only and
    inside หมวด 4 the Mapping only (BRD 01 §2) · ตรวจสอบสำเร็จ/เผยแพร่: nobody, via สมอ.08."""
    if status in ("verified", "published"):
        return 409, "คู่มือหลักสูตรนี้ตรวจสอบสำเร็จแล้ว ถูกล็อก แก้ได้ผ่าน สมอ.08 เท่านั้น"
    if status == "import":
        return None if can_act(user.roles, steps[SUBMIT]) else (403, "บทบาทของคุณแก้ร่างนี้ไม่ได้")
    if not can_act(user.roles, steps[REVIEW]) or n not in REVIEW_EDITABLE:
        return 403, "ระหว่างคณะตรวจสอบ แก้ได้เฉพาะหมวด 3–4 โดยผู้ตรวจของคณะ"
    allowed = REVIEW_EDITABLE[n]
    if allowed is not None:
        if part is not None and part not in allowed:
            return 403, "หมวด 4 ระหว่างคณะตรวจสอบ แก้ได้เฉพาะ Curriculum Mapping"
        if change is not None:
            old, new = change
            if any(old.get(k) != new.get(k) for k in set(old) | set(new) if k not in allowed):
                return 403, "หมวด 4 ระหว่างคณะตรวจสอบ แก้ได้เฉพาะ Curriculum Mapping"
    return None


def _from(status: str, expected: str, action: str) -> None:
    if status != expected:
        raise HTTPException(
            409,
            f"ทำ '{ACTIONS[action]}' ได้เฉพาะเมื่อสถานะเป็น '{STATUSES[expected]}' "
            f"(ตอนนี้ '{STATUSES.get(status, status)}')",
        )


def _count(data: dict[str, Any]) -> int | None:
    """Item count of a part: its own `count`, else the longest list it holds."""
    for k in ("count", "node_count"):
        if isinstance(data.get(k), int):
            return data[k]
    lists = [len(v) for v in data.values() if isinstance(v, list)]
    return max(lists) if lists else None
