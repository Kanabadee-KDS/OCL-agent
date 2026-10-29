"""Role groups and their per-menu permissions: the defaults that seed the database.

From FS-1a the tables `role_groups` and `role_perms` (migration 006) decide who may do what;
this module only supplies their first contents and the fallback when there is no database.
The menus mirror apps/web/src/lib/nav.ts (tests/test_auth.py checks). No imports, so db.py can
build the seed from it.
"""

from __future__ import annotations

ROLES: dict[str, str] = {
    "admin": "ผู้ดูแลระบบ",
    "central": "ผู้ดูแลส่วนกลาง",
    "curator": "ผู้ตรวจสอบระดับหลักสูตร",
    "faculty": "ผู้ตรวจสอบระดับส่วนงาน",
    "evaluator": "ผู้ประเมินหลักสูตร",
    "teacher": "อาจารย์ผู้สอน",
    "advisor": "อาจารย์ที่ปรึกษา",
    "student": "นิสิต",
    "exec": "ผู้บริหาร",
}
# ขอบเขตข้อมูล of each built-in group (BRD 00 §3); applied per module from FS-2
ROLE_SCOPES: dict[str, str] = {
    "admin": "ทั้งมหาวิทยาลัย",
    "central": "ทั้งมหาวิทยาลัย",
    "curator": "หลักสูตรที่รับผิดชอบ",
    "faculty": "คณะ/ส่วนงาน",
    "evaluator": "หลักสูตรที่ได้รับมอบหมาย",
    "teacher": "รายวิชาที่สอน",
    "advisor": "นิสิตในความดูแล",
    "student": "ข้อมูลของตนเอง",
    "exec": "ตามส่วนงานที่กำหนด",
}
# ขอบเขตข้อมูล choices of the mock's role-edit page, and what each built-in group starts with
SCOPE_KINDS: dict[str, str] = {
    "program": "มุมมองหลักสูตร (เฉพาะหลักสูตรที่รับผิดชอบ)",
    "self": "มุมมองรายบุคคล (เฉพาะข้อมูลของตนเอง)",
    "faculty": "มุมมองส่วนงานเจ้าของหลักสูตร",
    "all": "ทั้งมหาวิทยาลัย",
}
DEFAULT_SCOPE_KIND: dict[str, str] = {
    "admin": "all",
    "central": "all",
    "curator": "program",
    "faculty": "faculty",
    "evaluator": "program",
    "teacher": "self",
    "advisor": "self",
    "student": "self",
    "exec": "faculty",
}
# the six per-menu actions of the mock's role-edit page (TOR 6.16.3)
ACTIONS: dict[str, str] = {
    "view": "ดู",
    "add": "เพิ่ม",
    "edit": "แก้ไข",
    "delete": "ลบ",
    "approve": "อนุมัติ",
    "print": "พิมพ์",
}
MENUS: dict[str, list[str]] = {
    "c": ["c1", "c1b", "c2", "c3", "c3h", "c5", "c4"],
    "p": ["p1", "p2", "p4"],
    "s": ["s1", "s2", "s2b", "s3", "s4", "s5", "s6"],
    "q": ["q1", "q2", "q1b", "q3", "q4"],
    "r": ["r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "ra", "rb", "rc"],
    "u": ["u1", "u2", "u3"],
    "m": ["m1", "m2"],
}
MENU_INHERITS: dict[str, str] = {"c3h": "c3"}  # pages beyond the mock follow their parent menu
ALL_MENUS = [m for ids in MENUS.values() for m in ids]

# who sees which module, and the only menus some roles see inside it (mock ROLES.mods/only)
_ACCESS: dict[str, tuple[list[str], list[str] | None]] = {
    "admin": (["c", "p", "s", "q", "r", "u"], None),
    "central": (["c", "p", "s", "q", "r", "u"], None),
    "curator": (["c", "p", "s", "q", "r"], None),
    "faculty": (["c", "p", "s", "q", "r"], None),
    "evaluator": (["q"], None),
    "teacher": (["p", "s", "r"], ["p2", "p4", "s4", "s5", "r0", "r7", "r8"]),
    "advisor": (["s", "r"], ["s5", "r0", "r8"]),
    "student": (["m"], None),
    "exec": (["r"], None),
}
# actions on the menus a role sees, as the mock's role-edit defaults them (`has()`)
_ACTIONS_OF: dict[str, set[str]] = {
    "admin": set(ACTIONS),
    "central": set(ACTIONS),
    "curator": set(ACTIONS) - {"delete"},
    "faculty": set(ACTIONS) - {"delete"},
    "evaluator": set(ACTIONS) - {"delete"},
    "teacher": set(ACTIONS) - {"delete", "approve"},
    "advisor": {"view", "print"},
    "student": {"view", "print"},
    "exec": {"view", "print"},
}
# where the system already behaves differently from the mock's defaults
_OVERRIDES: dict[tuple[str, str], set[str]] = {
    # BRD 00 §3: the faculty reviewer reads imports but does not import (J-04)
    ("faculty", "c3"): {"view", "print"},
}

Table = dict[str, dict[str, set[str]]]  # role -> menu -> actions


def default_table() -> Table:
    out: Table = {}
    for role, (mods, only) in _ACCESS.items():
        menus: dict[str, set[str]] = {}
        for mod in mods:
            for m in MENUS[mod]:
                if m in MENU_INHERITS or (only is not None and m not in only):
                    continue
                menus[m] = set(_OVERRIDES.get((role, m), _ACTIONS_OF[role]))
        out[role] = menus
    return out


def perms_for(roles: list[str], table: Table) -> dict[str, list[str]]:
    """Menu -> actions a user with `roles` holds (the union of their groups), in menu order."""
    got: dict[str, set[str]] = {}
    for r in roles:
        for menu, acts in table.get(r, {}).items():
            got.setdefault(menu, set()).update(acts)
    for child, parent in MENU_INHERITS.items():
        if parent in got:
            got[child] = set(got[parent])
    order = list(ACTIONS)
    return {m: sorted(got[m], key=order.index) for m in ALL_MENUS if got.get(m)}


def seed_sql() -> str:
    """INSERTs of the built-in groups and their defaults; existing rows are left alone."""

    def q(s: str) -> str:
        return "'" + s.replace("'", "''") + "'"

    groups = ",\n".join(
        f"({q(r)}, {q(n)}, {q(ROLE_SCOPES[r])}, true, {i})"
        for i, (r, n) in enumerate(ROLES.items())
    )
    perms = ",\n".join(
        f"({q(r)}, {q(m)}, {q(a)})"
        for r, menus in default_table().items()
        for m, acts in menus.items()
        for a in sorted(acts)
    )
    return (
        f"INSERT INTO role_groups (id, name, scope, builtin, ord) VALUES\n{groups}\n"
        "ON CONFLICT (id) DO NOTHING;\n"
        f"INSERT INTO role_perms (role_id, menu, action) VALUES\n{perms}\n"
        "ON CONFLICT DO NOTHING;"
    )


def scope_kind_sql() -> str:
    """UPDATE that gives the built-in groups their starting ขอบเขตข้อมูล."""
    cases = " ".join(f"WHEN '{r}' THEN '{k}'" for r, k in DEFAULT_SCOPE_KIND.items())
    return f"UPDATE role_groups SET scope_kind = CASE id {cases} ELSE scope_kind END WHERE builtin;"
