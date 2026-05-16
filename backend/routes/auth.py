"""Auth routes."""
import os
import secrets as _secrets
from datetime import timedelta
from fastapi import APIRouter, HTTPException, Response, Depends, Request
from pydantic import BaseModel, EmailStr
from core.models import LoginRequest, UserOut
from core.auth import (
    verify_password, create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies, get_current_user,
    hash_password,
)
from core.db import get_db, tenant_db
from core.utils import clean_doc, utc_now, new_id
from core import telegram_sender as tg

router = APIRouter(prefix="/auth", tags=["auth"])

# Password reset constants
RESET_CODE_TTL_MINUTES = 10
RESET_CODE_REQUEST_COOLDOWN_SECONDS = 30
RESET_CODE_MAX_VERIFY_ATTEMPTS = 5


@router.post("/login")
async def login(payload: LoginRequest, response: Response, request: Request):
    db = get_db()
    email = payload.email.lower()
    # brute force check
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("locked_until"):
        from datetime import timezone as _tz
        lu = attempt["locked_until"]
        if lu.tzinfo is None:
            lu = lu.replace(tzinfo=_tz.utc)
        if lu > utc_now():
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        # increment failures
        from datetime import timedelta, timezone
        # Normalise lock time to UTC-aware before comparison (Mongo may return naive)
        if attempt and attempt.get("locked_until"):
            lu = attempt["locked_until"]
            if lu.tzinfo is None:
                lu = lu.replace(tzinfo=timezone.utc)
            if lu > utc_now():
                raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
        fails = (attempt["fails"] if attempt else 0) + 1
        update = {"fails": fails, "last_at": utc_now()}
        if fails >= 5:
            update["locked_until"] = utc_now() + timedelta(minutes=15)
            update["fails"] = 0
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$set": update},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    await db.login_attempts.delete_one({"identifier": identifier})
    await db.users.update_one({"id": user["id"]}, {"$set": {"last_login_at": utc_now()}})

    access = create_access_token(user["id"], user["email"], user["role"], user.get("school_id"))
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    out = clean_doc(user)
    # Attach subscription state + school metadata so the UI banner renders immediately on login
    if user.get("school_id"):
        school = await db.schools.find_one(
            {"id": user["school_id"]},
            {"_id": 0, "subscription": 1, "subscription_approval": 1, "name": 1, "language": 1, "branding": 1, "mandatory_channels": 1},
        ) or {}
        from core.subscription_guard import compute_subscription_state
        out["subscription_state"] = compute_subscription_state(school.get("subscription"), school.get("subscription_approval"))
        out["school_name"] = school.get("name")
        out["school_language"] = school.get("language") or "en"
        out["school_branding"] = school.get("branding") or {}
        out["school_mandatory_channels"] = school.get("mandatory_channels") or ["telegram"]
    # Reachability flags so the UI can decide which mandatory-channel banners to render
    out["email_linked"] = bool(out.get("email"))
    out["phone_linked"] = bool(out.get("phone"))
    out["telegram_linked"] = bool(out.get("telegram_chat_id"))
    return out


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    import os
    db = get_db()
    out = dict(user)
    # Attach a compact subscription snapshot so the UI can render an expiry banner.
    if user.get("school_id"):
        school = await db.schools.find_one(
            {"id": user["school_id"]},
            {"_id": 0, "subscription": 1, "subscription_approval": 1, "name": 1, "language": 1, "branding": 1, "mandatory_channels": 1},
        ) or {}
        from core.subscription_guard import compute_subscription_state
        out["subscription_state"] = compute_subscription_state(school.get("subscription"), school.get("subscription_approval"))
        out["school_name"] = school.get("name")
        out["school_language"] = school.get("language") or "en"
        out["school_branding"] = school.get("branding") or {}
        out["school_mandatory_channels"] = school.get("mandatory_channels") or ["telegram"]
    # Reachability flags so the UI can decide which mandatory-channel banners to render
    out["email_linked"] = bool(out.get("email"))
    out["phone_linked"] = bool(out.get("phone"))
    # Telegram link helpers — render the deep-link to /start the bot with the
    # user's role-specific identifier (student UID for parents, email otherwise).
    # The UI uses this for the "Link Telegram" mandatory banner.
    bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip()
    if not bot_username and os.environ.get("TELEGRAM_BOT_TOKEN"):
        # Try to resolve once and cache via env update — best effort
        try:
            import httpx
            tok = os.environ["TELEGRAM_BOT_TOKEN"]
            r = httpx.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=5)
            if r.status_code == 200:
                bot_username = (r.json().get("result") or {}).get("username") or ""
                if bot_username:
                    os.environ["TELEGRAM_BOT_USERNAME"] = bot_username
        except Exception:
            pass
    out["telegram_linked"] = bool(out.get("telegram_chat_id"))
    out["telegram_bot_username"] = bot_username
    if bot_username and not out["telegram_linked"]:
        # Identifier the webhook uses to bind chat_id — for parents we prefer
        # their child's student UID; for staff we use their email.
        ident = None
        if user.get("role") == "parent":
            tdb = await tenant_db(user["school_id"]) if user.get("school_id") else None
            if tdb is not None:
                child = await tdb.students.find_one({"parent_user_id": user["id"]}, {"_id": 0, "student_uid": 1})
                if child:
                    ident = child.get("student_uid")
        ident = ident or user.get("email")
        out["telegram_link_url"] = f"https://t.me/{bot_username}?start={ident}" if ident else f"https://t.me/{bot_username}"
    return clean_doc(out)



