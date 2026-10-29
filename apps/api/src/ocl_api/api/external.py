"""Read-only views of the SUPREME / HURIS copies; every answer names its source."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ocl_api.auth import User, current_user, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.external import ExternalStore

router = APIRouter(prefix="/api/external", tags=["external"])

# staff pickers: คู่มือหลักสูตร (อาจารย์หลักสูตร), ผู้บันทึก/ผู้ยืนยันของการประเมิน, ผู้ใช้งาน (u3)
REQUIRE_STAFF_PICKER = require_menu("c1", "q3", "u3")


def get_external(settings: Settings = Depends(get_settings)) -> ExternalStore:
    if not settings.database_url:
        raise HTTPException(503, "ข้อมูลระบบภายนอกต้องการ DATABASE_URL")
    return ExternalStore(settings.database_url, settings.database_schema)


@router.get("/status")
def status(
    ext: ExternalStore = Depends(get_external), _: User = Depends(current_user)
) -> list[dict[str, Any]]:
    """Which systems are loaded, by which adapter, and the data date."""
    return ext.status()


@router.get("/staff")
def staff(
    q: str = "",
    faculty: str = "",
    limit: int = 20,
    ext: ExternalStore = Depends(get_external),
    _: User = Depends(REQUIRE_STAFF_PICKER),
) -> dict[str, Any]:
    return ext.staff(q, faculty, max(1, min(limit, 100)))
