"""Audit logs route — School Admin (own school) + Platform Admin (any).

Supports filtering by date range, actor role, action, resource type, free-text search,
and school (platform admin only).
"""
from fastapi import APIRouter, Depends
from core.auth import get_current_user
from core.db import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit(
    limit: int = 200,
    actor_role: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    school_id: str | None = None,
    date_from: str | None = None,  # YYYY-MM-DD
    date_to: str | None = None,    # YYYY-MM-DD
    q: str | None = None,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if user["role"] not in ("platform_admin", "school_admin"):
        return []
    flt: dict = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    if user["role"] == "platform_admin" and school_id:
        flt["school_id"] = school_id
    if actor_role:
        flt["actor_role"] = actor_role
    if action:
        flt["action"] = action
    if resource:
        flt["resource"] = resource
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59"
        if rng:
            flt["created_at_str"] = rng  # fallback if stored as str; primary check below
    # Note: created_at is datetime; convert to ISO string filter via aggregation alternative
    # For simplicity we apply string comparison on date_from/date_to via $expr
    from datetime import datetime, time, timezone
    if date_from:
        flt.setdefault("created_at", {})["$gte"] = datetime.combine(datetime.fromisoformat(date_from).date(), time.min, tzinfo=timezone.utc)
    if date_to:
        flt.setdefault("created_at", {})["$lte"] = datetime.combine(datetime.fromisoformat(date_to).date(), time.max, tzinfo=timezone.utc)
    flt.pop("created_at_str", None)
    if q:
        rx = {"$regex": q, "$options": "i"}
        flt["$or"] = [
            {"action": rx},
            {"resource": rx},
            {"resource_id": rx},
            {"actor_id": rx},
        ]
    docs = await db.audit_logs.find(flt, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
    # also resolve actor names for display
    actor_ids = list({d["actor_id"] for d in docs if d.get("actor_id")})
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": actor_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(500)}
    for d in docs:
        u = users.get(d.get("actor_id")) or {}
        d["actor_name"] = u.get("name")
        d["actor_email"] = u.get("email")
    return docs


@router.get("/facets")
async def audit_facets(user: dict = Depends(get_current_user)):
    """Distinct values for filters — used by the UI dropdowns."""
    db = get_db()
    if user["role"] not in ("platform_admin", "school_admin"):
        return {"actions": [], "resources": [], "roles": []}
    flt: dict = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    actions = await db.audit_logs.distinct("action", flt)
    resources = await db.audit_logs.distinct("resource", flt)
    roles = await db.audit_logs.distinct("actor_role", flt)
    return {
        "actions": sorted([a for a in actions if a]),
        "resources": sorted([r for r in resources if r]),
        "roles": sorted([r for r in roles if r]),
    }
