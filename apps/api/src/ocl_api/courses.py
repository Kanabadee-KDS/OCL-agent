"""ฐานข้อมูลรายวิชากลาง (FS-3a · US-M1-18, mock course-master / CUR23).

A course is its Thai code; what a curriculum book prints about it (names, credits,
descriptions) is kept per Version, shown as รหัส-Version (มศว191-2). A curriculum keeps the
Version it uses (`version` on the course row of หมวด 4) and changes it only while it is a draft
or through an approved สมอ.08 (BR-06, FS-3 Q2 ก). Started from the courses of the curricula
already in the system (FS-3 Q1 ก).
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.db import connect
from ocl_api.flows import today_th

TYPES = [
    "วิชาศึกษาทั่วไป",
    "วิชาแกน",
    "วิชาเฉพาะด้าน (บังคับ)",
    "วิชาเฉพาะด้าน (เลือก)",
    "วิชาเลือกเสรี",
    "สหกิจศึกษา/ฝึกงาน",
    "ปริญญานิพนธ์/วิทยานิพนธ์",
]
STATUSES = ["ใช้งาน", "ร่างรายวิชา", "ไม่ใช้งาน"]
KINDS = ["ใหม่", "เดิม", "ปรับปรุง"]  # how a Version came about (mock VST)
GE_UNIT = "สำนักนวัตกรรมการเรียนรู้ (วิชาศึกษาทั่วไป)"
TRANSCRIPT_MAX = 40
# master fields (one value per course) and versioned fields (one value per Version)
MASTER = ("code_en", "transcript_th", "transcript_en", "course_type", "module", "unit", "major",
          "reg_no", "telebank", "status", "note")  # fmt: skip
VERSIONED = ("name_th", "name_en", "credits", "credit_text", "description_th", "description_en")
CREDIT_RE = re.compile(r"^\s*(\d+)\s*\(\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*\)\s*$")


class CourseError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def be_year() -> int:
    return today_th().year + 543


def credits_of(text: str | None) -> int | None:
    m = re.match(r"\s*(\d+)", text or "")
    return int(m.group(1)) if m else None


def same_content(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Whether a book's course says the same as a Version (BR-09: name, credits, description)."""

    def norm(v: Any) -> str:
        return re.sub(r"\s+", "", str(v or ""))

    return all(
        norm(a.get(k)) == norm(b.get(k)) for k in ("name_th", "credit_text", "description_th")
    )


class CourseStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url, self.schema = url, schema

    def _conn(self):
        return connect(self.url, self.schema)

    # ---------- reads ----------

    def usage(self, conn=None) -> dict[str, list[dict[str, Any]]]:
        """code -> the curricula whose หมวด 4 has it, with the Version each one uses."""
        sql = (
            "SELECT d.id, d.name_th, d.status, c->>'code_th' AS code, c->>'version' AS version "
            "FROM curriculum_sections s JOIN curriculum_drafts d ON d.id = s.draft_id, "
            "jsonb_array_elements(coalesce(s.data->'courses'->'courses', '[]'::jsonb)) c "
            "WHERE s.section = '4' ORDER BY d.id"
        )
        own = conn is None
        conn = conn or self._conn()
        try:
            rows = conn.execute(sql).fetchall()
        finally:
            if own:
                conn.close()
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            if r["code"]:
                out.setdefault(r["code"], []).append({
                    "draft_id": r["id"], "name_th": r["name_th"], "status": r["status"],
                    "version": int(r["version"]) if r["version"] else None,
                })  # fmt: skip
        return out

    def list(self) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT c.*, v.kind, v.year, v.name_th, v.name_en, v.credits, v.credit_text, "
                "v.description_th, v.description_en FROM courses c "
                "JOIN course_versions v ON v.code_th = c.code_th AND v.version = c.latest "
                "ORDER BY c.code_th"
            ).fetchall()
            used = self.usage(conn)
            units = conn.execute(
                "SELECT DISTINCT faculty FROM ext_programs WHERE faculty IS NOT NULL ORDER BY 1"
            ).fetchall()
        items = [_row(r, used.get(r["code_th"], [])) for r in rows]
        return {
            "items": items,
            "counts": {
                "all": len(items),
                **{s: sum(i["status"] == s for i in items) for s in STATUSES},
            },
            "options": {
                "types": TYPES,
                "statuses": STATUSES,
                "units": list(
                    dict.fromkeys(
                        [
                            GE_UNIT,
                            *[u["faculty"] for u in units],
                            *[i["unit"] for i in items if i["unit"]],
                        ]
                    )
                ),  # fmt: skip
            },
        }

    def get(self, code: str) -> dict[str, Any]:
        with self._conn() as conn:
            r = conn.execute(
                "SELECT c.*, v.kind, v.year, v.name_th, v.name_en, v.credits, v.credit_text, "
                "v.description_th, v.description_en FROM courses c JOIN course_versions v "
                "ON v.code_th = c.code_th AND v.version = c.latest WHERE c.code_th = %s",
                (code,),
            ).fetchone()
            if r is None:
                raise CourseError(f"ไม่พบรายวิชา {code}", 404)
            versions = conn.execute(
                "SELECT version, kind, year, name_th, name_en, credits, credit_text, "
                "description_th, description_en, source, created_by, created_at "
                "FROM course_versions WHERE code_th = %s ORDER BY version DESC",
                (code,),
            ).fetchall()
            used = self.usage(conn).get(code, [])
        out = _row(r, used)
        out["versions"] = [{**v, "created_at": v["created_at"].isoformat()} for v in versions]
        return out

    def catalog(self, q: str = "", exclude: list[str] | None = None) -> list[dict[str, Any]]:
        """What หมวด 4 may pick: courses in use (not drafts or retired), latest Version, max 50."""
        words = [w for w in re.split(r"\s+", q.strip()) if w]
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT c.code_th, c.code_en, c.unit, c.course_type, c.module, "
                "c.latest AS version, v.name_th, v.name_en, v.credits, v.credit_text, "
                "v.description_th, v.description_en "
                "FROM courses c JOIN course_versions v ON v.code_th = c.code_th "
                "AND v.version = c.latest WHERE c.status = 'ใช้งาน' ORDER BY c.code_th"
            ).fetchall()
        skip = set(exclude or [])
        out = []
        for r in rows:
            hay = re.sub(
                r"\s+", "", f"{r['code_th']}{r['code_en'] or ''}{r['name_th']}{r['name_en'] or ''}"
            )
            if r["code_th"] in skip or not all(w in hay for w in words):
                continue
            out.append(dict(r))
            if len(out) == 50:
                break
        return out

    def latest(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT code_th, latest, status FROM courses WHERE code_th = ANY(%s)", (codes,)
            ).fetchall()
        return {r["code_th"]: {"latest": r["latest"], "status": r["status"]} for r in rows}

    def version(self, code: str, version: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM course_versions WHERE code_th = %s AND version = %s", (code, version)
            ).fetchone()

    # ---------- writes ----------

    def create(self, data: dict[str, Any], by: str, *, status: str | None = None) -> dict[str, Any]:
        code = (data.get("code_th") or "").strip()
        clean = _clean(data, need_all=status is None)
        if not code:
            raise CourseError("ต้องมีรหัสวิชา (ไทย)")
        with self._conn() as conn, conn.transaction():
            if conn.execute("SELECT 1 FROM courses WHERE code_th = %s", (code,)).fetchone():
                raise CourseError(f"มีรหัสวิชา {code} ในฐานข้อมูลแล้ว ให้เลือกจากรายการแทน", 409)
            master = {k: clean.get(k) for k in MASTER}
            master["status"] = status or master.get("status") or "ร่างรายวิชา"
            conn.execute(
                f"INSERT INTO courses (code_th, {', '.join(MASTER)}, latest, created_by, "
                "updated_by) "
                f"VALUES (%s, {', '.join(['%s'] * len(MASTER))}, 1, %s, %s)",
                (code, *[master[k] for k in MASTER], by, by),
            )
            _insert_version(conn, code, 1, "ใหม่", clean, by, "เพิ่มที่ฐานข้อมูลรายวิชากลาง")
        return self.get(code)

    def update(self, code: str, data: dict[str, Any], by: str, new_version: bool) -> dict[str, Any]:
        """Change a course; `new_version` keeps the current Version for the curricula using it."""
        clean = _clean(data, need_all=True)
        with self._conn() as conn, conn.transaction():
            r = conn.execute(
                "SELECT latest FROM courses WHERE code_th = %s FOR UPDATE", (code,)
            ).fetchone()
            if r is None:
                raise CourseError(f"ไม่พบรายวิชา {code}", 404)
            conn.execute(
                f"UPDATE courses SET {', '.join(f'{k} = %s' for k in MASTER)}, "
                "updated_by = %s, updated_at = now() WHERE code_th = %s",
                (*[clean.get(k) for k in MASTER], by, code),
            )
            if new_version:
                n = r["latest"] + 1
                _insert_version(conn, code, n, "ปรับปรุง", clean, by, "ปรับปรุงที่ฐานข้อมูลรายวิชากลาง")
                conn.execute("UPDATE courses SET latest = %s WHERE code_th = %s", (n, code))
            else:
                conn.execute(
                    f"UPDATE course_versions SET {', '.join(f'{k} = %s' for k in VERSIONED)} "
                    "WHERE code_th = %s AND version = %s",
                    (*[clean.get(k) for k in VERSIONED], code, r["latest"]),
                )
        return self.get(code)

    def delete(self, code: str) -> None:
        used = self.usage().get(code, [])
        if used:
            names = ", ".join(u["name_th"] or str(u["draft_id"]) for u in used[:3])
            raise CourseError(f"รายวิชา {code} ถูกใช้ใน {names} ลบไม่ได้ ให้ตั้งสถานะ 'ไม่ใช้งาน' แทน", 409)
        with self._conn() as conn:
            if conn.execute("DELETE FROM courses WHERE code_th = %s", (code,)).rowcount == 0:
                raise CourseError(f"ไม่พบรายวิชา {code}", 404)

    def backfill(self) -> int:
        """The first time: every course of every curriculum becomes a Version (เดิม), and the
        curricula point at it. Same code with other content → the next Version. Returns links."""
        from ocl_api.sections import write_one

        with self._conn() as conn, conn.transaction():
            if conn.execute("SELECT 1 FROM course_versions LIMIT 1").fetchone():
                return 0
            secs = conn.execute(
                "SELECT s.draft_id, s.data, d.faculty FROM curriculum_sections s "
                "JOIN curriculum_drafts d ON d.id = s.draft_id WHERE s.section = '4' "
                "ORDER BY s.draft_id"
            ).fetchall()
            versions: dict[str, list[dict[str, Any]]] = {}
            linked = 0
            for s in secs:
                data = s["data"] or {}
                rows = (data.get("courses") or {}).get("courses") or []
                changed = False
                for c in rows:
                    code = (c.get("code_th") or "").strip()
                    if not code or not c.get("name_th"):
                        continue
                    have = versions.setdefault(code, [])
                    match = next((v for v in have if same_content(c, v)), None)
                    if match is None:
                        if not have:
                            mod = c.get("module") or (
                                c.get("group")
                                if str(c.get("group") or "").startswith("ชุดวิชา")
                                else None
                            )
                            conn.execute(
                                "INSERT INTO courses (code_th, code_en, module, unit, status, "
                                "latest, created_by, updated_by) "
                                "VALUES (%s, %s, %s, %s, 'ใช้งาน', 1, 'system', 'system')",
                                (
                                    code,
                                    c.get("code_en"),
                                    mod,
                                    GE_UNIT if code.startswith(("ศท", "มศว")) else s["faculty"],
                                ),
                            )
                        match = {**c, "version": len(have) + 1}
                        _insert_version(conn, code, match["version"], "เดิม", c, "system",
                                        f"จากคู่มือหลักสูตร {s['draft_id']}")  # fmt: skip
                        conn.execute(
                            "UPDATE courses SET latest = %s WHERE code_th = %s",
                            (match["version"], code),
                        )
                        have.append(match)
                    if c.get("version") != match["version"]:
                        c["version"] = match["version"]
                        changed = True
                        linked += 1
                if changed:
                    write_one(
                        conn, s["draft_id"], "4", data, "system", "ผูกรายวิชากับฐานข้อมูลรายวิชากลาง"
                    )
        return linked


