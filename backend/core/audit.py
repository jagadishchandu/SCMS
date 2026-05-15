"""Audit log helper."""
from .db import get_db
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
    await db.audit_logs.insert_one({
        "id": new_id(),
        "actor_id": actor_id,
        "actor_role": actor_role,
        "school_id": school_id,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "meta": meta or {},
        "created_at": utc_now(),
    })
