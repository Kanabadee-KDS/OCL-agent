"""Approval flows (mock: approval · flow-edit · US-U-05), versioned.

A flow is an ordered list of steps; each step names who acts (permission groups, or a
position outside the system such as สภาวิชาการ), what they do, how many business days they
have and what a rejection does. Saving makes a new version; work already started keeps the
version it started with (C13). The administrators may act on any step.

The คู่มือหลักสูตร workflow (curricula.py) reads its flow `curriculum`: step 1 submits, step 2
reviews within `days` business days, step 3 publishes. Its four states are fixed, so that flow
keeps exactly three steps; who acts, the days and the e-mails are what the page changes (Q2 ก).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from ocl_api.db import Jsonb, connect
from ocl_api.flow_defaults import ON_REJECT, STEP_ACTIONS, STEP_COLS

WHOLE = "ทั้งมหาวิทยาลัย"


def today_th() -> date:
    return datetime.now(timezone(timedelta(hours=7))).date()


class FlowError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def can_act(roles: list[str], step: dict[str, Any]) -> bool:
    """A step is done by its groups; the administrators may act on any step."""
    return "admin" in roles or bool(set(roles) & set(step.get("roles") or []))


class FlowStore:
    def __init__(self, url: str, schema: str | None = None):
        self.url = url
        self.schema = schema

    def _conn(self):
        return connect(self.url, self.schema)

    @staticmethod
    def _steps(conn, flow_id: str, version: int) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in conn.execute(
                f"SELECT {', '.join(STEP_COLS)} FROM flow_steps "
                "WHERE flow_id = %s AND version = %s ORDER BY ord",
                (flow_id, version),
            )
        ]

    def groups(self) -> list[dict[str, Any]]:
        """Permission groups a step may name (ids and names for the flow-edit page)."""
        with self._conn() as conn:
            return conn.execute("SELECT id, name FROM role_groups ORDER BY ord, name").fetchall()

    def list(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            flows = conn.execute("SELECT * FROM flows ORDER BY ord").fetchall()
            return [{**_flow(f), "steps": self._steps(conn, f["id"], f["version"])} for f in flows]

    def get(self, flow_id: str, version: int | None = None) -> dict[str, Any]:
        with self._conn() as conn:
            f = conn.execute("SELECT * FROM flows WHERE id = %s", (flow_id,)).fetchone()
            if f is None:
                raise FlowError("ไม่พบขั้นตอนอนุมัตินี้", 404)
            v = version or f["version"]
            steps = self._steps(conn, flow_id, v)
            history = conn.execute(
                "SELECT version, by, ts FROM flow_versions WHERE flow_id = %s "
                "ORDER BY version DESC",
                (flow_id,),
            ).fetchall()
        return {
            **_flow(f),
            "steps": steps,
            "shown_version": v,
            "history": [{**h, "ts": h["ts"].isoformat(timespec="seconds")} for h in history],
        }

    def steps(self, flow_id: str, version: int | None = None) -> tuple[int, list[dict], dict]:
        """(version, steps, flags) of a flow; the current version when `version` is None."""
        f = self.get(flow_id, version)
        return f["shown_version"], f["steps"], f

    def save(
        self,
        flow_id: str,
        by: str,
        steps: list[dict[str, Any]],
        *,
        notify_next: bool | None = None,
        notify_sender: bool | None = None,
        remind_overdue: bool | None = None,
    ) -> dict[str, Any]:
        """Store the edited steps as a new version (unchanged steps: only the flags change)."""
        with self._conn() as conn, conn.transaction():
            f = conn.execute("SELECT * FROM flows WHERE id = %s FOR UPDATE", (flow_id,)).fetchone()
            if f is None:
                raise FlowError("ไม่พบขั้นตอนอนุมัตินี้", 404)
            known = {r["id"] for r in conn.execute("SELECT id FROM role_groups")}
            clean = [_clean(s, known) for s in steps]
            if not clean:
                raise FlowError("ต้องมีอย่างน้อย 1 ขั้นตอน")
            if f["fixed_steps"] and len(clean) != f["fixed_steps"]:
                raise FlowError(
                    f"ขั้นตอนนี้ต้องมี {f['fixed_steps']} ขั้นตามสถานะของงาน "
                    "แก้ผู้ดำเนินการ ระยะเวลา และการแจ้งเตือนได้ แต่เพิ่มหรือลบขั้นไม่ได้",
                    409,
                )
            if clean[-1]["action"] not in ("approve", "sign"):
                raise FlowError("ขั้นสุดท้ายต้องเป็นการอนุมัติหรือลงนาม")
            if clean[0]["on_reject"] == "previous":
                clean[0]["on_reject"] = "sender"
            if f["fixed_steps"] and not clean[0]["roles"]:
                raise FlowError("ขั้นแรกของงานนี้ต้องเลือกกลุ่มสิทธิ์ที่ส่งงานได้")
            version = f["version"]
            if clean != self._steps(conn, flow_id, version):
                version += 1
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO flow_steps (flow_id, version, ord, roles, position, label, "
                        "action, days, on_reject) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        [
                            (flow_id, version, n, Jsonb(s["roles"]), s["position"], s["label"],
                             s["action"], s["days"], s["on_reject"])
                            for n, s in enumerate(clean)
                        ],
                    )  # fmt: skip
                conn.execute(
                    "INSERT INTO flow_versions (flow_id, version, by) VALUES (%s, %s, %s)",
                    (flow_id, version, by),
                )
            conn.execute(
                "UPDATE flows SET version = %s, notify_next = coalesce(%s, notify_next), "
                "notify_sender = coalesce(%s, notify_sender), "
                "remind_overdue = coalesce(%s, remind_overdue), "
                "updated_by = %s, updated_at = now() "
                "WHERE id = %s",
                (version, notify_next, notify_sender, remind_overdue, by, flow_id),
            )
        return self.get(flow_id)

    def recipients(self, roles: list[str], faculty: str | None) -> list[str]:
        """Usable members of `roles` whose units cover `faculty` (no units = everywhere)."""
        if not roles:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT email, units FROM users WHERE active "
                "AND (expires_at IS NULL "
                "OR expires_at >= (now() AT TIME ZONE 'Asia/Bangkok')::date) "
                "AND roles ?| %s ORDER BY email",
                (roles,),
            ).fetchall()
        out = []
        for r in rows:
            units = r["units"] or []
            if not units or WHOLE in units or (faculty and faculty in units):
                out.append(r["email"])
        return out


def _flow(f: dict[str, Any]) -> dict[str, Any]:
    out = dict(f)
    out["updated_at"] = f["updated_at"].isoformat(timespec="seconds") if f["updated_at"] else None
    return out


def _clean(s: dict[str, Any], known: set[str]) -> dict[str, Any]:
    roles = [r for r in dict.fromkeys(s.get("roles") or [])]
    bad = [r for r in roles if r not in known]
    if bad:
        raise FlowError(f"ไม่รู้จักกลุ่มสิทธิ์ {', '.join(bad)}")
    position = (s.get("position") or "").strip() or None
    if not roles and not position:
        raise FlowError("ทุกขั้นต้องมีผู้ดำเนินการ: กลุ่มสิทธิ์ หรือชื่อตำแหน่ง")
    action = s.get("action")
    if action not in STEP_ACTIONS:
        raise FlowError(f"การดำเนินการต้องเป็น {', '.join(STEP_ACTIONS.values())}")
    days = int(s.get("days") or 0)
    if not 0 <= days <= 365:
        raise FlowError("ระยะเวลาต้องอยู่ระหว่าง 0–365 วันทำการ")
    on_reject = s.get("on_reject") or "sender"
    if on_reject not in ON_REJECT:
        raise FlowError("เมื่อไม่ผ่านต้องเป็นส่งคืนผู้ส่ง หรือส่งคืนขั้นก่อนหน้า")
    label = (s.get("label") or "").strip() or STEP_ACTIONS[action]
    return {
        "roles": roles,
        "position": position,
        "label": label,
        "action": action,
        "days": days,
        "on_reject": on_reject,
    }
