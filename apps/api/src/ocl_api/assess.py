"""Skill assessment, portfolio and Skill Transcript (FS-5d–g · M3 · BRD 03 US-M3-05–10).

Teachers score the students of their sections on the skills the approved mapping gives the
course (BR-M3-06); a confirmed section counts in the portfolio, where a skill's score is the
plain average over the courses that assessed it (BR-M3-01) and its level comes from the
five-level table (BR-M3-02). A graduate whose set is fully assessed and whose Ethics are all
S gets a numbered, signed Skill Transcript (BR-M3-04) that anyone can check by its number or
QR code (BR-M3-05). The signing service is not chosen, so SampleSigner signs [สมมติ].
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import date
from typing import Any

from ocl_api.auth import User
from ocl_api.db import Jsonb, connect
from ocl_api.external.signature import SampleSigner
from ocl_api.flows import FlowStore, covers, today_th
from ocl_api.mail import Outbox
from ocl_api.skill_defaults import CATS
from ocl_api.skills import SkillError, SkillStore, _event, level_of, pick_set, term_sort

SECTION_STATUS = {
    "todo": "ยังไม่ประเมิน",
    "doing": "กำลังประเมิน",
    "wait": "รอยืนยัน",
    "ok": "ยืนยันแล้ว",
}
GRADUATED = "สำเร็จการศึกษา"
DOC_FLOW = "skill_transcript"


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


class AssessStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema
        self.skills = SkillStore(url, schema)
        self.flows = FlowStore(url, schema)

    def _conn(self):
        return connect(self.url, self.schema)

    # ---------- FS-5d บันทึกประเมิน (US-M3-05 06) ----------

    def _deadline(self, conn, term: str) -> str | None:
        """กำหนดส่ง [สมมติ]: the term's report deadline in M2, else its last day."""
        r = conn.execute(
            "SELECT report_close, ends_on FROM m2_terms WHERE term = %s", (term,)
        ).fetchone()
        d = r and (r["report_close"] or r["ends_on"])
        return d.isoformat() if d else None

    def sections(self, term: str, user: User) -> dict[str, Any]:
        """Course sections to assess in the term within the user's scope."""
        maps = self.skills.approved_maps(term)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT s.*, p.faculty, p.short AS program FROM ext_sections s "
                "LEFT JOIN ext_programs p ON p.code = s.program_code "
                "WHERE s.term = %s AND s.course_code = ANY(%s) ORDER BY s.course_code, s.section",
                (term, list(maps)),
            ).fetchall()
            roster = {
                (r["course_code"], r["section"]): r["n"]
                for r in conn.execute(
                    "SELECT course_code, section, count(*) AS n FROM ext_enrollments "
                    "WHERE term = %s GROUP BY 1, 2",
                    (term,),
                )
            }
            done = {}
            for r in conn.execute(
                "SELECT course_code, section, sid, array_agg(skill) AS skills FROM skill_scores "
                "WHERE term = %s GROUP BY 1, 2, 3",
                (term,),
            ):
                done.setdefault((r["course_code"], r["section"]), []).append(set(r["skills"]))
            state = {
                (r["course_code"], r["section"]): r
                for r in conn.execute("SELECT * FROM skill_sections WHERE term = %s", (term,))
            }
            deadline = self._deadline(conn, term)
        names = self.skills.staff_names()
        kinds = user.scope_kinds()
        items = []
        for s in rows:
            if not (
                user.sees_all()
                or ("faculty" in kinds and covers(user.units, s["faculty"]))
                or (user.pid and user.pid in (s["teachers"] or []))
            ):
                continue
            key = (s["course_code"], s["section"])
            need = set(maps[s["course_code"]]["skills"])
            n = roster.get(key, 0)
            scored = done.get(key, [])
            full = sum(1 for got in scored if need <= got)
            st = state.get(key)
            status = (
                "ok"
                if st and st["status"] == "confirmed"
                else "todo"
                if not scored
                else "wait"
                if full >= n and n
                else "doing"
            )
            items.append(
                {
                    "course_code": s["course_code"],
                    "section": s["section"],
                    "name_th": s["course_name"],
                    "program": s["program"],
                    "faculty": s["faculty"],
                    "curricula": maps[s["course_code"]]["curricula"],
                    "skills": maps[s["course_code"]]["skills"],
                    "n": n,
                    "done": full,
                    "teachers": [{"pid": p, "name": names.get(p, p)} for p in s["teachers"] or []],
                    "mine": bool(user.pid and user.pid in (s["teachers"] or [])),
                    "status": status,
                    "deadline": deadline,
                }
            )
        return {"term": term, "items": items, "statuses": SECTION_STATUS, "deadline": deadline}

    def section(self, term: str, code: str, sec: str, user: User) -> dict[str, Any]:
        got = next(
            (
                i
                for i in self.sections(term, user)["items"]
                if i["course_code"] == code and i["section"] == sec
            ),
            None,
        )
        if got is None:
            raise SkillError("ไม่พบรายวิชา-กลุ่มนี้ในรายการที่ต้องประเมินของบัญชีนี้", 404)
        with self._conn() as conn:
            students = conn.execute(
                "SELECT e.sid, s.name_th, s.program_code FROM ext_enrollments e "
                "LEFT JOIN ext_students s ON s.sid = e.sid "
                "WHERE e.term = %s AND e.course_code = %s AND e.section = %s ORDER BY e.sid",
                (term, code, sec),
            ).fetchall()
            scores: dict[str, dict[str, float]] = {}
            for r in conn.execute(
                "SELECT sid, skill, score FROM skill_scores "
                "WHERE term = %s AND course_code = %s AND section = %s",
                (term, code, sec),
            ):
                scores.setdefault(r["sid"], {})[r["skill"]] = float(r["score"])
            st = conn.execute(
                "SELECT * FROM skill_sections WHERE term = %s AND course_code = %s "
                "AND section = %s",
                (term, code, sec),
            ).fetchone()
            events = conn.execute(
                "SELECT ts, by, action, note FROM skill_events WHERE kind = 'section' "
                "AND ref = %s ORDER BY id",
                (f"{term}|{code}|{sec}",),
            ).fetchall()
        locked = got["status"] == "ok"
        may = got["mine"] or user.sees_all()
        return {
            **got,
            "term": term,
            "students": students,
            "scores": scores,
            "skill_rows": [s for s in self.skills.skills() if s["code"] in got["skills"]],
            "levels": self.skills.settings()["levels"],
            "confirmed_by": st and st["confirmed_by"],
            "confirmed_at": st and st["confirmed_at"] and st["confirmed_at"].isoformat(),
            "events": [{**e, "ts": e["ts"].isoformat()} for e in events],
            "can_edit": may and not locked,
            "can_reopen": locked and user.sees_all(),
        }

    def save_scores(
        self, term: str, code: str, sec: str, scores: dict[str, dict[str, float | None]], user: User
    ) -> dict[str, Any]:
        d = self.section(term, code, sec, user)
        if not d["can_edit"]:
            raise SkillError("บัญชีนี้บันทึกคะแนนกลุ่มนี้ไม่ได้ (ไม่ใช่ผู้สอน หรือยืนยันผลแล้ว)", 403)
        sids = {s["sid"] for s in d["students"]}
        need = set(d["skills"])
        rows, gone = [], []
        for sid, per in scores.items():
            if sid not in sids:
                raise SkillError(f"นิสิต {sid} ไม่อยู่ในกลุ่มเรียนนี้")
            for skill, v in per.items():
                if skill not in need:
                    raise SkillError(f"{skill} ไม่ใช่ Skill ที่ต้องประเมินในรายวิชานี้")
                if v is None or v == "":
                    gone.append((sid, skill))
                    continue
                v = float(v)
                if not 0 <= v <= 5:
                    raise SkillError("คะแนนต้องอยู่ระหว่าง 0–5")
                rows.append((sid, skill, round(v, 2)))
        with self._conn() as conn, conn.transaction():
            for sid, skill in gone:
                conn.execute(
                    "DELETE FROM skill_scores WHERE term = %s AND course_code = %s "
                    "AND section = %s AND sid = %s AND skill = %s",
                    (term, code, sec, sid, skill),
                )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO skill_scores (term, course_code, section, sid, skill, score) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (term, course_code, section, "
                    "sid, skill) DO UPDATE SET score = EXCLUDED.score",
                    [(term, code, sec, *r) for r in rows],
                )
            conn.execute(
                "INSERT INTO skill_sections (term, course_code, section, updated_by) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (term, course_code, section) "
                "DO UPDATE SET updated_by = EXCLUDED.updated_by, updated_at = now()",
                (term, code, sec, user.email),
            )
            _event(
                conn, "section", f"{term}|{code}|{sec}", user.email, "save", f"{len(rows)} คะแนน"
            )
        return self.section(term, code, sec, user)

    def confirm(self, term: str, code: str, sec: str, user: User) -> dict[str, Any]:
        d = self.section(term, code, sec, user)
        if not d["can_edit"]:
            raise SkillError("บัญชีนี้ยืนยันผลกลุ่มนี้ไม่ได้", 403)
        if d["done"] < d["n"] or not d["n"]:
            raise SkillError(f"ยังประเมินไม่ครบ ({d['done']} / {d['n']} คน)")
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "INSERT INTO skill_sections (term, course_code, section, status, updated_by, "
                "confirmed_by, confirmed_at) VALUES (%s, %s, %s, 'confirmed', %s, %s, now()) "
                "ON CONFLICT (term, course_code, section) DO UPDATE SET status = 'confirmed', "
                "confirmed_by = EXCLUDED.confirmed_by, confirmed_at = now()",
                (term, code, sec, user.email, user.email),
            )
            _event(conn, "section", f"{term}|{code}|{sec}", user.email, "confirm")
        return self.section(term, code, sec, user)

    def reopen(self, term: str, code: str, sec: str, note: str, user: User) -> dict[str, Any]:
        d = self.section(term, code, sec, user)
        if not d["can_reopen"]:
            raise SkillError("เปิดให้แก้ได้เฉพาะส่วนกลาง เมื่อยืนยันผลแล้ว", 403)
        if not note.strip():
            raise SkillError("ต้องระบุเหตุผลที่เปิดให้แก้")
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE skill_sections SET status = 'draft', confirmed_by = NULL, "
                "confirmed_at = NULL WHERE term = %s AND course_code = %s AND section = %s",
                (term, code, sec),
            )
            _event(conn, "section", f"{term}|{code}|{sec}", user.email, "reopen", note)
        return self.section(term, code, sec, user)

    def form_xlsx(self, term: str, code: str, sec: str, user: User) -> bytes:
        from openpyxl import Workbook

        d = self.section(term, code, sec, user)
        wb = Workbook()
        ws = wb.active
        ws.title = "คะแนน"
        ws.append(["รหัสนิสิต", "ชื่อ", *d["skills"]])
        for s in d["students"]:
            got = d["scores"].get(s["sid"], {})
            ws.append([s["sid"], s["name_th"], *[got.get(k) for k in d["skills"]]])
        info = wb.create_sheet("วิธีกรอก")
        info.append([f"{code} กลุ่ม {sec} ภาค {term}"])
        info.append(["กรอกคะแนน 0–5 (ทศนิยม 2 ตำแหน่ง) ใต้รหัส Skill · ช่องว่าง = ยังไม่ประเมิน"])
        for s in d["skill_rows"]:
            info.append([s["code"], s["name_th"], s["name_en"] or ""])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def import_xlsx(
        self, term: str, code: str, sec: str, data: bytes, user: User
    ) -> dict[str, Any]:
        from openpyxl import load_workbook

        try:
            ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
        except Exception as e:  # noqa: BLE001 -- any unreadable file is the user's error
            raise SkillError("อ่านไฟล์ .xlsx ไม่ได้") from e
        rows = list(ws.iter_rows(values_only=True))
        if not rows or str(rows[0][0] or "").strip() != "รหัสนิสิต":
            raise SkillError("หัวตารางไม่ตรงแบบฟอร์ม (ดาวน์โหลดแบบฟอร์ม Excel ก่อน)")
        head = [str(c or "").strip() for c in rows[0]]
        scores: dict[str, dict[str, float | None]] = {}
        for row in rows[1:]:
            sid = str(row[0] or "").strip()
            if not sid:
                continue
            scores[sid] = {
                k: (None if row[i] in (None, "") else row[i])
                for i, k in enumerate(head)
                if i >= 2 and k
            }
        out = self.save_scores(term, code, sec, scores, user)
        return {**out, "imported": len(scores)}

    # ---------- FS-5e Portfolio (US-M3-07 09) ----------

    def _students(self, conn, user: User | None) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT s.*, p.faculty, p.short AS program FROM ext_students s "
            "LEFT JOIN ext_programs p ON p.code = s.program_code ORDER BY s.sid"
        ).fetchall()
        if user is None or user.sees_all():
            return rows
        kinds = user.scope_kinds()
        taught: set[str] = set()
        if user.pid and user.can_do("s4"):  # a teacher: the students of their sections
            taught = {
                r["sid"]
                for r in conn.execute(
                    "SELECT e.sid FROM ext_enrollments e JOIN ext_sections s ON s.term = e.term "
                    "AND s.course_code = e.course_code AND s.section = e.section "
                    "WHERE s.teachers ? %s",
                    (user.pid,),
                )
            }
        programs = {c["program_code"] for c in self.skills.curricula(user) if c["program_code"]}
        return [
            r
            for r in rows
            if ("faculty" in kinds and covers(user.units, r["faculty"]))
            or (user.pid and r["advisor_pid"] == user.pid)  # อาจารย์ที่ปรึกษา: นิสิตในความดูแล
            or r["sid"] in taught
            or ("program" in kinds and r["program_code"] in programs)
        ]

    def _scores(self, conn, sids: list[str]) -> list[dict[str, Any]]:
        """Scores of confirmed sections only (US-M3-06: confirmed results count)."""
        return conn.execute(
            "SELECT sc.*, s.course_name FROM skill_scores sc JOIN skill_sections ss "
            "ON ss.term = sc.term AND ss.course_code = sc.course_code "
            "AND ss.section = sc.section AND ss.status = 'confirmed' "
            "LEFT JOIN ext_sections s ON s.term = sc.term AND s.course_code = sc.course_code "
            "AND s.section = sc.section WHERE sc.sid = ANY(%s) ORDER BY sc.term, sc.course_code",
            (sids,),
        ).fetchall()

    def _summary(
        self,
        student: dict[str, Any],
        scores: list[dict[str, Any]],
        skills: dict[str, dict[str, Any]],
        settings: dict[str, Any],
    ) -> dict:
        """Averages per skill (BR-M3-01), per side and overall, with levels and Ethics S/U."""
        levels = settings["levels"]
        per: dict[str, list[float]] = {}
        for r in scores:
            per.setdefault(r["skill"], []).append(float(r["score"]))
        avg = {k: _avg(v) for k, v in per.items()}
        cats = {c: _avg([avg[k] for k in avg if skills.get(k, {}).get("cat") == c]) for c in CATS}
        overall = _avg([v for v in cats.values() if v is not None])
        lv = level_of(overall, levels)
        return {
            "avg": avg,
            "n": {k: len(v) for k, v in per.items()},
            "cats": cats,
            "overall": overall,
            "level": lv and lv["en"],
        }

    def _load(self, conn, studs: list[dict[str, Any]]) -> dict[str, Any]:
        """Everything a set of portfolios needs, in a handful of queries (Neon is slow)."""
        sids = [s["sid"] for s in studs]
        codes = list({s["program_code"] for s in studs if s["program_code"]})
        curs = {}
        for r in conn.execute(
            "SELECT DISTINCT ON (program_code) id, name_th, program_code FROM curriculum_drafts "
            "WHERE program_code = ANY(%s) ORDER BY program_code, id DESC",
            (codes,),
        ):
            curs[r["program_code"]] = {"id": r["id"], "name_th": r["name_th"]}
        sets: dict[int, list[dict[str, Any]]] = {}
        for r in conn.execute(
            "SELECT * FROM skill_sets WHERE curriculum_id = ANY(%s)",
            ([c["id"] for c in curs.values()],),
        ):
            sets.setdefault(r["curriculum_id"], []).append(r)
        scores: dict[str, list[dict[str, Any]]] = {}
        for r in self._scores(conn, sids):
            scores.setdefault(r["sid"], []).append(r)
        docs = {
            r["sid"]: r
            for r in conn.execute(
                "SELECT DISTINCT ON (sid) sid, no, status, issued_at FROM skill_transcripts "
                "WHERE sid = ANY(%s) ORDER BY sid, created_at DESC",
                (sids,),
            )
        }
        return {
            "curs": curs,
            "sets": sets,
            "scores": scores,
            "docs": docs,
            "skills": {s["code"]: s for s in self.skills.skills()},
            "settings": self.skills.settings(),
        }

    def portfolio_list(self, user: User) -> dict[str, Any]:
        with self._conn() as conn:
            studs = self._students(conn, user)
            ld = self._load(conn, studs)
        items = []
        for s in studs:
            sm = self._summary(s, ld["scores"].get(s["sid"], []), ld["skills"], ld["settings"])
            items.append(
                {
                    "sid": s["sid"],
                    "name_th": s["name_th"],
                    "program": s["program"],
                    "program_code": s["program_code"],
                    "faculty": s["faculty"],
                    "entry_year": s["entry_year"],
                    "status": s["status"],
                    "cats": sm["cats"],
                    "overall": sm["overall"],
                    "level": sm["level"],
                }
            )
        return {"items": items, "levels": ld["settings"]["levels"]}

    def portfolio(self, sid: str, user: User | None) -> dict[str, Any]:
        """One student's portfolio; `user` None = the student's own (checked by the caller)."""
        with self._conn() as conn:
            studs = self._students(conn, user)
            st = next((s for s in studs if s["sid"] == sid), None)
            if st is None:
                exists = conn.execute("SELECT 1 FROM ext_students WHERE sid = %s", (sid,))
                if user is not None and exists.fetchone():
                    raise SkillError("นิสิตคนนี้อยู่นอกขอบเขตข้อมูลของบัญชีนี้", 403)
                raise SkillError("ไม่พบนิสิต", 404)
            ld = self._load(conn, [st])
            advisor = conn.execute(
                "SELECT title_short, name_th FROM ext_staff WHERE pid = %s", (st["advisor_pid"],)
            ).fetchone()
            pname = conn.execute(
                "SELECT name_th FROM ext_programs WHERE code = %s", (st["program_code"],)
            ).fetchone()
        st = {
            **st,
            "program_name": pname and pname["name_th"],
            "advisor": advisor and f"{advisor['title_short'] or ''}{advisor['name_th']}",
        }
        return self._build(st, ld)

    def _build(self, st: dict[str, Any], ld: dict[str, Any]) -> dict[str, Any]:
        skills, settings = ld["skills"], ld["settings"]
        cur = ld["curs"].get(st["program_code"])
        sset = cur and pick_set(ld["sets"].get(cur["id"], []), (st["entry_year"] or 0) % 100)
        scores = ld["scores"].get(st["sid"], [])
        doc = ld["docs"].get(st["sid"])
        sm = self._summary(st, scores, skills, settings)
        codes = list(sset["skills"]) if sset else []
        codes += [k for k in sm["avg"] if k not in codes]
        rows = []
        for k in codes:
            s = skills.get(k, {"code": k, "cat": "?", "name_th": k})
            a = sm["avg"].get(k)
            lv = level_of(a, settings["levels"])
            rows.append(
                {
                    "code": k,
                    "cat": s["cat"],
                    "name_th": s["name_th"],
                    "name_en": s.get("name_en"),
                    "definition": s.get("definition"),
                    "avg": a,
                    "level": lv and lv["en"],
                    "n": sm["n"].get(k, 0),
                    "in_set": bool(sset) and k in sset["skills"],
                    "su": (
                        None
                        if s["cat"] != "E" or a is None
                        else "S"
                        if a >= settings["ethics_pass"]
                        else "U"
                    ),
                    "sources": [
                        {
                            "term": r["term"],
                            "course_code": r["course_code"],
                            "course_name": r["course_name"],
                            "section": r["section"],
                            "score": float(r["score"]),
                        }
                        for r in scores
                        if r["skill"] == k
                    ],
                }
            )
        terms = sorted({r["term"] for r in scores}, key=term_sort)
        entry = st["entry_year"] or 0
        by_term = []
        for t in terms:
            n, y = t.split("/")
            part = [r for r in scores if r["term"] == t]
            tsm = self._summary(st, part, skills, settings)
            by_term.append({"term": t, "label": f"ปี {int(y) - entry + 1}/{n}", "cats": tsm["cats"]})
        missing = [r["code"] for r in rows if r["in_set"] and r["avg"] is None]
        ethics_u = [r["code"] for r in rows if r["su"] == "U"]
        graduated = st["status"] == GRADUATED or bool(st["graduated"])
        return {
            "student": st,
            "curriculum": cur,
            "set": sset
            and {
                "version": sset["version"],
                "cohort_from": sset["cohort_from"],
                "skills": sset["skills"],
            },
            "skills": rows,
            "cats": sm["cats"],
            "overall": sm["overall"],
            "level": sm["level"],
            "by_term": by_term,
            "levels": settings["levels"],
            "ethics_pass": settings["ethics_pass"],
            "placement": None,  # สถานที่ฝึกประสบการณ์: not in the SUPREME sample (A4)
            "readiness": {
                "graduated": graduated,
                "has_set": bool(sset),
                "missing": missing,
                "ethics_u": ethics_u,
                "ready": graduated and bool(sset) and not missing and not ethics_u,
            },
            "transcript": doc
            and {
                "no": doc["no"],
                "status": doc["status"],
                "issued_at": doc["issued_at"] and doc["issued_at"].isoformat(),
            },
        }

    # ---------- FS-5f ออกเอกสาร Skill Transcript (US-M3-08 · BR-M3-04 05) ----------

    def graduates(self, user: User) -> dict[str, Any]:
        with self._conn() as conn:
            studs = [
                s for s in self._students(conn, user) if s["status"] == GRADUATED or s["graduated"]
            ]
            ld = self._load(conn, studs)
        items = []
        for s in studs:
            p = self._build(s, ld)
            rd = p["readiness"]
            doc = p["transcript"]
            group = (
                "issued"
                if doc
                else "ready"
                if rd["ready"]
                else "ethics"
                if rd["has_set"] and not rd["missing"]
                else "incomplete"
            )
            items.append(
                {
                    "sid": s["sid"],
                    "name_th": s["name_th"],
                    "program": s["program"],
                    "faculty": s["faculty"],
                    "graduated": s["graduated"],
                    "curriculum": p["curriculum"],
                    "set_size": len((p["set"] or {}).get("skills", [])),
                    "missing": rd["missing"],
                    "has_set": rd["has_set"],
                    "ethics_u": rd["ethics_u"],
                    "group": group,
                    "transcript": doc and {"no": doc["no"], "status": doc["status"]},
                }
            )
        groups = {
            g: sum(1 for i in items if i["group"] == g)
            for g in ("ready", "incomplete", "ethics", "issued")
        }
        return {"items": items, "groups": groups, "ethics_pass": ld["settings"]["ethics_pass"]}

    def _signer(self, conn) -> dict[str, Any]:
        r = conn.execute("SELECT * FROM ext_signers ORDER BY id LIMIT 1").fetchone()
        if r is None:
            raise SkillError("ยังไม่มีข้อมูลผู้ลงนามจาก SUPREME")
        return {"id": r["id"], "name_th": r["name_th"], "position": r["position"]}

    def _document(self, p: dict[str, Any], signer: dict[str, Any] | None) -> dict[str, Any]:
        st = p["student"]
        return {
            "student": {
                k: st.get(k)
                for k in (
                    "sid",
                    "name_th",
                    "program",
                    "program_name",
                    "faculty",
                    "entry_year",
                    "graduated",
                )
            },
            "curriculum": p["curriculum"],
            "set_version": (p["set"] or {}).get("version"),
            "skills": [
                {
                    k: r[k]
                    for k in (
                        "code",
                        "cat",
                        "name_th",
                        "name_en",
                        "definition",
                        "avg",
                        "level",
                        "su",
                    )
                }
                for r in p["skills"]
                if r["in_set"]
            ],
            "cats": p["cats"],
            "overall": p["overall"],
            "level": p["level"],
            "placement": p["placement"],
            "signer": signer,
        }

    def issue(self, sids: list[str], user: User) -> dict[str, Any]:
        """สร้างเอกสารและส่งลงนาม: only graduates ready under BR-M3-04."""
        ready = {i["sid"]: i for i in self.graduates(user)["items"] if i["group"] == "ready"}
        bad = [s for s in sids if s not in ready]
        if bad:
            raise SkillError(f"ออกเอกสารได้เฉพาะผู้ที่พร้อมออก ({', '.join(bad)} ยังไม่พร้อม)")
        _, steps, _ = self.flows.steps(DOC_FLOW)
        year = today_th().year + 543
        out = []
        with self._conn() as conn, conn.transaction():
            conn.execute("LOCK TABLE skill_transcripts IN EXCLUSIVE MODE")
            last = conn.execute(
                "SELECT max(no) AS no FROM skill_transcripts WHERE no LIKE %s", (f"ST-{year}-%",)
            ).fetchone()["no"]
            seq = int(last.rsplit("-", 1)[1]) if last else 0
            signer = self._signer(conn)
            for sid in sids:
                seq += 1
                no = f"ST-{year}-{seq:06d}"
                data = {
                    **self._document(self.portfolio(sid, None), signer),
                    "no": no,
                    "issued_on": today_th().isoformat(),
                }
                sha = digest(data)
                sig = SampleSigner().sign(sha.encode(), signer["id"])
                conn.execute(
                    "INSERT INTO skill_transcripts (no, sid, curriculum_id, data, sha256, signer, "
                    "status, step, created_by, issued_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'issued', %s, %s, now())",
                    (
                        no,
                        sid,
                        (data["curriculum"] or {}).get("id"),
                        Jsonb(data),
                        sha,
                        Jsonb({**signer, **sig}),
                        len(steps),
                        user.email,
                    ),
                )
                _event(conn, "transcript", no, user.email, "review", steps[0]["label"])
                _event(conn, "transcript", no, f"signer:{signer['id']}", "sign", sig["method"])
                out.append(no)
        return {"issued": out}

    def transcript(self, sid: str, user: User | None) -> dict[str, Any]:
        """The issued document, else the draft built from the live portfolio (ฉบับร่าง)."""
        p = self.portfolio(sid, user)
        with self._conn() as conn:
            r = conn.execute(
                "SELECT * FROM skill_transcripts WHERE sid = %s ORDER BY created_at DESC LIMIT 1",
                (sid,),
            ).fetchone()
        levels = self.skills.settings()["levels"]
        if r is None:
            return {
                "draft": True,
                "no": None,
                "data": self._document(p, None),
                "levels": levels,
                "readiness": p["readiness"],
            }
        return {
            "draft": False,
            "no": r["no"],
            "data": r["data"],
            "signer": r["signer"],
            "issued_at": r["issued_at"] and r["issued_at"].isoformat(),
            "checks": r["checks"],
            "levels": levels,
            "readiness": p["readiness"],
        }

    def register(self, user: User) -> list[dict[str, Any]]:
        """R09: documents issued, with how often each was checked."""
        with self._conn() as conn:
            seen = {s["sid"] for s in self._students(conn, user)}
            rows = conn.execute(
                "SELECT no, sid, data, status, checks, issued_at, created_by "
                "FROM skill_transcripts ORDER BY no DESC"
            ).fetchall()
        return [
            {
                "no": r["no"],
                "sid": r["sid"],
                "name_th": r["data"]["student"]["name_th"],
                "program": r["data"]["student"]["program"],
                "status": r["status"],
                "checks": r["checks"],
                "issued_at": r["issued_at"] and r["issued_at"].isoformat(),
                "by": r["created_by"],
            }
            for r in rows
            if r["sid"] in seen
        ]

    def verify(self, no: str) -> dict[str, Any]:
        """The public check (BR-M3-05): no sign-in; counts each check for R09."""
        with self._conn() as conn:
            r = conn.execute(
                "UPDATE skill_transcripts SET checks = checks + 1 WHERE no = %s RETURNING *",
                (no.strip().upper(),),
            ).fetchone()
        if r is None:
            raise SkillError("ไม่พบเอกสารเลขที่นี้", 404)
        d = r["data"]
        sig = r["signer"] or {}
        return {
            "no": r["no"],
            "name_th": d["student"]["name_th"],
            "sid": d["student"]["sid"],
            "program": d["student"]["program"],
            "faculty": d["student"]["faculty"],
            "curriculum": (d.get("curriculum") or {}).get("name_th"),
            "issued_at": r["issued_at"] and r["issued_at"].isoformat(),
            "signer": {"name_th": sig.get("name_th"), "position": sig.get("position")},
            "signature": {
                "method": sig.get("method"),
                "sample": bool(sig.get("sample")),
                "valid": digest(d) == r["sha256"],
            },
            "checks": r["checks"],
        }

    # ---------- FS-5g แดชบอร์ด Skill (US-M3-10) ----------

    def dashboard(self, term: str, user: User, target: int = 70) -> dict[str, Any]:
        rows = self.sections(term, user)["items"]
        g = self.graduates(user)
        st = {k: sum(1 for r in rows if r["status"] == k) for k in SECTION_STATUS}
        n, done = sum(r["n"] for r in rows), sum(r["done"] for r in rows)
        fac: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            fac.setdefault(r["faculty"] or "ไม่ระบุคณะ", []).append(r)

        def pct(a: int, b: int) -> int:
            return round(a * 100 / b) if b else 0

        units = []
        for f, rs in sorted(fac.items()):
            p = pct(sum(r["done"] for r in rs), sum(r["n"] for r in rs))
            units.append(
                {
                    "faculty": f,
                    "sections": len(rs),
                    "status": {k: sum(1 for r in rs if r["status"] == k) for k in SECTION_STATUS},
                    "confirmed_pct": pct(sum(1 for r in rs if r["status"] == "ok"), len(rs)),
                    "assessed_pct": p,
                    "below": p < target,
                }
            )
        dl = rows[0]["deadline"] if rows else None
        late_days = (today_th() - date.fromisoformat(dl)).days if dl else None
        order = {"todo": 0, "doing": 1, "wait": 2}
        late = sorted(
            [r for r in rows if r["status"] != "ok"], key=lambda r: (order[r["status"]], -r["n"])
        )
        return {
            "term": term,
            "sections": len(rows),
            "students": n,
            "assessed_pct": pct(done, n),
            "status": st,
            "transcripts": g["groups"],
            "graduates": len(g["items"]),
            "units": units,
            "target_pct": target,
            "deadline": dl,
            "late_days": late_days if late_days and late_days > 0 else 0,
            "late": [
                {
                    k: r[k]
                    for k in (
                        "course_code",
                        "section",
                        "name_th",
                        "faculty",
                        "status",
                        "n",
                        "done",
                        "teachers",
                    )
                }
                for r in late[:50]
            ],
        }

    def remind(
        self, term: str, user: User, code: str | None = None, sec: str | None = None
    ) -> dict[str, Any]:
        rows = [
            r
            for r in self.sections(term, user)["items"]
            if r["status"] != "ok"
            and (code is None or (r["course_code"] == code and r["section"] == sec))
        ]
        day = today_th().isoformat()
        box, sent = Outbox(self.url, self.schema), 0
        with self._conn() as conn:
            emails = {
                r["pid"]: r["email"]
                for r in conn.execute("SELECT pid, email FROM ext_staff WHERE email IS NOT NULL")
            }
        for r in rows:
            to = [emails[t["pid"]] for t in r["teachers"] if t["pid"] in emails]
            if not to:
                continue
            m = box.send(
                to,
                f"ประเมิน Skill รายวิชา {r['course_code']} กลุ่ม {r['section']} ภาค {term}",
                f"สถานะ {SECTION_STATUS[r['status']]} · ประเมินแล้ว {r['done']} / {r['n']} คน",
                kind="reminder",
                by=user.email,
                ref=f"skill-section:{term}:{r['course_code']}:{r['section']}",
                dedupe_key=f"skill-late:{term}:{r['course_code']}:{r['section']}:{day}",
            )
            sent += m is not None
        return {"sent": sent, "late": len(rows)}