# ---------- Password reset via Telegram OTP ----------

class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetVerify(BaseModel):
    email: EmailStr
    code: str
    new_password: str


def _generate_otp() -> str:
    """6-digit numeric OTP using a CSPRNG. Leading zeros preserved."""
    return f"{_secrets.randbelow(1_000_000):06d}"


def _generic_request_response() -> dict:
    """A response that does not reveal whether the email exists or has Telegram linked.
    This blocks email-enumeration via the password-reset endpoint."""
    return {
        "ok": True,
        "message": (
            "If an account with that email exists and has Telegram linked, "
            "a verification code has been sent to its Telegram chat."
        ),
    }


@router.post("/password-reset/request")
async def request_password_reset(payload: PasswordResetRequest):
    """Step 1 of password reset: send a 6-digit OTP to the user's linked Telegram chat.

    Response is intentionally generic to avoid leaking which emails exist.
    Cooldown: 30 seconds between requests for the same email (silently ignored).
    """
    db = get_db()
    email = payload.email.lower()

    # Cooldown: silently ignore frequent re-requests
    last = await db.password_reset_codes.find_one(
        {"email": email}, sort=[("created_at", -1)]
    )
    if last and last.get("created_at"):
        from datetime import timezone as _tz
        c = last["created_at"]
        if c.tzinfo is None:
            c = c.replace(tzinfo=_tz.utc)
        if (utc_now() - c).total_seconds() < RESET_CODE_REQUEST_COOLDOWN_SECONDS:
            return _generic_request_response()

    user = await db.users.find_one({"email": email, "is_active": True})
    # Always return generic response — never tell the caller if the email exists.
    if not user:
        return _generic_request_response()

    chat_id = user.get("telegram_chat_id")
    if not chat_id:
        # User exists but has not linked Telegram — record the attempt in audit but stay generic.
        try:
            from core.audit import log_action
            await log_action(
                user["id"], user["role"], user.get("school_id"),
                "password_reset_request_no_telegram", "user", user["id"],
            )
        except Exception:
            pass
        return _generic_request_response()

    # Invalidate any prior unconsumed codes for this email
    await db.password_reset_codes.update_many(
        {"email": email, "consumed_at": None},
        {"$set": {"consumed_at": utc_now(), "consumed_reason": "superseded"}},
    )

    otp = _generate_otp()
    code_doc = {
        "id": new_id(),
        "email": email,
        "user_id": user["id"],
        "code_hash": hash_password(otp),  # never store the plaintext OTP
        "channel": "telegram",
        "telegram_chat_id": chat_id,
        "created_at": utc_now(),
        "expires_at": utc_now() + timedelta(minutes=RESET_CODE_TTL_MINUTES),
        "attempts": 0,
        "consumed_at": None,
    }
    await db.password_reset_codes.insert_one(code_doc)

    body = (
        f"SCMS password reset code: {otp}\n"
        f"This code expires in {RESET_CODE_TTL_MINUTES} minutes. "
        f"If you did not request this, please ignore this message."
    )
    sent, info = tg.send_telegram(chat_id, body)
    try:
        from core.audit import log_action
        await log_action(
            user["id"], user["role"], user.get("school_id"),
            "password_reset_request", "user", user["id"],
            meta={"channel": "telegram", "sent": bool(sent), "info": info},
        )
    except Exception:
        pass

    return _generic_request_response()


