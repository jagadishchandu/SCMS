"""Fees: structure, assignment, payments, dues."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import FeeStructureCreate, FeePaymentCreate
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now
from core.notify import queue_notification

router = APIRouter(prefix="/fees", tags=["fees"])


@router.get("/structures")
async def list_structures(user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    return await tdb.fee_structures.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(500)


@router.post("/structures")
async def create_structure(payload: FeeStructureCreate, user: dict = Depends(require_roles("school_admin", "accounts"))):
    tdb = await tenant_db(user["school_id"])
    total = sum(it.get("amount", 0) for it in payload.items)
    section = (payload.section or "").strip().upper() or None
    # Validate section against class definition if provided
    if section:
        cls = await tdb.classes.find_one({"id": payload.class_id, "school_id": user["school_id"]})
        if not cls:
            raise HTTPException(status_code=404, detail="Class not found")
        cls_sections = [s.upper() for s in (cls.get("sections") or [])]
        if section not in cls_sections:
            raise HTTPException(status_code=400, detail=f"Section '{section}' not found in class")
    doc = {
        "id": new_id(),
        "school_id": user["school_id"],
        "class_id": payload.class_id,
        "section": section,
        "term": (payload.term or None),
        "name": payload.name,
        "items": payload.items,
        "total": total,
        "due_date": payload.due_date,
        "created_at": utc_now(),
    }
    await tdb.fee_structures.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/structures/{structure_id}/clone-to-sections")
async def clone_structure_to_sections(structure_id: str, user: dict = Depends(require_roles("school_admin", "accounts"))):
    """Clone a section-scoped fee structure to ALL other sections of the same class.

    Useful when admin defines e.g. "Grade 1 Term 1 Fees" for section A and wants
    to replicate it for sections B, C, D... in one click.

    Skips sections that already have a structure with the same (class_id, term, name).
    If the source structure was class-wide (no section), the response indicates
    nothing was cloned (because it already covers all sections).
    """
    tdb = await tenant_db(user["school_id"])
    src = await tdb.fee_structures.find_one(
        {"id": structure_id, "school_id": user["school_id"]}, {"_id": 0}
    )
    if not src:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    cls = await tdb.classes.find_one({"id": src["class_id"], "school_id": user["school_id"]})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found for this structure")

    all_sections = [s.upper() for s in (cls.get("sections") or [])]
    src_section = (src.get("section") or "").upper() or None
    if not src_section:
        return {
            "cloned": 0,
            "skipped": [],
            "message": "Source structure is class-wide (no specific section) — already covers all sections.",
        }

    target_sections = [s for s in all_sections if s != src_section]
    cloned = 0
    skipped = []
    created_ids = []
    for sec in target_sections:
        # idempotency: if a structure already exists for this class/section with same term+name, skip
        dup = await tdb.fee_structures.find_one({
            "school_id": user["school_id"],
            "class_id": src["class_id"],
            "section": sec,
            "term": src.get("term"),
            "name": src["name"],
        })
        if dup:
            skipped.append(sec)
            continue
        doc = {
            "id": new_id(),
            "school_id": user["school_id"],
            "class_id": src["class_id"],
            "section": sec,
            "term": src.get("term"),
            "name": src["name"],
            "items": src["items"],
            "total": src["total"],
            "due_date": src["due_date"],
            "created_at": utc_now(),
            "cloned_from": structure_id,
        }
        await tdb.fee_structures.insert_one(doc)
        created_ids.append(doc["id"])
        cloned += 1
    return {
        "cloned": cloned,
        "skipped": skipped,
        "target_sections": target_sections,
        "created_ids": created_ids,
    }


@router.post("/structures/{structure_id}/assign")
async def assign_structure(structure_id: str, user: dict = Depends(require_roles("school_admin", "accounts"))):
    tdb = await tenant_db(user["school_id"])
    struct = await tdb.fee_structures.find_one({"id": structure_id, "school_id": user["school_id"]})
    if not struct:
        raise HTTPException(status_code=404, detail="Not found")
    student_filter = {"school_id": user["school_id"], "class_id": struct["class_id"]}
    if struct.get("section"):
        student_filter["section"] = struct["section"]
    students = await tdb.students.find(student_filter, {"_id": 0}).to_list(5000)
    created = 0
    for s in students:
        existing = await tdb.fees.find_one({"school_id": user["school_id"], "student_id": s["id"], "structure_id": structure_id})
        if existing:
            continue
        fee_doc = {
            "id": new_id(),
            "school_id": user["school_id"],
            "structure_id": structure_id,
            "student_id": s["id"],
            "class_id": struct["class_id"],
            "section": struct.get("section") or s.get("section"),
            "term": struct.get("term"),
            "name": struct["name"],
            "total": struct["total"],
            "paid": 0.0,
            "due": struct["total"],
            "due_date": struct["due_date"],
            "status": "pending",
            "created_at": utc_now(),
        }
        await tdb.fees.insert_one(fee_doc)
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
    tdb = await tenant_db(user["school_id"])
    flt = {"school_id": user["school_id"]}
    if user["role"] == "parent":
        kids = await tdb.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(50)
        flt["student_id"] = {"$in": [k["id"] for k in kids]}
    if user["role"] == "teacher":
        raise HTTPException(status_code=403, detail="Fee data not accessible to teachers")
    if student_id:
        flt["student_id"] = student_id
    if status:
        flt["status"] = status
    return await tdb.fees.find(flt, {"_id": 0}).to_list(5000)


@router.post("/payments")
async def record_payment(payload: FeePaymentCreate, user: dict = Depends(require_roles("school_admin", "accounts"))):
    tdb = await tenant_db(user["school_id"])
    fee = await tdb.fees.find_one({"id": payload.fee_id, "school_id": user["school_id"], "student_id": payload.student_id})
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
    await tdb.fee_payments.insert_one(payment_doc)
    await tdb.fees.update_one({"id": payload.fee_id}, {"$set": {"paid": new_paid, "due": new_due, "status": status}})

    s = await tdb.students.find_one({"id": payload.student_id}, {"_id": 0})
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
    tdb = await tenant_db(user["school_id"])
    flt = {"school_id": user["school_id"]}
    if user["role"] == "parent":
        kids = await tdb.students.find({"parent_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(50)
        flt["student_id"] = {"$in": [k["id"] for k in kids]}
    if student_id:
        flt["student_id"] = student_id
    return await tdb.fee_payments.find(flt, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.get("/per-student-summary")
async def per_student_summary(
    class_id: str | None = None,
    status: str | None = None,
    q: str | None = None,
    user: dict = Depends(require_roles("school_admin", "accounts")),
):
    """One row per active student with total fee, paid amount, balance,
    percent_paid (0–100) and overall status (paid / partial / not_paid / no_fees).
    Used by the Accountant fee tracker page.
    """
    tdb = await tenant_db(user["school_id"])
    student_flt = {"school_id": user["school_id"], "status": "active"}
    if class_id:
        student_flt["class_id"] = class_id
    if q:
        student_flt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"uid": {"$regex": q, "$options": "i"}},
        ]
    students = await tdb.students.find(student_flt, {"_id": 0}).sort("name", 1).to_list(10000)

    # Pre-aggregate fees per student (one DB call instead of N).
    agg = tdb.fees.aggregate([
        {"$match": {"school_id": user["school_id"]}},
        {"$group": {
            "_id": "$student_id",
            "total_fee": {"$sum": "$total"},
            "paid_amount": {"$sum": "$paid"},
            "due_amount": {"$sum": "$due"},
            "invoices": {"$sum": 1},
        }},
    ])
    fee_map: dict[str, dict] = {}
    async for row in agg:
        fee_map[row["_id"]] = row

    rows = []
    counts = {"paid": 0, "partial": 0, "not_paid": 0, "no_fees": 0}
    for s in students:
        f = fee_map.get(s["id"])
        total = float(f["total_fee"]) if f else 0.0
        paid = float(f["paid_amount"]) if f else 0.0
        balance = max(total - paid, 0.0)
        if total <= 0:
            st = "no_fees"
            percent = 0.0
        elif balance <= 0.01:
            st = "paid"
            percent = 100.0
        elif paid <= 0:
            st = "not_paid"
            percent = 0.0
        else:
            st = "partial"
            percent = round((paid / total) * 100, 1)
        if status and st != status:
            continue
        counts[st] += 1
        rows.append({
            "student_id": s["id"],
            "student_name": s["name"],
            "student_uid": s.get("uid"),
            "class_id": s.get("class_id"),
            "section": s.get("section"),
            "parent_name": (s.get("parent") or {}).get("name"),
            "parent_phone": (s.get("parent") or {}).get("phone"),
            "total_fee": total,
            "paid_amount": paid,
            "balance_due": balance,
            "percent_paid": percent,
            "status": st,
            "invoice_count": int(f["invoices"]) if f else 0,
        })

    return {
        "rows": rows,
        "summary": counts,
        "total_students": len(rows),
        "totals": {
            "total_fee": sum(r["total_fee"] for r in rows),
            "paid_amount": sum(r["paid_amount"] for r in rows),
            "balance_due": sum(r["balance_due"] for r in rows),
        },
    }
