"""Auth routes."""
from fastapi import APIRouter, HTTPException, Response, Depends, Request
from core.models import LoginRequest, UserOut
from core.auth import (
    verify_password, create_access_token, create_refresh_token,
    set_auth_cookies, clear_auth_cookies, get_current_user,
)
from core.db import get_db
from core.utils import clean_doc, utc_now

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(payload: LoginRequest, response: Response, request: Request):
    db = get_db()
    email = payload.email.lower()
    # brute force check
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    attempt = await db.login_attempts.find_one({"identifier": identifier})
    if attempt and attempt.get("locked_until") and attempt["locked_until"] > utc_now():
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")

    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        # increment failures
        from datetime import timedelta
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
    return clean_doc(user)


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return user
