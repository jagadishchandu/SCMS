"""Per-child subscription billing.

Pricing comes from environment variables so it stays in sync across docker-compose,
the backend container, and every API consumer:
    SUBSCRIPTION_PRICE_PER_CHILD_MONTHLY   (default 30)
    SUBSCRIPTION_PRICE_PER_CHILD_YEARLY    (default 300)
    SUBSCRIPTION_MONTHLY_DAYS              (default 30)
    SUBSCRIPTION_YEARLY_DAYS               (default 365)
    SUBSCRIPTION_CURRENCY                  (default INR)

Workflow:
- School Admin views quote at GET /subscriptions/my (includes student count + amounts)
- School Admin submits POST /subscriptions/payments  with billing_cycle and optional payment_reference
  → status = "pending_confirmation"
- Platform Super Admin lists pending via GET /subscriptions/payments
- Platform Super Admin approves via POST /subscriptions/payments/{id}/confirm
  → school.subscription becomes "active", valid_until set
- Platform Super Admin can reject via POST /subscriptions/payments/{id}/reject
"""
import os
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now
from core.audit import log_action

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# Per-child pricing pulled from env at call-time so a docker-compose / .env update
# reflects everywhere (pricing endpoint, quote calculation, validity window) without
# requiring a code change. Defaults preserve the legacy ₹30 / ₹300 prices.
def _monthly_price() -> int:
    return int(os.environ.get("SUBSCRIPTION_PRICE_PER_CHILD_MONTHLY", "30"))


def _yearly_price() -> int:
    return int(os.environ.get("SUBSCRIPTION_PRICE_PER_CHILD_YEARLY", "300"))


def _monthly_days() -> int:
    return int(os.environ.get("SUBSCRIPTION_MONTHLY_DAYS", "30"))


def _yearly_days() -> int:
    return int(os.environ.get("SUBSCRIPTION_YEARLY_DAYS", "365"))


def _currency() -> str:
    return os.environ.get("SUBSCRIPTION_CURRENCY", "INR").strip() or "INR"


def _yearly_nudge_threshold() -> int:
    """Min billed-children count at which we suggest switching from monthly to yearly."""
    try:
        return int(os.environ.get("SUBSCRIPTION_YEARLY_NUDGE_THRESHOLD", "50"))
    except ValueError:
        return 50


class PaymentRequest(BaseModel):
    billing_cycle: str = Field(..., pattern="^(monthly|yearly)$")
    payment_reference: str | None = None  # UPI/UTR/bank ref
    payment_mode: str | None = "upi"  # upi/bank_transfer/cash/other
    note: str | None = None


class ApprovalRequest(BaseModel):
    requested_children_count: int = Field(..., ge=1, le=100000)
    note: str | None = None


