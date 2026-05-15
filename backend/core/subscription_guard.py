"""Middleware: block write actions when a school's subscription has lapsed.

Behaviour:
- Read endpoints stay open so the school can still view their data and renew.
- Auth + subscription endpoints are always allowed so the user can log in and pay.
- Platform Admin is never gated.
- A configurable grace period (`SUBSCRIPTION_GRACE_DAYS`, default 3) is added on top
  of `valid_until` so writes don't break the moment the clock ticks over midnight.
- Returns 402 with code='subscription_expired' (or 'subscription_grace' if still in
  the grace window — UI can use this to nudge but allow).
"""
import os
from datetime import datetime, timezone, timedelta
import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.db import get_db
from core.auth import _secret, JWT_ALGORITHM


# Paths (prefix match) that are always allowed for writes even on expired subscription:
ALLOWED_WRITE_PREFIXES = (
    "/api/auth/",
    "/api/subscriptions/",
    "/api/webhooks/",
)


def _grace_days() -> int:
    try:
        return max(0, int(os.environ.get("SUBSCRIPTION_GRACE_DAYS", "3")))
    except ValueError:
        return 3


class SubscriptionGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip for safe (read) methods
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)
        if any(path.startswith(p) for p in ALLOWED_WRITE_PREFIXES):
            return await call_next(request)
        # Identify caller from cookie (best-effort; if no token, normal auth dependency will 401)
        token = request.cookies.get("access_token")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if not token:
            return await call_next(request)
        try:
            payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
        except Exception:
            return await call_next(request)
        role = payload.get("role")
        school_id = payload.get("school_id")
        if role == "platform_admin" or not school_id:
            return await call_next(request)

        db = get_db()
        school = await db.schools.find_one({"id": school_id}, {"_id": 0, "subscription": 1})
        sub = (school or {}).get("subscription") or {}
        valid_until = sub.get("valid_until")
        # If no active subscription at all (first run), allow writes — onboarding window.
        if sub.get("status") != "active" or not valid_until:
            return await call_next(request)
        try:
            vu = valid_until if isinstance(valid_until, datetime) else datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=timezone.utc)
        except Exception:
            return await call_next(request)
        now = datetime.now(timezone.utc)
        grace_until = vu + timedelta(days=_grace_days())
        if grace_until < now:
            return JSONResponse(
                status_code=402,
                content={
                    "detail": "Subscription expired. Please renew to continue making changes.",
                    "code": "subscription_expired",
                    "valid_until": vu.isoformat(),
                    "grace_until": grace_until.isoformat(),
                    "renew_url": "/school/subscription",
                },
            )
        return await call_next(request)


def is_enabled() -> bool:
    return os.environ.get("ENABLE_SUBSCRIPTION_GUARD", "false").lower() in ("1", "true", "yes")


# ----- Helper for /auth/me + topbar banner -----

def compute_subscription_state(sub: dict | None) -> dict:
    """Return a compact state object for the frontend banner:
    {status, valid_until, days_left, is_expired, is_in_grace, is_expiring_soon}
    `is_expiring_soon` = within 7 days; `is_in_grace` = expired but inside grace_days.
    """
    if not sub or sub.get("status") != "active":
        return {"status": "none"}
    vu = sub.get("valid_until")
    if not vu:
        return {"status": sub.get("status", "none")}
    if not isinstance(vu, datetime):
        try:
            vu = datetime.fromisoformat(str(vu).replace("Z", "+00:00"))
        except Exception:
            return {"status": sub.get("status", "none")}
    if vu.tzinfo is None:
        vu = vu.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    days_left = (vu.date() - now.date()).days
    grace_until = vu + timedelta(days=_grace_days())
    return {
        "status": "active",
        "valid_until": vu.isoformat(),
        "grace_until": grace_until.isoformat(),
        "days_left": days_left,
        "is_expiring_soon": 0 <= days_left <= 7,
        "is_in_grace": vu < now <= grace_until,
        "is_expired": grace_until < now,
    }
