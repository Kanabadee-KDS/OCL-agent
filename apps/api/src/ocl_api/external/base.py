"""What each external system supplies, and the shape every adapter returns."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

# system -> label shown on screen, and the tables it fills (BRD 00 §5)
SYSTEMS: dict[str, dict[str, Any]] = {
    "huris": {"label": "HURIS (บุคลากร)", "tables": ["ext_staff"]},
    "supreme": {
        "label": "SUPREME (ทะเบียนหลักสูตร · ตารางสอน · ทะเบียนนิสิต · ผู้ลงนาม)",
        "tables": ["ext_programs", "ext_sections", "ext_students", "ext_signers"],
    },
}

# columns of each table, in insert order; jsonb columns listed separately
COLUMNS: dict[str, list[str]] = {
    "ext_staff": [
        "pid",
        "title_full",
        "title_short",
        "position",
        "name_th",
        "name_en",
        "faculty",
        "department",
        "email",
        "education",
        "works",
    ],
    "ext_programs": ["code", "name_th", "name_en", "short", "level", "faculty", "version"],
    "ext_sections": [
        "term",
        "course_code",
        "section",
        "course_name",
        "program_code",
        "teachers",
        "schedule",
        "room",
        "enrolled",
    ],
    "ext_students": ["sid", "name_th", "program_code", "entry_year", "status", "graduated"],
    "ext_signers": ["id", "name_th", "position", "scope"],
}
JSONB = {"education", "works", "teachers"}

ADAPTER_LABELS = {"sample": "ข้อมูลตัวอย่าง", "datawarehouse": "Data Warehouse"}


@dataclass
class Snapshot:
    """One system's data as an adapter delivers it: table -> rows, and the date it reflects."""

    rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    as_of: date | None = None


class Adapter(Protocol):
    name: str  # "sample", "datawarehouse", ...

    def fetch(self, system: str) -> Snapshot: ...
