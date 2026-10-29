"""ทะเบียนบุคคลภายนอก (FS-3b · US-M1-19, mock ext-person).

People who are not in HURIS (external experts, special lecturers, industry experts, network
teachers). A curriculum lists one in หมวด 0.2 by `xid`; editing the person here rewrites that
row in every curriculum that lists them (the mock: "แก้ที่นี่แล้วอัปเดตทุกหลักสูตรที่ใช้").
A person in use cannot be deleted; set ไม่ใช้งาน instead.
"""

from __future__ import annotations

from typing import Any

from ocl_api.db import Jsonb, connect

KINDS = [
    "ผู้ทรงคุณวุฒิภายนอก",
    "อาจารย์พิเศษ",
    "ผู้เชี่ยวชาญจากภาคอุตสาหกรรม",
    "อาจารย์จากสถาบันเครือข่าย",
]
EDU_LEVELS = ["ปริญญาตรี", "ปริญญาโท", "ปริญญาเอก"]
WORK_TYPES = ["ผลงานวิชาการ", "งานวิจัย"]
FIELDS = ("kind", "title_full", "title_short", "position", "name_th", "name_en", "national_id",
          "org", "email", "tel")  # fmt: skip
REQUIRED = {"name_th": "ชื่อ-นามสกุล (ไทย)", "name_en": "ชื่อ-นามสกุล (อังกฤษ)",
            "title_full": "คำนำหน้าชื่อ", "org": "หน่วยงาน/สังกัด",
            "national_id": "เลขประจำตัวประชาชน"}  # fmt: skip


class PersonError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def highest(education: list[Any]) -> str | None:
    """ตรี/โท/เอก as หมวด 0.2 keeps it, from rows [level, degree, major, school, country, year]."""
    levels = {str(e[0]) for e in education if isinstance(e, list | tuple) and e}
    for lv, short in (("ปริญญาเอก", "เอก"), ("ปริญญาโท", "โท"), ("ปริญญาตรี", "ตรี")):
        if lv in levels:
            return short
    return None


def teacher_row(p: dict[str, Any]) -> dict[str, Any]:
    """What a curriculum keeps of the person in หมวด 0.2 (the rest stays with the person)."""
    return {
        "xid": p["id"],
        "name": f"{p.get('title_short') or ''}{p['name_th']}",
        "rank": p.get("position") or p.get("title_short"),
        "highest_level": highest(p.get("education") or []),
        "org": p.get("org"),
    }


def masked(nid: str | None) -> str | None:
    digits = [c for c in nid or "" if c.isdigit()]
    return f"x-xxxx-xxxxx-{''.join(digits[-3:-1])}-{digits[-1]}" if len(digits) >= 3 else None


class PersonStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url, self.schema = url, schema

    def _conn(self):
        return connect(self.url, self.schema)

    def usage(self, conn) -> dict[str, list[dict[str, Any]]]:
        rows = conn.execute(
            "SELECT d.id, d.name_th, d.status, t->>'xid' AS xid FROM curriculum_sections s "
            "JOIN curriculum_drafts d ON d.id = s.draft_id, "
            "jsonb_array_elements(coalesce(s.data->'teachers'->'teachers', '[]'::jsonb)) t "
            "WHERE s.section = '0' AND t ? 'xid' ORDER BY d.id"
        ).fetchall()
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r["xid"], []).append(
                {"draft_id": r["id"], "name_th": r["name_th"], "status": r["status"]}
            )
        return out

    def list(self) -> dict[str, Any]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ext_persons ORDER BY id").fetchall()
            used = self.usage(conn)
        items = [_out(r, used.get(r["id"], []), full=False) for r in rows]
        return {
            "items": items,
            "counts": {
                "all": len(items),
                "active": sum(i["active"] for i in items),
                "used": sum(bool(i["used_in"]) for i in items),
            },
            "options": {"kinds": KINDS, "levels": EDU_LEVELS, "work_types": WORK_TYPES},
        }

    def get(self, pid: str) -> dict[str, Any]:
        with self._conn() as conn:
            r = conn.execute("SELECT * FROM ext_persons WHERE id = %s", (pid,)).fetchone()
            if r is None:
                raise PersonError(f"ไม่พบบุคคลภายนอก {pid}", 404)
            used = self.usage(conn).get(pid, [])
        return _out(r, used, full=True)

    def search(self, q: str) -> list[dict[str, Any]]:
        """Active people for a curriculum's 0.2, with what the curriculum keeps (no ID number)."""
        needle = "".join(q.split())
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ext_persons WHERE active ORDER BY id").fetchall()
        hits = [
            r
            for r in rows
            if needle in "".join(f"{r['name_th']}{r['name_en'] or ''}{r['org'] or ''}".split())
        ]
        return [teacher_row(r) | {"kind": r["kind"]} for r in hits[:20]]

    def save(self, pid: str | None, data: dict[str, Any], by: str) -> dict[str, Any]:
        """Add (pid None) or change a person; a change rewrites the person in every curriculum."""
        from ocl_api.sections import write_one

        clean = _clean(data)
        with self._conn() as conn, conn.transaction():
            if pid is None:
                n = conn.execute(
                    "SELECT coalesce(max(substring(id from 2)::int), 0) + 1 AS n FROM ext_persons"
                ).fetchone()["n"]
                pid = f"X{n:03d}"
                conn.execute(
                    f"INSERT INTO ext_persons (id, {', '.join(FIELDS)}, education, works, active, "
                    f"created_by, updated_by) VALUES (%s, {', '.join(['%s'] * len(FIELDS))}, "
                    "%s, %s, %s, %s, %s)",
                    (pid, *[clean.get(k) for k in FIELDS], Jsonb(clean["education"]),
                     Jsonb(clean["works"]), clean["active"], by, by),
                )  # fmt: skip
            else:
                done = conn.execute(
                    f"UPDATE ext_persons SET {', '.join(f'{k} = %s' for k in FIELDS)}, "
                    "education = %s, works = %s, active = %s, updated_by = %s, updated_at = now() "
                    "WHERE id = %s",
                    (*[clean.get(k) for k in FIELDS], Jsonb(clean["education"]),
                     Jsonb(clean["works"]), clean["active"], by, pid),
                )  # fmt: skip
                if done.rowcount == 0:
                    raise PersonError(f"ไม่พบบุคคลภายนอก {pid}", 404)
                person = conn.execute("SELECT * FROM ext_persons WHERE id = %s", (pid,)).fetchone()
                row = teacher_row(person)
                for s in conn.execute(
                    "SELECT draft_id, data FROM curriculum_sections WHERE section = '0' "
                    "AND data->'teachers'->'teachers' @> %s",
                    (Jsonb([{"xid": pid}]),),
                ).fetchall():
                    data0 = s["data"]
                    data0["teachers"]["teachers"] = [
                        {**t, **row} if t.get("xid") == pid else t
                        for t in data0["teachers"]["teachers"]
                    ]
                    write_one(conn, s["draft_id"], "0", data0, by, f"แก้ข้อมูลบุคคลภายนอก {pid}")
        return self.get(pid)

    def delete(self, pid: str) -> None:
        with self._conn() as conn, conn.transaction():
            used = self.usage(conn).get(pid, [])
            if used:
                names = ", ".join(u["name_th"] or str(u["draft_id"]) for u in used[:3])
                raise PersonError(f"ถูกใช้ใน {names} ลบไม่ได้ ให้ตั้งสถานะ 'ไม่ใช้งาน' แทน", 409)
            if conn.execute("DELETE FROM ext_persons WHERE id = %s", (pid,)).rowcount == 0:
                raise PersonError(f"ไม่พบบุคคลภายนอก {pid}", 404)


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: (str(data.get(k) or "").strip() or None) for k in FIELDS}
    miss = [label for k, label in REQUIRED.items() if not out.get(k)]
    if miss:
        raise PersonError("กรุณากรอก " + ", ".join(miss))
    if out["kind"] not in KINDS:
        raise PersonError("ไม่รู้จักประเภทบุคคลภายนอกนี้")
    digits = [c for c in out["national_id"] or "" if c.isdigit()]
    if len(digits) != 13:
        raise PersonError("เลขประจำตัวประชาชนต้องมี 13 หลัก")
    edu = [list(e)[:6] + [""] * (6 - len(list(e)[:6])) for e in data.get("education") or []]
    edu = [e for e in edu if e[1] or e[2]]
    if any(e[0] not in EDU_LEVELS for e in edu):
        raise PersonError("ระดับการศึกษาต้องเป็น ปริญญาตรี โท หรือเอก")
    works = [w for w in data.get("works") or [] if str(w.get("title") or "").strip()]
    if any(w.get("type") not in WORK_TYPES for w in works):
        raise PersonError("ประเภทผลงานต้องเป็น ผลงานวิชาการ หรือ งานวิจัย")
    out |= {"education": edu, "works": works, "active": bool(data.get("active", True))}
    return out


def _out(r: dict[str, Any], used: list[dict[str, Any]], *, full: bool) -> dict[str, Any]:
    out = {k: v for k, v in r.items() if k not in ("created_at", "updated_at", "national_id")}
    out["national_id"] = r["national_id"] if full else masked(r["national_id"])
    out["updated_at"] = r["updated_at"].isoformat()
    out["highest"] = highest(r["education"] or [])
    out["used_in"] = used
    return out