class ApprovalDecide(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    approved_children_count: int | None = Field(default=None, ge=1, le=100000)
    note: str | None = None


# ----------------- pricing & quotes -----------------

def _calc(student_count: int, cycle: str) -> dict:
    rate = _monthly_price() if cycle == "monthly" else _yearly_price()
    amount = student_count * rate
    return {"billing_cycle": cycle, "rate_per_child": rate, "students": student_count, "amount": amount}


async def _quote_for_school(db, school_id: str) -> dict:
    """Build the live quote for a school.

    Billing basis: `billed_children = max(approved_children_count,
    requested_children_count, actual_active_students)`. This way, the moment a
    school admin enters their planned children count (via the approval-request
    form) the charge updates — even before any students are added to the system.
    """
    from core.db import tenant_db
    tdb = await tenant_db(school_id)
    students = await tdb.students.count_documents({"school_id": school_id, "status": "active"})

    # Pull approval doc so we can use the requested/approved count as the billable count.
    school_doc = await db.schools.find_one({"id": school_id}, {"_id": 0, "subscription_approval": 1})
    approval = (school_doc or {}).get("subscription_approval") or {}
    approved_count = approval.get("approved_children_count")
    requested_count = approval.get("requested_children_count")
    capacity = approved_count or requested_count or 0
    billed_children = max(int(capacity or 0), int(students or 0))

    monthly = _calc(billed_children, "monthly")
    yearly = _calc(billed_children, "yearly")
    yearly_undiscounted = billed_children * _monthly_price() * 12
    yearly["savings_vs_monthly"] = max(yearly_undiscounted - yearly["amount"], 0)
    return {
        "school_id": school_id,
        "students_active": students,
        "requested_children_count": requested_count,
        "approved_children_count": approved_count,
        "billed_children": billed_children,
        "pricing": {
            "per_child_monthly": _monthly_price(),
            "per_child_yearly": _yearly_price(),
            "currency": _currency(),
        },
        "monthly": monthly,
        "yearly": yearly,
    }


@router.get("/pricing")
async def pricing(_: dict = Depends(get_current_user)):
    return {
        "per_child_monthly": _monthly_price(),
        "per_child_yearly": _yearly_price(),
        "monthly_days": _monthly_days(),
        "yearly_days": _yearly_days(),
        "currency": _currency(),
        "yearly_nudge_threshold": _yearly_nudge_threshold(),
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
    approval = school.get("subscription_approval") or {"status": "not_started"}
    return {
        "school": {"id": school["id"], "name": school["name"], "code": school.get("code")},
        "subscription": school.get("subscription") or {"status": "none"},
        "subscription_approval": approval,
        "quote": quote,
        "pending_payment": pending,
    }


# ----------------- approval workflow -----------------

@router.post("/approval-request")
async def submit_approval_request(payload: ApprovalRequest, user: dict = Depends(require_roles("school_admin"))):
    """School admin submits an approval request with the desired children count.
    Until the Platform Super Admin approves it, the school is locked out of all
    operational routes (the SubscriptionGuard middleware enforces this).
    """
    db = get_db()
    school = await db.schools.find_one({"id": user["school_id"]})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    now = utc_now()
    existing = school.get("subscription_approval") or {}
    current_status = existing.get("status") or "not_started"

    # If the school is already approved, treat this as an edit — keep status='approved',
    # update the requested count, and log an edit event. Compliance view surfaces variance.
    if current_status == "approved":
        update = {
            "subscription_approval.requested_children_count": payload.requested_children_count,
            "subscription_approval.last_edited_at": now,
            "subscription_approval.last_edited_by": user["id"],
        }
        if payload.note:
            update["subscription_approval.note"] = payload.note
        await db.schools.update_one({"id": user["school_id"]}, {"$set": update})
        await log_action(
            user["id"], user["role"], user["school_id"], "edit_approval_request",
            "subscription_approval", user["school_id"],
            meta={"requested_children_count": payload.requested_children_count,
                  "prev_requested": existing.get("requested_children_count")},
        )
        refreshed = (await db.schools.find_one({"id": user["school_id"]}, {"_id": 0})).get("subscription_approval") or {}
        for k in ("requested_at", "decided_at", "last_edited_at"):
            v = refreshed.get(k)
            if hasattr(v, "isoformat"):
                refreshed[k] = v.isoformat()
        return {"ok": True, "edited": True, "subscription_approval": refreshed}

    # Otherwise (not_started / pending / rejected) — submit/resubmit as a fresh request.
    approval = {
        "status": "pending",
        "requested_children_count": payload.requested_children_count,
        "requested_at": now,
        "requested_by": user["id"],
        "requested_by_email": user["email"],
        "note": payload.note,
        "school_id": user["school_id"],
        "school_name": school["name"],
        "school_code": school.get("code"),
    }
    await db.schools.update_one(
        {"id": user["school_id"]}, {"$set": {"subscription_approval": approval}},
    )
    await log_action(
        user["id"], user["role"], user["school_id"], "submit_approval_request",
        "subscription_approval", user["school_id"],
        meta={"requested_children_count": payload.requested_children_count},
    )
    approval.pop("_id", None)
    if isinstance(approval.get("requested_at"), object):
        approval["requested_at"] = now.isoformat()
    return {"ok": True, "subscription_approval": approval}


@router.get("/approval-requests")
async def list_approval_requests(status: str | None = None,
                                  user: dict = Depends(require_roles("platform_admin"))):
    """Platform Super Admin: list school approval requests (default: pending only)."""
    db = get_db()
    flt: dict = {}
    if status:
        flt["subscription_approval.status"] = status
    else:
        flt["subscription_approval.status"] = "pending"
    cursor = db.schools.find(
        flt, {"_id": 0, "id": 1, "name": 1, "code": 1, "subscription_approval": 1, "subscription": 1},
    )
    rows = []
    async for s in cursor:
        appr = s.get("subscription_approval") or {}
        # Compose datetime → iso
        for k in ("requested_at", "decided_at"):
            v = appr.get(k)
            if hasattr(v, "isoformat"):
                appr[k] = v.isoformat()
        rows.append({
            "school_id": s["id"],
            "school_name": s["name"],
            "school_code": s.get("code"),
            "approval": appr,
        })
    return rows


@router.post("/approval/{school_id}/decide")
async def decide_approval_request(school_id: str, payload: ApprovalDecide,
                                    user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    school = await db.schools.find_one({"id": school_id})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    approval = school.get("subscription_approval") or {}
    if approval.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"No pending approval request (current: {approval.get('status', 'not_started')})")
    now = utc_now()
    new_status = "approved" if payload.decision == "approve" else "rejected"
    approved_count = payload.approved_children_count or approval.get("requested_children_count")
    update = {
        "subscription_approval.status": new_status,
        "subscription_approval.decided_at": now,
        "subscription_approval.decided_by": user["id"],
        "subscription_approval.decided_by_email": user["email"],
        "subscription_approval.note": payload.note,
    }
    if new_status == "approved":
        update["subscription_approval.approved_children_count"] = approved_count
    await db.schools.update_one({"id": school_id}, {"$set": update})
    await log_action(
        user["id"], user["role"], school_id, f"approval_{new_status}",
        "subscription_approval", school_id,
        meta={"approved_children_count": approved_count if new_status == "approved" else None,
              "requested_children_count": approval.get("requested_children_count")},
    )
    return {"ok": True, "status": new_status, "approved_children_count": approved_count if new_status == "approved" else None}


# ----------------- compliance view (platform admin) -----------------

def _compute_compliance(approval: dict, actual: int) -> str:
    """Return one of: no_request, compliant, over_capacity, pending_review, rejected."""
    status = (approval or {}).get("status") or "not_started"
    if status == "not_started":
        return "no_request"
    if status == "rejected":
        return "rejected"
    if status == "pending":
        return "pending_review"
    # approved
    cap = approval.get("approved_children_count") or approval.get("requested_children_count")
    if cap is None:
        return "compliant"  # legacy auto-approved with no cap
    return "over_capacity" if actual > cap else "compliant"


@router.get("/compliance")
async def compliance_view(filter: str | None = None,
                           user: dict = Depends(require_roles("platform_admin"))):
    """View-only compliance report for Platform Super Admin.

    For each school, compares the school admin's requested/approved children count
    against the live actual student count in their tenant DB. View-only — no edits.

    Optional `filter`: compliant | over_capacity | pending_review | rejected | no_request
    """
    from core.db import tenant_db
    db = get_db()
    schools = await db.schools.find({}, {"_id": 0}).sort("name", 1).to_list(2000)
    rows = []
    for s in schools:
        tdb = await tenant_db(s["id"])
        actual = await tdb.students.count_documents({"status": "active"})
        approval = s.get("subscription_approval") or {}
        requested = approval.get("requested_children_count")
        approved = approval.get("approved_children_count")
        status = approval.get("status") or "not_started"
        compliance = _compute_compliance(approval, actual)
        cap = approved or requested
        variance = (actual - cap) if cap is not None else None
        # Convert datetime → iso
        approval_view = dict(approval)
        for k in ("requested_at", "decided_at", "last_edited_at"):
            v = approval_view.get(k)
            if hasattr(v, "isoformat"):
                approval_view[k] = v.isoformat()
        rows.append({
            "school_id": s["id"],
            "school_name": s["name"],
            "school_code": s.get("code"),
            "approval_status": status,
            "requested_children_count": requested,
            "approved_children_count": approved,
            "actual_active_students": actual,
            "variance": variance,
            "compliance": compliance,
            "approval_meta": approval_view,
        })
    if filter:
        rows = [r for r in rows if r["compliance"] == filter]
    # Summary buckets for KPI tiles
    summary = {"compliant": 0, "over_capacity": 0, "pending_review": 0, "rejected": 0, "no_request": 0}
    for r in rows:
        summary[r["compliance"]] = summary.get(r["compliance"], 0) + 1
    return {"rows": rows, "summary": summary, "total": len(rows)}


@router.post("/compliance/run-alert")
async def trigger_over_capacity_alert(user: dict = Depends(require_roles("platform_admin"))):
    """Manually trigger the over-capacity alert (also runs as a daily cron @ 09:00 IST)."""
    from core.scheduler import _run_over_capacity_alerts
    sent = await _run_over_capacity_alerts()
    return {"ok": True, "messages_queued": sent}



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
    days = _monthly_days() if pay["billing_cycle"] == "monthly" else _yearly_days()
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

@router.get("/active")
async def list_active_subscriptions(user: dict = Depends(require_roles("platform_admin"))):
    """Platform admin overview of every school's active subscription:
    school identity, cycle, amount, valid_until, days_left, and the timestamp
    of the most recent renewal nudge (so the admin can see who's been notified)."""
    from datetime import datetime as _dt
    db = get_db()
    schools = await db.schools.find({}, {"_id": 0}).sort("name", 1).to_list(2000)
    now = utc_now()
    rows = []
    for s in schools:
        sub = s.get("subscription") or {}
        vu = sub.get("valid_until")
        days_left = None
        valid_until_iso = None
        is_expired = False
        if vu:
            try:
                vu_dt = vu if isinstance(vu, _dt) else _dt.fromisoformat(str(vu).replace("Z", "+00:00"))
                if vu_dt.tzinfo is None:
                    from datetime import timezone as _tz
                    vu_dt = vu_dt.replace(tzinfo=_tz.utc)
                days_left = (vu_dt.date() - now.date()).days
                is_expired = vu_dt < now
                valid_until_iso = vu_dt.isoformat()
            except Exception:
                pass
        # last nudge sent for this school (any in-app or out-of-band renewal nudge)
        last_nudge = await db.notifications.find_one(
            {"school_id": s["id"], "template": {"$in": [
                "subscription_renewal", "subscription_renewal_manual",
                "subscription_renewal_t7", "subscription_renewal_t1",
            ]}},
            {"_id": 0, "created_at": 1, "channel": 1, "template": 1},
            sort=[("created_at", -1)],
        )
        rows.append({
            "school_id": s["id"],
            "school_name": s["name"],
            "school_code": s.get("code"),
            "status": sub.get("status") or "none",
            "billing_cycle": sub.get("billing_cycle"),
            "amount": sub.get("amount"),
            "students_count": sub.get("students_count"),
            "valid_from": (sub.get("valid_from").isoformat() if isinstance(sub.get("valid_from"), _dt) else sub.get("valid_from")),
            "valid_until": valid_until_iso,
            "days_left": days_left,
            "is_expired": is_expired,
            "last_nudge": last_nudge,
        })
    # Summary
    summary = {
        "active": sum(1 for r in rows if r["status"] == "active" and not r["is_expired"]),
        "expiring_soon": sum(1 for r in rows if r["status"] == "active" and r["days_left"] is not None and 0 <= r["days_left"] <= 7),
        "expired": sum(1 for r in rows if r["is_expired"]),
        "no_subscription": sum(1 for r in rows if r["status"] != "active"),
    }
    return {"rows": rows, "summary": summary, "total": len(rows)}


class NotifySchoolPayload(BaseModel):
    message: str | None = None  # optional custom message; default is auto-generated from days_left


@router.post("/notify/{school_id}")
async def notify_school_renewal(school_id: str, payload: NotifySchoolPayload,
                                 user: dict = Depends(require_roles("platform_admin"))):
    """Platform Super Admin → in-app nudge to the school's admin. The notification
    appears in the school admin's `/school/notifications` page (channel='in_app').
    """
    from datetime import datetime as _dt
    from core.notify import queue_notification

    db = get_db()
    school = await db.schools.find_one({"id": school_id})
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    sub = school.get("subscription") or {}
    vu = sub.get("valid_until")
    days_left = None
    valid_until_str = "—"
    if vu:
        try:
            vu_dt = vu if isinstance(vu, _dt) else _dt.fromisoformat(str(vu).replace("Z", "+00:00"))
            from datetime import timezone as _tz
            if vu_dt.tzinfo is None:
                vu_dt = vu_dt.replace(tzinfo=_tz.utc)
            days_left = (vu_dt.date() - utc_now().date()).days
            valid_until_str = vu_dt.date().isoformat()
        except Exception:
            pass

    if payload.message:
        body = payload.message
    elif days_left is None:
        body = "Reminder from SCMS: your school subscription is not active. Please submit a payment to keep features enabled."
    elif days_left < 0:
        body = (
            f"Reminder from SCMS: your subscription expired on {valid_until_str} "
            f"({abs(days_left)} day(s) ago). Please renew immediately to avoid feature lockout."
        )
    else:
        body = (
            f"Reminder from SCMS: your subscription expires in {days_left} day(s) "
            f"(on {valid_until_str}). Please renew to keep features active."
        )

    # Notify every active school admin for this school (usually one, but supports many).
    admins = await db.users.find(
        {"school_id": school_id, "role": "school_admin", "is_active": True},
        {"_id": 0},
    ).to_list(50)
    if not admins:
        raise HTTPException(status_code=400, detail="No active school admin to notify")

    notified = 0
    for admin in admins:
        await queue_notification(
            school_id=school_id,
            recipient_type="school_admin",
            recipient_id=admin["id"],
            phone=None,
            channel="in_app",
            template="subscription_renewal_manual",
            message=body,
            context={
                "valid_until": valid_until_str,
                "days_left": days_left,
                "source": "platform_admin_manual",
                "sent_by": user["email"],
            },
        )
        notified += 1

    await log_action(
        user["id"], user["role"], school_id, "notify_school_renewal",
        "subscription", school_id,
        meta={"days_left": days_left, "valid_until": valid_until_str, "notified": notified},
    )
    return {"ok": True, "notified": notified, "message": body, "days_left": days_left,
            "valid_until": valid_until_str}


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
