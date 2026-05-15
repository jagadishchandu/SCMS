"""Fees: structure, assignment, payments, dues."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import FeeStructureCreate, FeePaymentCreate
from core.auth import require_roles, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now
from core.notify import queue_notification

router = APIRouter(prefix="/fees", tags=["fees"])


@router.get("/structures")
async def list_structures(user: dict = Depends(get_current_user)):
    db = get_db()
    return await db.fee_structures.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(500)


@router.post("/structures")
async def create_structure(payload: FeeStructureCreate, user: dict = Depends(require_roles("school_admin", "accounts"))):
    db = get_db()
    total = sum(it.get("amount", 0) for it in payload.items)
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "class_id": payload.class_id,
        "name": payload.name,
        "items": payload.items,
        "total": total,
        "due_date": payload.due_date,
        "created_at": utc_now(),
    }
    await db.fee_structures.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/structures/{structure_id}/assign")
async def assign_structure(structure_id: str, user: dict = Depends(require_roles("school_admin", "accounts"))):
    """Assign this fee structure to all students in that class — creates dues."""
    db = get_db()
    struct = await db.fee_structures.find_one({"id": structure_id, "school_id": user["school_id"]})
    if not struct:
        raise HTTPException(status_code=404, detail="Not found")
    students = await db.students.find({"school_id": user["school_id"], "class_id": struct["class_id"]}, {"_id": 0}).to_list(5000)
    created = 0
    for s in students:
        existing = await db.fees.find_one({"school_id": user["school_id"], "student_id": s["id"], "structure_id": structure_id})
        if existing:
            continue
        fee_doc = {
            "id": new_id(),
            "school_id": user["school_id"],
            "structure_id": structure_id,
            "student_id": s["id"],
            "class_id": struct["class_id"],
            "name": struct["name"],
            "total": struct["total"],
            "paid": 0.0,
            "due": struct["total"],
            "due_date": struct["due_date"],
            "status": "pending",
            "created_at": utc_now(),
        }
        await db.fees.insert_one(fee_doc)
        created += 1
        await queue_notification(
            user["school_id"], "parent", s.get("parent_user_id"),
            s.get("parent", {}).get("whatsapp") or s.get("parent", {}).get("phone"),
            "whatsapp", "fee_invoice",
            f"Fee invoice for {struct['name']} ({struct['total']}) generated for {s['name']}. Due {struct['due_date']}.",
            context={"fee_id": fee_doc["id"]},
        )
    return {"assigned": created}


@router.get("")
async def list_fees(student_id: str | None = None, status: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {"school_id": user["school_id"]}
    if user["role"] == "parent":
        kids = await db.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(50)
        flt["student_id"] = {"$in": [k["id"] for k in kids]}
    if user["role"] == "teacher":
        raise HTTPException(status_code=403, detail="Fee data not accessible to teachers")
    if student_id:
        flt["student_id"] = student_id
    if status:
        flt["status"] = status
    return await db.fees.find(flt, {"_id": 0}).to_list(5000)


@router.post("/payments")
async def record_payment(payload: FeePaymentCreate, user: dict = Depends(require_roles("school_admin", "accounts"))):
    db = get_db()
    fee = await db.fees.find_one({"id": payload.fee_id, "school_id": user["school_id"], "student_id": payload.student_id})
    if not fee:
        raise HTTPException(status_code=404, detail="Fee not found")
    new_paid = fee["paid"] + payload.amount
    new_due = max(fee["total"] - new_paid, 0)
    status = "paid" if new_due <= 0 else ("partial" if new_paid > 0 else "pending")
    receipt_no = f"RCPT-{new_id()[:8].upper()}"
    payment_doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "fee_id": payload.fee_id,
        "student_id": payload.student_id,
        "amount": payload.amount,
        "mode": payload.mode,
        "note": payload.note,
        "receipt_no": receipt_no,
        "recorded_by": user["id"],
        "created_at": utc_now(),
    }
    await db.fee_payments.insert_one(payment_doc)
    await db.fees.update_one({"id": payload.fee_id}, {"$set": {"paid": new_paid, "due": new_due, "status": status}})

    # notify parent
    s = await db.students.find_one({"id": payload.student_id}, {"_id": 0})
    if s:
        await queue_notification(
            user["school_id"], "parent", s.get("parent_user_id"),
            s.get("parent", {}).get("whatsapp") or s.get("parent", {}).get("phone"),
            "whatsapp", "payment_received",
            f"Payment of {payload.amount} received for {s['name']}. Receipt: {receipt_no}.",
            context={"fee_id": payload.fee_id, "receipt_no": receipt_no},
        )
    payment_doc.pop("_id", None)
    return payment_doc


@router.get("/payments")
async def list_payments(student_id: str | None = None, user: dict = Depends(get_current_user)):
    db = get_db()
    flt = {"school_id": user["school_id"]}
    if user["role"] == "parent":
        kids = await db.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(50)
        flt["student_id"] = {"$in": [k["id"] for k in kids]}
    if student_id:
        flt["student_id"] = student_id
    return await db.fee_payments.find(flt, {"_id": 0}).sort("created_at", -1).to_list(1000)
