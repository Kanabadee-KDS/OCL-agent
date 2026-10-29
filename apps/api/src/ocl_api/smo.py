"""งานปรับปรุงแก้ไขหลักสูตร สมอ.08 (FS-3c · US-M1-09 10 · BR-06, mock smo / smo-new / smo-view).

A request (S08-ปปปป-nnn) on a curriculum that is verified or published. Step 0 of the flow
`smo08` submits it; each later step approves it or sends it back; after the last step the
proposed teacher list replaces หมวด 0.2 of the curriculum (FS-3 Q3 ก). The other kinds
(courses, study plan, other) are recorded as text with the request, as the mock says: course
data itself changes in บริหารรายวิชา.

Steps done by a body that is not a group in the system (คณะกรรมการประจำคณะ · สภาวิชาการ ·
สภามหาวิทยาลัย) are recorded by central staff [สมมติ: they key in the body's resolution].
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ocl_api.auth import User
from ocl_api.curricula import BANGKOK, visible
from ocl_api.db import Jsonb, connect
from ocl_api.flows import FlowStore, can_act, today_th
from ocl_api.mail import Outbox

FLOW = "smo08"
STATUSES = {"draft": "ร่าง", "pending": "ระหว่างอนุมัติ", "returned": "ส่งคืนแก้ไข", "approved": "อนุมัติแล้ว"}
TYPES = {
    "teacher": "อาจารย์ผู้รับผิดชอบ/ประจำหลักสูตร",
    "course": "รายวิชา",
    "plan": "แผนการศึกษา",
    "other": "อื่น ๆ",
}
FILE_MAX = 20 * 1024 * 1024
FILE_TYPES = (".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png")
# what identifies a teacher across the old and new list, and what counts as an edit
TEACHER_FIELDS = ("name", "rank", "highest_level", "responsible", "group", "chair")


class SmoError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def may_act(user: User, step: dict[str, Any]) -> bool:
    """The step's groups; a step done by an outside body (no group): central records it."""
    return can_act(user.roles, step) or (not step.get("roles") and "central" in user.roles)


def teacher_key(t: dict[str, Any]) -> str:
    return t.get("pid") or t.get("xid") or "name:" + "".join(str(t.get("name") or "").split())


