"""Curriculum assessment by the standard (FS-6 · M4 · BRD 04 US-M4-01–08).

A round (one academic year) holds curricula, each assessed on the set of the announcement its
คู่มือ names (BR-M4-05), with recorders and a confirmer from HURIS and evaluators from the
group ผู้ประเมินหลักสูตร. The recorder sees each item's evidence, read from the curriculum,
HURIS and the SUPREME timetable with the date of the data (BR-M4-02), and what the system
computes from it (FS-6 Q2 ก); adds notes and sends; the confirmer confirms (locks) or returns;
the evaluator gives each item ผ่าน / ไม่ผ่าน / รอพิจารณา; the result follows BR-M4-01. A round
whose curricula are all assessed is locked (BR-M4-04).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from ocl_api.auth import User
from ocl_api.db import Jsonb, connect
from ocl_api.flows import today_th
from ocl_api.mail import Outbox
from ocl_api.qa_defaults import LEVELS, RULES, SETS
from ocl_api.skills import SkillStore

STATUSES = {
    "none": "ยังไม่บันทึก",
    "doing": "อยู่ระหว่างบันทึก",
    "sent": "ส่งยืนยันแล้ว",
    "confirmed": "ยืนยันข้อมูลแล้ว",
}
RESULTS = {"pass": "ผ่าน", "fail": "ไม่ผ่าน", "pending": "รอพิจารณา"}
ROUND_STATUS = {"draft": "ร่าง", "open": "เปิดใช้งาน", "closed": "ล็อกข้อมูลแล้ว"}
RANKS = ("ผู้ช่วยศาสตราจารย์", "รองศาสตราจารย์", "ศาสตราจารย์", "ผศ.", "รศ.", "ศ.")
GRAD_DEGREES = ("ปริญญาโท", "ปริญญาเอก", "โท", "เอก")
NO_THESIS = "ยังไม่มีข้อมูลปริญญานิพนธ์จาก SUPREME (A4) · ผู้บันทึกระบุในหมายเหตุ ผู้ประเมินพิจารณา"


class QaError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def set_of(standard: str | None) -> int:
    """BR-M4-05: the year of the announcement the curriculum names ('ประกาศ อว. 2565 (ตรี)')."""
    m = re.search(r"25\d\d", standard or "")
    return int(m.group()) if m and int(m.group()) in SETS else max(SETS)


def is_grad(level: str | None) -> bool:
    return bool(level) and "ตรี" not in (level or "")


def final_of(items: list[dict[str, Any]], results: dict[str, Any]) -> str:
    """BR-M4-01: ผ่าน when every applicable item passes, ไม่ผ่าน when one fails, else รอพิจารณา."""
    got = [(results.get(str(i["no"])) or {}).get("result") for i in items if i["applies"]]
    if got and all(r == "pass" for r in got):
        return "pass"
    if any(r == "fail" for r in got):
        return "fail"
    return "pending"


def _key(name: str | None) -> str:
    return re.sub(r"\s+", "", name or "")


def _event(conn, rid: int, cid: int | None, by: str, action: str, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO qa_events (round_id, curriculum_id, by, action, note) "
        "VALUES (%s, %s, %s, %s, %s)",
        (rid, cid, by, action, note),
    )


class QaStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema
        self.skills = SkillStore(url, schema)

    def _conn(self):
        return connect(self.url, self.schema)

    # ---------- FS-6a เกณฑ์ (US-M4-02) ----------

    def criteria(self) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM qa_criteria ORDER BY set_year, no").fetchall()
        return {
            "items": [{**r, "updated_at": r["updated_at"].isoformat()} for r in rows],
            "sets": SETS,
            "levels": LEVELS,
            "rules": RULES,
        }

    def save_criterion(self, cid: int | None, body: dict[str, Any], by: str) -> dict[str, Any]:
        if body.get("set_year") not in SETS:
            raise QaError("ชุดเกณฑ์ต้องเป็น พ.ศ. 2548 2558 หรือ 2565")
        title = str(body.get("title") or "").strip()
        if not title:
            raise QaError("ต้องมีชื่อเกณฑ์")
        no = int(body.get("no") or 0)
        if no < 1:
            raise QaError("ลำดับต้องเป็นเลขบวก")
        level = body.get("level") if body.get("level") in LEVELS else "all"
        rule = body.get("rule") if body.get("rule") in RULES else "none"
        vals = (
            body["set_year"],
            no,
            title,
            str(body.get("detail") or "").strip() or None,
            Jsonb([str(x) for x in body.get("sources") or []]),
            level,
            rule,
            bool(body.get("active", True)),
            by,
        )
        with self._conn() as conn:
            dup = conn.execute(
                "SELECT id FROM qa_criteria WHERE set_year = %s AND no = %s AND id <> %s",
                (body["set_year"], no, cid or 0),
            ).fetchone()
            if dup:
                raise QaError(f"ชุด {body['set_year']} มีข้อ {no} แล้ว", 409)
            if cid:
                conn.execute(
                    "UPDATE qa_criteria SET set_year = %s, no = %s, title = %s, detail = %s, "
                    "sources = %s, level = %s, rule = %s, active = %s, updated_by = %s, "
                    "updated_at = now() WHERE id = %s",
                    (*vals, cid),
                )
            else:
                conn.execute(
                    "INSERT INTO qa_criteria (set_year, no, title, detail, sources, level, rule, "
                    "active, updated_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    vals,
                )
        return self.criteria()

    def _live(self, set_year: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT no, title, detail, sources, level, rule FROM qa_criteria "
                "WHERE set_year = %s AND active ORDER BY no",
                (set_year,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------- FS-6a รอบการประเมิน (US-M4-01) ----------

    def evaluators(self) -> list[dict[str, Any]]:
        """Accounts of the group ผู้ประเมินหลักสูตร, internal or invited (FS-6 Q3 ก)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT email, name, kind FROM users WHERE roles ? 'evaluator' AND active "
                "AND (expires_at IS NULL "
                "OR expires_at >= (now() AT TIME ZONE 'Asia/Bangkok')::date) "
                "ORDER BY name, email"
            ).fetchall()
        return [dict(r) for r in rows]

    def _round(self, conn, rid: int) -> dict[str, Any]:
        r = conn.execute("SELECT * FROM qa_rounds WHERE id = %s", (rid,)).fetchone()
        if r is None:
            raise QaError("ไม่พบรอบการประเมิน", 404)
        return r

    def _round_out(self, r: dict[str, Any], progs: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": r["id"],
            "year": r["year"],
            "name": r["name"],
            "starts_on": r["starts_on"] and r["starts_on"].isoformat(),
            "ends_on": r["ends_on"] and r["ends_on"].isoformat(),
            "status": r["status"],
            "status_th": ROUND_STATUS[r["status"]],
            "closed_at": r["closed_at"] and r["closed_at"].isoformat(),
            "programs": len(progs),
            "sets": sorted({p["set_year"] for p in progs}),
            "confirmed": sum(1 for p in progs if p["status"] == "confirmed"),
        }

    def rounds(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM qa_rounds ORDER BY year DESC, id DESC").fetchall()
            progs = conn.execute("SELECT round_id, set_year, status FROM qa_programs").fetchall()
        return [self._round_out(r, [p for p in progs if p["round_id"] == r["id"]]) for r in rows]

    def round(self, rid: int) -> dict[str, Any]:
        curs = {c["id"]: c for c in self.skills.curricula(None)}
        evs = {e["email"]: e["name"] or e["email"] for e in self.evaluators()}
        with self._conn() as conn:
            r = self._round(conn, rid)
            progs = conn.execute(
                "SELECT * FROM qa_programs WHERE round_id = %s ORDER BY curriculum_id", (rid,)
            ).fetchall()
        out = self._round_out(r, progs)
        out["items"] = [
            {
                "curriculum_id": p["curriculum_id"],
                "name_th": (curs.get(p["curriculum_id"]) or {}).get("name_th"),
                "level": (curs.get(p["curriculum_id"]) or {}).get("level"),
                "faculty": (curs.get(p["curriculum_id"]) or {}).get("faculty"),
                "set_year": p["set_year"],
                "status": p["status"],
                "evaluators": [{"email": e, "name": evs.get(e, e)} for e in p["evaluators"]],
            }
            for p in progs
        ]
        return out

    def candidates(self) -> list[dict[str, Any]]:
        """Every curriculum, with the set its คู่มือ names (BR-M4-05)."""
        curs = self.skills.curricula(None)
        with self._conn() as conn:
            std = {
                r["draft_id"]: r["s"]
                for r in conn.execute(
                    "SELECT draft_id, data->'info'->'values'->>'standard_criteria' AS s "
                    "FROM curriculum_sections WHERE section = '0'"
                )
            }
        return [
            {
                "id": c["id"],
                "name_th": c["name_th"],
                "level": c["level"],
                "faculty": c["faculty"],
                "standard": std.get(c["id"]),
                "set_year": set_of(std.get(c["id"])),
            }
            for c in curs
        ]

    def save_round(self, rid: int | None, body: dict[str, Any], user: User) -> dict[str, Any]:
        year = int(body.get("year") or 0)
        if not 2500 < year < 2700:
            raise QaError("ปีการศึกษาเป็น พ.ศ. เช่น 2569")
        name = str(body.get("name") or "").strip() or f"รอบการประเมิน ปีการศึกษา {year}"
        dates = {
            k: (date.fromisoformat(body[k]) if body.get(k) else None)
            for k in ("starts_on", "ends_on")
        }
        if dates["starts_on"] and dates["ends_on"] and dates["ends_on"] < dates["starts_on"]:
            raise QaError("วันสิ้นสุดต้องไม่ก่อนวันเริ่ม")
        known = {c["id"] for c in self.skills.curricula(None)}
        evs = {e["email"] for e in self.evaluators()}
        progs = body.get("programs") or []
        for p in progs:
            if p.get("curriculum_id") not in known:
                raise QaError(f"ไม่พบคู่มือหลักสูตร {p.get('curriculum_id')}")
            if p.get("set_year") not in SETS:
                raise QaError("เกณฑ์ต้องเป็นชุด พ.ศ. 2548 2558 หรือ 2565")
            bad = [e for e in p.get("evaluators") or [] if e not in evs]
            if bad:
                raise QaError(f"{', '.join(bad)} ไม่อยู่ในกลุ่มผู้ประเมินหลักสูตร")
        with self._conn() as conn, conn.transaction():
            if rid:
                r = self._round(conn, rid)
                if r["status"] == "closed":
                    raise QaError("รอบนี้ล็อกข้อมูลแล้ว แก้ไม่ได้", 409)
                conn.execute(
                    "UPDATE qa_rounds SET year = %s, name = %s, starts_on = %s, ends_on = %s "
                    "WHERE id = %s",
                    (year, name, dates["starts_on"], dates["ends_on"], rid),
                )
            else:
                rid = conn.execute(
                    "INSERT INTO qa_rounds (year, name, starts_on, ends_on, created_by) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (year, name, dates["starts_on"], dates["ends_on"], user.email),
                ).fetchone()["id"]
            keep = [p["curriculum_id"] for p in progs]
            conn.execute(
                "DELETE FROM qa_programs WHERE round_id = %s AND NOT (curriculum_id = ANY(%s))",
                (rid, keep),
            )
            for p in progs:
                conn.execute(
                    "INSERT INTO qa_programs (round_id, curriculum_id, set_year, evaluators, "
                    "updated_by) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (round_id, "
                    "curriculum_id) DO UPDATE SET set_year = EXCLUDED.set_year, "
                    "evaluators = EXCLUDED.evaluators, updated_by = EXCLUDED.updated_by, "
                    "updated_at = now()",
                    (
                        rid,
                        p["curriculum_id"],
                        p["set_year"],
                        Jsonb(p.get("evaluators") or []),
                        user.email,
                    ),
                )
            _event(conn, rid, None, user.email, "save", name)
        return self.round(rid)

    def copy_round(self, rid: int, user: User) -> dict[str, Any]:
        """คัดลอกจากรอบก่อน: next year, same curricula, sets, evaluators and recorders."""
        with self._conn() as conn, conn.transaction():
            r = self._round(conn, rid)
            new = conn.execute(
                "INSERT INTO qa_rounds (year, name, created_by) VALUES (%s, %s, %s) RETURNING id",
                (r["year"] + 1, f"รอบการประเมิน ปีการศึกษา {r['year'] + 1}", user.email),
            ).fetchone()["id"]
            conn.execute(
                "INSERT INTO qa_programs (round_id, curriculum_id, set_year, evaluators, "
                "recorders, confirmer, updated_by) SELECT %s, curriculum_id, set_year, "
                "evaluators, recorders, confirmer, %s FROM qa_programs WHERE round_id = %s",
                (new, user.email, rid),
            )
            _event(conn, new, None, user.email, "copy", f"จากรอบ {r['name']}")
        return self.round(new)

    def open_round(self, rid: int, user: User) -> dict[str, Any]:
        """เปิดใช้งาน (one round at a time [สมมติ]); the criteria are copied into the round,
        so a later edit of the criteria does not change it."""
        with self._conn() as conn:
            r = self._round(conn, rid)
            if r["status"] != "draft":
                raise QaError("เปิดได้เฉพาะรอบที่เป็นร่าง", 409)
            other = conn.execute(
                "SELECT name FROM qa_rounds WHERE status = 'open' AND id <> %s", (rid,)
            ).fetchone()
            if other:
                raise QaError(f"มีรอบที่เปิดอยู่แล้ว ({other['name']}) ปิดรอบนั้นก่อน", 409)
            sets = [
                p["set_year"]
                for p in conn.execute(
                    "SELECT DISTINCT set_year FROM qa_programs WHERE round_id = %s", (rid,)
                )
            ]
            if not sets:
                raise QaError("ยังไม่มีหลักสูตรในรอบ")
        snap = {str(y): self._live(y) for y in sets}
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE qa_rounds SET status = 'open', criteria = %s WHERE id = %s",
                (Jsonb(snap), rid),
            )
            _event(conn, rid, None, user.email, "open")
        return self.round(rid)

    def close_round(self, rid: int, by: str, note: str | None = None) -> dict[str, Any]:
        """ปิดรอบ: locked for good, still searchable (BR-M4-04)."""
        with self._conn() as conn, conn.transaction():
            r = self._round(conn, rid)
            if r["status"] == "closed":
                raise QaError("รอบนี้ล็อกข้อมูลแล้ว", 409)
            conn.execute(
                "UPDATE qa_rounds SET status = 'closed', closed_at = now() WHERE id = %s", (rid,)
            )
            _event(conn, rid, None, by, "close", note)
        return self.round(rid)

    # ---------- FS-6b ผู้บันทึกและผู้ยืนยัน (US-M4-03) ----------

    def assign_overview(self, rid: int) -> dict[str, Any]:
        d = self.round(rid)
        names = self.skills.staff_names()
        with self._conn() as conn:
            progs = {
                p["curriculum_id"]: p
                for p in conn.execute("SELECT * FROM qa_programs WHERE round_id = %s", (rid,))
            }
        for it in d["items"]:
            p = progs[it["curriculum_id"]]
            it["recorders"] = [{"pid": x, "name": names.get(x, x)} for x in p["recorders"]]
            it["confirmer"] = p["confirmer"] and {
                "pid": p["confirmer"],
                "name": names.get(p["confirmer"], p["confirmer"]),
            }
            it["complete"] = bool(p["recorders"]) and bool(p["confirmer"])
        d["kpi"] = {
            "complete": sum(1 for i in d["items"] if i["complete"]),
            "incomplete": sum(1 for i in d["items"] if not i["complete"]),
            "confirmed": sum(1 for i in d["items"] if i["status"] == "confirmed"),
        }
        d["statuses"] = STATUSES
        return d

    def set_assign(
        self, rid: int, cid: int, recorders: list[str], confirmer: str | None, user: User
    ) -> dict[str, Any]:
        pids = [*recorders, *([confirmer] if confirmer else [])]
        known = self.skills.staff_names(pids) if pids else {}
        bad = [p for p in pids if p not in known]
        if bad:
            raise QaError(f"ไม่พบบุคลากร {', '.join(bad)} ในข้อมูล HURIS")
        with self._conn() as conn, conn.transaction():
            if self._round(conn, rid)["status"] == "closed":
                raise QaError("รอบนี้ล็อกข้อมูลแล้ว", 409)
            old = conn.execute(
                "SELECT * FROM qa_programs WHERE round_id = %s AND curriculum_id = %s",
                (rid, cid),
            ).fetchone()
            if old is None:
                raise QaError("หลักสูตรนี้ไม่อยู่ในรอบ", 404)
            conn.execute(
                "UPDATE qa_programs SET recorders = %s, confirmer = %s, updated_by = %s, "
                "updated_at = now() WHERE round_id = %s AND curriculum_id = %s",
                (Jsonb(list(dict.fromkeys(recorders))), confirmer, user.email, rid, cid),
            )
            _event(conn, rid, cid, user.email, "assign", ", ".join(known.values()))
        return self.assign_overview(rid)

    def copy_assign(self, rid: int, user: User) -> dict[str, Any]:
        """From the latest earlier round, for curricula here that have no one yet."""
        with self._conn() as conn, conn.transaction():
            prev = conn.execute(
                "SELECT id FROM qa_rounds WHERE id <> %s AND year <= (SELECT year FROM qa_rounds "
                "WHERE id = %s) ORDER BY year DESC, id DESC LIMIT 1",
                (rid, rid),
            ).fetchone()
            if prev is None:
                raise QaError("ไม่มีรอบก่อนให้คัดลอก", 404)
            n = conn.execute(
                "UPDATE qa_programs t SET recorders = s.recorders, confirmer = s.confirmer, "
                "updated_by = %s, updated_at = now() FROM qa_programs s WHERE t.round_id = %s "
                "AND s.round_id = %s AND s.curriculum_id = t.curriculum_id "
                "AND t.recorders = '[]'::jsonb AND t.confirmer IS NULL",
                (user.email, rid, prev["id"]),
            ).rowcount
            _event(conn, rid, None, user.email, "copy-assign", f"{n} หลักสูตร")
        return {**self.assign_overview(rid), "copied": n}

    def notify(self, rid: int, user: User) -> dict[str, Any]:
        d = self.assign_overview(rid)
        with self._conn() as conn:
            emails = {
                r["pid"]: r["email"]
                for r in conn.execute("SELECT pid, email FROM ext_staff WHERE email IS NOT NULL")
            }
        per: dict[str, list[str]] = {}
        for it in d["items"]:
            for p in it["recorders"]:
                per.setdefault(emails.get(p["pid"], ""), []).append(f"ผู้บันทึก · {it['name_th']}")
            if it["confirmer"]:
                per.setdefault(emails.get(it["confirmer"]["pid"], ""), []).append(
                    f"ผู้ยืนยัน · {it['name_th']}"
                )
        per.pop("", None)
        box, sent, day = Outbox(self.url, self.schema), 0, today_th().isoformat()
        for to, lines in per.items():
            m = box.send(
                [to],
                f"ได้รับมอบหมายตรวจสอบข้อมูลหลักสูตร · {d['name']}",
                "\n".join(lines),
                kind="assign",
                by=user.email,
                dedupe_key=f"qa-assign:{rid}:{to}:{day}",
            )
            sent += m is not None
        return {"sent": sent, "recipients": len(per)}

    # ---------- FS-6c หลักฐานและการตรวจสอบ (US-M4-04 05) ----------

    def _roles(self, user: User, p: dict[str, Any]) -> set[str]:
        out = set()
        if user.pid and user.pid in p["recorders"]:
            out.add("recorder")
        if user.pid and user.pid == p["confirmer"]:
            out.add("confirmer")
        if user.email.lower() in [e.lower() for e in p["evaluators"]]:
            out.add("evaluator")
        return out

    def programs(self, rid: int, user: User) -> dict[str, Any]:
        """qa-check: curricula of the round the user may see, with each item's result."""
        d = self.round(rid)
        curs = {c["id"]: c for c in self.skills.curricula(user)}
        with self._conn() as conn:
            progs = {
                p["curriculum_id"]: p
                for p in conn.execute("SELECT * FROM qa_programs WHERE round_id = %s", (rid,))
            }
            crit = self._round(conn, rid)["criteria"]
        items = []
        for it in d["items"]:
            p = progs[it["curriculum_id"]]
            roles = self._roles(user, p)
            seen = user.sees_all() or it["curriculum_id"] in curs or roles
            if not seen:
                continue
            if "evaluator" in user.roles and not user.sees_all() and "evaluator" not in roles:
                continue  # ผู้ประเมินเห็นเฉพาะหลักสูตรที่ได้รับมอบหมาย (US-M4-06)
            cr = self._items(crit, p["set_year"], it["level"])
            items.append(
                {
                    **it,
                    "roles": sorted(roles),
                    "status_th": STATUSES[p["status"]],
                    "results": {
                        str(c["no"]): (
                            "na"
                            if not c["applies"]
                            else (p["results"].get(str(c["no"])) or {}).get("result") or "none"
                        )
                        for c in cr
                    },
                    "final": final_of(cr, p["results"]),
                    "complete": bool(p["recorders"]) and bool(p["confirmer"]),
                }
            )
        return {
            **{k: d[k] for k in ("id", "year", "name", "status", "status_th")},
            "items": items,
            "statuses": STATUSES,
            "results": RESULTS,
        }

    def _items(self, crit: dict | None, set_year: int, level: str | None) -> list[dict[str, Any]]:
        rows = (crit or {}).get(str(set_year)) if crit else None
        rows = rows if rows is not None else self._live(set_year)
        grad = is_grad(level)
        return [{**r, "applies": r["level"] == "all" or grad} for r in rows]

    def _evidence(self, cur: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        """What the system reads for each item and what it computes (FS-6 Q2 ก)."""
        with self._conn() as conn:
            secs = {
                r["section"]: r["data"]
                for r in conn.execute(
                    "SELECT section, data FROM curriculum_sections WHERE draft_id = %s "
                    "AND section IN ('0', '5')",
                    (cur["id"],),
                )
            }
            others = conn.execute(
                "SELECT s.draft_id, d.name_th, s.data->'teachers'->'teachers' AS t "
                "FROM curriculum_sections s JOIN curriculum_drafts d ON d.id = s.draft_id "
                "WHERE s.section = '0' AND s.draft_id <> %s",
                (cur["id"],),
            ).fetchall()
            staff = {r["pid"]: r for r in conn.execute("SELECT * FROM ext_staff")}
            src = {r["system"]: r for r in conn.execute("SELECT * FROM ext_sources")}
            updated = conn.execute(
                "SELECT updated_at FROM curriculum_drafts WHERE id = %s", (cur["id"],)
            ).fetchone()["updated_at"]
        teachers = ((secs.get("0") or {}).get("teachers") or {}).get("teachers") or []
        approvals = ((secs.get("5") or {}).get("appr") or {}).get("approvals") or []
        grad = is_grad(cur["level"])
        now_be = today_th().year + 543

        def qual(t: dict[str, Any] | None, st: dict[str, Any] | None, works: bool) -> dict:
            edu = [str((e or [""])[0]) for e in (st or {}).get("education") or []]
            level = (t or {}).get("highest_level") or ""
            rank = f"{(st or {}).get('position') or ''} {(t or {}).get('rank') or ''}"
            q_ok = (
                any(x in GRAD_DEGREES for x in edu)
                or level in ("โท", "เอก")
                or any(r in rank for r in RANKS)
            )
            n_works = None
            if st is not None:
                n_works = sum(
                    1
                    for w in st.get("works") or []
                    if str(w.get("year") or "").isdigit() and int(w["year"]) >= now_be - 4
                )
            state = (
                "fail"
                if not q_ok
                else "pending"
                if works and n_works is None
                else "fail"
                if works and not n_works
                else "pass"
            )
            return {
                "name": (t or {}).get("name")
                or f"{(st or {}).get('title_short') or ''}{(st or {}).get('name_th') or ''}",
                "pid": (t or {}).get("pid") or (st or {}).get("pid"),
                "degree": level or (edu[-1] if edu else "–"),
                "rank": (st or {}).get("position") or (t or {}).get("rank") or "–",
                "works": n_works,
                "result": state,
            }

        def table(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return "pending"
            if any(r["result"] == "fail" for r in rows):
                return "fail"
            return "pending" if any(r["result"] == "pending" for r in rows) else "pass"

        out: dict[str, Any] = {}
        resp = [t for t in teachers if t.get("responsible")]
        for c in items:
            no, rule = str(c["no"]), c["rule"]
            if not c["applies"]:
                out[no] = {"result": "na", "text": "ไม่เกี่ยวข้องกับหลักสูตรระดับนี้"}
            elif rule == "responsible_count":
                need = 3 if grad else 5
                mine = {_key(t.get("name")) for t in resp} | {
                    t["pid"] for t in resp if t.get("pid")
                }
                dup = []
                for o in others:
                    for t in o["t"] or []:
                        if t.get("responsible") and (
                            _key(t.get("name")) in mine or (t.get("pid") and t["pid"] in mine)
                        ):
                            dup.append(f"{t.get('name')} ({o['name_th']})")
                ok = len(resp) >= need and not dup
                out[no] = {
                    "result": "pass" if ok else "fail",
                    "text": f"อาจารย์ผู้รับผิดชอบ {len(resp)} คน (เกณฑ์อย่างน้อย {need})"
                    + (f" · ซ้ำกับหลักสูตรอื่น: {', '.join(dup)}" if dup else " · ไม่ซ้ำหลักสูตรอื่น"),
                    "rows": [
                        {
                            "name": t.get("name"),
                            "pid": t.get("pid"),
                            "degree": t.get("highest_level") or "–",
                            "rank": t.get("rank") or "–",
                            "works": None,
                            "result": "pass",
                        }
                        for t in resp
                    ],
                }
            elif rule in ("responsible_qual", "staff_qual"):
                pool = resp if rule == "responsible_qual" else teachers
                rows = [qual(t, staff.get(t.get("pid")), True) for t in pool]
                res = table(rows)
                unlinked = sum(1 for t in pool if not t.get("pid"))
                out[no] = {
                    "result": res,
                    "rows": rows,
                    "text": f"{sum(1 for r in rows if r['result'] == 'pass')} / {len(rows)} คนผ่าน"
                    + (f" · {unlinked} คนยังไม่จับคู่กับ HURIS จึงไม่มีข้อมูลผลงาน" if unlinked else ""),
                }
            elif rule == "teacher_qual":
                secs_ = self.skills._sections_of(cur)
                term = max(
                    (s["term"] for s in secs_),
                    default=None,
                    key=lambda x: tuple(int(v) for v in reversed(x.split("/"))),
                )
                pids = sorted({p for s in secs_ if s["term"] == term for p in s["teachers"] or []})
                rows = [qual(None, staff.get(p), False) | {"pid": p} for p in pids]
                out[no] = {
                    "result": table(rows),
                    "rows": rows,
                    "text": (
                        f"ผู้สอนตามตารางสอนภาค {term}: {len(rows)} คน · อาจารย์พิเศษแยกไม่ได้ "
                        "จากข้อมูลตัวอย่าง"
                    )
                    if term
                    else "ไม่พบรายวิชาของหลักสูตรในตารางสอน",
                }
            elif rule == "revision_age":
                uni = next(
                    (
                        a
                        for a in approvals
                        if a.get("level_key") == "university_council"
                        and (a.get("date") or {}).get("iso")
                    ),
                    None,
                )
                if uni is None:
                    out[no] = {"result": "pending", "text": "ไม่พบวันที่สภามหาวิทยาลัยอนุมัติในหมวด 5"}
                else:
                    d = date.fromisoformat(uni["date"]["iso"])
                    years = round((today_th() - d).days / 365.25, 1)
                    out[no] = {
                        "result": "pass" if years <= 5 else "fail",
                        "text": f"สภามหาวิทยาลัยอนุมัติ {uni['date'].get('text') or d} · "
                        f"ผ่านมา {years} ปี (เกณฑ์ไม่เกิน 5 ปี)",
                    }
            else:
                out[no] = {"result": "pending", "text": NO_THESIS}

        def as_of(s: str) -> str | None:
            r = src.get(s)
            return r and r["as_of"] and r["as_of"].isoformat()

        return {
            "items": out,
            "dates": {
                "curriculum": updated.isoformat(timespec="seconds"),
                "huris": as_of("huris"),
                "supreme": as_of("supreme"),
            },
        }

    def detail(self, rid: int, cid: int, user: User) -> dict[str, Any]:
        r = self.programs(rid, user)
        it = next((i for i in r["items"] if i["curriculum_id"] == cid), None)
        if it is None:
            raise QaError("หลักสูตรนี้ไม่อยู่ในรอบ หรืออยู่นอกขอบเขตข้อมูลของบัญชีนี้", 404)
        cur = next(c for c in self.skills.curricula(None) if c["id"] == cid)
        with self._conn() as conn:
            rnd = self._round(conn, rid)
            p = conn.execute(
                "SELECT * FROM qa_programs WHERE round_id = %s AND curriculum_id = %s", (rid, cid)
            ).fetchone()
            events = conn.execute(
                "SELECT ts, by, action, note FROM qa_events WHERE round_id = %s "
                "AND curriculum_id = %s ORDER BY id",
                (rid, cid),
            ).fetchall()
        items = self._items(rnd["criteria"], p["set_year"], cur["level"])
        ev = self._evidence(cur, items)
        roles = set(it["roles"])
        staff = user.sees_all()
        live = rnd["status"] == "open"
        names = self.skills.staff_names()
        return {
            "round": {k: r[k] for k in ("id", "name", "status", "status_th")},
            "curriculum": {
                "id": cid,
                "name_th": cur["name_th"],
                "level": cur["level"],
                "faculty": cur["faculty"],
                "grad": is_grad(cur["level"]),
            },
            "set_year": p["set_year"],
            "items": [
                {
                    **c,
                    "evidence": ev["items"][str(c["no"])],
                    "note": (p["notes"] or {}).get(str(c["no"]), ""),
                    "result": (p["results"] or {}).get(str(c["no"])),
                }
                for c in items
            ],
            "dates": ev["dates"],
            "status": p["status"],
            "status_th": STATUSES[p["status"]],
            "final": final_of(items, p["results"] or {}),
            "recorders": [{"pid": x, "name": names.get(x, x)} for x in p["recorders"]],
            "confirmer": p["confirmer"]
            and {"pid": p["confirmer"], "name": names.get(p["confirmer"], p["confirmer"])},
            "evaluators": it["evaluators"],
            "roles": sorted(roles),
            "events": [{**e, "ts": e["ts"].isoformat()} for e in events],
            "can_note": live
            and it["complete"]
            and p["status"] in ("none", "doing")
            and ("recorder" in roles or staff),
            "can_confirm": live and p["status"] == "sent" and ("confirmer" in roles or staff),
            "can_evaluate": live and p["status"] == "confirmed" and ("evaluator" in roles or staff),
            "complete": it["complete"],
            "results": RESULTS,
        }

    def save_notes(self, rid: int, cid: int, notes: dict[str, str], user: User) -> dict:
        d = self.detail(rid, cid, user)
        if not d["can_note"]:
            raise QaError("บันทึกได้เฉพาะผู้บันทึกของหลักสูตร เมื่อกำหนดผู้บันทึกและผู้ยืนยันครบ และยังไม่ส่งยืนยัน", 403)
        nos = {str(i["no"]) for i in d["items"]}
        clean = {k: str(v).strip() for k, v in notes.items() if k in nos and str(v).strip()}
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE qa_programs SET notes = %s, status = 'doing', updated_by = %s, "
                "updated_at = now() WHERE round_id = %s AND curriculum_id = %s",
                (Jsonb(clean), user.email, rid, cid),
            )
            _event(conn, rid, cid, user.email, "save")
        return self.detail(rid, cid, user)

    def send(self, rid: int, cid: int, user: User) -> dict[str, Any]:
        d = self.detail(rid, cid, user)
        if not d["can_note"]:
            raise QaError("ส่งยืนยันได้เฉพาะผู้บันทึก ก่อนส่ง", 403)
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE qa_programs SET status = 'sent', updated_by = %s, updated_at = now() "
                "WHERE round_id = %s AND curriculum_id = %s",
                (user.email, rid, cid),
            )
            _event(conn, rid, cid, user.email, "send")
        self._mail_pids(
            [d["confirmer"]["pid"]],
            f"ข้อมูลหลักสูตรรอยืนยัน · {d['curriculum']['name_th']}",
            "ผู้บันทึกส่งข้อมูลเกณฑ์มาตรฐานหลักสูตรให้ยืนยัน",
            user.email,
            rid,
            cid,
        )
        return self.detail(rid, cid, user)

    def confirm(self, rid: int, cid: int, ok: bool, note: str, user: User) -> dict[str, Any]:
        d = self.detail(rid, cid, user)
        if not d["can_confirm"]:
            raise QaError("ยืนยันได้เฉพาะผู้ยืนยันของหลักสูตร เมื่อส่งยืนยันแล้ว", 403)
        if not ok and not note.strip():
            raise QaError("การส่งคืนแก้ไขต้องระบุเหตุผล")
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE qa_programs SET status = %s, updated_by = %s, updated_at = now() "
                "WHERE round_id = %s AND curriculum_id = %s",
                ("confirmed" if ok else "doing", user.email, rid, cid),
            )
            _event(conn, rid, cid, user.email, "confirm" if ok else "return", note or None)
        if ok:
            self._mail_emails(
                [e["email"] for e in d["evaluators"]],
                f"หลักสูตรพร้อมประเมิน · {d['curriculum']['name_th']}",
                "ข้อมูลยืนยันแล้ว รอบันทึกผลการประเมินรายข้อ",
                user.email,
                rid,
                cid,
            )
        else:
            self._mail_pids(
                [r["pid"] for r in d["recorders"]],
                f"ข้อมูลหลักสูตรถูกส่งคืนแก้ไข · {d['curriculum']['name_th']}",
                note,
                user.email,
                rid,
                cid,
            )
        return self.detail(rid, cid, user)

    # ---------- FS-6d ผู้ประเมินและสรุปผล (US-M4-06 07 08) ----------

    def evaluate(
        self, rid: int, cid: int, results: dict[str, dict[str, str]], user: User
    ) -> dict[str, Any]:
        d = self.detail(rid, cid, user)
        if not d["can_evaluate"]:
            raise QaError("บันทึกผลได้เฉพาะผู้ประเมินที่ได้รับมอบหมาย เมื่อยืนยันข้อมูลแล้ว", 403)
        applies = {str(i["no"]) for i in d["items"] if i["applies"]}
        got = {str(i["no"]): i["result"] for i in d["items"] if i["result"]}
        for no, r in results.items():
            if no not in applies:
                raise QaError(f"ข้อ {no} ไม่ใช้กับหลักสูตรนี้")
            if r.get("result") not in RESULTS:
                raise QaError("ผลต้องเป็น ผ่าน ไม่ผ่าน หรือ รอพิจารณา")
            got[no] = {
                "result": r["result"],
                "note": str(r.get("note") or "").strip(),
                "by": user.email,
                "at": today_th().isoformat(),
            }
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE qa_programs SET results = %s, updated_by = %s, updated_at = now() "
                "WHERE round_id = %s AND curriculum_id = %s",
                (Jsonb(got), user.email, rid, cid),
            )
            _event(conn, rid, cid, user.email, "evaluate", f"{len(results)} ข้อ")
        self._close_when_done(rid, user.email)
        return self.detail(rid, cid, user)

    def eval_return(self, rid: int, cid: int, note: str, user: User) -> dict[str, Any]:
        d = self.detail(rid, cid, user)
        if not d["can_evaluate"]:
            raise QaError("ส่งคืนได้เฉพาะผู้ประเมินที่ได้รับมอบหมาย", 403)
        if not note.strip():
            raise QaError("การส่งคืนผู้บันทึกต้องระบุเหตุผล")
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE qa_programs SET status = 'doing', updated_by = %s, updated_at = now() "
                "WHERE round_id = %s AND curriculum_id = %s",
                (user.email, rid, cid),
            )
            _event(conn, rid, cid, user.email, "eval-return", note)
        self._mail_pids(
            [r["pid"] for r in d["recorders"]],
            f"ผู้ประเมินส่งคืนข้อมูลหลักสูตร · {d['curriculum']['name_th']}",
            note,
            user.email,
            rid,
            cid,
        )
        return self.detail(rid, cid, user)

    def _close_when_done(self, rid: int, by: str) -> None:
        """BR-M4-04: when every curriculum is fully assessed (each item it uses has ผ่าน or
        ไม่ผ่าน), the round locks itself."""
        with self._conn() as conn:
            rnd = self._round(conn, rid)
            progs = conn.execute("SELECT * FROM qa_programs WHERE round_id = %s", (rid,)).fetchall()
        curs = {c["id"]: c for c in self.skills.curricula(None)}

        def done(p: dict[str, Any]) -> bool:
            level = (curs.get(p["curriculum_id"]) or {}).get("level")
            items = self._items(rnd["criteria"], p["set_year"], level)
            return p["status"] == "confirmed" and all(
                ((p["results"] or {}).get(str(i["no"])) or {}).get("result") in ("pass", "fail")
                for i in items
                if i["applies"]
            )

        if progs and rnd["status"] == "open" and all(done(p) for p in progs):
            self.close_round(rid, by, "ประเมินครบทุกหลักสูตร ระบบล็อกรอบอัตโนมัติ")

    def summary(self, rid: int, user: User) -> dict[str, Any]:
        r = self.programs(rid, user)
        rows = []
        for it in r["items"]:
            res = [v for v in it["results"].values() if v != "na"]
            rows.append(
                {
                    **{
                        k: it[k]
                        for k in (
                            "curriculum_id",
                            "name_th",
                            "level",
                            "faculty",
                            "set_year",
                            "status",
                            "final",
                        )
                    },
                    "passed": res.count("pass"),
                    "total": len(res),
                    "complete": "none" not in res and "pending" not in res,
                }
            )
        f = [x["final"] for x in rows]
        return {
            **{k: r[k] for k in ("id", "year", "name", "status", "status_th")},
            "items": rows,
            "kpi": {
                "programs": len(rows),
                "pass": f.count("pass"),
                "fail": f.count("fail"),
                "pending": f.count("pending"),
            },
        }

    def preview(self, rid: int, cid: int | None, user: User) -> list[dict[str, Any]]:
        """R10 of one curriculum or of all in the round: ฉบับร่าง until every item has a result."""
        ids = [cid] if cid else [i["curriculum_id"] for i in self.programs(rid, user)["items"]]
        out = []
        for c in ids:
            d = self.detail(rid, c, user)
            applies = [i for i in d["items"] if i["applies"]]
            complete = d["status"] == "confirmed" and all(
                (i["result"] or {}).get("result") in ("pass", "fail") for i in applies
            )
            out.append({**d, "complete": complete})
        return out

    # ---------- mail ----------

    def _mail_pids(
        self, pids: list[str], subject: str, body: str, by: str, rid: int, cid: int
    ) -> None:
        with self._conn() as conn:
            to = [
                r["email"]
                for r in conn.execute(
                    "SELECT email FROM ext_staff WHERE pid = ANY(%s) AND email IS NOT NULL", (pids,)
                )
            ]
        self._mail_emails(to, subject, body, by, rid, cid)

    def _mail_emails(
        self, to: list[str], subject: str, body: str, by: str, rid: int, cid: int
    ) -> None:
        if to:
            Outbox(self.url, self.schema).send(
                to, subject, body or "-", kind="qa", by=by, ref=f"qa:{rid}:{cid}"
            )
