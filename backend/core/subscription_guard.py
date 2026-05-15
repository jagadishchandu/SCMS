"""Middleware: block write actions when a school's subscription has lapsed.

Read endpoints stay open so the school can still view their data and renew.
Auth + subscription endpoints are always allowed so the user can log in and pay.
Platform Admin is never gated.
"""
import os
from datetime import datetime, timezone
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
)


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
        # If no active subscription at all, we allow but log header (soft mode for first run)
        if sub.get("status") != "active" or not valid_until:
            return await call_next(request)
        # Compare dates
        now = datetime.now(timezone.utc)
        try:
            vu = valid_until if isinstance(valid_until, datetime) else datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=timezone.utc)
        except Exception:
            return await call_next(request)
        if vu < now:
            return JSONResponse(
                status_code=402,
                content={
                    "detail": "Subscription expired",
                    "code": "subscription_expired",
                    "valid_until": vu.isoformat(),
                    "renew_url": "/school/subscription",
                },
            )
        return await call_next(request)


def is_enabled() -> bool:
    return os.environ.get("ENABLE_SUBSCRIPTION_GUARD", "false").lower() in ("1", "true", "yes")
