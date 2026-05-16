"""User management (teachers, accounts, parent staff users) — School Super Admin only."""
from fastapi import APIRouter, Depends, HTTPException
from core.models import UserCreate, UserUpdate
from core.auth import require_roles, hash_password, get_current_user
from core.db import get_db
from core.utils import new_id, utc_now, clean_doc
from core.audit import log_action

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

    # Enrich with last-telegram-credentials timestamp (per user) so the UI can
    # surface "📲 Last sent on …" hints without an extra round-trip.
    if docs and user["role"] in ("platform_admin", "school_admin"):
        ids = [d["id"] for d in docs]
        pipeline = [
            {"$match": {
                "resource": "user",
                "resource_id": {"$in": ids},
                "$or": [
                    {"action": "reset_password", "meta.sent_via_telegram": True},
                    {"action": "send_credentials", "meta.channel": "telegram"},
                ],
            }},
            {"$sort": {"created_at": -1}},
            {"$group": {
                "_id": "$resource_id",
                "last_at": {"$first": "$created_at"},
                "last_action": {"$first": "$action"},
            }},
        ]
        last_by_user: dict[str, dict] = {}
        async for row in db.audit_logs.aggregate(pipeline):
            last_by_user[row["_id"]] = {
                "last_telegram_credential_at": row["last_at"],
                "last_telegram_credential_action": row["last_action"],
            }
        for d in docs:
            info = last_by_user.get(d["id"])
            if info:
                d.update(info)
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


@router.post("/{user_id}/send-credentials")
async def send_user_credentials(
    user_id: str,
    payload: dict | None = None,
    user: dict = Depends(require_roles("school_admin")),
):
    """Send (and optionally reset) the login credentials for any staff user
    (teacher / accounts) directly to their Telegram (or whatsapp/sms).

    Body: {"channel": "telegram" | "whatsapp" | "sms", "reset_first": bool, "default_password": "..."}
    - reset_first=true resets the user's password to `default_password` (or
      `Staff@123`) and includes it in the message.
    - reset_first=false sends a generic 'use your existing password' notice.

    Used by the new "Send creds" action on the Teachers/Staff page so school
    admins can hand staff their login over Telegram instead of email/in-person.
    """
    body = payload or {}
    channel = (body.get("channel") or "telegram").lower()
    reset_first = bool(body.get("reset_first", True))
    default_pwd = str(body.get("default_password") or "Staff@123")
    if channel not in ("telegram", "whatsapp", "sms"):
        raise HTTPException(status_code=400, detail="channel must be one of: telegram, whatsapp, sms")
    if len(default_pwd) < 6:
        raise HTTPException(status_code=400, detail="default_password must be at least 6 characters")

    db = get_db()
    target = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("school_id") != user["school_id"]:
        raise HTTPException(status_code=403, detail="Cross-school operation forbidden")
    if target.get("role") not in ("teacher", "accounts"):
        raise HTTPException(status_code=400, detail="This endpoint is for staff (teacher/accounts) only")

    pwd_line: str
    if reset_first:
        from core.auth import hash_password
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"password_hash": hash_password(default_pwd), "password_reset_to_default_at": utc_now()}},
        )
        pwd_line = f"Password: {default_pwd} (just reset — please change after login)"
    else:
        pwd_line = "Password: use your existing password, or tap 'Forgot password' on the login page"

    role_label = "Teacher" if target["role"] == "teacher" else "Accounts"
    msg = (
        f"👋 Welcome to the {role_label.lower()} portal!\n"
        f"Login email: {target.get('email')}\n"
        f"{pwd_line}\n\n"
        f"📲 This is the school's official communication channel — please keep notifications enabled. "
        f"You'll receive timetable updates, calendar events, holidays and duty assignments here."
    )

    from core.notify import queue_notification
    note = await queue_notification(
        school_id=user["school_id"],
        recipient_type=target["role"],
        recipient_id=user_id,
        phone=target.get("phone"),
        channel=channel,
        template="staff_credentials",
        message=msg,
        context={"reset_first": reset_first, "role": target["role"]},
        telegram_chat_id=target.get("telegram_chat_id"),
    )
    await log_action(
        user["id"], user["role"], user["school_id"],
        "send_credentials", "user", user_id,
        {
            "target_email": target.get("email"),
            "target_role": target.get("role"),
            "channel": channel,
            "reset_first": reset_first,
            "delivery_status": note.get("status"),
        },
    )
    return {
        "ok": True,
        "channel": channel,
        "reset_first": reset_first,
        "delivery_status": note.get("status"),
        "delivery_note": note.get("delivery_note"),
        "email": target.get("email"),
        "default_password": default_pwd if reset_first else None,
    }



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


