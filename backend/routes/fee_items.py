"""Fee items catalog + per-student fee summary.

Fee items are reusable line-items (Tuition, Books, Transport, Lab, Activities, …)
that an admin defines once and references from Fee Structures. The catalog
itself lives in the tenant DB so each school owns its own pricing.

Per-student summary returns one row per child with total / paid / balance /
percent_paid / status — used by the Accountant fee tracker.
"""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import require_roles, get_current_user
from core.db import tenant_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

router = APIRouter(prefix="/fee-items", tags=["fee-items"])

CATEGORIES = Literal[
    "tuition", "books", "transport", "lab", "activities", "uniform",
    "exam", "library", "sports", "hostel", "meals", "other",
]
FREQUENCIES = Literal["one_time", "monthly", "quarterly", "yearly"]


class FeeItemCreate(BaseModel):
    name: str
    category: CATEGORIES
    default_amount: float = Field(..., ge=0)
    frequency: FREQUENCIES = "yearly"
    description: Optional[str] = None
    is_active: bool = True


class FeeItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[CATEGORIES] = None
    default_amount: Optional[float] = Field(default=None, ge=0)
    frequency: Optional[FREQUENCIES] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_fee_items(include_inactive: bool = False,
                          user: dict = Depends(require_roles("school_admin", "accounts"))):
    tdb = await tenant_db(user["school_id"])
    flt = {"school_id": user["school_id"]}
    if not include_inactive:
        flt["is_active"] = True
    return await tdb.fee_items.find(flt, {"_id": 0}).sort("category", 1).to_list(500)


@router.post("")
async def create_fee_item(payload: FeeItemCreate,
                           user: dict = Depends(require_roles("school_admin", "accounts"))):
    tdb = await tenant_db(user["school_id"])
    doc = payload.model_dump()
    doc.update({
        "id": new_id(),
        "school_id": user["school_id"],
        "created_at": utc_now(),
        "created_by": user["id"],
    })
    await tdb.fee_items.insert_one(doc)
    await log_action(user["id"], user["role"], user["school_id"],
                      "create_fee_item", "fee_item", doc["id"], {"name": doc["name"]})
    return clean_doc(doc)


@router.patch("/{item_id}")
async def update_fee_item(item_id: str, payload: FeeItemUpdate,
                            user: dict = Depends(require_roles("school_admin", "accounts"))):
    tdb = await tenant_db(user["school_id"])
    existing = await tdb.fee_items.find_one({"id": item_id, "school_id": user["school_id"]})
    if not existing:
        raise HTTPException(status_code=404, detail="Fee item not found")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        return clean_doc(existing)
    update["updated_at"] = utc_now()
    await tdb.fee_items.update_one({"id": item_id}, {"$set": update})
    await log_action(user["id"], user["role"], user["school_id"],
                      "update_fee_item", "fee_item", item_id, update)
    refreshed = await tdb.fee_items.find_one({"id": item_id}, {"_id": 0})
    return clean_doc(refreshed)


@router.delete("/{item_id}")
async def delete_fee_item(item_id: str,
                           user: dict = Depends(require_roles("school_admin"))):
    """Soft delete (is_active=False)."""
    tdb = await tenant_db(user["school_id"])
    res = await tdb.fee_items.update_one(
        {"id": item_id, "school_id": user["school_id"]},
        {"$set": {"is_active": False, "deactivated_at": utc_now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fee item not found")
    await log_action(user["id"], user["role"], user["school_id"],
                      "deactivate_fee_item", "fee_item", item_id)
    return {"ok": True}
