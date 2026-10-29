"""จับคู่ข้อมูลในเล่มกับระบบ (FS-3d · US-M1-13 · BR-05 BR-09), on the curriculum's own data
(FS-3 Q4 ก: the import page is read-only once a curriculum is in the system).

Teachers of หมวด 0.2 → HURIS by name (one hit proposes, several let a person choose, none
proposes the register of external persons); a qualification that differs from HURIS shows both
values. Courses of หมวด 4 → the central database: same code and content → its latest Version ·
a new code → Version 1 · same code, other content → the next Version. Nothing is stored until a
person confirms each row, and saving goes through the curriculum's edit rules.
"""

from __future__ import annotations

import re
from typing import Any

from ocl_api.auth import User
from ocl_api.courses import _insert_version, same_content
from ocl_api.db import connect
from ocl_api.persons import highest

# titles that come before a Thai name in a book, longest first
TITLES = sorted(
    [
        "ศาสตราจารย์",
        "รองศาสตราจารย์",
        "ผู้ช่วยศาสตราจารย์",
        "อาจารย์",
        "ดร.",
        "ศ.",
        "รศ.",
        "ผศ.",
        "อ.",
        "นาย",
        "นางสาว",
        "นาง",
        "น.ส.",
        "พล.ต.",
        "ร.อ.",
    ],  # fmt: skip
    key=len,
    reverse=True,
)


def bare(name: str | None) -> str:
    """A name without titles and spaces, for comparing a book with HURIS."""
    s = re.sub(r"\[|\]", "", str(name or "")).strip()
    changed = True
    while changed:
        changed = False
        for t in TITLES:
            if s.startswith(t):
                s, changed = s[len(t) :].strip(), True
    return "".join(s.split())


