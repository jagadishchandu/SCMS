"""Schools routes - platform admin only for create/list-all."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import SchoolCreate, SchoolUpdate, SchoolBranding
from core.auth import require_roles, hash_password, get_current_user
from core.db import get_db, init_school_db, school_db_name
from core.utils import new_id, utc_now, clean_doc

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("")
async def list_schools(user: dict = Depends(get_current_user)):
    db = get_db()
    q = {}
    if user["role"] != "platform_admin":
        q["id"] = user.get("school_id")
    schools = await db.schools.find(q, {"_id": 0}).to_list(1000)
    return schools


@router.post("")
async def create_school(payload: SchoolCreate, user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    # uniqueness
    if await db.schools.find_one({"code": payload.code}):
        raise HTTPException(status_code=400, detail="School code already exists")
    if await db.users.find_one({"email": payload.admin_email.lower()}):
        raise HTTPException(status_code=400, detail="Admin email already exists")

    school_id = new_id()
    school_doc = {
        "id": school_id,
        "name": payload.name,
        "code": payload.code,
        "address": payload.address,
        "phone": payload.phone,
        "email": payload.email,
        "academic_year": payload.academic_year or "2025-2026",
        "is_active": True,
        "created_at": utc_now(),
    }
    school_doc["db_name"] = school_db_name(school_doc)
    await db.schools.insert_one(school_doc)
    # Provision dedicated database with full index schema for this school
    try:
        await init_school_db(school_doc)
    except Exception as e:
        print(f"[schools] init_school_db failed for {school_id}: {e}")

    admin_doc = {
        "id": new_id(),
        "email": payload.admin_email.lower(),
        "password_hash": hash_password(payload.admin_password),
        "name": payload.admin_name,
        "role": "school_admin",
        "school_id": school_id,
        "is_active": True,
        "created_at": utc_now(),
    }
    await db.users.insert_one(admin_doc)

    return {"school": clean_doc(school_doc), "admin_email": admin_doc["email"]}


@router.patch("/{school_id}")
async def update_school(school_id: str, payload: SchoolUpdate, user: dict = Depends(require_roles("platform_admin"))):
    db = get_db()
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    if not update:
        return {"ok": True}
    res = await db.schools.update_one({"id": school_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="School not found")
    return {"ok": True}


@router.get("/{school_id}")
async def get_school(school_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != "platform_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    s = await db.schools.find_one({"id": school_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    return s


@router.patch("/{school_id}/branding")
async def update_branding(school_id: str, payload: SchoolBranding, user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "school_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    branding = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    # validate logo size if data URL
    if branding.get("logo", "").startswith("data:"):
        # rough size check ~ 1.4x bytes
        if len(branding["logo"]) > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Logo too large (max ~1.4 MB)")
    res = await db.schools.update_one({"id": school_id}, {"$set": {"branding": branding}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True, "branding": branding}


from pydantic import BaseModel as _BaseModel
from core.i18n import SUPPORTED_LANGUAGES, supported_languages


class LanguagePayload(_BaseModel):
    language: str


@router.get("/{school_id}/language")
async def get_school_language(school_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in ("platform_admin",) and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db = get_db()
    s = await db.schools.find_one({"id": school_id}, {"_id": 0, "language": 1})
    return {
        "language": (s or {}).get("language") or "en",
        "supported": supported_languages(),
    }


@router.patch("/{school_id}/language")
async def set_school_language(school_id: str, payload: LanguagePayload, user: dict = Depends(get_current_user)):
    if user["role"] not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "school_admin" and user.get("school_id") != school_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if payload.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Choose one of: {SUPPORTED_LANGUAGES}")
    db = get_db()
    res = await db.schools.update_one({"id": school_id}, {"$set": {"language": payload.language}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True, "language": payload.language}
