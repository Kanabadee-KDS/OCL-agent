"""Reports R01–R14 and the home dashboard (FS-7 · M5 · BRD 05 US-M5-01–04 · US-G-01).

Every report is built from the stores of its module, so the rows already follow the user's
ขอบเขตข้อมูล (US-M5-02), and comes back in one shape the web shows and exports: filters, KPI
tiles and one or more tables (an Excel file has one sheet per table). R11 is public.
"""

from __future__ import annotations

import io
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from ocl_api.assess import SECTION_STATUS, AssessStore
from ocl_api.auth import User
from ocl_api.courses import CourseStore
from ocl_api.curricula import STATUSES as CUR_STATUSES
from ocl_api.curricula import CurriculumStore
from ocl_api.db import connect
from ocl_api.m2 import STATUSES as M2_STATUSES
from ocl_api.m2 import M2Store
from ocl_api.qa import RESULTS, QaStore
from ocl_api.skill_defaults import CATS
from ocl_api.skills import SkillStore, level_of, term_sort
from ocl_api.smo import SmoStore

# code -> (title, TOR, users, exports, menu, proposed)
CATALOG: dict[str, tuple[str, str, str, list[str], str, bool]] = {
    "R01": (
        "ติดตามการบันทึกแผน/รายงานผลการจัดการเรียนรู้",
        "6.9.1 6.9.3 6.3",
        "ส่วนกลาง คณะ",
        ["PDF", "Excel"],
        "r1",
        False,
    ),
    "R02": (
        "ความครบถ้วนการประเมิน Skill",
        "6.15.2 6.11.1",
        "ส่วนกลาง หลักสูตร",
        ["PDF", "Excel"],
        "r2",
        False,
    ),
    "R03": ("สถานะคู่มือหลักสูตรและ สมอ.08", "6.1 6.2", "ส่วนกลาง คณะ", ["PDF", "Excel"], "r3", False),
    "R04": (
        "สรุปภาพรวมทักษะนิสิตทั้งมหาวิทยาลัย",
        "6.15.1 6.15.5",
        "ผู้บริหาร",
        ["PDF", "Excel"],
        "r4",
        False,
    ),
    "R05": ("สถิติผลลัพธ์ Skill ตามกลุ่มผู้เรียน", "6.15.4", "ผู้บริหาร คณะ", ["PDF", "Excel"], "r5", False),
    "R06": ("เปรียบเทียบและแนวโน้มทักษะ", "6.15.6 6.15.7", "ผู้บริหาร", ["PDF", "Excel"], "r6", False),
    "R07": ("ผลคะแนน Skill รายวิชา", "6.11.3", "อาจารย์ผู้สอน", ["PDF", "Excel"], "r7", False),
    "R08": ("ผลลัพธ์การเรียนรู้รายบุคคล", "6.13.1 6.15.3", "อาจารย์ที่ปรึกษา", ["PDF", "Excel"], "r8", False),
    "R09": (
        "ทะเบียนการออก Skill Transcript",
        "6.12.4 6.12.5",
        "ส่วนกลาง",
        ["PDF", "Excel"],
        "r9",
        False,
    ),
    "R10": (
        "รายงานผลการตรวจสอบข้อมูลหลักสูตร",
        "6.16.6.7",
        "ผู้ตรวจสอบ ผู้ประเมิน",
        ["PDF", "Excel"],
        "ra",
        False,
    ),
    "R11": ("สถิติหลักสูตร (เผยแพร่สาธารณะ)", "6.16.7", "สาธารณะ", ["เว็บ", "PDF"], "rb", False),
    "R12": ("รายงานคู่มือหลักสูตร (9 + 3 รายงาน)", "6.1", "ส่วนกลาง", ["Excel"], "rc", False),
    "R13": (
        "ผลลัพธ์การเรียนรู้ CLO/PLO ระดับหลักสูตร",
        "–",
        "ประธานหลักสูตร คณะ",
        ["PDF", "Excel"],
        "r0",
        True,
    ),
    "R14": ("ทะเบียนรายวิชาและ Version", "–", "ส่วนกลาง คณะ", ["Excel"], "r0", True),
}
REMIND = ("R01", "R02", "R03")
TR_STATUS = {"issued": "ออกแล้ว", "review": "รอตรวจ"}
SIGN_METHOD = {"sample": "บริการตัวอย่าง (ยังไม่มีผลทางกฎหมาย)"}
TH = timezone(timedelta(hours=7))
SET_OK = ("verified", "published")


def _col(key: str, label: str, num: bool = False) -> dict[str, Any]:
    return {"key": key, "label": label, "num": num}


def _table(
    title: str, cols: list[dict[str, Any]], rows: list[dict[str, Any]], note: str | None = None
) -> dict[str, Any]:
    return {"title": title, "columns": cols, "rows": rows, "note": note}


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def _pct(a: int, b: int) -> int:
    return round(a * 100 / b) if b else 0


def _when(iso: str | None) -> str | None:
    """'2026-10-30T06:37:59+00:00' -> '2026-10-30 13:37' (Thai time)."""
    return datetime.fromisoformat(iso).astimezone(TH).strftime("%Y-%m-%d %H:%M") if iso else None


class ReportStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema
        self.skills = SkillStore(url, schema)
        self.assess = AssessStore(url, schema)
        self.m2 = M2Store(url, schema)
        self.qa = QaStore(url, schema)

    def _conn(self):
        return connect(self.url, self.schema)

    # ---------- the catalog (US-M5-01) ----------

    def catalog(self, user: User) -> list[dict[str, Any]]:
        out = []
        for code, (title, tor, users, exports, menu, proposed) in CATALOG.items():
            allowed = code == "R11" or user.can_do(menu)
            out.append(
                {
                    "code": code,
                    "title": title,
                    "tor": tor,
                    "users": users,
                    "exports": exports,
                    "proposed": proposed,
                    "allowed": allowed,
                    "public": code == "R11",
                    "remind": code in REMIND,
                }
            )
        return out

    def report(self, code: str, user: User | None, params: dict[str, str]) -> dict[str, Any]:
        if code not in CATALOG:
            raise HTTPException(404, "ไม่มีรายงานนี้")
        title, tor, users, exports, menu, proposed = CATALOG[code]
        if code != "R11" and (user is None or not user.can_do(menu)):
            raise HTTPException(403, "บัญชีนี้ไม่มีสิทธิ์ดูรายงานนี้")
        body = getattr(self, f"_{code.lower()}")(user, params)
        return {
            "code": code,
            "title": title,
            "tor": tor,
            "users": users,
            "exports": exports,
            "proposed": proposed,
            "remind": code in REMIND,
            "filters": [],
            "kpis": [],
            "note": None,
            **body,
        }

    def xlsx(self, code: str, user: User | None, params: dict[str, str]) -> bytes:
        from openpyxl import Workbook

        r = self.report(code, user, params)
        wb = Workbook()
        wb.remove(wb.active)
        for i, t in enumerate(r["tables"]):
            ws = wb.create_sheet((t["title"] or f"ตาราง {i + 1}")[:31].replace("/", "-"))
            ws.append([c["label"] for c in t["columns"]])
            for row in t["rows"]:
                ws.append([_cell(row.get(c["key"])) for c in t["columns"]])
            if t.get("note"):
                ws.append([])
                ws.append([t["note"]])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def remind(self, code: str, user: User, params: dict[str, str]) -> dict[str, Any]:
        """US-M5-03: e-mail whoever has not sent yet, once a day per item."""
        if code not in REMIND or not user.can_do(CATALOG[code][4], "edit"):
            raise HTTPException(403, "บัญชีนี้ส่งแจ้งเตือนจากรายงานนี้ไม่ได้")
        if code == "R01":
            return self.m2.remind(self._term(params), user)
        if code == "R02":
            return self.assess.remind(self._term(params), user)
        sent = late = 0
        for c in CurriculumStore(self.url, self.schema, None).list(user)["items"]:
            if c["status"] in ("import", "review"):
                late += 1
                try:
                    sent += bool(
                        CurriculumStore(self.url, self.schema, None).remind(c["id"], user)["sent"]
                    )
                except HTTPException:
                    pass
        return {"sent": sent, "late": late}

    # ---------- shared ----------

    def _term(self, params: dict[str, str]) -> str:
        terms = self.skills.terms()
        t = params.get("term")
        if t and t in terms:
            return t
        if not terms:
            raise HTTPException(409, "ยังไม่มีตารางสอนจาก SUPREME")
        return terms[0]

    def _term_filter(self, term: str) -> dict[str, Any]:
        return {
            "key": "term",
            "label": "ภาค/ปี",
            "value": term,
            "options": [[t, f"ภาค {t}"] for t in self.skills.terms()],
        }

    def _students(self, user: User, params: dict[str, str]):
        with self._conn() as conn:
            studs = self.assess._students(conn, user)
            facs = sorted({s["faculty"] for s in studs if s["faculty"]})
            progs = sorted({s["program"] for s in studs if s["program"]})
            years = sorted({str(s["entry_year"]) for s in studs if s["entry_year"]})
            studs = [
                s
                for s in studs
                if (not params.get("faculty") or s["faculty"] == params["faculty"])
                and (not params.get("program") or s["program"] == params["program"])
                and (not params.get("entry") or str(s["entry_year"]) == params["entry"])
            ]
            ld = self.assess._load(conn, studs)
        filters = [
            {
                "key": "faculty",
                "label": "คณะ",
                "value": params.get("faculty", ""),
                "options": [[f, f] for f in facs],
            },
            {
                "key": "program",
                "label": "หลักสูตร",
                "value": params.get("program", ""),
                "options": [[p, p] for p in progs],
            },
            {
                "key": "entry",
                "label": "ปีเข้า",
                "value": params.get("entry", ""),
                "options": [[y, y] for y in years],
            },
        ]
        return studs, ld, filters

    # ---------- FS-7b ติดตาม ----------

    def _r01(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        term = self._term(p)
        d = self.m2.items(term, user)
        late = {(x["key"], x["doc"]): x["days"] for x in self.m2.dashboard(term, user)["late"]}
        items = [
            i for i in d["items"] if i["offered"] and (not p.get("unit") or i["unit"] == p["unit"])
        ]
        rows = [
            {
                "unit": i["unit"],
                "code": i["code"],
                "name": i["name_th"],
                "plan": M2_STATUSES[i["status"]["plan"]],
                "plan_by": ", ".join(x["name"] for x in i["assign"]["plan"]),
                "report": M2_STATUSES[i["status"]["report"]],
                "report_by": ", ".join(x["name"] for x in i["assign"]["report"]),
                "late": max(late.get((i["key"], "plan"), 0), late.get((i["key"], "report"), 0))
                or None,
            }
            for i in items
        ]
        sent = ("sent", "approved", "published")
        unpublished = [
            r
            for r, i in zip(rows, items, strict=True)
            if i["status"]["plan"] != "published" or i["status"]["report"] != "published"
        ]
        cols = [
            _col("unit", "หน่วยงานเจ้าของวิชา"),
            _col("code", "รหัส"),
            _col("name", "ชื่อ"),
            _col("plan", "แผนฯ"),
            _col("plan_by", "ผู้บันทึกแผน"),
            _col("report", "รายงานผลฯ"),
            _col("report_by", "ผู้บันทึกรายงาน"),
            _col("late", "เลยกำหนด (วัน)", True),
        ]
        return {
            "filters": [
                self._term_filter(term),
                {
                    "key": "unit",
                    "label": "หน่วยงาน",
                    "value": p.get("unit", ""),
                    "options": [
                        [u, u] for u in sorted({i["unit"] for i in d["items"] if i["unit"]})
                    ],
                },
            ],
            "kpis": [
                {"label": "เปิดสอน", "value": len(items)},
                {
                    "label": "แผนฯ ส่งแล้ว",
                    "value": f"{_pct(sum(i['status']['plan'] in sent for i in items), len(items))}%",
                },
                {
                    "label": "รายงานผลฯ ส่งแล้ว",
                    "value": f"{_pct(sum(i['status']['report'] in sent for i in items), len(items))}%",
                },
                {"label": "ยังไม่เผยแพร่", "value": len(unpublished)},
                {"label": "เลยกำหนด", "value": sum(1 for r in rows if r["late"])},
            ],
            "tables": [
                _table("สถานะรายรายวิชา/ชุดวิชา", cols, rows),
                _table(
                    "ยังไม่เผยแพร่และเลยกำหนด",
                    cols,
                    sorted([r for r in unpublished if r["late"]], key=lambda r: -r["late"]),
                ),
            ],
        }

    def _r02(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        term = self._term(p)
        d = self.assess.sections(term, user)
        rows = [
            {
                "code": i["course_code"],
                "section": i["section"],
                "name": i["name_th"],
                "faculty": i["faculty"],
                "skills": ", ".join(i["skills"]),
                "n": i["n"],
                "done": i["done"],
                "status": SECTION_STATUS[i["status"]],
                "teachers": ", ".join(t["name"] for t in i["teachers"]),
            }
            for i in d["items"]
        ]
        n, done = sum(i["n"] for i in d["items"]), sum(i["done"] for i in d["items"])
        st = Counter(i["status"] for i in d["items"])
        return {
            "filters": [self._term_filter(term)],
            "kpis": [
                {"label": "รายวิชา-กลุ่มใน Mapping", "value": len(rows)},
                {"label": "ยืนยันแล้ว", "value": st["ok"]},
                {"label": "รอยืนยัน", "value": st["wait"]},
                {"label": "ยังไม่เริ่ม", "value": st["todo"]},
                {"label": "นิสิตประเมินครบ", "value": f"{_pct(done, n)}%"},
            ],
            "tables": [
                _table(
                    "รายวิชา-กลุ่มที่ต้องประเมิน",
                    [
                        _col("code", "รหัสวิชา"),
                        _col("section", "กลุ่ม"),
                        _col("name", "ชื่อวิชา"),
                        _col("faculty", "คณะ"),
                        _col("skills", "Skill"),
                        _col("n", "นิสิต", True),
                        _col("done", "ประเมินครบ", True),
                        _col("status", "สถานะ"),
                        _col("teachers", "ผู้สอน"),
                    ],
                    rows,
                )
            ],
        }

    def _r03(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        curs = CurriculumStore(self.url, self.schema, None).list(user)["items"]
        smo = SmoStore(self.url, self.schema).list(user)["items"]
        open_smo = Counter(s["draft_id"] for s in smo if s["status"] in ("pending", "returned"))
        with self._conn() as conn:
            books = {
                r["draft_id"]
                for r in conn.execute(
                    "SELECT draft_id FROM curriculum_sections WHERE section = '0' "
                    "AND data ? 'approved_book' AND data->'approved_book' <> 'null'::jsonb"
                )
            }
        rows = [
            {
                "name": c["name_th"],
                "faculty": c.get("scope_faculty") or c.get("faculty"),
                "level": c["level"],
                "start": c["start_year"],
                "status": CUR_STATUSES[c["status"]],
                "book": "มี" if c["id"] in books else "ยังไม่แนบ",
                "smo": open_smo.get(c["id"], 0),
            }
            for c in curs
        ]
        st = Counter(c["status"] for c in curs)
        return {
            "kpis": [{"label": v, "value": st[k]} for k, v in CUR_STATUSES.items()]
            + [{"label": "สมอ.08 ค้าง", "value": sum(open_smo.values())}],
            "tables": [
                _table(
                    "คู่มือหลักสูตร",
                    [
                        _col("name", "หลักสูตร"),
                        _col("faculty", "คณะ"),
                        _col("level", "ระดับ"),
                        _col("start", "ปีที่เริ่มใช้"),
                        _col("status", "สถานะ"),
                        _col("book", "เล่มอนุมัติ"),
                        _col("smo", "สมอ.08 ค้าง", True),
                    ],
                    rows,
                )
            ],
        }

    def _r09(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        reg = self.assess.register(user)
        nos = [r["no"] for r in reg]
        with self._conn() as conn:
            log = conn.execute(
                "SELECT to_char(ts AT TIME ZONE 'Asia/Bangkok', 'YYYY-MM') AS month, "
                "count(*) AS n, count(DISTINCT who) AS who FROM transcript_checks "
                "WHERE no = ANY(%s) GROUP BY 1 ORDER BY 1",
                (nos,),
            ).fetchall()
            signer = {
                r["no"]: r["signer"]
                for r in conn.execute(
                    "SELECT no, signer FROM skill_transcripts WHERE no = ANY(%s)", (nos,)
                )
            }
        rows = [
            {
                **r,
                "issued_at": _when(r["issued_at"]),
                "status": TR_STATUS.get(r["status"], r["status"]),
                "signer": (signer.get(r["no"]) or {}).get("name_th"),
                "method": SIGN_METHOD.get(m := (signer.get(r["no"]) or {}).get("method"), m),
            }
            for r in reg
        ]
        return {
            "kpis": [
                {"label": "เอกสารที่ออก", "value": len(rows)},
                {"label": "ตรวจสอบผ่าน QR (ครั้ง)", "value": sum(r["checks"] for r in rows)},
                {"label": "ผู้ตรวจสอบไม่ซ้ำ", "value": sum(x["who"] for x in log)},
            ],
            "tables": [
                _table(
                    "เอกสารที่ออก",
                    [
                        _col("no", "เลขที่"),
                        _col("sid", "รหัสนิสิต"),
                        _col("name_th", "ชื่อ"),
                        _col("program", "หลักสูตร"),
                        _col("issued_at", "ออกเมื่อ"),
                        _col("signer", "ผู้ลงนาม"),
                        _col("method", "วิธีลงนาม"),
                        _col("status", "สถานะ"),
                        _col("checks", "ตรวจสอบ (ครั้ง)", True),
                    ],
                    rows,
                ),
                _table(
                    "การตรวจสอบรายเดือน",
                    [
                        _col("month", "เดือน"),
                        _col("n", "ครั้ง", True),
                        _col("who", "ผู้ตรวจสอบไม่ซ้ำ", True),
                    ],
                    log,
                    "นับจากหน้าตรวจสอบสาธารณะ ผู้ตรวจสอบไม่ซ้ำนับจากที่อยู่เครือข่ายที่เข้ารหัสทางเดียว",
                ),
            ],
        }

    def _r10(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        rounds = self.qa.rounds()
        if not rounds:
            return {"tables": [_table("ผลการตรวจสอบ", [], [])], "note": "ยังไม่มีรอบการประเมิน"}
        rid = int(p["round"]) if p.get("round", "").isdigit() else rounds[0]["id"]
        s = self.qa.summary(rid, user)
        asg = {i["curriculum_id"]: i for i in self.qa.assign_overview(rid)["items"]}
        rows = [
            {
                "name": i["name_th"],
                "faculty": i["faculty"],
                "level": i["level"],
                "set": i["set_year"],
                "passed": f"{i['passed']}/{i['total']}",
                "final": RESULTS[i["final"]],
                "recorders": ", ".join(x["name"] for x in asg[i["curriculum_id"]]["recorders"]),
                "confirmer": (asg[i["curriculum_id"]]["confirmer"] or {}).get("name"),
                "doc": "ฉบับจริง" if i["complete"] and i["status"] == "confirmed" else "ฉบับร่าง",
            }
            for i in s["items"]
        ]
        return {
            "filters": [
                {
                    "key": "round",
                    "label": "รอบ",
                    "value": str(rid),
                    "options": [[str(r["id"]), r["name"]] for r in rounds],
                }
            ],
            "kpis": [
                {"label": "หลักสูตรในรอบ", "value": s["kpi"]["programs"]},
                {"label": "ผ่านทุกข้อ", "value": s["kpi"]["pass"]},
                {"label": "ไม่ผ่าน ≥ 1 ข้อ", "value": s["kpi"]["fail"]},
                {"label": "รอพิจารณา", "value": s["kpi"]["pending"]},
            ],
            "tables": [
                _table(
                    "ผลการตรวจสอบรายหลักสูตร",
                    [
                        _col("name", "หลักสูตร"),
                        _col("faculty", "คณะ"),
                        _col("level", "ระดับ"),
                        _col("set", "เกณฑ์ พ.ศ."),
                        _col("passed", "ผ่าน/ทั้งหมด"),
                        _col("final", "ผลสุดท้าย"),
                        _col("recorders", "ผู้บันทึก"),
                        _col("confirmer", "ผู้ยืนยัน"),
                        _col("doc", "R10"),
                    ],
                    rows,
                )
            ],
            "round": rid,
        }

    # ---------- FS-7c ทักษะ ----------

    def _skill_rows(self, studs, ld) -> list[dict[str, Any]]:
        levels = ld["settings"]["levels"]
        per_skill: dict[str, list[float]] = defaultdict(list)
        courses: dict[str, set[str]] = defaultdict(set)
        for s in studs:
            sc = ld["scores"].get(s["sid"], [])
            by: dict[str, list[float]] = defaultdict(list)
            for r in sc:
                by[r["skill"]].append(float(r["score"]))
                courses[r["skill"]].add(r["course_code"])
            for k, v in by.items():
                per_skill[k].append(sum(v) / len(v))
        rows = []
        for code, xs in sorted(
            per_skill.items(),
            key=lambda kv: (list(CATS).index(ld["skills"].get(kv[0], {}).get("cat", "C")), kv[0]),
        ):
            sk = ld["skills"].get(code, {})
            dist = Counter(level_of(x, levels)["level"] for x in xs)
            row = {
                "code": code,
                "cat": sk.get("cat"),
                "name": sk.get("name_th"),
                "n": len(xs),
                "avg": _avg(xs),
                "pro": _pct(dist[4] + dist[5], len(xs)),
                "courses": len(courses[code]),
            }
            for lv in levels:
                row[f"l{lv['level']}"] = dist[lv["level"]]
            if sk.get("cat") == "E":
                row["s"] = f"{_pct(sum(x >= ld['settings']['ethics_pass'] for x in xs), len(xs))}%"
            rows.append(row)
        return rows

    def _r04(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        studs, ld, filters = self._students(user, p)
        rows = self._skill_rows(studs, ld)
        levels = ld["settings"]["levels"]
        cat_avg = {
            c: _avg([r["avg"] for r in rows if r["cat"] == c and r["avg"] is not None])
            for c in CATS
        }
        return {
            "filters": filters,
            "kpis": [
                {"label": f"{c} เฉลี่ย", "value": cat_avg[c] if cat_avg[c] is not None else "–"}
                for c in CATS
            ]
            + [{"label": "นิสิตที่มีผล", "value": sum(1 for s in studs if ld["scores"].get(s["sid"]))}],
            "tables": [
                _table(
                    "รายทักษะ",
                    [
                        _col("cat", "ด้าน"),
                        _col("code", "รหัส"),
                        _col("name", "ทักษะ"),
                        _col("n", "นิสิต", True),
                        _col("avg", "เฉลี่ย", True),
                        *[_col(f"l{lv['level']}", lv["en"], True) for lv in levels],
                        _col("pro", "% Proficient ขึ้นไป", True),
                        _col("s", "Ethics % ผ่าน (S)"),
                        _col("courses", "รายวิชาที่ประเมิน", True),
                    ],
                    rows,
                    "คะแนนนิสิตแต่ละคน = ค่าเฉลี่ยรายวิชาที่ยืนยันแล้ว (BR-M3-01) · คอลัมน์ระดับ = จำนวนนิสิต",
                )
            ],
        }

    def _group(self, studs, ld, key) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for s in studs:
            groups[str(s.get(key) or "ไม่ระบุ")].append(s)
        rows = []
        for g, ss in sorted(groups.items()):
            sums = [
                self.assess._summary(
                    s, ld["scores"].get(s["sid"], []), ld["skills"], ld["settings"]
                )
                for s in ss
            ]
            have = [x for x in sums if x["overall"] is not None]
            row = {
                "group": g,
                "students": len(ss),
                "assessed": len(have),
                "overall": _avg([x["overall"] for x in have]),
            }
            for c in CATS:
                row[c] = _avg([x["cats"][c] for x in have if x["cats"][c] is not None])
            rows.append(row)
        return rows

    def _r05(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        studs, ld, filters = self._students(user, p)
        by = p.get("by") if p.get("by") in ("faculty", "program", "entry_year") else "faculty"
        label = {"faculty": "คณะ", "program": "หลักสูตร", "entry_year": "รหัสปีเข้า"}[by]
        rows = self._group(studs, ld, by)
        allrow = self._group([{**s, "_": "ทั้งมหาวิทยาลัย"} for s in studs], ld, "_")
        cols = [
            _col("group", label),
            _col("students", "นิสิต", True),
            _col("assessed", "มีผล", True),
            *[_col(c, c, True) for c in CATS],
            _col("overall", "รวม", True),
        ]
        return {
            "filters": [
                {
                    "key": "by",
                    "label": "จำแนกตาม",
                    "value": by,
                    "options": [
                        ["faculty", "คณะ"],
                        ["program", "หลักสูตร"],
                        ["entry_year", "รหัสปีเข้า"],
                    ],
                },
                *filters,
            ],
            "tables": [_table(f"ตาม{label}", cols, allrow + rows)],
        }

    def _r06(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        studs, ld, filters = self._students(user, p)
        compare = self._group(studs, ld, "faculty" if not p.get("faculty") else "program")
        trend: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for s in studs:
            for r in ld["scores"].get(s["sid"], []):
                cat = ld["skills"].get(r["skill"], {}).get("cat")
                if cat:
                    trend[r["term"]][cat].append(float(r["score"]))
        trows = [
            {"term": t, **{c: _avg(v.get(c, [])) for c in CATS}}
            for t, v in sorted(trend.items(), key=lambda kv: term_sort(kv[0]))
        ]
        return {
            "filters": filters,
            "tables": [
                _table(
                    "เปรียบเทียบส่วนงาน/หลักสูตร",
                    [
                        _col("group", "กลุ่ม"),
                        _col("assessed", "นิสิตที่มีผล", True),
                        *[_col(c, c, True) for c in CATS],
                        _col("overall", "รวม", True),
                    ],
                    compare,
                ),
                _table(
                    "แนวโน้มรายภาค",
                    [_col("term", "ภาค"), *[_col(c, c, True) for c in CATS]],
                    trows,
                    "ค่าเฉลี่ยคะแนนรายวิชาที่ยืนยันแล้วในภาคนั้น",
                ),
            ],
        }

    def _r07(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        term = self._term(p)
        secs = self.assess.sections(term, user)["items"]
        opts = [
            [f"{s['course_code']}|{s['section']}", f"{s['course_code']} กลุ่ม {s['section']}"]
            for s in secs
        ]
        key = p.get("section") or (opts[0][0] if opts else "")
        filters = [
            self._term_filter(term),
            {"key": "section", "label": "รายวิชา-กลุ่ม", "value": key, "options": opts},
        ]
        if not key:
            return {
                "filters": filters,
                "tables": [_table("คะแนน", [], [])],
                "note": "ไม่มีรายวิชา-กลุ่มที่ต้องประเมินในขอบเขตของบัญชีนี้",
            }
        code, sec = key.split("|", 1)
        d = self.assess.section(term, code, sec, user)
        rows = []
        for s in d["students"]:
            got = d["scores"].get(s["sid"], {})
            vals = [got[k] for k in d["skills"] if k in got]
            lv = level_of(sum(vals) / len(vals), d["levels"]) if vals else None
            rows.append(
                {
                    "sid": s["sid"],
                    "name": s["name_th"],
                    **{k: got.get(k) for k in d["skills"]},
                    "level": lv and lv["en"],
                }
            )
        return {
            "filters": filters,
            "kpis": [
                {"label": "นิสิต", "value": d["n"]},
                {"label": "ประเมินครบ", "value": d["done"]},
                {"label": "สถานะ", "value": SECTION_STATUS[d["status"]]},
            ],
            "tables": [
                _table(
                    f"{code} กลุ่ม {sec}",
                    [
                        _col("sid", "รหัสนิสิต"),
                        _col("name", "ชื่อ"),
                        *[_col(k, k, True) for k in d["skills"]],
                        _col("level", "ระดับเฉลี่ย"),
                    ],
                    rows,
                    "ระดับตาม Rubric 5 ระดับของฐานข้อมูล Skill",
                )
            ],
        }

    def _r08(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        items = self.assess.portfolio_list(user)["items"]
        opts = [[i["sid"], f"{i['sid']} {i['name_th']}"] for i in items[:500]]
        sid = p.get("sid") or (opts[0][0] if opts else "")
        filters = [{"key": "sid", "label": "นิสิต", "value": sid, "options": opts}]
        if not sid:
            return {
                "filters": filters,
                "tables": [_table("ทักษะ", [], [])],
                "note": "ไม่มีนิสิตในขอบเขตของบัญชีนี้",
            }
        pf = self.assess.portfolio(sid, user)
        rows = [
            {
                "code": s["code"],
                "cat": s["cat"],
                "name": s["name_th"],
                "avg": s["avg"],
                "level": s["level"],
                "su": s["su"],
                "n": s["n"],
            }
            for s in pf["skills"]
        ]
        return {
            "filters": filters,
            "kpis": [
                {"label": c, "value": pf["cats"][c] if pf["cats"][c] is not None else "–"}
                for c in CATS
            ]
            + [{"label": "ระดับรวม", "value": pf["level"] or "–"}],
            "radar": {c: pf["cats"][c] for c in CATS},
            "tables": [
                _table(
                    f"{pf['student']['name_th']} ({sid})",
                    [
                        _col("cat", "ด้าน"),
                        _col("code", "รหัส"),
                        _col("name", "ทักษะ"),
                        _col("avg", "คะแนน", True),
                        _col("level", "ระดับ"),
                        _col("su", "S/U"),
                        _col("n", "รายวิชา", True),
                    ],
                    rows,
                )
            ],
        }

    # ---------- FS-7d R11–R14 ----------

    def _r11(self, user: User | None, p: dict[str, str]) -> dict[str, Any]:
        """Public (BR: R11 needs no sign-in): curricula by faculty and level, and the latest
        round's results; names of people never appear."""
        curs = self.skills.curricula(None)
        levels = sorted({c["level"] or "ไม่ระบุ" for c in curs})
        by: dict[str, Counter] = defaultdict(Counter)
        for c in curs:
            by[c["faculty"] or "ไม่ระบุ"][c["level"] or "ไม่ระบุ"] += 1
        rows = [
            {"faculty": f, **{lv: n[lv] for lv in levels}, "total": sum(n.values())}
            for f, n in sorted(by.items())
        ]
        tables = [
            _table(
                "จำนวนหลักสูตรตามส่วนงานและระดับ",
                [
                    _col("faculty", "ส่วนงาน"),
                    *[_col(lv, lv, True) for lv in levels],
                    _col("total", "รวม", True),
                ],
                rows,
            )
        ]
        kpis = [{"label": "หลักสูตรทั้งหมด", "value": len(curs)}]
        rounds = [r for r in self.qa.rounds() if r["status"] in ("open", "closed")]
        if rounds:
            r = rounds[0]
            admin = User(email="public@r11", roles=["admin"])
            s = self.qa.summary(r["id"], admin)
            kpis += [
                {"label": f"ผ่านเกณฑ์ ({r['name']})", "value": s["kpi"]["pass"]},
                {"label": "ไม่ผ่าน", "value": s["kpi"]["fail"]},
                {"label": "รอพิจารณา", "value": s["kpi"]["pending"]},
            ]
        return {"kpis": kpis, "tables": tables}

    def _r12(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        curs = [
            c
            for c in CurriculumStore(self.url, self.schema, None).list(user)["items"]
            if c["status"] in SET_OK or p.get("all") == "1"
        ]
        ids = [c["id"] for c in curs]
        with self._conn() as conn:
            s0 = {
                r["draft_id"]: r["data"]
                for r in conn.execute(
                    "SELECT draft_id, data FROM curriculum_sections WHERE section = '0' "
                    "AND draft_id = ANY(%s)",
                    (ids,),
                )
            }
            grads = Counter(
                r["program_code"]
                for r in conn.execute(
                    "SELECT program_code FROM ext_students WHERE graduated IS NOT NULL"
                )
            )
            persons = conn.execute(
                "SELECT id, name_th, org FROM ext_persons ORDER BY name_th"
            ).fetchall()
        info = {i: (s0.get(i) or {}).get("info", {}).get("values", {}) for i in ids}
        teach = {i: ((s0.get(i) or {}).get("teachers") or {}).get("teachers") or [] for i in ids}
        name = {c["id"]: c["name_th"] for c in curs}
        t1 = [
            {
                "cur": name[i],
                "teacher": t.get("name"),
                "responsible": "ผู้รับผิดชอบ" if t.get("responsible") else "ประจำ",
                "degree": t.get("highest_level"),
                "rank": t.get("rank"),
                "hr": t.get("pid") or "–",
            }
            for i in ids
            for t in teach[i]
        ]
        seen: dict[str, list[str]] = defaultdict(list)
        for i in ids:
            for t in teach[i]:
                seen[(t.get("pid") or (t.get("name") or "").replace(" ", ""))].append(name[i])
        t2 = [
            {"teacher": k, "count": len(v), "curricula": ", ".join(v)}
            for k, v in seen.items()
            if len(v) > 1
        ]
        lv = Counter(c["level"] or "ไม่ระบุ" for c in curs)
        typ = Counter(str(info[i].get("program_type") or "ไม่ระบุ") for i in ids)
        lang = Counter(str(info[i].get("language") or "ไม่ระบุ") for i in ids)
        cwie = [
            i
            for i in ids
            if str(info[i].get("cwie") or "").strip() not in ("", "ไม่มี", "False", "false", "None")
        ]
        prog = {i: info[i].get("program_code") for i in ids}
        no_data = "ยังไม่มีข้อมูลการลงทะเบียนสหกิจจาก SUPREME (A4)"
        used = [r for r in persons]
        tables = [
            _table(
                "1 อาจารย์ผู้รับผิดชอบ-ประจำ",
                [
                    _col("cur", "หลักสูตร"),
                    _col("teacher", "อาจารย์"),
                    _col("responsible", "ประเภท"),
                    _col("degree", "คุณวุฒิสูงสุด"),
                    _col("rank", "ตำแหน่ง"),
                    _col("hr", "รหัส HURIS"),
                ],
                t1,
            ),
            _table(
                "2 ความซ้ำซ้อนอาจารย์",
                [
                    _col("teacher", "อาจารย์/รหัส"),
                    _col("count", "จำนวนหลักสูตร", True),
                    _col("curricula", "หลักสูตร"),
                ],
                t2,
            ),
            _table(
                "3 จำนวนหลักสูตรตามระดับ",
                [_col("k", "ระดับ"), _col("n", "จำนวน", True)],
                [{"k": k, "n": n} for k, n in sorted(lv.items())],
            ),
            _table(
                "4 ตามประเภท",
                [_col("k", "ประเภทหลักสูตร"), _col("n", "จำนวน", True)],
                [{"k": k, "n": n} for k, n in sorted(typ.items())],
            ),
            _table(
                "5 ตามภาษา",
                [_col("k", "ภาษา"), _col("n", "จำนวน", True)],
                [{"k": k, "n": n} for k, n in sorted(lang.items())],
            ),
            _table(
                "6 ร้อยละหลักสูตรสหกิจ",
                [_col("k", "รายการ"), _col("n", "ค่า")],
                [
                    {"k": "หลักสูตรทั้งหมด", "n": len(ids)},
                    {"k": "มีสหกิจ/CWIE", "n": len(cwie)},
                    {"k": "ร้อยละ", "n": f"{_pct(len(cwie), len(ids))}%"},
                ],
            ),
            _table("7 นิสิตลงทะเบียนสหกิจ", [_col("k", "รายการ")], [], no_data),
            _table("8 ร้อยละนิสิตสหกิจ", [_col("k", "รายการ")], [], no_data),
            _table(
                "9 บัณฑิตจากหลักสูตรสหกิจ",
                [_col("cur", "หลักสูตร"), _col("n", "ผู้สำเร็จการศึกษา", True)],
                [{"cur": name[i], "n": grads.get(prog[i], 0)} for i in cwie],
            ),
            _table(
                "10 บุคคลภายนอก (เสนอเพิ่ม)", [_col("name_th", "ชื่อ"), _col("org", "หน่วยงาน")], used
            ),
            _table(
                "11 หลักสูตรต้นทาง (เสนอเพิ่ม)",
                [_col("cur", "หลักสูตร"), _col("prev", "หลักสูตรต้นทาง"), _col("year", "ปี")],
                [
                    {
                        "cur": name[i],
                        "prev": info[i].get("previous_program"),
                        "year": info[i].get("previous_year"),
                    }
                    for i in ids
                    if info[i].get("previous_program")
                ],
            ),
            _table(
                "12 ยังไม่แนบเล่มอนุมัติ (เสนอเพิ่ม)",
                [_col("cur", "หลักสูตร")],
                [{"cur": name[i]} for i in ids if not (s0.get(i) or {}).get("approved_book")],
            ),
        ]
        return {
            "filters": [
                {
                    "key": "all",
                    "label": "หลักสูตร",
                    "value": p.get("all", ""),
                    "options": [["", "เฉพาะตรวจสอบสำเร็จ/เผยแพร่"], ["1", "ทุกสถานะ"]],
                }
            ],
            "kpis": [{"label": "หลักสูตรในรายงาน", "value": len(ids)}],
            "tables": tables,
            "note": "คอลัมน์ตามข้อมูลที่ระบบมี [สมมติ: รอแบบฟอร์ม Excel ของ TOR 6.1]",
        }

    def _r13(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        curs = self.skills.curricula(user)
        cid = (
            int(p["curriculum"])
            if p.get("curriculum", "").isdigit()
            else (curs[0]["id"] if curs else 0)
        )
        filters = [
            {
                "key": "curriculum",
                "label": "หลักสูตร",
                "value": str(cid),
                "options": [[str(c["id"]), c["name_th"]] for c in curs],
            }
        ]
        cur = next((c for c in curs if c["id"] == cid), None)
        if cur is None:
            return {
                "filters": filters,
                "tables": [_table("รายงานผล", [], [])],
                "note": "ไม่มีหลักสูตรในขอบเขต",
            }
        codes = set(self.skills.courses_of(cur))
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT d.term, d.key, d.data, d.status, i.code, i.courses FROM m2_docs d "
                "JOIN m2_items i ON i.term = d.term AND i.key = d.key WHERE d.doc = 'report' "
                "AND d.status IN ('sent', 'approved', 'published') ORDER BY d.term, i.code"
            ).fetchall()
        out, grades = [], Counter()
        for r in rows:
            if not codes & set(r["courses"] or []):
                continue
            r3, r4 = (r["data"] or {}).get("r3") or {}, (r["data"] or {}).get("r4") or {}
            grades.update({k: int(v or 0) for k, v in (r3.get("grades") or {}).items()})
            out.append(
                {
                    "term": r["term"],
                    "code": r["code"],
                    "status": M2_STATUSES[r["status"]],
                    "achieved": r3.get("achieved"),
                    "not": r3.get("not_achieved"),
                    "critique": r4.get("critique"),
                    "plan": r4.get("improvement"),
                }
            )
        return {
            "filters": filters,
            "kpis": [{"label": "รายงานผลที่ส่งแล้ว", "value": len(out)}],
            "tables": [
                _table(
                    "สรุปจากรายงานผลการจัดการเรียนรู้",
                    [
                        _col("term", "ภาค"),
                        _col("code", "รายวิชา"),
                        _col("status", "สถานะ"),
                        _col("achieved", "บรรลุ CLO เนื่องจาก"),
                        _col("not", "ไม่บรรลุเนื่องจาก"),
                        _col("critique", "ข้อวิพากษ์"),
                        _col("plan", "แผนปรับปรุง"),
                    ],
                    out,
                ),
                _table(
                    "การกระจายเกรดรวม",
                    [_col("g", "เกรด"), _col("n", "จำนวน", True)],
                    [{"g": g, "n": n} for g, n in grades.items()],
                ),
            ],
            "note": "ประกอบ มคอ.7 · รายวิชาของหลักสูตร = หมวด 4 และตารางสอนรหัสหลักสูตรเดียวกัน",
        }

    def _r14(self, user: User, p: dict[str, str]) -> dict[str, Any]:
        d = CourseStore(self.url, self.schema).list()
        rows = [
            {
                "code": c["code_th"],
                "name": c.get("name_th"),
                "version": c.get("latest"),
                "module": c.get("module"),
                "unit": c.get("unit"),
                "status": c.get("status"),
                "credits": c.get("credit_text"),
                "used": len(c.get("used_in") or []),
            }
            for c in d["items"]
        ]
        return {
            "kpis": [{"label": "รายวิชาทั้งหมด", "value": len(rows)}],
            "tables": [
                _table(
                    "ฐานข้อมูลรายวิชากลาง",
                    [
                        _col("code", "รหัส"),
                        _col("name", "ชื่อ"),
                        _col("version", "Version ล่าสุด", True),
                        _col("credits", "หน่วยกิต"),
                        _col("module", "ชุดวิชา"),
                        _col("unit", "หน่วยงาน"),
                        _col("status", "สถานะ"),
                        _col("used", "ใช้ในหลักสูตร", True),
                    ],
                    rows,
                )
            ],
        }

    # ---------- FS-7e หน้าแรก (US-G-01) ----------

    def home(self, user: User) -> dict[str, Any]:
        """What the signed-in user should see first: figures for central/executive/faculty,
        'งานของฉัน' for teachers and recorders; every number in the user's scope."""
        out: dict[str, Any] = {"cards": [], "units": [], "skills": None, "tasks": []}
        term = None
        try:
            term = self._term({})
        except HTTPException:
            pass
        if user.can_do("c1"):
            curs = CurriculumStore(self.url, self.schema, None).list(user)
            out["cards"].append(
                {
                    "label": "หลักสูตรในระบบ",
                    "value": len(curs["items"]),
                    "sub": " · ".join(f"{CUR_STATUSES[k]} {v}" for k, v in curs["counts"].items()),
                    "href": "/curricula",
                }
            )
        if term and (user.can_do("d2") or user.can_do("p1")):
            d = self.m2.dashboard(term, user)
            out["cards"].append(
                {
                    "label": f"แผนฯ ส่งแล้ว (ภาค {term})",
                    "value": f"{d['plan_pct']}%",
                    "sub": f"รายงานผลฯ {d['report_pct']}%",
                    "href": "/dashboard/plans",
                }
            )
            out["units"] = d["units"]
            out["target"] = d["target_pct"]
        if term and user.can_do("d3"):
            d = self.assess.dashboard(term, user)
            out["cards"].append(
                {
                    "label": "ประเมิน Skill ครบ",
                    "value": f"{d['assessed_pct']}%",
                    "sub": f"{d['sections']} รายวิชา-กลุ่ม",
                    "href": "/dashboard/skills",
                }
            )
            out["cards"].append(
                {
                    "label": "Skill Transcript ที่ออกแล้ว",
                    "value": d["transcripts"]["issued"],
                    "sub": f"พร้อมออก {d['transcripts']['ready']}",
                    "href": "/transcripts",
                }
            )
        if user.can_do("r4") or user.can_do("d3"):
            studs, ld, _ = self._students(user, {})
            rows = self._skill_rows(studs, ld)
            out["skills"] = {
                c: _avg([r["avg"] for r in rows if r["cat"] == c and r["avg"] is not None])
                for c in CATS
            }
        out["tasks"] = self._tasks(user, term)
        return out

    def _tasks(self, user: User, term: str | None) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        if term and (user.can_do("p2") or user.can_do("p4")) and user.pid:
            for i in self.m2.items(term, user)["items"]:
                for doc, base in (("plan", "/plans"), ("report", "/reports")):
                    if i["mine"][doc] and i["status"][doc] in ("none", "draft", "returned"):
                        tasks.append(
                            {
                                "text": f"บันทึก{'แผน' if doc == 'plan' else 'รายงานผล'} {i['code']}",
                                "status": M2_STATUSES[i["status"][doc]],
                                "href": f"{base}/{term.replace('/', '-')}/{i['key']}",
                            }
                        )
        if term and user.can_do("s4"):
            for s in self.assess.sections(term, user)["items"]:
                if s["mine"] and s["status"] != "ok":
                    tasks.append(
                        {
                            "text": f"ประเมิน Skill {s['course_code']} กลุ่ม {s['section']}",
                            "status": SECTION_STATUS[s["status"]],
                            "href": f"/assess/{term.replace('/', '-')}/{s['course_code']}/{s['section']}",
                        }
                    )
        if user.can_do("q3"):
            for r in [x for x in self.qa.rounds() if x["status"] == "open"]:
                for it in self.qa.programs(r["id"], user)["items"]:
                    roles = set(it["roles"])
                    st = it["status"]
                    need = (
                        ("recorder" in roles and st in ("none", "doing") and it["complete"])
                        or ("confirmer" in roles and st == "sent")
                        or ("evaluator" in roles and st == "confirmed" and it["final"] == "pending")
                    )
                    if need:
                        tasks.append(
                            {
                                "text": f"ประเมินหลักสูตร {it['name_th']}",
                                "status": it["status_th"],
                                "href": f"/qa/{r['id']}/{it['curriculum_id']}",
                            }
                        )
        return tasks[:30]


def _cell(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str)):
        return v
    return str(v)