class Matcher:
    def __init__(self, url: str, schema: str | None = None):
        self.url, self.schema = url, schema

    def _conn(self):
        return connect(self.url, self.schema)

    def teachers(self, s0: dict[str, Any]) -> list[dict[str, Any]]:
        rows = (s0.get("teachers") or {}).get("teachers") or []
        with self._conn() as conn:
            staff = conn.execute(
                "SELECT pid, title_short, position, name_th, faculty, education FROM ext_staff"
            ).fetchall()
            ext = conn.execute(
                "SELECT id, title_short, position, name_th, org, education FROM ext_persons "
                "WHERE active"
            ).fetchall()
        by_name: dict[str, list[dict[str, Any]]] = {}
        for s in staff:
            by_name.setdefault(bare(s["name_th"]), []).append(s)
        out = []
        for i, t in enumerate(rows):
            if t.get("pid") or t.get("xid"):
                out.append({"index": i, "name": t.get("name"), "state": "linked",
                            "pid": t.get("pid"), "xid": t.get("xid")})  # fmt: skip
                continue
            hits = by_name.get(bare(t.get("name")), [])
            cands = [{
                "pid": s["pid"], "name": f"{s['title_short'] or ''}{s['name_th']}",
                "rank": s["position"],
                "highest_level": highest(s["education"] or []), "faculty": s["faculty"],
                "differs": bool(t.get("highest_level"))
                and highest(s["education"] or []) != t.get("highest_level"),
            } for s in hits]  # fmt: skip
            externals = [{"xid": x["id"], "name": f"{x['title_short'] or ''}{x['name_th']}",
                          "org": x["org"]}
                         for x in ext if bare(x["name_th"]) == bare(t.get("name"))]  # fmt: skip
            state = (
                "one"
                if len(cands) == 1
                else "many"
                if cands
                else "external"
                if externals
                else "none"
            )
            out.append({"index": i, "name": t.get("name"), "rank": t.get("rank"),
                        "highest_level": t.get("highest_level"), "state": state,
                        "candidates": cands, "externals": externals})  # fmt: skip
        return out

    def courses(self, s4: dict[str, Any]) -> list[dict[str, Any]]:
        rows = (s4.get("courses") or {}).get("courses") or []
        codes = [str(c.get("code_th") or "").strip() for c in rows]
        with self._conn() as conn:
            vers = conn.execute(
                "SELECT v.*, c.latest FROM course_versions v "
                "JOIN courses c ON c.code_th = v.code_th "
                "WHERE v.code_th = ANY(%s) ORDER BY v.version",
                (codes,),
            ).fetchall()
        by_code: dict[str, list[dict[str, Any]]] = {}
        for v in vers:
            by_code.setdefault(v["code_th"], []).append(v)
        out = []
        for i, c in enumerate(rows):
            code = codes[i]
            have = by_code.get(code, [])
            same = next((v for v in reversed(have) if same_content(c, v)), None)
            if c.get("version"):
                state, version = "linked", c["version"]
            elif not code:
                state, version = "no_code", None
            elif not have:
                state, version = "new", 1
            elif same:
                state, version = "same", same["version"]
            else:
                state, version = "changed", have[-1]["latest"] + 1
            latest = have[-1] if have else None
            out.append({
                "index": i, "code_th": code, "name_th": c.get("name_th"),
                "credit_text": c.get("credit_text"),
                "state": state, "version": version,
                "central": {k: latest.get(k) for k in ("version", "name_th", "credit_text")}
                if latest else None,
            })  # fmt: skip
        return out

    # ---------- confirm ----------

    def apply_teachers(self, s0: dict[str, Any], choices: list[dict[str, Any]]) -> tuple[dict, int]:
        """choices: {index, pid | xid, quals: 'huris' | 'book'} (BR-05: which qualification)."""
        rows = (s0.get("teachers") or {}).get("teachers") or []
        with self._conn() as conn:
            done = 0
            for ch in choices:
                i = ch.get("index")
                if not isinstance(i, int) or not 0 <= i < len(rows):
                    continue
                t = rows[i]
                if ch.get("pid"):
                    s = conn.execute(
                        "SELECT * FROM ext_staff WHERE pid = %s", (ch["pid"],)
                    ).fetchone()
                    if s is None:
                        continue
                    t["pid"] = s["pid"]
                    t.pop("xid", None)
                    if ch.get("quals") == "huris":
                        t |= {"rank": s["position"], "highest_level": highest(s["education"] or [])}
                    done += 1
                elif ch.get("xid"):
                    x = conn.execute(
                        "SELECT * FROM ext_persons WHERE id = %s", (ch["xid"],)
                    ).fetchone()
                    if x is None:
                        continue
                    t["xid"] = x["id"]
                    t.pop("pid", None)
                    done += 1
        return s0, done

    def apply_courses(
        self, s4: dict[str, Any], choices: list[dict[str, Any]], user: User
    ) -> tuple[dict, int]:
        """choices: {index, accept: true}; a new code → Version 1 · other content → next Version
        (both made from the book's text, BR-09)."""
        rows = (s4.get("courses") or {}).get("courses") or []
        want = {
            ch["index"] for ch in choices if ch.get("accept") and isinstance(ch.get("index"), int)
        }
        proposals = {p["index"]: p for p in self.courses(s4)}
        done = 0
        with self._conn() as conn, conn.transaction():
            for i in sorted(want):
                p = proposals.get(i)
                if p is None or p["state"] not in ("new", "same", "changed"):
                    continue
                c, code = rows[i], p["code_th"]
                if p["state"] == "new":
                    conn.execute(
                        "INSERT INTO courses (code_th, code_en, module, status, latest, "
                        "created_by, updated_by) "
                        "VALUES (%s, %s, %s, 'ใช้งาน', 1, %s, %s) ON CONFLICT DO NOTHING",
                        (code, c.get("code_en"), c.get("module"), user.email, user.email),
                    )
                    _insert_version(conn, code, 1, "ใหม่", c, user.email, "จับคู่จากคู่มือหลักสูตร")
                elif p["state"] == "changed":
                    _insert_version(
                        conn, code, p["version"], "ปรับปรุง", c, user.email, "จับคู่จากคู่มือหลักสูตร"
                    )
                    conn.execute(
                        "UPDATE courses SET latest = %s, updated_by = %s, updated_at = now() "
                        "WHERE code_th = %s",
                        (p["version"], user.email, code),
                    )
                c["version"] = p["version"]
                done += 1
        return s4, done
