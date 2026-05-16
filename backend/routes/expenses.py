"""School expenses + teacher reimbursement requests.

Stored in the per-school DB collection `expenses`.

Workflow:
- School admin records a direct expense  → status `approved` (school money already spent)
- Teacher submits an out-of-pocket expense → status `pending` → school admin or
  accounts review → `approve` / `reject` → optionally `mark_paid` (reimbursed
  with next salary if `reimburse_with_salary=True`).
"""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.auth import require_roles, get_current_user
from core.db import tenant_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

router = APIRouter(prefix="/expenses", tags=["expenses"])


ExpenseCategory = Literal[
    "salary", "supplies", "maintenance", "utilities", "travel",
    "events", "transport", "food", "stationery", "books", "other",
]
ExpenseStatus = Literal["pending", "approved", "rejected", "paid"]


class ExpenseCreate(BaseModel):
    category: ExpenseCategory
    description: str
    amount: float
    vendor: Optional[str] = None
    incurred_on: Optional[str] = None  # YYYY-MM-DD
    receipt_data_url: Optional[str] = None
    reimburse_with_salary: bool = False  # only meaningful for teacher submissions


class ExpenseDecide(BaseModel):
    decision: Literal["approve", "reject", "mark_paid"]
    note: Optional[str] = None


@router.post("")
async def create_expense(payload: ExpenseCreate, user: dict = Depends(require_roles("school_admin", "accounts", "teacher"))):
    """School admin / accounts: directly record an expense (auto-approved).
    Teacher: submit a reimbursement request (status=`pending`)."""
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    tdb = await tenant_db(user["school_id"])
    is_teacher_request = user["role"] == "teacher"
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "category": payload.category,
        "description": payload.description,
        "amount": payload.amount,
        "vendor": payload.vendor,
        "incurred_on": payload.incurred_on,
        "receipt_data_url": payload.receipt_data_url,
        "reimburse_with_salary": bool(payload.reimburse_with_salary) if is_teacher_request else False,
        "submitted_by": user["id"],
        "submitted_by_role": user["role"],
        "submitted_by_name": user.get("name"),
        "status": "pending" if is_teacher_request else "approved",
        "approved_by": None if is_teacher_request else user["id"],
        "approved_at": None if is_teacher_request else utc_now(),
        "paid_at": None,
        "note": None,
        "created_at": utc_now(),
    }
    await tdb.expenses.insert_one(doc)
    await log_action(
        user["id"], user["role"], user["school_id"],
        "submit" if is_teacher_request else "record", "expense", doc["id"],
        {"category": payload.category, "amount": payload.amount},
    )
    return clean_doc(doc)


