"""Subscription / Package management — Platform Admin only.
Schools are subscribed to a plan; usage caps tracked (informational MVP)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class PlanCreate(BaseModel):
    name: str
    monthly_price: float
    max_students: int = 500
    max_teachers: int = 50
    features: list[str] = []
    description: str | None = None


class AssignPlan(BaseModel):
    school_id: str
    plan_id: str


@router.get("/plans")
async def list_plans(user: dict = Depends(get_current_user)):
    db = get_db()
    plans = await db.plans.find({}, {"_id": 0}).sort("monthly_price", 1).to_list(100)
    if not plans:
        # seed defaults
        defaults = [
            {"id": new_id(), "name": "Starter", "monthly_price": 0, "max_students": 100, "max_teachers": 10,
             "features": ["Attendance", "Marks", "Parent log"], "description": "For small schools getting started.", "created_at": utc_now()},
            {"id": new_id(), "name": "Growth", "monthly_price": 4999, "max_students": 1000, "max_teachers": 75,
             "features": ["Everything in Starter", "Fees + Receipts", "WhatsApp delivery", "Excel uploads"], "description": "For growing single-campus schools.", "created_at": utc_now()},
            {"id": new_id(), "name": "Enterprise", "monthly_price": 14999, "max_students": 10000, "max_teachers": 500,
             "features": ["Everything in Growth", "Teacher Performance", "Audit logs", "Priority support", "Custom branding"], "description": "For multi-campus and enterprise.", "created_at": utc_now()},
        ]
        await db.plans.insert_many([{**p} for p in defaults])
        plans = await db.plans.find({}, {"_id": 0}).sort("monthly_price", 1).to_list(100)
    return plans


@router.post("/plans")
async def create_plan(payload: PlanCreate, _: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    doc = {"id": new_id(), **payload.model_dump(), "created_at": utc_now()}
    await db.plans.insert_one(doc); doc.pop("_id", None)
    return doc


@router.post("/assign")
async def assign_plan(payload: AssignPlan, _: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    plan = await db.plans.find_one({"id": payload.plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    school = await db.schools.find_one({"id": payload.school_id})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    await db.schools.update_one(
        {"id": payload.school_id},
        {"$set": {
            "subscription": {
                "plan_id": payload.plan_id,
                "plan_name": plan["name"],
                "monthly_price": plan["monthly_price"],
                "max_students": plan["max_students"],
                "max_teachers": plan["max_teachers"],
                "assigned_at": utc_now(),
            }
        }}
    )
    return {"ok": True}


@router.get("/usage/{school_id}")
async def usage(school_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "platform_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    s = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    students = await db.students.count_documents({"school_id": school_id, "status": "active"})
    teachers = await db.users.count_documents({"school_id": school_id, "role": "teacher", "is_active": True})
    notifs = await db.notifications.count_documents({"school_id": school_id})
    return {
        "school": s,
        "usage": {"students": students, "teachers": teachers, "notifications_sent": notifs},
    }