def _insert_version(
    conn, code: str, n: int, kind: str, c: dict[str, Any], by: str, source: str
) -> None:
    conn.execute(
        "INSERT INTO course_versions (code_th, version, kind, year, name_th, name_en, credits, "
        "credit_text, description_th, description_en, source, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (code, n, kind, be_year(), c.get("name_th"), c.get("name_en"),
         c["credits"] if isinstance(c.get("credits"), int) else credits_of(c.get("credit_text")),
         c.get("credit_text"), c.get("description_th"), c.get("description_en"), source, by),
    )  # fmt: skip


def _clean(data: dict[str, Any], *, need_all: bool) -> dict[str, Any]:
    out = {k: (v.strip() if isinstance(v, str) else v) or None for k, v in data.items()}
    need = {"code_en": "รหัสวิชา (อังกฤษ)", "name_th": "ชื่อวิชา (ไทย)", "name_en": "ชื่อวิชา (อังกฤษ)",
            "transcript_th": "ชื่อวิชา Transcript (ไทย)", "transcript_en": "ชื่อวิชา Transcript (อังกฤษ)",
            "course_type": "ประเภทรายวิชา", "credit_text": "จำนวนหน่วยกิต"}  # fmt: skip
    if not need_all:  # a quick add from a curriculum: code and Thai name (US-M1-20)
        need = {"name_th": need["name_th"]}
    miss = [label for k, label in need.items() if not out.get(k)]
    if miss:
        raise CourseError("กรุณากรอก " + ", ".join(miss))
    if out.get("credit_text") and not CREDIT_RE.match(out["credit_text"]):
        raise CourseError("หน่วยกิตต้องอยู่ในรูป x(a-b-c) เช่น 3(2-2-5)")
    for k in ("transcript_th", "transcript_en"):
        if out.get(k) and len(out[k]) > TRANSCRIPT_MAX:
            raise CourseError(f"ชื่อวิชา Transcript ยาวได้ไม่เกิน {TRANSCRIPT_MAX} ตัวอักษร")
    if out.get("course_type") and out["course_type"] not in TYPES:
        raise CourseError("ไม่รู้จักประเภทรายวิชานี้")
    if out.get("status") and out["status"] not in STATUSES:
        raise CourseError("สถานะต้องเป็น ใช้งาน ร่างรายวิชา หรือ ไม่ใช้งาน")
    out["credits"] = credits_of(out.get("credit_text"))
    return out


def _row(r: dict[str, Any], used: list[dict[str, Any]]) -> dict[str, Any]:
    out = {k: v for k, v in r.items() if k not in ("created_at", "updated_at")}
    out["updated_at"] = r["updated_at"].isoformat() if r.get("updated_at") else None
    out["used_in"] = used
    out["label"] = f"{r['code_th']}-{r['latest']}"
    return out