@router.post("/password-reset/verify")
async def verify_password_reset(payload: PasswordResetVerify):
    """Step 2 of password reset: verify the OTP and set the new password.

    Returns specific errors here (code invalid / expired / too many attempts) because
    the user has already proven email knowledge in step 1; we don't gain anything by
    being generic at this step.
    """
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    db = get_db()
    email = payload.email.lower()
    submitted_code = (payload.code or "").strip()
    if not submitted_code:
        raise HTTPException(status_code=400, detail="Verification code is required")

    rec = await db.password_reset_codes.find_one(
        {"email": email, "consumed_at": None},
        sort=[("created_at", -1)],
    )
    if not rec:
        raise HTTPException(status_code=400, detail="No active reset code. Please request a new code.")

    # Expiry check
    from datetime import timezone as _tz
    exp = rec.get("expires_at")
    if exp:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=_tz.utc)
        if exp < utc_now():
            await db.password_reset_codes.update_one(
                {"id": rec["id"]},
                {"$set": {"consumed_at": utc_now(), "consumed_reason": "expired"}},
            )
            raise HTTPException(status_code=400, detail="Code has expired. Please request a new code.")

    # Attempt cap
    attempts = int(rec.get("attempts", 0))
    if attempts >= RESET_CODE_MAX_VERIFY_ATTEMPTS:
        await db.password_reset_codes.update_one(
            {"id": rec["id"]},
            {"$set": {"consumed_at": utc_now(), "consumed_reason": "too_many_attempts"}},
        )
        raise HTTPException(status_code=429, detail="Too many incorrect attempts. Please request a new code.")

    if not verify_password(submitted_code, rec["code_hash"]):
        await db.password_reset_codes.update_one(
            {"id": rec["id"]}, {"$inc": {"attempts": 1}}
        )
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    # Code valid — set new password + consume code + clear any login lock
    user = await db.users.find_one({"id": rec["user_id"]})
    if not user or not user.get("is_active", True):
        raise HTTPException(status_code=400, detail="Account is no longer active. Contact your administrator.")

    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "password_changed_at": utc_now()}},
    )
    await db.password_reset_codes.update_one(
        {"id": rec["id"]},
        {"$set": {"consumed_at": utc_now(), "consumed_reason": "used"}},
    )
    # Clear brute-force lock so the user can immediately log in
    await db.login_attempts.delete_many({"identifier": {"$regex": f":{email}$"}})

    try:
        from core.audit import log_action
        await log_action(
            user["id"], user["role"], user.get("school_id"),
            "password_reset_complete", "user", user["id"],
            meta={"channel": "telegram"},
        )
    except Exception:
        pass

    return {"ok": True, "message": "Password updated. You can now sign in with the new password."}
