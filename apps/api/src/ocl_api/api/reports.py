"""Reports (FS-7 · M5): the catalog (menu r0), each report by its own menu r1–rc (R13 R14 under
r0), the Excel file of each, reminders of R01–R03; the home dashboard (US-G-01); and R11, the
public statistics, which need no sign-in."""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ocl_api.auth import User, current_user, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.reports import ReportStore

router = APIRouter(prefix="/api/reports", tags=["reports"])
home_router = APIRouter(prefix="/api/home", tags=["home"])
public = APIRouter(prefix="/api/public", tags=["public"])

ANY_REPORT = require_menu(
    "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "ra", "rb", "rc"
)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILTERS = (
    "term",
    "unit",
    "faculty",
    "program",
    "entry",
    "by",
    "section",
    "sid",
    "round",
    "curriculum",
    "all",
)


def get_reports(settings: Settings = Depends(get_settings)) -> ReportStore:
    if not settings.database_url:
        raise HTTPException(503, "รายงานต้องการ DATABASE_URL")
    return ReportStore(settings.database_url, settings.database_schema)


def _params(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.query_params.items() if k in FILTERS}


@router.get("")
def catalog(rs: ReportStore = Depends(get_reports), user: User = Depends(ANY_REPORT)) -> list[dict]:
    return [r for r in rs.catalog(user) if r["allowed"]]


@router.get("/{code}.xlsx")
def xlsx(
    code: str,
    request: Request,
    rs: ReportStore = Depends(get_reports),
    user: User = Depends(current_user),
) -> Response:
    data = rs.xlsx(code.upper(), user, _params(request))
    name = f"{code.upper()}-{date.today().isoformat()}.xlsx"
    return Response(
        data,
        media_type=XLSX,
        headers={
            "content-disposition": f'attachment; filename="{name}"; '
            f"filename*=UTF-8''{quote(name)}"
        },
    )


@router.get("/{code}")
def report(
    code: str,
    request: Request,
    rs: ReportStore = Depends(get_reports),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    return rs.report(code.upper(), user, _params(request))


@router.post("/{code}/remind")
def remind(
    code: str,
    request: Request,
    rs: ReportStore = Depends(get_reports),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    return rs.remind(code.upper(), user, _params(request))


@home_router.get("")
def home(rs: ReportStore = Depends(get_reports), user: User = Depends(current_user)) -> dict:
    return rs.home(user)


@public.get("/stats")
def stats(rs: ReportStore = Depends(get_reports)) -> dict[str, Any]:
    """R11: curricula by faculty and level, and the latest round's results; no sign-in."""
    return rs.report("R11", None, {})
