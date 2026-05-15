"""Per-child subscription billing.

Pricing (per active student):
- Monthly: ₹30
- Yearly:  ₹300 (≈ 16% discount vs ₹360)

Workflow:
- School Admin views quote at GET /subscriptions/my (includes student count + amounts)
- School Admin submits POST /subscriptions/payments  with billing_cycle and optional payment_reference
  → status = "pending_confirmation"
- Platform Super Admin lists pending via GET /subscriptions/payments
- Platform Super Admin approves via POST /subscriptions/payments/{id}/confirm
  → school.subscription becomes "active", valid_until set
- Platform Super Admin can reject via POST /subscriptions/payments/{id}/reject
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now
from core.audit import log_action

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

# Per-child pricing (INR)
PRICE_PER_CHILD_MONTHLY = 30
PRICE_PER_CHILD_YEARLY = 300


class PaymentRequest(BaseModel):
    billing_cycle: str = Field(..., pattern="^(monthly|yearly)$")
    payment_reference: str | None = None  # UPI/UTR/bank ref
    payment_mode: str | None = "upi"  # upi/bank_transfer/cash/other
    note: str | None = None


# ----------------- pricing & quotes -----------------

def _calc(student_count: int, cycle: str) -> dict:
    rate = PRICE_PER_CHILD_MONTHLY if cycle == "monthly" else PRICE_PER_CHILD_YEARLY
    amount = student_count * rate
    return {"billing_cycle": cycle, "rate_per_child": rate, "students": student_count, "amount": amount}


async def _quote_for_school(db, school_id: str) -> dict:
    from core.db import tenant_db
    tdb = await tenant_db(school_id)
    students = await tdb.students.count_documents({"school_id": school_id, "status": "active"})
    monthly = _calc(students, "monthly")
    yearly = _calc(students, "yearly")
    yearly_undiscounted = students * PRICE_PER_CHILD_MONTHLY * 12
    yearly["savings_vs_monthly"] = max(yearly_undiscounted - yearly["amount"], 0)
    return {
        "school_id": school_id,
        "students_active": students,
        "pricing": {
            "per_child_monthly": PRICE_PER_CHILD_MONTHLY,
            "per_child_yearly": PRICE_PER_CHILD_YEARLY,
        },
        "monthly": monthly,
        "yearly": yearly,
    }


@router.get("/pricing")
async def pricing(_: dict = Depends(get_current_user)):
    return {
        "per_child_monthly": PRICE_PER_CHILD_MONTHLY,
        "per_child_yearly": PRICE_PER_CHILD_YEARLY,
        "currency": "INR",
    }


@router.get("/my")
async def my_subscription(user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    school = await db.schools.find_one({"id": user["school_id"]}, {"_id": 0})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    quote = await _quote_for_school(db, school["id"])
    # latest pending request (if any)
    pending = await db.subscription_payments.find_one(
        {"school_id": school["id"], "status": "pending_confirmation"},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    return {
        "school": {"id": school["id"], "name": school["name"], "code": school.get("code")},
        "subscription": school.get("subscription") or {"status": "none"},
        "quote": quote,
        "pending_payment": pending,
    }


@router.get("/quote/{school_id}")
async def quote_for_school(school_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "platform_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    school = await db.schools.find_one({"id": school_id})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return await _quote_for_school(db, school_id)


# ----------------- payments -----------------

@router.post("/payments")
async def submit_payment(payload: PaymentRequest, user: dict = Depends(require_roles("school_admin"))):
    db = get_db()
    school_id = user["school_id"]
    school = await db.schools.find_one({"id": school_id})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    # Block duplicate pending requests
    existing = await db.subscription_payments.find_one(
        {"school_id": school_id, "status": "pending_confirmation"}
    )
    if existing:
        raise HTTPException(status_code=400, detail="A payment is already pending confirmation. Please wait for the Platform Super Admin to confirm it.")

    quote = await _quote_for_school(db, school_id)
    line = quote["monthly"] if payload.billing_cycle == "monthly" else quote["yearly"]
    doc = {
        "id": new_id(),
        "school_id": school_id,
        "school_name": school["name"],
        "school_code": school.get("code"),
        "billing_cycle": payload.billing_cycle,
        "rate_per_child": line["rate_per_child"],
        "students_count": line["students"],
        "amount": line["amount"],
        "currency": "INR",
        "payment_mode": payload.payment_mode or "upi",
        "payment_reference": payload.payment_reference,
        "note": payload.note,
        "submitted_by": user["id"],
        "submitted_by_email": user["email"],
        "status": "pending_confirmation",
        "created_at": utc_now(),
    }
    await db.subscription_payments.insert_one(doc)
    await log_action(user["id"], user["role"], school_id, "submit_subscription_payment",
                     "subscription_payment", doc["id"],
                     meta={"amount": doc["amount"], "cycle": doc["billing_cycle"]})
    doc.pop("_id", None)
    return doc


@router.get("/payments")
async def list_payments(status: str | None = None, user: dict = Depends(get_current_user)):
    """Platform Super Admin: sees all. School Admin: sees own school only."""
    db = get_db()
    q: dict = {}
    if user["role"] == "school_admin":
        q["school_id"] = user["school_id"]
    elif user["role"] != "platform_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if status:
        q["status"] = status
    docs = await db.subscription_payments.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return docs


@router.post("/payments/{payment_id}/confirm")
async def confirm_payment(payment_id: str, user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    pay = await db.subscription_payments.find_one({"id": payment_id})
    if not pay:
        raise HTTPException(status_code=404, detail="Payment not found")
    if pay["status"] != "pending_confirmation":
        raise HTTPException(status_code=400, detail=f"Payment already {pay['status']}")

    # Compute new validity window. If currently active and not yet expired, extend from valid_until.
    school = await db.schools.find_one({"id": pay["school_id"]}) or {}
    current_sub = school.get("subscription") or {}
    now = utc_now()
    start = now
    if current_sub.get("status") == "active" and current_sub.get("valid_until"):
        try:
            cur_end = current_sub["valid_until"]
            if hasattr(cur_end, "tzinfo") and cur_end > now:
                start = cur_end
        except Exception:
            start = now
    days = 30 if pay["billing_cycle"] == "monthly" else 365
    valid_until = start + timedelta(days=days)

    sub = {
        "status": "active",
        "billing_cycle": pay["billing_cycle"],
        "rate_per_child": pay["rate_per_child"],
        "students_count": pay["students_count"],
        "amount": pay["amount"],
        "valid_from": now,
        "valid_until": valid_until,
        "last_payment_id": pay["id"],
        "confirmed_by": user["id"],
        "confirmed_at": now,
    }
    await db.schools.update_one({"id": pay["school_id"]}, {"$set": {"subscription": sub}})
    await db.subscription_payments.update_one(
        {"id": payment_id},
        {"$set": {
            "status": "confirmed",
            "confirmed_at": now,
            "confirmed_by": user["id"],
            "valid_from": now,
            "valid_until": valid_until,
        }},
    )
    await log_action(user["id"], user["role"], pay["school_id"], "confirm_subscription_payment",
                     "subscription_payment", payment_id,
                     meta={"amount": pay["amount"], "cycle": pay["billing_cycle"]})
    return {"ok": True, "subscription": {**sub, "valid_until": valid_until.isoformat(), "valid_from": now.isoformat()}}


@router.post("/payments/{payment_id}/reject")
async def reject_payment(payment_id: str, user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    pay = await db.subscription_payments.find_one({"id": payment_id})
    if not pay:
        raise HTTPException(status_code=404, detail="Payment not found")
    if pay["status"] != "pending_confirmation":
        raise HTTPException(status_code=400, detail=f"Payment already {pay['status']}")
    await db.subscription_payments.update_one(
        {"id": payment_id},
        {"$set": {"status": "rejected", "rejected_at": utc_now(), "rejected_by": user["id"]}},
    )
    await log_action(user["id"], user["role"], pay["school_id"], "reject_subscription_payment",
                     "subscription_payment", payment_id, meta={"amount": pay["amount"]})
    return {"ok": True}


class AdminSetValidUntil(BaseModel):
    school_id: str
    valid_until: str  # ISO-8601 datetime (e.g. "2026-06-01T00:00:00Z")
    reason: str | None = None


@router.post("/admin/set-valid-until")
async def admin_set_valid_until(payload: AdminSetValidUntil, user: dict = Depends(require_roles("platform_admin"))):
    """Platform admin override: directly set a school's subscription.valid_until.
    Used for goodwill extensions, refunds, or to test the renewal-nudge cron."""
    from datetime import datetime as _dt
    db = get_db()
    school = await db.schools.find_one({"id": payload.school_id})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    try:
        vu = _dt.fromisoformat(payload.valid_until.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="valid_until must be ISO-8601 (e.g. 2026-06-01T00:00:00Z)")
    sub = school.get("subscription") or {}
    sub.update({
        "status": "active",
        "valid_until": vu,
        "billing_cycle": sub.get("billing_cycle") or "monthly",
        "amount": sub.get("amount") or 0,
    })
    await db.schools.update_one({"id": payload.school_id}, {"$set": {"subscription": sub}})
    await log_action(user["id"], user["role"], payload.school_id, "admin_set_valid_until",
                     "subscription", payload.school_id,
                     meta={"valid_until": vu.isoformat(), "reason": payload.reason})
    return {"ok": True, "school_id": payload.school_id, "valid_until": vu.isoformat()}


# ----------------- usage stats (used by older overview cards) -----------------

@router.get("/usage/{school_id}")
async def usage(school_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "platform_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    from core.db import tenant_db
    tdb = await tenant_db(school_id)
    s = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    students = await tdb.students.count_documents({"school_id": school_id, "status": "active"})
    teachers = await db.users.count_documents({"school_id": school_id, "role": "teacher", "is_active": True})
    notifs = await db.notifications.count_documents({"school_id": school_id})
    return {
        "school": s,
        "usage": {"students": students, "teachers": teachers, "notifications_sent": notifs},
    }


# ----------------- manual renewal nudge (admin trigger) -----------------

@router.post("/nudge-renewals")
async def run_renewal_nudge(user: dict = Depends(require_roles("platform_admin"))):
    """Manually trigger the 'subscription expiring in 7 days' nudge for all eligible schools.
    Useful for testing without waiting for the daily cron (also runs daily @ 08:00 IST when
    ENABLE_DIGEST_SCHEDULER=true). Respects the 24h cooldown."""
    from core.scheduler import _run_subscription_nudges
    sent = await _run_subscription_nudges()
    return {"ok": True, "messages_queued": sent}