class AdminResetPasswordPayload(_BaseModel):
    new_password: str
    send_via_telegram: bool = False


@router.post("/{user_id}/reset-password")
async def admin_reset_user_password(
    user_id: str,
    payload: AdminResetPasswordPayload,
    user: dict = Depends(get_current_user),
):
    """Admin-driven password reset (no current-password verification).

    RBAC:
    - `school_admin` can reset passwords for `teacher` and `accounts` users in their own school.
    - `platform_admin` can reset passwords for `school_admin` users in any school.
    Returns `{ok: True, email, new_password}` so the resetting admin can share the new password
    with the user manually. The new password is shown on-screen exactly once (audit-logged but never
    persisted in plaintext).
    Pass `send_via_telegram: true` to also push the new credentials to the target's linked
    Telegram chat in the same call. The response then also carries `telegram` with the delivery
    status (sent / queued / failed) and any delivery_note.
    """
    if user["role"] not in ("school_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    db = get_db()
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target_role = target.get("role")
    if user["role"] == "school_admin":
        if target.get("school_id") != user.get("school_id"):
            raise HTTPException(status_code=403, detail="Cross-school operation forbidden")
        if target_role not in ("teacher", "accounts"):
            raise HTTPException(
                status_code=403,
                detail="School admins can only reset passwords for teachers and accounts staff. "
                       "Contact the Platform Super Admin to reset another school admin's password.",
            )
    else:  # platform_admin
        if target_role != "school_admin":
            raise HTTPException(
                status_code=403,
                detail="Platform Super Admin can only reset passwords for School Super Admins via this endpoint. "
                       "Use the school admin's panel for teacher/accounts resets.",
            )

    new_hash = hash_password(payload.new_password)
    await db.users.update_one(
        {"id": user_id},
        {"$set": {
            "password_hash": new_hash,
            "password_changed_at": utc_now(),
            "password_reset_by_id": user["id"],
            "password_reset_by_role": user["role"],
            "password_reset_at": utc_now(),
        }},
    )

    # Mirror the new hash into the per-school DB (if applicable).
    try:
        from core.db import get_school_db
        school = await db.schools.find_one({"id": target.get("school_id")}, {"_id": 0})
        if school:
            sdb = get_school_db(school)
            await sdb.users.update_one(
                {"id": user_id},
                {"$set": {"password_hash": new_hash, "password_changed_at": utc_now()}},
            )
    except Exception as e:
        print(f"[users] mirror reset password to school db failed: {e}")

    await log_action(
        user["id"], user["role"], target.get("school_id"),
        "reset_password", "user", user_id,
        {
            "target_email": target.get("email"),
            "target_role": target_role,
            "sent_via_telegram": bool(payload.send_via_telegram),
        },
    )

    response: dict = {
        "ok": True,
        "email": target.get("email"),
        "name": target.get("name"),
        "role": target_role,
        "new_password": payload.new_password,
    }

    if payload.send_via_telegram:
        role_label = {"teacher": "Teacher", "accounts": "Accounts", "school_admin": "School Super Admin"}.get(target_role, target_role.title())
        msg = (
            f"🔐 Your {role_label.lower()} password has been reset by an administrator.\n"
            f"Login email: {target.get('email')}\n"
            f"New password: {payload.new_password}\n\n"
            f"Please log in and change this password from your profile."
        )
        try:
            from core.notify import queue_notification
            note = await queue_notification(
                school_id=target.get("school_id"),
                recipient_type=target_role,
                recipient_id=user_id,
                phone=target.get("phone"),
                channel="telegram",
                template="admin_password_reset",
                message=msg,
                context={"target_role": target_role, "reset_by": user["role"]},
                telegram_chat_id=target.get("telegram_chat_id"),
            )
            response["telegram"] = {
                "status": note.get("status"),
                "delivery_note": note.get("delivery_note"),
                "linked": bool(target.get("telegram_chat_id")),
            }
        except Exception as e:
            response["telegram"] = {"status": "failed", "delivery_note": str(e), "linked": bool(target.get("telegram_chat_id"))}

    return response


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
