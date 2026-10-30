"""แผนและรายงานการจัดการเรียนรู้ (FS-4 · M2 · BRD 02).

The unit of work is a course, or a module (ชุดวิชา) of the central course database, offered
in a term according to the SUPREME timetable (BR-M2-01); a course shared by several curricula
has one plan and one report a term, owned by the unit that owns the course (BR-M2-02).
Each item has recorders for the plan and for the report (BR-M2-05), two documents, and goes
through the flow `learning_plan`: the recorder sends (step 1), a curator of a curriculum
that teaches the course certifies (step 2, FS-4 Q4 ก), then central staff publish.

The fields of plan sections 2–6 and report sections 2–4 follow the mock [สมมติ: until the
customer sends their มคอ.3/มคอ.5 forms] (FS-4 Q1 ก).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from ocl_api.auth import User
from ocl_api.db import Jsonb, connect
from ocl_api.flows import FlowStore, can_act, covers, today_th
from ocl_api.mail import Outbox

FLOW = "learning_plan"
DOCS = {"plan": "แผนการจัดการเรียนรู้", "report": "รายงานผลการจัดการเรียนรู้"}
STATUSES = {
    "none": "ยังไม่บันทึก",
    "draft": "บันทึกแล้ว",
    "sent": "ส่งตรวจสอบ",
    "returned": "ส่งคืนแก้ไข",
    "approved": "รับรองแล้ว",
    "published": "เผยแพร่",
}
DONE = ("sent", "approved", "published")  # counted as sent on the dashboard
GRADES = ["A", "B+", "B", "C+", "C", "D+", "D", "E"]
GRADE_CUTS = [
    ["A", 80, 100],
    ["B+", 75, 79],
    ["B", 70, 74],
    ["C+", 65, 69],
    ["C", 60, 64],
    ["D+", 55, 59],
    ["D", 50, 54],
    ["E", 0, 49],
]
TERM_RE = re.compile(r"^[123]/25\d\d$")
GE_PREFIX = ("ศท", "มศว")


class M2Error(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def term_key(term: str) -> str:
    """'2/2569' in a URL is '2-2569'."""
    return term.replace("/", "-")


def previous_term(term: str) -> str:
    n, y = term.split("/")
    return f"{int(n) - 1}/{y}" if n != "1" else f"2/{int(y) - 1}"


def blank_plan(kind: str) -> dict[str, Any]:
    return {
        "s1": {
            "status_type": "",
            "hours_week": "",
            "mode": "",
            "consult_hours": "",
            "contact": "",
            "appeal": "",
            "updated_on": "",
        },
        "s3": {
            "clos": [],
            "ai": {"teach": "", "assign": "", "assess": ""},
            "grades": [list(g) for g in GRADE_CUTS],
        },
        "s4": {"pattern": "integrate" if kind == "module" else None, "weeks": []},
        "s5": {"texts": "", "sources": "", "others": ""},
        "s6": {"participation": "", "verify_outcome": "", "verify_quality": "", "appeal_risk": ""},
    }


def blank_report() -> dict[str, Any]:
    return {
        "r3": {
            "withdrawn": 0,
            "grades": {g: 0 for g in GRADES},
            "achieved": "",
            "not_achieved": "",
        },
        "r4": {"critique": "", "improvement": ""},
    }


def plan_missing(d: dict[str, Any]) -> list[str]:
    """What a plan still lacks before it may be sent (the required fields of the 6 sections)."""
    s1, s3, s4, s5, s6 = (d.get(k) or {} for k in ("s1", "s3", "s4", "s5", "s6"))
    miss = [
        f"หมวด 1 {label}"
        for k, label in (
            ("status_type", "สถานภาพของวิชา"),
            ("hours_week", "ชั่วโมงสอน/สัปดาห์"),
            ("mode", "รูปแบบการสอน"),
            ("contact", "ช่องทางติดต่อ"),
            ("appeal", "ช่องทางอุทธรณ์"),
        )
        if not str(s1.get(k) or "").strip()
    ]
    clos = [c for c in s3.get("clos") or [] if str(c.get("criteria") or "").strip()]
    if not clos:
        miss.append("หมวด 3 ผลลัพธ์การเรียนรู้ (CLO/MLO) อย่างน้อย 1 ข้อ")
    elif round(sum(float(c.get("pct") or 0) for c in clos)) != 100:
        miss.append("หมวด 3 ร้อยละของ CLO/MLO รวมต้องเท่ากับ 100")
    if not [w for w in s4.get("weeks") or [] if str(w.get("topic") or "").strip()]:
        miss.append("หมวด 4 แผนรายสัปดาห์อย่างน้อย 1 สัปดาห์")
    if not str(s5.get("texts") or "").strip():
        miss.append("หมวด 5 เอกสาร/ตำรา")
    miss += [
        f"หมวด 6 ข้อ {i + 1}"
        for i, k in enumerate(("participation", "verify_outcome", "verify_quality", "appeal_risk"))
        if not str(s6.get(k) or "").strip()
    ]
    return miss


def report_missing(d: dict[str, Any], enrolled: int) -> list[str]:
    r3, r4 = d.get("r3") or {}, d.get("r4") or {}
    counts = [int((r3.get("grades") or {}).get(g) or 0) for g in GRADES]
    total = sum(counts) + int(r3.get("withdrawn") or 0)
    miss = []
    if not sum(counts):
        miss.append("หมวด 3 จำนวนนิสิตตามเกรด")
    if enrolled and total > enrolled:
        miss.append(f"หมวด 3 จำนวนรวม {total} เกินจำนวนลงทะเบียน {enrolled}")
    miss += [
        f"หมวด 3 {label}"
        for k, label in (("achieved", "เหตุผลที่บรรลุ"), ("not_achieved", "เหตุผลที่ไม่บรรลุ"))
        if not str(r3.get(k) or "").strip()
    ]
    miss += [
        f"หมวด 4 {label}"
        for k, label in (("critique", "ข้อวิพากษ์"), ("improvement", "แผนการปรับปรุง"))
        if not str(r4.get(k) or "").strip()
    ]
    return miss


class M2Store:
    def __init__(self, url: str, schema: str | None = None):
        self.url, self.schema = url, schema
        self.flows = FlowStore(url, schema)

    def _conn(self):
        return connect(self.url, self.schema)

    # ---------- terms and offerings ----------

    def terms(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            offered = [r["term"] for r in conn.execute("SELECT DISTINCT term FROM ext_sections")]
            rows = {r["term"]: r for r in conn.execute("SELECT * FROM m2_terms")}
        out = []
        for t in sorted(
            set(offered) | set(rows), key=lambda x: (x.split("/")[1], x.split("/")[0]), reverse=True
        ):
            out.append(_term_out(t, rows.get(t)))
        return out

    def term(self, term: str) -> dict[str, Any]:
        if not TERM_RE.match(term):
            raise M2Error("ภาคการศึกษาต้องอยู่ในรูป ภาค/ปี เช่น 2/2569")
        with self._conn() as conn:
            r = conn.execute("SELECT * FROM m2_terms WHERE term = %s", (term,)).fetchone()
        return _term_out(term, r)

    def save_term(self, term: str, data: dict[str, Any], by: str) -> dict[str, Any]:
        self.term(term)
        fields = ("starts_on", "ends_on", "plan_open", "plan_close", "report_open", "report_close")
        vals = {k: (date.fromisoformat(data[k]) if data.get(k) else None) for k in fields}
        if vals["starts_on"] and vals["ends_on"] and vals["ends_on"] <= vals["starts_on"]:
            raise M2Error("วันสุดท้ายของภาคต้องหลังวันเปิดภาค")
        for a, b in (("plan_open", "plan_close"), ("report_open", "report_close")):
            if vals[a] and vals[b] and vals[b] < vals[a]:
                raise M2Error("วันปิดรับต้องไม่ก่อนวันเปิดรับ")
        target = int(data.get("target_pct") or 70)
        with self._conn() as conn:
            conn.execute(
                f"INSERT INTO m2_terms (term, {', '.join(fields)}, target_pct, updated_by) "
                f"VALUES (%s, {', '.join(['%s'] * len(fields))}, %s, %s) ON CONFLICT (term) DO "
                f"UPDATE SET "
                + ", ".join(f"{k} = EXCLUDED.{k}" for k in (*fields, "target_pct", "updated_by"))
                + ", updated_at = now()",
                (term, *[vals[k] for k in fields], target, by),
            )
        return self.term(term)

    def sync(self, term: str) -> dict[str, Any]:
        """ดึงใหม่: the term's items from the SUPREME timetable copy. A course in a module of the
        central course database is planned with its module; items no longer offered are kept
        (not counted) if they have documents, else removed."""
        self.term(term)
        with self._conn() as conn, conn.transaction():
            secs = conn.execute(
                "SELECT s.*, p.faculty FROM ext_sections s LEFT JOIN ext_programs p "
                "ON p.code = s.program_code WHERE s.term = %s ORDER BY s.course_code, s.section",
                (term,),
            ).fetchall()
            codes = sorted({s["course_code"] for s in secs})
            central = {
                r["code_th"]: r
                for r in conn.execute(
                    "SELECT c.code_th, c.module, c.unit, v.name_th FROM courses c JOIN "
                    "course_versions v "
                    "ON v.code_th = c.code_th AND v.version = c.latest WHERE c.code_th = ANY(%s)",
                    (codes,),
                )
            }
            items: dict[str, dict[str, Any]] = {}
            for s in secs:
                code = s["course_code"]
                c = central.get(code) or {}
                unit = c.get("unit") or s["faculty"]
                if c.get("module"):
                    key, kind, name = f"M:{c['module']}", "module", c["module"]
                else:
                    key, kind, name = f"C:{code}", "course", c.get("name_th") or s["course_name"]
                it = items.setdefault(
                    key,
                    {
                        "kind": kind,
                        "code": c.get("module") or code,
                        "name_th": name,
                        "unit": unit,
                        "courses": [],
                        "sections": [],
                    },
                )
                if code not in it["courses"]:
                    it["courses"].append(code)
                it["sections"].append(
                    {
                        k: s[k]
                        for k in (
                            "course_code",
                            "section",
                            "teachers",
                            "schedule",
                            "room",
                            "enrolled",
                            "program_code",
                        )
                    }
                )
            for key, it in items.items():
                conn.execute(
                    "INSERT INTO m2_items (term, key, kind, code, name_th, unit, courses, "
                    "sections, offered) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true) ON CONFLICT (term, key) DO "
                    "UPDATE SET "
                    "kind = EXCLUDED.kind, code = EXCLUDED.code, name_th = EXCLUDED.name_th, "
                    "unit = EXCLUDED.unit, courses = EXCLUDED.courses, sections = "
                    "EXCLUDED.sections, "
                    "offered = true, synced_at = now()",
                    (
                        term,
                        key,
                        it["kind"],
                        it["code"],
                        it["name_th"],
                        it["unit"],
                        Jsonb(it["courses"]),
                        Jsonb(it["sections"]),
                    ),
                )
            gone = conn.execute(
                "SELECT key FROM m2_items WHERE term = %s AND NOT key = ANY(%s)",
                (term, list(items)),
            ).fetchall()
            for g in gone:
                used = conn.execute(
                    "SELECT 1 FROM m2_docs WHERE term = %s AND key = %s", (term, g["key"])
                ).fetchone()
                if used:
                    conn.execute(
                        "UPDATE m2_items SET offered = false, synced_at = now() WHERE term = %s "
                        "AND key = %s",
                        (term, g["key"]),
                    )
                else:
                    conn.execute(
                        "DELETE FROM m2_items WHERE term = %s AND key = %s", (term, g["key"])
                    )
                    conn.execute(
                        "DELETE FROM m2_assign WHERE term = %s AND key = %s", (term, g["key"])
                    )
        return {"items": len(items), "removed": len(gone)}

    # ---------- reading ----------

    def _scope(self, user: User) -> tuple[bool, set[str]]:
        """(sees every item, course codes taught in the curricula of a curator's 0.2)."""
        if user.sees_all():
            return True, set()
        codes: set[str] = set()
        if user.pid and "program" in user.scope_kinds():  # a teacher (รายบุคคล): assigned only
            with self._conn() as conn:
                for r in conn.execute(
                    "SELECT s4.data FROM curriculum_sections s0 JOIN curriculum_sections s4 "
                    "ON s4.draft_id = s0.draft_id AND s4.section = '4' WHERE s0.section = '0' "
                    "AND s0.data->'teachers'->'teachers' @> %s",
                    (Jsonb([{"pid": user.pid}]),),
                ):
                    codes |= {
                        c.get("code_th")
                        for c in ((r["data"] or {}).get("courses") or {}).get("courses") or []
                    }
        return False, codes

    def _scoped(self, user: User, it: dict[str, Any], scope) -> bool:
        """In the account's ขอบเขตข้อมูล: both documents, whoever records them."""
        everyone, codes = scope
        if everyone:
            return True
        if "faculty" in user.scope_kinds() and covers(user.units, it["unit"]):
            return True
        return bool(codes & set(it["courses"]))

    def items(self, term: str, user: User) -> dict[str, Any]:
        t = self.term(term)
        with self._conn() as conn:
            items = conn.execute(
                "SELECT * FROM m2_items WHERE term = %s ORDER BY unit, code", (term,)
            ).fetchall()
            assign = _by_key(
                conn.execute("SELECT key, doc, pids FROM m2_assign WHERE term = %s", (term,))
            )
            docs = _by_key(
                conn.execute(
                    "SELECT key, doc, status, step, submitted_at, published_at FROM m2_docs "
                    "WHERE term = %s",
                    (term,),
                )
            )
            names = {
                r["pid"]: f"{r['title_short'] or ''}{r['name_th']}"
                for r in conn.execute("SELECT pid, title_short, name_th FROM ext_staff")
            }
            synced = conn.execute(
                "SELECT max(synced_at) AS t FROM m2_items WHERE term = %s", (term,)
            ).fetchone()["t"]
        scope = self._scope(user)
        out = []
        for it in items:
            a = assign.get(it["key"], {})
            mine = {k: bool(user.pid and user.pid in (a.get(k) or [])) for k in DOCS}
            scoped = self._scoped(user, it, scope)
            if not scoped and not any(mine.values()):  # a recorder sees what they record
                continue
            d = docs.get(it["key"], {})
            out.append(
                {
                    "key": it["key"],
                    "kind": it["kind"],
                    "code": it["code"],
                    "name_th": it["name_th"],
                    "unit": it["unit"],
                    "courses": it["courses"],
                    "offered": it["offered"],
                    "enrolled": sum(int(s.get("enrolled") or 0) for s in it["sections"]),
                    "sections": len(it["sections"]),
                    "assign": {
                        k: [{"pid": p, "name": names.get(p, p)} for p in a.get(k) or []]
                        for k in DOCS
                    },
                    "status": {k: (d.get(k) or {}).get("status", "none") for k in DOCS},
                    "mine": mine,
                    "scoped": scoped,
                }
            )
        return {
            "term": t,
            "items": out,
            "synced_at": synced.isoformat() if synced else None,
            "statuses": STATUSES,
        }

    def item(self, term: str, key: str, user: User) -> dict[str, Any]:
        lst = {i["key"]: i for i in self.items(term, user)["items"]}
        if key not in lst:
            with self._conn() as conn:
                hit = conn.execute(
                    "SELECT 1 FROM m2_items WHERE term = %s AND key = %s", (term, key)
                ).fetchone()
            raise (
                M2Error("รายการนี้อยู่นอกขอบเขตข้อมูลของบัญชีนี้", 403) if hit else M2Error("ไม่พบรายการ", 404)
            )
        return lst[key]

    # ---------- recorders (US-M2-01) ----------

    def set_assign(
        self, term: str, key: str, doc: str, pids: list[str], user: User
    ) -> dict[str, Any]:
        if doc not in DOCS:
            raise M2Error("doc ต้องเป็น plan หรือ report")
        self.item(term, key, user)
        with self._conn() as conn:
            known = {
                r["pid"]
                for r in conn.execute("SELECT pid FROM ext_staff WHERE pid = ANY(%s)", (pids,))
            }
            bad = [p for p in pids if p not in known]
            if bad:
                raise M2Error(f"ไม่พบบุคลากร {', '.join(bad)} ในระบบบุคลากร")
            conn.execute(
                "INSERT INTO m2_assign (term, key, doc, pids, updated_by) VALUES (%s, %s, %s, "
                "%s, %s) "
                "ON CONFLICT (term, key, doc) DO UPDATE SET pids = EXCLUDED.pids, "
                "updated_by = EXCLUDED.updated_by, updated_at = now()",
                (term, key, doc, Jsonb(list(dict.fromkeys(pids))), user.email),
            )
            _event(conn, term, key, doc, user.email, "assign", ", ".join(pids) or "ล้างรายชื่อ")
        return self.item(term, key, user)

    def copy_assign(self, term: str, user: User) -> dict[str, Any]:
        """คัดลอกจากภาคก่อน: the recorders of the same item, where this term has none yet."""
        prev = previous_term(term)
        mine = {i["key"] for i in self.items(term, user)["items"]}
        copied = 0
        with self._conn() as conn, conn.transaction():
            for r in conn.execute(
                "SELECT p.key, p.doc, p.pids FROM m2_assign p WHERE p.term = %s AND NOT EXISTS "
                "(SELECT 1 FROM m2_assign t WHERE t.term = %s AND t.key = p.key AND t.doc = p.doc "
                "AND jsonb_array_length(t.pids) > 0)",
                (prev, term),
            ).fetchall():
                if r["key"] in mine and r["pids"]:
                    conn.execute(
                        "INSERT INTO m2_assign (term, key, doc, pids, updated_by) VALUES (%s, "
                        "%s, %s, %s, %s) "
                        "ON CONFLICT (term, key, doc) DO UPDATE SET pids = EXCLUDED.pids, "
                        "updated_by = EXCLUDED.updated_by, updated_at = now()",
                        (term, r["key"], r["doc"], Jsonb(r["pids"]), user.email),
                    )
                    copied += 1
        return {"copied": copied, "from": prev}

    def notify_assigned(self, term: str, user: User) -> dict[str, Any]:
        """แจ้งเตือนทางอีเมล: every recorder of the items in scope, once a day."""
        data = self.items(term, user)
        with self._conn() as conn:
            emails = {
                r["pid"]: r["email"]
                for r in conn.execute("SELECT pid, email FROM ext_staff")
                if r["email"]
            }
        box, sent = Outbox(self.url, self.schema), 0
        today = today_th().isoformat()
        per: dict[str, list[str]] = {}
        for it in data["items"]:
            for doc in DOCS:
                for p in it["assign"][doc]:
                    if emails.get(p["pid"]):
                        per.setdefault(emails[p["pid"]], []).append(
                            f"{DOCS[doc]} {it['code']} {it['name_th']}"
                        )
        for to, lines in per.items():
            m = box.send(
                [to],
                f"ได้รับมอบหมายบันทึกแผน/รายงานการจัดการเรียนรู้ ภาค {term}",
                "\n".join(sorted(set(lines))),
                kind="assign",
                by=user.email,
                dedupe_key=f"m2-assign:{term}:{to}:{today}",
            )
            sent += m is not None
        return {"sent": sent, "recipients": len(per)}

    # ---------- documents (US-M2-04 06) ----------

    def pulled(self, term: str, key: str, user: User) -> dict[str, Any]:
        """What the forms show without letting anyone type it (ดึงอัตโนมัติ)."""
        it = self.item(term, key, user)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT sections FROM m2_items WHERE term = %s AND key = %s", (term, key)
            ).fetchone()
            sections = row["sections"]
            names = {
                r["pid"]: f"{r['title_short'] or ''}{r['name_th']}"
                for r in conn.execute("SELECT pid, title_short, name_th FROM ext_staff")
            }
            courses = {
                r["code_th"]: r
                for r in conn.execute(
                    "SELECT c.code_th, c.code_en, c.unit, v.name_th, v.name_en, v.credit_text, "
                    "v.description_th "
                    "FROM courses c JOIN course_versions v ON v.code_th = c.code_th "
                    "AND v.version = "
                    "c.latest "
                    "WHERE c.code_th = ANY(%s)",
                    (it["courses"],),
                )
            }
            # BR-M2-03: PLO and KSEC of the course from the curricula that are verified or published
            plos = []
            for r in conn.execute(
                "SELECT d.id, d.name_th, s3.data AS s3, s4.data AS s4 FROM curriculum_drafts d "
                "JOIN curriculum_sections s3 ON s3.draft_id = d.id AND s3.section = '3' "
                "JOIN curriculum_sections s4 ON s4.draft_id = d.id AND s4.section = '4' "
                "WHERE d.status IN ('verified', 'published') ORDER BY d.id"
            ):
                rows = [
                    x
                    for x in ((r["s4"] or {}).get("mapping") or {}).get("ksec_rows") or []
                    if x.get("course_code") in it["courses"]
                ]
                if rows:
                    plos.append(
                        {
                            "curriculum": r["name_th"],
                            "draft_id": r["id"],
                            "plos": [
                                {"code": p.get("code"), "text": p.get("text")}
                                for p in ((r["s3"] or {}).get("plo") or {}).get("plos") or []
                            ],
                            "rows": rows,
                        }
                    )
        teachers = sorted({p for s in sections for p in s.get("teachers") or []})
        return {
            "item": it,
            "courses": [
                {
                    "code_th": c,
                    **({k: v for k, v in (courses.get(c) or {}).items() if k != "code_th"}),
                }
                for c in it["courses"]
            ],
            "teachers": [{"pid": p, "name": names.get(p, p)} for p in teachers],
            "sections": [
                {**s, "teachers": [names.get(p, p) for p in s.get("teachers") or []]}
                for s in sections
            ],
            "enrolled": it["enrolled"],
            "plos": plos,
        }

    def doc(self, term: str, key: str, doc: str, user: User) -> dict[str, Any]:
        if doc not in DOCS:
            raise M2Error("ไม่มีเอกสารนี้", 404)
        pulled = self.pulled(term, key, user)
        it = pulled["item"]
        if not it["scoped"] and not it["mine"][doc]:  # BR-M2-05: only the document assigned
            raise M2Error(f"บัญชีนี้ไม่ได้เป็นผู้บันทึก{DOCS[doc]}ของรายการนี้", 403)
        with self._conn() as conn:
            r = conn.execute(
                "SELECT * FROM m2_docs WHERE term = %s AND key = %s AND doc = %s", (term, key, doc)
            ).fetchone()
            plan = conn.execute(
                "SELECT data, status FROM m2_docs WHERE term = %s AND key = %s AND doc = 'plan'",
                (term, key),
            ).fetchone()
            events = conn.execute(
                "SELECT ts, by, action, note FROM m2_events WHERE term = %s AND key = %s AND doc "
                "= %s ORDER BY id",
                (term, key, doc),
            ).fetchall()
        version, steps, _ = self.flows.steps(FLOW, r["flow_version"] if r else None)
        data = (r["data"] if r else None) or (
            blank_plan(it["kind"]) if doc == "plan" else blank_report()
        )
        status = r["status"] if r else "none"
        t = self.term(term)
        out = {
            "term": t,
            "doc": doc,
            "doc_th": DOCS[doc],
            "status": status,
            "status_th": STATUSES[status],
            "step": r["step"] if r else 0,
            "steps": steps,
            "data": data,
            "pulled": pulled,
            "missing": plan_missing(data)
            if doc == "plan"
            else report_missing(data, pulled["enrolled"]),
            "events": [{**e, "ts": e["ts"].isoformat()} for e in events],
            "window": _window(t, doc),
        }
        if doc == "report":  # หมวด 2: the CLOs of the plan of the same term
            out["plan"] = {
                "status": plan["status"] if plan else "none",
                "clos": ((plan["data"] if plan else {}).get("s3") or {}).get("clos") or [],
            }
        out |= self._rights(user, it, doc, status, steps, r["step"] if r else 0, out["window"])
        return out

    def _rights(self, user, it, doc, status, steps, step, window) -> dict[str, Any]:
        recorder = it["mine"][doc]
        staff = bool({"admin", "central"} & set(user.roles))
        editable = status in ("none", "draft", "returned") and (recorder or staff)
        return {
            "can_edit": editable and (window["open"] or staff),
            "can_submit": editable and window["open"] and (recorder or staff),
            "can_certify": status == "sent" and (staff or self._certifier(user, it, steps)),
            "can_publish": staff and status in ("approved", "published"),
            "recorder": recorder,
        }

    def _certifier(self, user: User, it: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
        """FS-4 Q4 ก: whoever step 2 names (curator) and is listed in 0.2 of a curriculum whose
        หมวด 4 has the course."""
        if not can_act(user.roles, steps[-1]) or not user.pid:
            return False
        return bool(self._scope(user)[1] & set(it["courses"]))

    def save(
        self, term: str, key: str, doc: str, data: dict[str, Any], user: User
    ) -> dict[str, Any]:
        d = self.doc(term, key, doc, user)
        if not d["can_edit"]:
            why = (
                "นอกช่วงเวลาเปิดให้บันทึก"
                if not d["window"]["open"]
                else "บัญชีนี้ไม่ได้เป็นผู้บันทึกหรือเอกสารส่งแล้ว"
            )
            raise M2Error(why, 403)
        clean = {
            k: v
            for k, v in data.items()
            if k in (("s1", "s3", "s4", "s5", "s6") if doc == "plan" else ("r3", "r4"))
        }
        if doc == "report":
            r3 = clean.get("r3") or {}
            for g in GRADES:
                if int((r3.get("grades") or {}).get(g) or 0) < 0:
                    raise M2Error("จำนวนนิสิตต้องไม่ติดลบ")
        status = "draft" if d["status"] in ("none", "draft") else d["status"]
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "INSERT INTO m2_docs (term, key, doc, data, status, created_by, updated_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (term, key, doc) DO UPDATE SET "
                "data = EXCLUDED.data, status = EXCLUDED.status, updated_by = EXCLUDED.updated_by, "
                "updated_at = now()",
                (term, key, doc, Jsonb(clean), status, user.email, user.email),
            )
            _event(conn, term, key, doc, user.email, "save", None)
        return self.doc(term, key, doc, user)

    def copy_previous(self, term: str, key: str, doc: str, user: User) -> dict[str, Any]:
        """คัดลอกจากภาคก่อน: the content of the same item's document, when this term has none."""
        d = self.doc(term, key, doc, user)
        if d["status"] != "none":
            raise M2Error("ภาคนี้บันทึกแล้ว คัดลอกทับไม่ได้", 409)
        with self._conn() as conn:
            prev = conn.execute(
                "SELECT data FROM m2_docs WHERE term = %s AND key = %s AND doc = %s",
                (previous_term(term), key, doc),
            ).fetchone()
        if prev is None:
            raise M2Error(f"ภาค {previous_term(term)} ไม่มี{DOCS[doc]}ของรายการนี้", 404)
        data = prev["data"]
        if doc == "plan":
            data.setdefault("s1", {})["updated_on"] = ""
        else:
            data = blank_report() | {"r4": data.get("r4") or {}}  # grades belong to their own term
        return self.save(term, key, doc, data, user)

    def submit(self, term: str, key: str, doc: str, user: User) -> dict[str, Any]:
        d = self.doc(term, key, doc, user)
        if not d["can_submit"]:
            raise M2Error("ส่งได้เฉพาะผู้บันทึก ในช่วงเวลาเปิดให้บันทึก", 403)
        if d["missing"]:
            raise M2Error("ยังขาด " + " · ".join(d["missing"]))
        if (
            doc == "report"
            and d["term"]["ends_on"]
            and today_th() < date.fromisoformat(d["term"]["ends_on"])
        ):
            raise M2Error(f"ส่งรายงานผลได้หลังวันสุดท้ายของภาค ({d['term']['ends_on']})")  # [สมมติ]
        version, steps, flow = self.flows.steps(FLOW)
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE m2_docs SET status = 'sent', step = 1, flow_version = %s, submitted_at = "
                "now(), "
                "updated_at = now() WHERE term = %s AND key = %s AND doc = %s",
                (version, term, key, doc),
            )
            _event(conn, term, key, doc, user.email, "submit", None)
        self._mail_certifiers(term, d["pulled"]["item"], doc, user.email)
        return self.doc(term, key, doc, user)

    def certify(
        self, term: str, key: str, doc: str, user: User, ok: bool, note: str | None
    ) -> dict[str, Any]:
        d = self.doc(term, key, doc, user)
        if not d["can_certify"]:
            raise M2Error("รับรองได้เฉพาะประธาน/อาจารย์ของหลักสูตรที่ใช้วิชานี้ หรือส่วนกลาง", 403)
        if not ok and not (note or "").strip():
            raise M2Error("ต้องระบุเหตุผลที่ส่งคืน")
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE m2_docs SET status = %s, step = %s, approved_at = CASE WHEN %s THEN "
                "now() END, "
                "updated_at = now() WHERE term = %s AND key = %s AND doc = %s",
                ("approved" if ok else "returned", 2 if ok else 0, ok, term, key, doc),
            )
            _event(conn, term, key, doc, user.email, "approve" if ok else "return", note)
        self._mail_recorders(
            term,
            d["pulled"]["item"],
            doc,
            f"{DOCS[doc]} {d['pulled']['item']['code']} "
            + ("รับรองแล้ว" if ok else f"ถูกส่งคืน: {note}"),
            user.email,
        )
        return self.doc(term, key, doc, user)

    def publish(self, term: str, key: str, doc: str, user: User, on: bool) -> dict[str, Any]:
        d = self.doc(term, key, doc, user)
        if not d["can_publish"]:
            raise M2Error("เผยแพร่ได้เฉพาะเอกสารที่รับรองแล้ว โดยส่วนกลาง", 403)
        with self._conn() as conn, conn.transaction():
            conn.execute(
                "UPDATE m2_docs SET status = %s, published_at = CASE WHEN %s THEN now() END, "
                "updated_at = now() "
                "WHERE term = %s AND key = %s AND doc = %s",
                ("published" if on else "approved", on, term, key, doc),
            )
            _event(conn, term, key, doc, user.email, "publish" if on else "unpublish", None)
        return self.doc(term, key, doc, user)

    def _mail_certifiers(self, term: str, it: dict[str, Any], doc: str, by: str) -> None:
        with self._conn() as conn:
            to = [
                r["email"]
                for r in conn.execute(
                    "SELECT DISTINCT u.email FROM users u "
                    "JOIN curriculum_sections s0 ON s0.section "
                    "= '0' "
                    "AND s0.data->'teachers'->'teachers' @> "
                    "jsonb_build_array(jsonb_build_object('pid', u.pid)) "
                    "JOIN curriculum_sections s4 ON s4.draft_id = s0.draft_id AND s4.section = '4' "
                    "WHERE u.active AND u.roles ? 'curator' AND u.pid IS NOT NULL AND EXISTS ("
                    "SELECT 1 FROM jsonb_array_elements(coalesce(s4.data->'courses'->'courses', "
                    "'[]')) c "
                    "WHERE c->>'code_th' = ANY(%s))",
                    (it["courses"],),
                )
            ]
        to = to or self.flows.recipients(["central"], it["unit"])
        if to:
            Outbox(self.url, self.schema).send(
                to,
                f"{DOCS[doc]}รอรับรอง: {it['code']} ภาค {term}",
                f"{it['name_th']} ส่งตรวจสอบแล้ว",
                kind="workflow",
                by=by,
                ref=f"m2:{term}:{it['key']}:{doc}",
            )

    def _mail_recorders(
        self, term: str, it: dict[str, Any], doc: str, body: str, by: str, dedupe: str | None = None
    ):
        pids = [p["pid"] for p in it["assign"][doc]]
        if not pids:  # no recorder yet: nothing to send, and no connection per late item
            return None
        with self._conn() as conn:
            to = [
                r["email"]
                for r in conn.execute(
                    "SELECT email FROM ext_staff WHERE pid = ANY(%s) AND email IS NOT NULL",
                    (pids,),
                )
            ]
        if not to:
            return None
        return Outbox(self.url, self.schema).send(
            to,
            f"{DOCS[doc]} {it['code']} ภาค {term}",
            body,
            kind="reminder",
            by=by,
            ref=f"m2:{term}:{it['key']}:{doc}",
            dedupe_key=dedupe,
        )

    # ---------- dashboard (US-M2-07) ----------

    def dashboard(self, term: str, user: User) -> dict[str, Any]:
        data = self.items(term, user)
        t = data["term"]
        items = [i for i in data["items"] if i["offered"]]
        n = len(items)
        today = today_th()
        deadline = {"plan": t["plan_close"], "report": t["report_close"]}
        units: dict[str, list[dict[str, Any]]] = {}
        for i in items:
            units.setdefault(i["unit"] or "ไม่ระบุหน่วยงาน", []).append(i)
        late = []
        for i in items:
            for doc in DOCS:
                due = deadline[doc]
                if due and today > date.fromisoformat(due) and i["status"][doc] not in DONE:
                    late.append(
                        {
                            "key": i["key"],
                            "code": i["code"],
                            "name_th": i["name_th"],
                            "unit": i["unit"],
                            "doc": doc,
                            "status": i["status"][doc],
                            "days": (today - date.fromisoformat(due)).days,
                            "recorders": [a["name"] for a in i["assign"][doc]],
                        }
                    )
        late.sort(key=lambda x: -x["days"])

        def pct(xs: list[dict[str, Any]], doc: str) -> int:
            return round(sum(x["status"][doc] in DONE for x in xs) * 100 / len(xs)) if xs else 0

        return {
            "term": t,
            "synced_at": data["synced_at"],
            "offered": n,
            "modules": sum(i["kind"] == "module" for i in items),
            "unassigned": sum(not (i["assign"]["plan"] and i["assign"]["report"]) for i in items),
            "plan_pct": pct(items, "plan"),
            "report_pct": pct(items, "report"),
            "published": {d: sum(i["status"][d] == "published" for i in items) for d in DOCS},
            "status": {
                d: {s: sum(i["status"][d] == s for i in items) for s in STATUSES} for d in DOCS
            },
            "units": [
                {
                    "unit": u,
                    "count": len(xs),
                    "plan_pct": pct(xs, "plan"),
                    "report_pct": pct(xs, "report"),
                    "below": pct(xs, "plan") < t["target_pct"],
                }
                for u, xs in sorted(units.items())
            ],
            "late": late,
            "target_pct": t["target_pct"],
        }

    def remind(
        self, term: str, user: User, key: str | None = None, doc: str | None = None
    ) -> dict[str, Any]:
        """แจ้งเตือน (one item) / แจ้งเตือนทั้งหมด (every late item not yet sent), once a day each."""
        dash = self.dashboard(term, user)
        rows = [x for x in dash["late"] if (key is None or (x["key"] == key and x["doc"] == doc))]
        items = {i["key"]: i for i in self.items(term, user)["items"]}
        sent = 0
        day = today_th().isoformat()
        for x in rows:
            m = self._mail_recorders(
                term,
                items[x["key"]],
                x["doc"],
                f"{DOCS[x['doc']]} {x['code']} เลยกำหนดส่ง {x['days']} วัน "
                f"(สถานะ {STATUSES[x['status']]})",
                user.email,
                dedupe=f"m2-late:{term}:{x['key']}:{x['doc']}:{day}",
            )
            sent += m is not None
        return {"sent": sent, "late": len(rows)}