@router.get("")
async def list_expenses(
    status: Optional[ExpenseStatus] = None,
    category: Optional[ExpenseCategory] = None,
    submitted_by: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    tdb = await tenant_db(user["school_id"])
    flt: dict = {"school_id": user["school_id"]}
    if user["role"] == "teacher":
        # Teachers see only their own submissions
        flt["submitted_by"] = user["id"]
    elif user["role"] not in ("school_admin", "accounts", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if status:
        flt["status"] = status
    if category:
        flt["category"] = category
    if submitted_by and user["role"] in ("school_admin", "accounts", "platform_admin"):
        flt["submitted_by"] = submitted_by
    return await tdb.expenses.find(flt, {"_id": 0}).sort("created_at", -1).to_list(2000)


@router.post("/{expense_id}/decide")
async def decide_expense(expense_id: str, payload: ExpenseDecide,
                          user: dict = Depends(require_roles("school_admin", "accounts"))):
    tdb = await tenant_db(user["school_id"])
    e = await tdb.expenses.find_one({"id": expense_id, "school_id": user["school_id"]}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.decision == "approve":
        if e["status"] not in ("pending",):
            raise HTTPException(status_code=400, detail=f"Only pending expenses can be approved (current: {e['status']})")
        new_status = "approved"
    elif payload.decision == "reject":
        if e["status"] not in ("pending",):
            raise HTTPException(status_code=400, detail=f"Only pending expenses can be rejected (current: {e['status']})")
        new_status = "rejected"
    elif payload.decision == "mark_paid":
        if e["status"] != "approved":
            raise HTTPException(status_code=400, detail="Only approved expenses can be marked paid")
        new_status = "paid"
    else:
        raise HTTPException(status_code=400, detail="Invalid decision")

    update = {
        "status": new_status,
        "note": payload.note,
        "approved_by": user["id"],
        "approved_at": utc_now() if new_status in ("approved", "rejected") else e.get("approved_at"),
        "paid_at": utc_now() if new_status == "paid" else e.get("paid_at"),
    }
    await tdb.expenses.update_one({"id": expense_id}, {"$set": update})
    await log_action(user["id"], user["role"], user["school_id"], f"expense_{payload.decision}", "expense", expense_id, update)
    return {"ok": True, "status": new_status}


@router.get("/summary")
async def expense_summary(month: Optional[str] = None, user: dict = Depends(require_roles("school_admin", "accounts", "platform_admin"))):
    """Totals by category + status, plus monthly trend."""
    tdb = await tenant_db(user["school_id"])
    match: dict = {"school_id": user["school_id"]}
    if month:  # YYYY-MM
        match["$expr"] = {
            "$eq": [{"$substr": ["$created_at", 0, 7]}, month],
        }
    by_status_pipe = [
        {"$match": match},
        {"$group": {"_id": "$status", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}},
    ]
    by_category_pipe = [
        {"$match": {**match, "status": {"$in": ["approved", "paid"]}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}, "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}},
    ]
    pending_reimburse_pipe = [
        {"$match": {**match, "status": "pending", "submitted_by_role": "teacher"}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "total": {"$sum": "$amount"}}},
    ]
    by_status = await tdb.expenses.aggregate(by_status_pipe).to_list(20)
    by_category = await tdb.expenses.aggregate(by_category_pipe).to_list(50)
    pending = await tdb.expenses.aggregate(pending_reimburse_pipe).to_list(1)
    total_approved = sum(b["total"] for b in by_status if b["_id"] in ("approved", "paid"))

    # ---- Monthly salary outflow (teachers + accounts from master users,
    #      other staff from per-school staff collection). Surfaced here so
    #      the school admin's expenses dashboard reflects ALL recurring
    #      spend, not just one-off reimbursements.
    from core.db import get_db
    mdb = get_db()
    user_pipe = [
        {"$match": {"school_id": user["school_id"], "is_active": True,
                     "monthly_salary": {"$gt": 0}, "role": {"$in": ["teacher", "accounts"]}}},
        {"$group": {"_id": "$role", "total": {"$sum": "$monthly_salary"}, "count": {"$sum": 1}}},
    ]
    staff_pipe = [
        {"$match": {"school_id": user["school_id"], "is_active": True,
                     "monthly_salary": {"$gt": 0}}},
        {"$group": {"_id": "$role", "total": {"$sum": "$monthly_salary"}, "count": {"$sum": 1}}},
    ]
    user_rows = await mdb.users.aggregate(user_pipe).to_list(10)
    staff_rows = await tdb.staff.aggregate(staff_pipe).to_list(20)
    by_role: dict[str, dict] = {}
    for r in user_rows + staff_rows:
        by_role[r["_id"]] = {"total": r["total"], "count": r["count"]}
    salaries_total = sum(v["total"] for v in by_role.values())
    salaries_headcount = sum(v["count"] for v in by_role.values())

    return {
        "by_status": {b["_id"]: {"count": b["count"], "total": b["total"]} for b in by_status},
        "by_category": [{"category": b["_id"], "count": b["count"], "total": b["total"]} for b in by_category],
        "pending_teacher_reimbursements": pending[0] if pending else {"count": 0, "total": 0},
        "total_spent": total_approved,
        "salaries": {
            "monthly_total": salaries_total,
            "headcount": salaries_headcount,
            "by_role": by_role,
        },
    }
