"""Non-teaching staff (cleaners, drivers, security, cook, sports coach, etc.).

Stored in the per-school DB collection `staff`. School admin manages CRUD;
Accounts can view (for payroll); teachers see no staff data.
"""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_roles, get_current_user
from core.db import tenant_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

router = APIRouter(prefix="/staff", tags=["staff"])

StaffRole = Literal[
    "cleaner", "bus_driver", "security", "cook", "sports_coach",
    "nurse", "librarian", "lab_assistant", "office_assistant", "other",
]


class StaffCreate(BaseModel):
    name: str
    role: StaffRole = "other"
    phone: Optional[str] = None
    email: Optional[str] = None
    monthly_salary: Optional[float] = None
    joining_date: Optional[str] = None
    notes: Optional[str] = None


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[StaffRole] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    monthly_salary: Optional[float] = None
    joining_date: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_staff(user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "accounts", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    tdb = await tenant_db(user["school_id"])
    docs = await tdb.staff.find(
        {"school_id": user["school_id"]}, {"_id": 0},
    ).sort("name", 1).to_list(1000)
    return docs


@router.post("")
async def create_staff(payload: StaffCreate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        **payload.model_dump(),
        "is_active": True,
        "created_at": utc_now(),
    }
    await tdb.staff.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"],
                      "create", "staff", doc["id"], {"name": payload.name, "role": payload.role})
    return clean_doc(doc)


@router.patch("/{staff_id}")
async def update_staff(staff_id: str, payload: StaffUpdate, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        return {"ok": True}
    res = await tdb.staff.update_one(
        {"id": staff_id, "school_id": user["school_id"]}, {"$set": update},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(user["id"], user["role"], user["school_id"], "update", "staff", staff_id, update)
    return {"ok": True}


@router.delete("/{staff_id}")
async def delete_staff(staff_id: str, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    res = await tdb.staff.update_one(
        {"id": staff_id, "school_id": user["school_id"]},
        {"$set": {"is_active": False}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    await log_action(user["id"], user["role"], user["school_id"], "deactivate", "staff", staff_id)
    return {"ok": True}


@router.get("/summary/payroll")
async def payroll_summary(user: dict = Depends(require_roles("school_admin", "accounts"))):
    """Returns total monthly outflow combining teacher + staff salaries."""
    from core.db import get_db
    db = get_db()
    tdb = await tenant_db(user["school_id"])

    # Teachers + accounts (master users)
    pipe_users = [
        {"$match": {"school_id": user["school_id"], "is_active": True,
                     "monthly_salary": {"$gt": 0}, "role": {"$in": ["teacher", "accounts"]}}},
        {"$group": {"_id": "$role", "total": {"$sum": "$monthly_salary"}, "count": {"$sum": 1}}},
    ]
    users_rows = await db.users.aggregate(pipe_users).to_list(20)
    by_role = {r["_id"]: {"count": r["count"], "monthly_total": r["total"]} for r in users_rows}

    # Non-teaching staff (tenant)
    pipe_staff = [
        {"$match": {"school_id": user["school_id"], "is_active": True,
                     "monthly_salary": {"$gt": 0}}},
        {"$group": {"_id": "$role", "total": {"$sum": "$monthly_salary"}, "count": {"$sum": 1}}},
    ]
    staff_rows = await tdb.staff.aggregate(pipe_staff).to_list(20)
    by_role.update({r["_id"]: {"count": r["count"], "monthly_total": r["total"]} for r in staff_rows})

    monthly_total = sum(v["monthly_total"] for v in by_role.values())
    return {
        "by_role": by_role,
        "monthly_total": monthly_total,
        "yearly_total": monthly_total * 12,
    }