def _event(conn, term: str, key: str, doc: str, by: str, action: str, note: str | None) -> None:
    conn.execute(
        "INSERT INTO m2_events (term, key, doc, by, action, note) VALUES (%s, %s, %s, %s, %s, %s)",
        (term, key, doc, by, action, note),
    )


def _by_key(rows) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        out.setdefault(r["key"], {})[r["doc"]] = r["pids"] if "pids" in r else dict(r)
    return out


def _term_out(term: str, r: dict[str, Any] | None) -> dict[str, Any]:
    r = r or {}
    starts = r.get("starts_on")
    # BR-M2-04 [สมมติ]: plans close 2 weeks before the term starts unless set
    plan_close = r.get("plan_close") or (starts - timedelta(days=14) if starts else None)
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return {
        "term": term,
        "slug": term_key(term),
        "starts_on": iso(starts),
        "ends_on": iso(r.get("ends_on")),
        "plan_open": iso(r.get("plan_open")),
        "plan_close": iso(plan_close),
        "report_open": iso(r.get("report_open")),
        "report_close": iso(r.get("report_close")),
        "target_pct": r.get("target_pct") or 70,
        "set": bool(r),
    }


def _window(t: dict[str, Any], doc: str) -> dict[str, Any]:
    """Open unless today is outside the term's dates for that document (unset = open)."""
    a, b = t[f"{doc}_open"], t[f"{doc}_close"]
    today = today_th()
    open_ = (not a or today >= date.fromisoformat(a)) and (not b or today <= date.fromisoformat(b))
    return {"open": open_, "from": a, "to": b}
