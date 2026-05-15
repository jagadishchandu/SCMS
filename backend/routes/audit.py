"""Audit logs route — School Admin (own school) + Platform Admin (any).

Supports filtering by date range, actor role, action, resource type, free-text search,
and school (platform admin only). CSV export available at GET /audit/export.csv.
"""
import csv
import io
import json
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.auth import get_current_user
from core.db import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


def _build_filter(user: dict, *, actor_role: str | None, action: str | None,
                  resource: str | None, school_id: str | None,
                  date_from: str | None, date_to: str | None, q: str | None) -> dict:
    flt: dict = {} if user["role"] == "platform_admin" else {"school_id": user["school_id"]}
    if user["role"] == "platform_admin" and school_id:
        flt["school_id"] = school_id
    if actor_role:
        flt["actor_role"] = actor_role
    if action:
        flt["action"] = action
    if resource:
        flt["resource"] = resource
    if date_from:
        flt.setdefault("created_at", {})["$gte"] = datetime.combine(
            datetime.fromisoformat(date_from).date(), time.min, tzinfo=timezone.utc)
    if date_to:
        flt.setdefault("created_at", {})["$lte"] = datetime.combine(
            datetime.fromisoformat(date_to).date(), time.max, tzinfo=timezone.utc)
    if q:
        rx = {"$regex": q, "$options": "i"}
        flt["$or"] = [
            {"action": rx},
            {"resource": rx},
            {"resource_id": rx},
            {"actor_id": rx},
        ]
    return flt


async def _decorate_with_actor(db, docs: list[dict]) -> list[dict]:
    actor_ids = list({d["actor_id"] for d in docs if d.get("actor_id")})
    users = {u["id"]: u for u in await db.users.find(
        {"id": {"$in": actor_ids}},
        {"_id": 0, "id": 1, "name": 1, "email": 1},
    ).to_list(500)}
    for d in docs:
        u = users.get(d.get("actor_id")) or {}
        d["actor_name"] = u.get("name")
        d["actor_email"] = u.get("email")
    return docs


@router.get("")
async def list_audit(
    limit: int = 200,
    actor_role: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    school_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if user["role"] not in ("platform_admin", "school_admin"):
        return []
    flt = _build_filter(user, actor_role=actor_role, action=action, resource=resource,
                        school_id=school_id, date_from=date_from, date_to=date_to, q=q)
    docs = await db.audit_logs.find(flt, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 1000))
    return await _decorate_with_actor(db, docs)


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


@router.get("/export.csv")
async def export_csv(
    limit: int = 5000,
    actor_role: str | None = None,
    action: str | None = None,
    resource: str | None = None,
    school_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    user: dict = Depends(get_current_user),
):
    """Stream the filtered audit log as a CSV file. Respects all filter params from /audit."""
    if user["role"] not in ("platform_admin", "school_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    flt = _build_filter(user, actor_role=actor_role, action=action, resource=resource,
                        school_id=school_id, date_from=date_from, date_to=date_to, q=q)
    docs = await db.audit_logs.find(flt, {"_id": 0}).sort("created_at", -1).to_list(min(limit, 20000))
    docs = await _decorate_with_actor(db, docs)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "When (UTC)", "Actor Name", "Actor Email", "Actor Role",
        "School ID", "Action", "Resource", "Resource ID", "Details (JSON)",
    ])
    for d in docs:
        created = d.get("created_at")
        when = created.isoformat() if hasattr(created, "isoformat") else str(created or "")
        writer.writerow([
            when,
            d.get("actor_name") or "",
            d.get("actor_email") or "",
            d.get("actor_role") or "",
            d.get("school_id") or "",
            d.get("action") or "",
            d.get("resource") or "",
            d.get("resource_id") or "",
            json.dumps(d.get("meta") or {}, ensure_ascii=False, default=str),
        ])
    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel
    filename = f"audit-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
