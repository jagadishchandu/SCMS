"""School-day break schedule (morning / lunch / evening / sports).

School admins can configure recurring breaks that appear on every user's
calendar. Each row lives in the per-school tenant DB:

  {
    id, school_id, name, kind, start_time, end_time,
    days_of_week (list of 0..6 where Mon=0), audience,
    color, is_active, created_at, created_by
  }

kind ∈ {morning, lunch, evening, sports, custom}.
audience ∈ {all, students, teachers}.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import get_current_user
from core.db import tenant_db
from core.utils import new_id, utc_now

router = APIRouter(prefix="/breaks", tags=["breaks"])


_ALLOWED_KINDS = {"morning", "lunch", "evening", "sports", "custom"}
_ALLOWED_AUDIENCE = {"all", "students", "teachers"}
_DEFAULT_COLOR = {
    "morning": "#FBBF24",   # amber
    "lunch":   "#FB7185",   # rose
    "evening": "#60A5FA",   # blue
    "sports":  "#34D399",   # green
    "custom":  "#A78BFA",   # purple
}


class BreakIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="custom")
    start_time: str = Field(min_length=4, max_length=5)   # HH:MM
    end_time: str = Field(min_length=4, max_length=5)
    days_of_week: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    audience: str = Field(default="all")
    color: Optional[str] = None
    is_active: bool = True


def _validate(payload: BreakIn) -> dict:
    if payload.kind not in _ALLOWED_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(_ALLOWED_KINDS)}")
    if payload.audience not in _ALLOWED_AUDIENCE:
        raise HTTPException(status_code=400, detail="audience must be all|students|teachers")
    # Times: HH:MM
    for label, t in (("start_time", payload.start_time), ("end_time", payload.end_time)):
        if len(t) != 5 or t[2] != ":":
            raise HTTPException(status_code=400, detail=f"{label} must be HH:MM")
        try:
            h, m = int(t[:2]), int(t[3:])
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"{label} invalid") from e
    if payload.start_time >= payload.end_time:
        raise HTTPException(status_code=400, detail="start_time must be before end_time")
    for d in payload.days_of_week:
        if d < 0 or d > 6:
            raise HTTPException(status_code=400, detail="days_of_week values must be 0..6 (Mon=0)")
    return {
        "name": payload.name.strip(),
        "kind": payload.kind,
        "start_time": payload.start_time,
        "end_time": payload.end_time,
        "days_of_week": sorted(set(payload.days_of_week)),
        "audience": payload.audience,
        "color": payload.color or _DEFAULT_COLOR.get(payload.kind, _DEFAULT_COLOR["custom"]),
        "is_active": bool(payload.is_active),
    }


def _filter_for_user(user: dict) -> dict:
    """Audience filter so the same /breaks endpoint serves every role."""
    role = user.get("role")
    if role == "teacher":
        return {"audience": {"$in": ["all", "teachers"]}, "is_active": True}
    if role in ("parent",):
        return {"audience": {"$in": ["all", "students"]}, "is_active": True}
    # admins / accounts: everything
    return {}


@router.get("")
async def list_breaks(user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    flt = _filter_for_user(user)
    rows = await tdb.school_breaks.find(flt, {"_id": 0}).sort([("start_time", 1)]).to_list(500)
    return {"breaks": rows}


@router.post("")
async def create_break(payload: BreakIn, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Only school admins can configure breaks")
    tdb = await tenant_db(user["school_id"])
    base = _validate(payload)
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        **base,
        "created_at": utc_now().isoformat(),
        "created_by": user["id"],
    }
    await tdb.school_breaks.insert_one(dict(doc))
    return doc


class BreakPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    kind: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: Optional[list[int]] = None
    audience: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


@router.patch("/{break_id}")
async def update_break(break_id: str, payload: BreakPatch, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    existing = await tdb.school_breaks.find_one({"id": break_id, "school_id": user["school_id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Break not found")
    merged = {**existing, **{k: v for k, v in payload.dict(exclude_none=True).items()}}
    base = _validate(BreakIn(**{k: merged.get(k) for k in BreakIn.model_fields.keys()}))
    await tdb.school_breaks.update_one({"id": break_id}, {"$set": base})
    return {"ok": True, "id": break_id, **base}


@router.delete("/{break_id}")
async def delete_break(break_id: str, user: dict = Depends(get_current_user)):
    if user.get("role") not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    res = await tdb.school_breaks.delete_one({"id": break_id, "school_id": user["school_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Break not found")
    return {"ok": True}
