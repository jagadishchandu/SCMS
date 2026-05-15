"""Audit logs route — School Admin (own school) + Platform Admin (any)."""
from fastapi import APIRouter, Depends
from core.auth import get_current_user
from core.db import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit(limit: int = 200, user: dict = Depends(get_current_user)):
    db = get_db()
    if user["role"] not in ("platform_admin", "school_admin"):
        return []
    flt = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    return await db.audit_logs.find(flt, {"_id": 0}).sort("created_at", -1).to_list(limit)
