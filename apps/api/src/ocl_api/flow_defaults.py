"""Default approval flows (BRD 00 §4, the mock's D.flows): the seed of migration 009.

No imports beyond json, so db.py can build the seed from it (flows.py uses the database).
"""

from __future__ import annotations

import json
from typing import Any

STEP_ACTIONS: dict[str, str] = {
    "submit": "ส่ง",
    "review": "ตรวจสอบ",
    "approve": "อนุมัติ",
    "sign": "ลงนาม",
}
ON_REJECT: dict[str, str] = {"sender": "ส่งคืนผู้ส่ง", "previous": "ส่งคืนขั้นก่อนหน้า"}


def _step(
    roles: list[str], label: str, action: str, days: int, position: str | None = None
) -> dict[str, Any]:
    return {
        "roles": roles,
        "position": position,
        "label": label,
        "action": action,
        "days": days,
        "on_reject": "sender",
    }


# BRD 00 §4 and the mock's D.flows; `fixed` = number of steps the code relies on
DEFAULT_FLOWS: list[dict[str, Any]] = [
    {
        "id": "curriculum", "name": "ตรวจสอบและเผยแพร่คู่มือหลักสูตร", "fixed": 3,
        "steps": [
            _step(["curator", "central"], "ส่งให้คณะตรวจสอบ", "submit", 3),
            _step(["faculty"], "ตรวจสอบสำเร็จ", "review", 5),
            _step(["central"], "เปิด/ปิดการเผยแพร่", "approve", 0),
        ],
    },
    {
        "id": "smo08", "name": "งานปรับปรุงแก้ไขหลักสูตร (สมอ.08)", "fixed": None,
        "steps": [
            _step(["curator"], "ส่ง", "submit", 3),
            _step([], "เห็นชอบ", "approve", 14, "คณะกรรมการประจำคณะ"),
            _step(["central"], "ตรวจสอบ", "review", 7),
            _step([], "เห็นชอบ", "approve", 30, "สภาวิชาการ"),
            _step([], "อนุมัติ", "approve", 30, "สภามหาวิทยาลัย"),
        ],
    },
    {
        "id": "skill_set", "name": "อนุมัติชุด Skill ของหลักสูตร", "fixed": None,
        "steps": [
            _step(["curator"], "ส่ง", "submit", 3, "ผู้กำหนด Skill ของหลักสูตร"),
            _step(["faculty"], "อนุมัติ", "approve", 7),
        ],
    },
    {
        "id": "skill_mapping", "name": "อนุมัติ Skill Mapping", "fixed": None,
        "steps": [
            _step(["curator"], "ส่ง", "submit", 3, "ผู้กำหนด Skill ของหลักสูตร"),
            _step(["faculty"], "อนุมัติ", "approve", 7),
        ],
    },
    {
        "id": "learning_plan", "name": "รับรองแผน/รายงานผลการจัดการเรียนรู้", "fixed": None,
        "steps": [
            _step(["teacher"], "ส่ง", "submit", 0, "อาจารย์ผู้รับผิดชอบรายวิชา"),
            _step(["curator"], "รับรอง", "approve", 7, "ประธานหลักสูตร"),
        ],
    },
    {
        "id": "skill_transcript", "name": "ออกเอกสาร Skill Transcript", "fixed": None,
        "steps": [
            _step(["central"], "ตรวจสอบ", "review", 3),
            _step([], "ลงนามดิจิทัล", "sign", 5, "ผู้ลงนาม (จาก SUPREME)"),
        ],
    },
]  # fmt: skip
STEP_COLS = ["roles", "position", "label", "action", "days", "on_reject"]


def seed_sql() -> str:
    def q(v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, int):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    flows = ",\n".join(
        f"({q(f['id'])}, {q(f['name'])}, 1, {q(f['fixed'])}, {i})"
        for i, f in enumerate(DEFAULT_FLOWS)
    )
    steps = ",\n".join(
        f"({q(f['id'])}, 1, {n}, {q(json.dumps(s['roles']))}::jsonb, {q(s['position'])}, "
        f"{q(s['label'])}, {q(s['action'])}, {s['days']}, {q(s['on_reject'])})"
        for f in DEFAULT_FLOWS
        for n, s in enumerate(f["steps"])
    )
    versions = ",\n".join(f"({q(f['id'])}, 1, 'seed')" for f in DEFAULT_FLOWS)
    return (
        "INSERT INTO flows (id, name, version, fixed_steps, ord) VALUES\n"
        f"{flows}\nON CONFLICT DO NOTHING;\n"
        "INSERT INTO flow_steps "
        "(flow_id, version, ord, roles, position, label, action, days, on_reject) VALUES\n"
        f"{steps}\nON CONFLICT DO NOTHING;\n"
        "INSERT INTO flow_versions (flow_id, version, by) VALUES\n"
        f"{versions}\nON CONFLICT DO NOTHING;"
    )
