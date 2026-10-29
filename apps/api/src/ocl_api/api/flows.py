"""กำหนดการตั้งค่าการอนุมัติ (menu u2 · US-U-05): read and edit the approval flows."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ocl_api.auth import User, require_menu
from ocl_api.config import Settings, get_settings
from ocl_api.flow_defaults import ON_REJECT, STEP_ACTIONS
from ocl_api.flows import FlowError, FlowStore

router = APIRouter(prefix="/api/flows", tags=["flows"])

REQUIRE_VIEW = require_menu("u2")
REQUIRE_EDIT = require_menu("u2", action="edit")


def get_flows(settings: Settings = Depends(get_settings)) -> FlowStore:
    if not settings.database_url:
        raise HTTPException(503, "ขั้นตอนอนุมัติต้องการ DATABASE_URL")
    return FlowStore(settings.database_url, settings.database_schema)


class Step(BaseModel):
    roles: list[str] = []
    position: str | None = None
    label: str = ""
    action: str
    days: int = 0
    on_reject: str = "sender"


class FlowEdit(BaseModel):
    steps: list[Step]
    notify_next: bool | None = None
    notify_sender: bool | None = None
    remind_overdue: bool | None = None


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except FlowError as e:
        raise HTTPException(e.status, str(e)) from e


def _with_labels(out: dict[str, Any], fs: FlowStore) -> dict[str, Any]:
    return {"actions": STEP_ACTIONS, "on_reject": ON_REJECT, "groups": fs.groups(), **out}


@router.get("")
def list_flows(fs: FlowStore = Depends(get_flows), _: User = Depends(REQUIRE_VIEW)) -> dict:
    return _with_labels({"items": fs.list()}, fs)


@router.get("/{flow_id}")
def get_flow(
    flow_id: str,
    version: int | None = None,
    fs: FlowStore = Depends(get_flows),
    _: User = Depends(REQUIRE_VIEW),
) -> dict[str, Any]:
    return _with_labels(_run(fs.get, flow_id, version), fs)


@router.put("/{flow_id}")
def save_flow(
    flow_id: str,
    body: FlowEdit,
    fs: FlowStore = Depends(get_flows),
    user: User = Depends(REQUIRE_EDIT),
) -> dict[str, Any]:
    out = _run(
        fs.save,
        flow_id,
        user.email,
        [s.model_dump() for s in body.steps],
        notify_next=body.notify_next,
        notify_sender=body.notify_sender,
        remind_overdue=body.remind_overdue,
    )
    return _with_labels(out, fs)
