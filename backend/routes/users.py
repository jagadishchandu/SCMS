"""User management (teachers, accounts, parent staff users) — School Super Admin only."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import UserCreate, UserUpdate
from core.auth import require_roles, hash_password, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now, clean_doc

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(role: str | None = None, user: dict = Depends(get_current_user)):
    """Strict visibility:
    - platform_admin: any school via ?school_id (TODO) — for MVP shows own scope
    - school_admin: all users in school
    - teacher / accounts / parent: only own profile (returns single-item list)
    """
    db = get_db()
    if user["role"] == "platform_admin":
        q = {}
    elif user["role"] == "school_admin":
        q = {"school_id": user["school_id"]}
    else:
        # restricted: only self
        return [user]
    if role:
        q["role"] = role
    docs = await db.users.find(q, {"_id": 0, "password_hash": 0}).to_list(2000)
    return docs


@router.post("")
async def create_user(payload: UserCreate, user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    db = get_db()
    school_id = user.get("school_id")
    if not school_id and user["role"] == "platform_admin":
        raise HTTPException(status_code=400, detail="Platform admin must specify school context — please use School Admin login.")
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    doc = {
        "id": new_id(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name,
        "role": payload.role,
        "school_id": school_id,
        "phone": payload.phone,
        "employee_id": payload.employee_id,
        "qualifications": payload.qualifications,
        "joining_date": payload.joining_date,
        "subjects": payload.subjects or [],
        "is_active": True,
        "created_at": utc_now(),
    }
    await db.users.insert_one(doc)
    return clean_doc(doc)


@router.get("/{user_id}")
async def get_user(user_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    if user["role"] in ("teacher", "accounts", "parent") and user["id"] != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    doc = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == "school_admin" and doc.get("school_id") != user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    return doc


@router.patch("/{user_id}")
async def update_user(user_id: str, payload: UserUpdate, user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    db = get_db()
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == "school_admin" and target.get("school_id") != user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        return {"ok": True}
    await db.users.update_one({"id": user_id}, {"$set": update})
    return {"ok": True}


@router.delete("/{user_id}")
async def deactivate_user(user_id: str, user: dict = Depends(require_roles("school_admin", "platform_admin"))):
    db = get_db()
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] == "school_admin" and target.get("school_id") != user["school_id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.users.update_one({"id": user_id}, {"$set": {"is_active": False}})
    return {"ok": True}
