"""Audit log helper.

Writes to the master `audit_logs` collection (for platform-wide visibility)
and also mirrors to the per-school DB's `audit_logs` collection when a
`school_id` is present (so school admins see only their own actions).
"""
from .db import get_db, tenant_db
from .utils import new_id, utc_now


async def log_action(
    actor_id: str,
    actor_role: str,
    school_id: str | None,
    action: str,
    resource: str,
    resource_id: str | None = None,
    meta: dict | None = None,
):
    db = get_db()
    doc = {
        "id": new_id(),
        "actor_id": actor_id,
        "actor_role": actor_role,
        "school_id": school_id,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "meta": meta or {},
        "created_at": utc_now(),
    }
    await db.audit_logs.insert_one(doc)
    if school_id:
        try:
            tdb = await tenant_db(school_id)
            mirror = {k: v for k, v in doc.items() if k != "_id"}
            await tdb.audit_logs.update_one({"id": mirror["id"]}, {"$set": mirror}, upsert=True)
        except Exception as e:
            print(f"[audit] mirror to tenant failed: {e}")

