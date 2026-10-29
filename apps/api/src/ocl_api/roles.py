"""Permission groups (role_groups / role_perms / role_events): the mock's roles and role-edit.

Rules the pages cannot break:
* a built-in group (the nine of BRD 00 §3) cannot be deleted, a group still held by users
  neither; the admin group always keeps "view" and "edit" on กำหนดกลุ่มสิทธิ์ (u1), so nobody
  can lock the administrators out of this page
* an action without "view" means nothing, so any action adds "view"
* every change is logged with who and when (NFR-15); when the group asks for it, every active
  member is told by e-mail (outbox, US-U-04)
"""

from __future__ import annotations

import secrets
from typing import Any

from ocl_api.db import Jsonb, connect
from ocl_api.perms import ACTIONS, ALL_MENUS, MENU_INHERITS, MENUS, SCOPE_KINDS

EDITABLE_MENUS = [m for m in ALL_MENUS if m not in MENU_INHERITS]
ADMIN_KEEPS = {"u1": {"view", "edit"}}


class RoleError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _iso(v: Any) -> Any:
    return v.isoformat(timespec="seconds") if hasattr(v, "isoformat") else v


def normalize(perms: dict[str, list[str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for menu, acts in perms.items():
        if menu not in EDITABLE_MENUS:
            raise RoleError(f"ไม่รู้จักเมนู {menu}")
        bad = [a for a in acts if a not in ACTIONS]
        if bad:
            raise RoleError(f"ไม่รู้จักการกระทำ {', '.join(bad)}")
        if acts:
            out[menu] = set(acts) | {"view"}
    return out


class RoleStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema

    def _conn(self):
        return connect(self.url, self.schema)

    @staticmethod
    def _perms(conn, role_id: str) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for r in conn.execute("SELECT menu, action FROM role_perms WHERE role_id = %s", (role_id,)):
            out.setdefault(r["menu"], set()).add(r["action"])
        return out

    @staticmethod
    def _members(conn, role_id: str) -> list[str]:
        rows = conn.execute(
            "SELECT email FROM users WHERE active AND roles ? %s ORDER BY email", (role_id,)
        )
        return [r["email"] for r in rows]

    def list(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            groups = conn.execute(
                "SELECT g.*, (SELECT count(*) FROM users u WHERE u.active AND u.roles ? g.id) "
                "AS users FROM role_groups g ORDER BY g.ord, g.name"
            ).fetchall()
            menus: dict[str, set[str]] = {}
            for r in conn.execute("SELECT DISTINCT role_id, menu FROM role_perms"):
                menus.setdefault(r["role_id"], set()).add(r["menu"])
        return [
            {
                **{k: _iso(v) for k, v in g.items()},
                "modules": [k for k, ids in MENUS.items() if menus.get(g["id"], set()) & set(ids)],
            }
            for g in groups
        ]

    def names(self, ids: list[str]) -> dict[str, str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT id, name FROM role_groups WHERE id = ANY(%s)", (ids,))
            return {r["id"]: r["name"] for r in rows}

    def ids(self) -> set[str]:
        with self._conn() as conn:
            return {r["id"] for r in conn.execute("SELECT id FROM role_groups")}

    def get(self, role_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            g = conn.execute("SELECT * FROM role_groups WHERE id = %s", (role_id,)).fetchone()
            if g is None:
                raise RoleError("ไม่พบกลุ่มสิทธิ์", 404)
            perms = self._perms(conn, role_id)
            members = self._members(conn, role_id)
            events = conn.execute(
                "SELECT ts, by, action, detail FROM role_events WHERE role_id = %s "
                "ORDER BY id DESC LIMIT 20",
                (role_id,),
            ).fetchall()
        order = list(ACTIONS)
        return {
            **{k: _iso(v) for k, v in g.items()},
            "users": len(members),
            "perms": {m: sorted(perms[m], key=order.index) for m in EDITABLE_MENUS if m in perms},
            "events": [{**e, "ts": _iso(e["ts"])} for e in events],
        }

    def create(self, name: str, copy_from: str | None, by: str) -> dict[str, Any]:
        name = name.strip()
        if not name:
            raise RoleError("ต้องตั้งชื่อกลุ่มสิทธิ์")
        role_id = "g" + secrets.token_hex(3)
        with self._conn() as conn, conn.transaction():
            if conn.execute("SELECT 1 FROM role_groups WHERE name = %s", (name,)).fetchone():
                raise RoleError("มีกลุ่มสิทธิ์ชื่อนี้แล้ว", 409)
            src = None
            if copy_from:
                src = conn.execute(
                    "SELECT * FROM role_groups WHERE id = %s", (copy_from,)
                ).fetchone()
                if src is None:
                    raise RoleError("ไม่พบกลุ่มสิทธิ์ต้นแบบ", 404)
            kind = src["scope_kind"] if src else "self"
            conn.execute(
                "INSERT INTO role_groups (id, name, scope, scope_kind, builtin, ord, updated_by) "
                "VALUES (%s, %s, %s, %s, false, "
                "(SELECT coalesce(max(ord), 0) + 1 FROM role_groups), %s)",
                (role_id, name, SCOPE_KINDS[kind], kind, by),
            )
            if src:
                conn.execute(
                    "INSERT INTO role_perms (role_id, menu, action) "
                    "SELECT %s, menu, action FROM role_perms WHERE role_id = %s",
                    (role_id, copy_from),
                )
            conn.execute(
                "INSERT INTO role_events (by, role_id, action, detail) VALUES (%s, %s, %s, %s)",
                (by, role_id, "create", Jsonb({"name": name, "copy_from": copy_from})),
            )
        return self.get(role_id)

    def update(
        self,
        role_id: str,
        by: str,
        *,
        name: str | None = None,
        scope_kind: str | None = None,
        perms: dict[str, list[str]] | None = None,
        auto_from_teachers: bool | None = None,
        notify_on_change: bool | None = None,
    ) -> dict[str, Any]:
        """Apply the role-edit form; returns the group plus `notified` (members e-mailed)."""
        from ocl_api.mail import Outbox

        if scope_kind is not None and scope_kind not in SCOPE_KINDS:
            raise RoleError(f"ไม่รู้จักขอบเขตข้อมูล {scope_kind}")
        new = normalize(perms) if perms is not None else None
        if new is not None and role_id == "admin":
            for menu, keep in ADMIN_KEEPS.items():
                if not keep <= new.get(menu, set()):
                    raise RoleError(
                        "กลุ่มผู้ดูแลระบบต้องคงสิทธิ์ดูและแก้ไขเมนูกำหนดกลุ่มสิทธิ์ เพื่อไม่ให้ไม่มีใครแก้สิทธิ์ได้",
                        409,
                    )
        with self._conn() as conn, conn.transaction():
            g = conn.execute(
                "SELECT * FROM role_groups WHERE id = %s FOR UPDATE", (role_id,)
            ).fetchone()
            if g is None:
                raise RoleError("ไม่พบกลุ่มสิทธิ์", 404)
            detail: dict[str, Any] = {}
            if name is not None and name.strip() and name.strip() != g["name"]:
                detail["name"] = [g["name"], name.strip()]
            if scope_kind is not None and scope_kind != g["scope_kind"]:
                detail["scope_kind"] = [g["scope_kind"], scope_kind]
            flags = {"auto_from_teachers": auto_from_teachers, "notify_on_change": notify_on_change}
            for k, v in flags.items():
                if v is not None and v != g[k]:
                    detail[k] = [g[k], v]
            if new is not None:
                old = self._perms(conn, role_id)
                pairs_old = {(m, a) for m, acts in old.items() for a in acts}
                pairs_new = {(m, a) for m, acts in new.items() for a in acts}
                added, removed = sorted(pairs_new - pairs_old), sorted(pairs_old - pairs_new)
                if added or removed:
                    detail["added"] = [f"{m}:{a}" for m, a in added]
                    detail["removed"] = [f"{m}:{a}" for m, a in removed]
                    conn.execute("DELETE FROM role_perms WHERE role_id = %s", (role_id,))
                    with conn.cursor() as cur:
                        cur.executemany(
                            "INSERT INTO role_perms (role_id, menu, action) VALUES (%s, %s, %s)",
                            [(role_id, m, a) for m, a in sorted(pairs_new)],
                        )
            if not detail:
                return {**self.get(role_id), "notified": 0}
            conn.execute(
                "UPDATE role_groups SET name = coalesce(%s, name), "
                "scope_kind = coalesce(%s, scope_kind), "
                "scope = CASE WHEN %s::text IS NULL THEN scope ELSE %s END, "
                "auto_from_teachers = coalesce(%s, auto_from_teachers), "
                "notify_on_change = coalesce(%s, notify_on_change), "
                "updated_by = %s, updated_at = now() WHERE id = %s",
                (
                    name.strip() if name and name.strip() else None,
                    scope_kind,
                    scope_kind if "scope_kind" in detail else None,
                    SCOPE_KINDS.get(scope_kind or "", ""),
                    auto_from_teachers,
                    notify_on_change,
                    by,
                    role_id,
                ),
            )
            conn.execute(
                "INSERT INTO role_events (by, role_id, action, detail) VALUES (%s, %s, %s, %s)",
                (by, role_id, "update", Jsonb(detail)),
            )
            members = self._members(conn, role_id)
            notify = notify_on_change if notify_on_change is not None else g["notify_on_change"]
        notified = 0
        if notify and ("added" in detail or "removed" in detail or "scope_kind" in detail):
            box = Outbox(self.url, self.schema)
            group = (name or "").strip() or g["name"]
            for email in members:
                box.send(
                    email,
                    f"สิทธิ์ของกลุ่ม {group} เปลี่ยนแปลง",
                    f"ผู้ดูแลระบบปรับสิทธิ์ของกลุ่ม {group} ที่บัญชีของคุณอยู่ "
                    "เมนูที่คุณเห็นจะเปลี่ยนภายในประมาณ 1 นาที "
                    "หากสิทธิ์ไม่ตรงกับงานที่รับผิดชอบ ติดต่อผู้ดูแลส่วนกลาง",
                    kind="perm_change",
                    by=by,
                    ref=f"role:{role_id}",
                )
                notified += 1
        return {**self.get(role_id), "notified": notified}

    def delete(self, role_id: str, by: str) -> None:
        with self._conn() as conn, conn.transaction():
            g = conn.execute("SELECT * FROM role_groups WHERE id = %s", (role_id,)).fetchone()
            if g is None:
                raise RoleError("ไม่พบกลุ่มสิทธิ์", 404)
            if g["builtin"]:
                raise RoleError("กลุ่มสิทธิ์ตั้งต้นลบไม่ได้", 409)
            held = conn.execute(
                "SELECT count(*) AS n FROM users WHERE roles ? %s", (role_id,)
            ).fetchone()["n"]
            if held:
                raise RoleError(f"ยังมีผู้ใช้ {held} คนในกลุ่มนี้ ย้ายผู้ใช้ออกก่อนลบ", 409)
            conn.execute("DELETE FROM role_groups WHERE id = %s", (role_id,))
            conn.execute(
                "INSERT INTO role_events (by, role_id, action, detail) VALUES (%s, %s, %s, %s)",
                (by, role_id, "delete", Jsonb({"name": g["name"]})),
            )