def changes(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows for the comparison: เพิ่ม · แก้ไข · นำออก (unchanged rows are left out)."""
    old = {teacher_key(t): t for t in before}
    new = {teacher_key(t): t for t in after}
    out = []
    for k, t in new.items():
        if k not in old:
            out.append({"change": "เพิ่ม", "before": None, "after": t})
        elif any(old[k].get(f) != t.get(f) for f in TEACHER_FIELDS):
            out.append({"change": "แก้ไข", "before": old[k], "after": t})
    out += [{"change": "นำออก", "before": t, "after": None} for k, t in old.items() if k not in new]
    return out


def in_scope(t: dict[str, Any], scope: dict[str, Any]) -> bool:
    """เล่มแม่: every teacher · เล่มลูก: the teachers of that แขนง (0.2 `group`)."""
    return scope.get("kind") != "child" or (t.get("group") or "") == (scope.get("branch") or "")


class SmoStore:
    def __init__(self, url: str, schema: str | None = None, data_dir: str | Path = "."):
        self.url, self.schema = url, schema
        self.flows = FlowStore(url, schema)
        self.data_dir = Path(data_dir)

    def _conn(self):
        return connect(self.url, self.schema)

    # ---------- reads ----------

    def options(self, user: User) -> dict[str, Any]:
        """Curricula a request may be made on (verified/published, in scope), with their แขนง."""
        from ocl_api.curricula import SCOPE_COLUMNS

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT d.id, d.name_th, d.status, s.data AS s0, {SCOPE_COLUMNS} "
                "FROM curriculum_drafts d JOIN curriculum_sections s ON s.draft_id = d.id "
                "AND s.section = '0' WHERE d.status IN ('verified', 'published') ORDER BY d.name_th"
            ).fetchall()
        out = []
        for r in rows:
            if not visible(user, r):
                continue
            teachers = ((r["s0"] or {}).get("teachers") or {}).get("teachers") or []
            v = ((r["s0"] or {}).get("info") or {}).get("values") or {}
            out.append({
                "id": r["id"], "name_th": r["name_th"], "status": r["status"],
                "edition_year": v.get("edition_year"), "faculty": r["scope_faculty"],
                "branches": sorted({t.get("group") for t in teachers if t.get("group")}),
            })  # fmt: skip
        _, steps, _ = self.flows.steps(FLOW)
        return {"curricula": out, "types": TYPES, "statuses": STATUSES, "steps": steps}

    def list(self, user: User) -> dict[str, Any]:
        from ocl_api.curricula import SCOPE_COLUMNS

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT r.*, d.name_th, {SCOPE_COLUMNS} FROM smo_requests r "
                "JOIN curriculum_drafts d ON d.id = r.draft_id ORDER BY r.created_at DESC"
            ).fetchall()
        items = []
        for r in rows:
            if not visible(user, r):
                continue
            _, steps, _ = self.flows.steps(FLOW, r["flow_version"])
            items.append(_brief(r, steps))
        return {
            "items": items,
            "counts": {s: sum(i["status"] == s for i in items) for s in STATUSES},
        }

    def get(self, rid: str, user: User) -> dict[str, Any]:
        r, cur = self._row(rid, user)
        _, steps, _ = self.flows.steps(FLOW, r["flow_version"])
        with self._conn() as conn:
            events = conn.execute(
                "SELECT ts, by, action, step, note FROM smo_events WHERE request_id = %s "
                "ORDER BY id",
                (rid,),
            ).fetchall()
            files = conn.execute(
                "SELECT id, name, size, by, ts FROM smo_files WHERE request_id = %s ORDER BY id",
                (rid,),
            ).fetchall()
        t = r["teachers"] or {}
        out = _brief(r, steps) | {
            "types": r["types"], "scope": r["scope"], "fields": r["fields"],
            "details": r["details"], "reason": r["reason"], "teachers": t,
            "changes": changes(t.get("before") or [], t.get("after") or []),
            "steps": steps, "curriculum": cur,
            "events": [{**e, "ts": e["ts"].isoformat()} for e in events],
            "files": [{**f, "ts": f["ts"].isoformat()} for f in files],
            "can_edit": r["status"] in ("draft", "returned") and self._may_edit(r, user),
            "can_act": r["status"] == "pending" and may_act(user, steps[r["step"]]),
        }  # fmt: skip
        return out

    def _row(self, rid: str, user: User) -> tuple[dict[str, Any], dict[str, Any]]:
        from ocl_api.curricula import SCOPE_COLUMNS

        with self._conn() as conn:
            r = conn.execute(
                f"SELECT r.*, d.name_th, d.status AS cur_status, {SCOPE_COLUMNS}, s.data AS s0 "
                "FROM smo_requests r JOIN curriculum_drafts d ON d.id = r.draft_id "
                "JOIN curriculum_sections s ON s.draft_id = d.id AND s.section = '0' "
                "WHERE r.id = %s",
                (rid,),
            ).fetchone()
        if r is None:
            raise SmoError(f"ไม่พบคำขอ {rid}", 404)
        if not visible(user, r):
            raise SmoError("คำขอนี้อยู่นอกขอบเขตข้อมูลของบัญชีนี้", 403)
        v = ((r["s0"] or {}).get("info") or {}).get("values") or {}
        cur = {"id": r["draft_id"], "name_th": r["name_th"], "status": r["cur_status"],
               "faculty": r["scope_faculty"], "edition_year": v.get("edition_year"),
               "name_en": v.get("name_en")}  # fmt: skip
        return r, cur

    def _may_edit(self, r: dict[str, Any], user: User) -> bool:
        return r["created_by"] == user.email or bool({"admin", "central"} & set(user.roles))

    # ---------- writes ----------

    def create(self, draft_id: int, user: User) -> dict[str, Any]:
        opts = {c["id"]: c for c in self.options(user)["curricula"]}
        if draft_id not in opts:
            raise SmoError("เลือกได้เฉพาะหลักสูตรที่ตรวจสอบสำเร็จหรือเผยแพร่แล้ว ในขอบเขตข้อมูลของบัญชีนี้", 409)
        version, steps, _ = self.flows.steps(FLOW)
        if not (may_act(user, steps[0]) or "central" in user.roles):
            raise SmoError("บทบาทของคุณสร้างคำขอ สมอ.08 ไม่ได้ (ดูการตั้งค่าการอนุมัติ)", 403)
        year = today_th().year + 543
        with self._conn() as conn, conn.transaction():
            conn.execute("LOCK TABLE smo_requests IN SHARE ROW EXCLUSIVE MODE")
            n = conn.execute(
                "SELECT count(*) AS n FROM smo_requests WHERE id LIKE %s", (f"S08-{year}-%",)
            ).fetchone()["n"]
            rid = f"S08-{year}-{n + 1:03d}"
            s0 = conn.execute(
                "SELECT data FROM curriculum_sections WHERE draft_id = %s AND section = '0'",
                (draft_id,),
            ).fetchone()["data"]
            current = ((s0 or {}).get("teachers") or {}).get("teachers") or []
            conn.execute(
                "INSERT INTO smo_requests "
                "(id, draft_id, flow_version, types, teachers, created_by) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (rid, draft_id, version, Jsonb(["teacher"]),
                 Jsonb({"before": current, "after": current}), user.email),
            )  # fmt: skip
            _event(conn, rid, user.email, "create", 0, None)
        return self.get(rid, user)

    def update(self, rid: str, data: dict[str, Any], user: User) -> dict[str, Any]:
        r, _ = self._row(rid, user)
        if r["status"] not in ("draft", "returned"):
            raise SmoError("คำขอที่ส่งแล้วแก้ไม่ได้", 409)
        if not self._may_edit(r, user):
            raise SmoError("แก้ได้เฉพาะผู้สร้างคำขอหรือส่วนกลาง", 403)
        types = [t for t in data.get("types") or [] if t in TYPES]
        scope = data.get("scope") or {"kind": "mother"}
        if scope.get("kind") not in ("mother", "child"):
            raise SmoError("ขอบเขตต้องเป็นเล่มแม่หรือเล่มลูก")
        before = (r["teachers"] or {}).get("before") or []
        after = [t for t in data.get("after") or [] if str(t.get("name") or "").strip()]
        if scope.get("kind") == "child":  # only that แขนง's rows may change
            after = [t for t in before if not in_scope(t, scope)] + [
                t for t in after if in_scope(t, scope)
            ]
        fields = {
            k: str(v).strip() for k, v in (data.get("fields") or {}).items() if v not in (None, "")
        }
        details = {
            k: str(v).strip() for k, v in (data.get("details") or {}).items() if k in TYPES and v
        }
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE smo_requests SET types = %s, scope = %s, fields = %s, teachers = %s, "
                "details = %s, reason = %s, updated_at = now() WHERE id = %s",
                (Jsonb(types), Jsonb(scope), Jsonb(fields),
                 Jsonb({"before": before, "after": after}),
                 Jsonb(details), (data.get("reason") or "").strip() or None, rid),
            )  # fmt: skip
            _event(conn, rid, user.email, "save", r["step"], None)
        return self.get(rid, user)

    def submit(self, rid: str, user: User) -> dict[str, Any]:
        d = self.get(rid, user)
        if d["status"] not in ("draft", "returned"):
            raise SmoError("คำขอนี้ส่งแล้ว", 409)
        if not d["can_edit"]:
            raise SmoError("ส่งได้เฉพาะผู้สร้างคำขอหรือส่วนกลาง", 403)
        f = d["fields"]
        need = {"ack_date": "1. วันที่ สป.อว. รับทราบ", "council": "2. มติสภามหาวิทยาลัย ครั้งที่/วันที่",
                "start_term": "3. เริ่มใช้ภาค", "start_year": "3. เริ่มใช้ปีการศึกษา"}  # fmt: skip
        miss = [label for k, label in need.items() if not f.get(k)] + (
            [] if d["reason"] else ["เหตุผล"]
        )
        if not d["types"]:
            miss.append("ประเภทการปรับปรุง")
        if "teacher" in d["types"] and not d["changes"]:
            miss.append("การเปลี่ยนแปลงรายชื่ออาจารย์")
        for t in d["types"]:
            if t != "teacher" and not d["details"].get(t):
                miss.append(f"รายละเอียด{TYPES[t]}")
        if miss:
            raise SmoError("ยังขาด " + " · ".join(miss))
        steps = d["steps"]
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE smo_requests SET status = 'pending', step = 1, submitted_at = now(), "
                "updated_at = now() WHERE id = %s",
                (rid,),
            )
            _event(conn, rid, user.email, "submit", 0, None)
        self._notify_step(d, steps[1], user.email)
        return self.get(rid, user)

    def approve(self, rid: str, user: User, note: str | None) -> dict[str, Any]:
        d = self.get(rid, user)
        if d["status"] != "pending":
            raise SmoError("คำขอนี้ไม่ได้อยู่ระหว่างอนุมัติ", 409)
        if not d["can_act"]:
            raise SmoError("ขั้นตอนนี้ไม่ใช่ของบทบาทคุณ (ดูการตั้งค่าการอนุมัติ)", 403)
        steps, step = d["steps"], d["step"]
        last = step == len(steps) - 1
        with self._conn() as conn, conn.transaction():
            _event(conn, rid, user.email, "approve", step, note)
            if not last:
                conn.execute(
                    "UPDATE smo_requests SET step = %s, updated_at = now() WHERE id = %s",
                    (step + 1, rid),
                )
            else:
                conn.execute(
                    "UPDATE smo_requests SET status = 'approved', approved_at = now(), "
                    "updated_at = now() WHERE id = %s",
                    (rid,),
                )
                self._apply(conn, d, user.email)
        if last:
            name = d["curriculum"]["name_th"]
            body = f"คำขอ {rid} ({name}) อนุมัติครบทุกขั้น ระบบปรับคู่มือหลักสูตรแล้ว"
            self._mail(d, [d["created_by"]], f"สมอ.08 {rid} อนุมัติแล้ว", body, user.email)
        else:
            self._notify_step(d, steps[step + 1], user.email)
        return self.get(rid, user)

    def send_back(self, rid: str, user: User, note: str | None) -> dict[str, Any]:
        d = self.get(rid, user)
        if d["status"] != "pending":
            raise SmoError("คำขอนี้ไม่ได้อยู่ระหว่างอนุมัติ", 409)
        if not d["can_act"]:
            raise SmoError("ขั้นตอนนี้ไม่ใช่ของบทบาทคุณ (ดูการตั้งค่าการอนุมัติ)", 403)
        if not (note or "").strip():
            raise SmoError("ต้องระบุเหตุผลที่ส่งคืน")
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE smo_requests SET status = 'returned', step = 0, updated_at = now() "
                "WHERE id = %s",
                (rid,),
            )
            _event(conn, rid, user.email, "return", d["step"], note)
        self._mail(d, [d["created_by"]], f"สมอ.08 {rid} ถูกส่งคืนแก้ไข",
                   f"ขั้น {d['steps'][d['step']]['label']}: {note}", user.email)  # fmt: skip
        return self.get(rid, user)

    def add_file(self, rid: str, name: str, content: bytes, user: User) -> dict[str, Any]:
        d = self.get(rid, user)
        if not d["can_edit"]:
            raise SmoError("แนบไฟล์ได้เมื่อคำขอเป็นร่างหรือถูกส่งคืน โดยผู้สร้างหรือส่วนกลาง", 403)
        if not name.lower().endswith(FILE_TYPES):
            raise SmoError("แนบได้เฉพาะ PDF, Word หรือรูปภาพ")
        if len(content) > FILE_MAX:
            raise SmoError("ไฟล์ใหญ่เกิน 20 MB", 413)
        folder = self.data_dir / "smo" / rid
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.\-ก-๙]", "_", Path(name).name)[-120:]
        path = folder / f"{datetime.now(BANGKOK):%Y%m%d%H%M%S}-{safe}"
        path.write_bytes(content)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO smo_files (request_id, name, path, size, by) "
                "VALUES (%s, %s, %s, %s, %s)",
                (rid, Path(name).name, str(path), len(content), user.email),
            )
        return self.get(rid, user)

    def file(self, rid: str, fid: int, user: User) -> tuple[Path, str]:
        self._row(rid, user)
        with self._conn() as conn:
            f = conn.execute(
                "SELECT name, path FROM smo_files WHERE request_id = %s AND id = %s", (rid, fid)
            ).fetchone()
        if f is None or not Path(f["path"]).is_file():
            raise SmoError("ไม่พบไฟล์", 404)
        return Path(f["path"]), f["name"]

    # ---------- after the last step ----------

    def _apply(self, conn, d: dict[str, Any], by: str) -> None:
        """The approved teacher list replaces หมวด 0.2 (of the branch, for เล่มลูก)."""
        from ocl_api.sections import write_one

        if "teacher" not in d["types"]:
            return
        s0 = conn.execute(
            "SELECT data FROM curriculum_sections WHERE draft_id = %s AND section = '0' FOR UPDATE",
            (d["curriculum"]["id"],),
        ).fetchone()["data"]
        now = (s0.get("teachers") or {}).get("teachers") or []
        scope = d["scope"]
        after = [t for t in now if not in_scope(t, scope)] + [
            t for t in d["teachers"].get("after") or [] if in_scope(t, scope)
        ]
        s0.setdefault("teachers", {})["teachers"] = [
            {**t, "order": i + 1} for i, t in enumerate(after)
        ]
        write_one(conn, d["curriculum"]["id"], "0", s0, by, f"สมอ.08 {d['id']}")
        conn.execute(
            "INSERT INTO curriculum_events (draft_id, by, action, from_status, to_status, note) "
            "VALUES (%s, %s, 'smo08', %s, %s, %s)",
            (d["curriculum"]["id"], by, d["curriculum"]["status"], d["curriculum"]["status"],
             f"สมอ.08 {d['id']} อนุมัติแล้ว ปรับรายชื่ออาจารย์ {len(d['changes'])} รายการ"),
        )  # fmt: skip

    def _notify_step(self, d: dict[str, Any], step: dict[str, Any], by: str) -> None:
        roles = step.get("roles") or ["central"]  # an outside body: central keys in its resolution
        to = self.flows.recipients(roles, d["curriculum"]["faculty"])
        who = step.get("position") or step["label"]
        body = f"{d['curriculum']['name_th']}: ขั้น {who}"
        self._mail(d, to, f"สมอ.08 {d['id']} รอ{step['label']}", body, by)

    def _mail(self, d: dict[str, Any], to: list[str], subject: str, body: str, by: str) -> None:
        if to:
            Outbox(self.url, self.schema).send(
                to, subject, body, kind="workflow", by=by, ref=f"smo:{d['id']}"
            )


def _event(conn, rid: str, by: str, action: str, step: int, note: str | None) -> None:
    conn.execute(
        "INSERT INTO smo_events (request_id, by, action, step, note) VALUES (%s, %s, %s, %s, %s)",
        (rid, by, action, step, note),
    )


def _brief(r: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    step = steps[min(r["step"], len(steps) - 1)]
    f = r["fields"] or {}
    return {
        "id": r["id"], "draft_id": r["draft_id"], "name_th": r["name_th"], "status": r["status"],
        "status_th": STATUSES[r["status"]], "step": r["step"], "steps_total": len(steps),
        "step_label": "ครบทุกขั้นตอน" if r["status"] == "approved"
        else f"{step.get('position') or ''} {step['label']}".strip(),
        "types_th": [TYPES[t] for t in r["types"] or [] if t in TYPES],
        "start": "/".join(x for x in (f.get("start_term"), f.get("start_year")) if x),
        "created_by": r["created_by"], "created_at": r["created_at"].isoformat(),
        "faculty": r["scope_faculty"],
    }  # fmt: skip
