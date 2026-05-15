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
    # Lock down: only one Platform Super Admin (seeded from env) and one School Super Admin
    # per school (created automatically with the school). Disallow creating more via API.
    if payload.role in ("platform_admin", "school_admin"):
        raise HTTPException(
            status_code=403,
            detail="Super Admins cannot be created from the app. Platform Super Admin is provisioned via Docker env; School Super Admin is created automatically with the school.",
        )
    school_id = user.get("school_id")
    if not school_id and user["role"] == "platform_admin":
        raise HTTPException(status_code=400, detail="Platform admin must specify school context — please use School Admin login.")
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    # Teachers MUST have at least one subject. Non-teaching staff (cleaners,
    # drivers, sports coaches, etc.) should be created via /api/staff instead.
    if payload.role == "teacher" and not (payload.subjects and len(payload.subjects) > 0):
        raise HTTPException(
            status_code=400,
            detail="Teachers must be assigned at least one subject. If this person doesn't teach, add them as Accounts (for fees) or as non-teaching Staff (sports coach, driver, cleaner, etc.).",
        )
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
        "monthly_salary": payload.monthly_salary,
        "is_active": True,
        "created_at": utc_now(),
    }
    await db.users.insert_one(doc)

    # Mirror into the per-school DB so the schema is populated for the school.
    try:
        from core.db import get_school_db
        school = await db.schools.find_one({"id": school_id}, {"_id": 0})
        if school:
            sdb = get_school_db(school)
            mirror = {k: v for k, v in doc.items() if k != "_id"}
            await sdb.users.update_one({"email": email}, {"$set": mirror}, upsert=True)
            role_to_collection = {
                "teacher": "teachers",
                "accounts": "accounts_users",
                "parent": "parents",
                "student": "students_users",
            }
            target = role_to_collection.get(doc["role"])
            if target:
                await sdb[target].update_one(
                    {"user_id": doc["id"]},
                    {"$set": {
                        "user_id": doc["id"], "email": email, "name": doc["name"],
                        "phone": doc.get("phone"), "created_at": doc["created_at"],
                    }},
                    upsert=True,
                )
    except Exception as e:
        print(f"[users] mirror to school db failed: {e}")

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


from pydantic import BaseModel as _BaseModel
from core.i18n import SUPPORTED_LANGUAGES


class LanguagePayload(_BaseModel):
    language: str


@router.patch("/me/language")
async def set_my_language(payload: LanguagePayload, user: dict = Depends(get_current_user)):
    """Any authenticated user can set their own notification language preference."""
    if payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Choose one of: {SUPPORTED_LANGUAGES}")
    db = get_db()
    await db.users.update_one({"id": user["id"]}, {"$set": {"language": payload.language}})
    return {"ok": True, "language": payload.language}


class ChangePasswordPayload(_BaseModel):
    current_password: str
    new_password: str


@router.post("/me/change-password")
async def change_my_password(
    payload: ChangePasswordPayload, user: dict = Depends(get_current_user)
):
    """Self-service password change for any authenticated user.
    Requires the user's current password for verification.
    """
    from core.auth import verify_password as _verify, hash_password as _hash

    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    if payload.new_password == payload.current_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    db = get_db()
    full = await db.users.find_one({"id": user["id"]})
    if not full or not _verify(payload.current_password, full["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": _hash(payload.new_password), "password_changed_at": utc_now()}},
    )
    return {"ok": True}
