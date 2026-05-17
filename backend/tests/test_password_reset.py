"""Tests for the password-reset-via-Telegram-OTP flow.

We don't have a real Telegram bot running in CI, so we monkey-patch
`core.telegram_sender.send_telegram` to capture what would have been sent
(returning success). The test then reads the latest unconsumed code from the
`password_reset_codes` collection — but since codes are stored hashed, we
inject our own known OTP into the DB by patching `_generate_otp`.
"""
import asyncio
import os
import time
import uuid
from datetime import timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://school-admin-fix.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "scms_db")

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


# ---------------- helpers ----------------

def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"login {email} → {r.status_code}: {r.text}"
    return s, r


async def _db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def reset_user():
    """Create a fresh school + admin via the platform API, then attach a fake
    telegram_chat_id to the admin so they qualify for OTP delivery."""
    plat, _ = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:8].upper()
    admin_email = f"reset.admin.{suffix.lower()}@reset.example.com"
    admin_password = "ResetPw@2026"
    payload = {
        "name": f"Reset School {suffix}",
        "code": f"RST{suffix}",
        "address": "Reset Lane",
        "phone": "+919000000010",
        "email": f"info.{suffix.lower()}@reset.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email,
        "admin_password": admin_password,
        "admin_name": "Reset Admin",
    }
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200

    async def _attach_telegram():
        db = await _db()
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"telegram_chat_id": 11111111}},
        )

    _run(_attach_telegram())
    yield {"email": admin_email, "password": admin_password}


def _read_latest_code_record(email):
    async def _read():
        db = await _db()
        return await db.password_reset_codes.find_one(
            {"email": email.lower()}, sort=[("created_at", -1)]
        )
    return _run(_read())


def _seed_known_code(email, otp, ttl_minutes=10, attempts=0, consumed=False):
    """Insert a known code (hashed by our auth.hash_password) so the test
    can verify the verify endpoint without needing real Telegram."""
    from datetime import datetime, timezone
    import bcrypt
    code_hash = bcrypt.hashpw(otp.encode(), bcrypt.gensalt()).decode()

    async def _ins():
        db = await _db()
        # Invalidate any prior open codes
        await db.password_reset_codes.update_many(
            {"email": email.lower(), "consumed_at": None},
            {"$set": {"consumed_at": datetime.now(timezone.utc), "consumed_reason": "test_supersede"}},
        )
        user = await db.users.find_one({"email": email.lower()})
        now = datetime.now(timezone.utc)
        doc = {
            "id": uuid.uuid4().hex,
            "email": email.lower(),
            "user_id": user["id"] if user else None,
            "code_hash": code_hash,
            "channel": "telegram",
            "telegram_chat_id": 11111111,
            "created_at": now,
            "expires_at": now + timedelta(minutes=ttl_minutes),
            "attempts": attempts,
            "consumed_at": now if consumed else None,
        }
        await db.password_reset_codes.insert_one(doc)
        return doc

    return _run(_ins())


# ---------------- tests ----------------


class TestPasswordResetRequest:
    def test_request_returns_generic_when_email_not_found(self):
        r = requests.post(
            f"{API}/auth/password-reset/request",
            json={"email": f"nobody-{uuid.uuid4().hex[:8]}@nowhere.example.com"},
            timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        # Generic message, never reveals "email not found"
        assert "exists and has Telegram linked" in body.get("message", "")

    def test_request_returns_generic_when_email_exists_without_telegram(self):
        # Use a known seeded user — the demo parent — and ensure we never error.
        r = requests.post(
            f"{API}/auth/password-reset/request",
            json={"email": "parent.stu-00001@sunrise.edu"},
            timeout=15,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_request_creates_code_record_when_user_has_telegram(self, reset_user):
        r = requests.post(
            f"{API}/auth/password-reset/request",
            json={"email": reset_user["email"]},
            timeout=15,
        )
        assert r.status_code == 200
        rec = _read_latest_code_record(reset_user["email"])
        assert rec is not None
        assert rec["email"] == reset_user["email"].lower()
        assert rec["channel"] == "telegram"
        assert rec["consumed_at"] is None
        assert rec.get("code_hash"), "code_hash must be stored, never plaintext"
        # Hash must not equal a 6-digit numeric string (sanity)
        assert not rec["code_hash"].isdigit()


class TestPasswordResetVerify:
    def test_verify_with_correct_code_updates_password(self, reset_user):
        otp = "123456"
        _seed_known_code(reset_user["email"], otp)
        new_pw = "BrandNew@2026"
        r = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": otp, "new_password": new_pw},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Old password no longer works
        _login(reset_user["email"], reset_user["password"], expect=401)
        # New password works
        _login(reset_user["email"], new_pw)
        # Restore so subsequent tests reuse the fixture creds.
        s, _ = _login(reset_user["email"], new_pw)
        s.post(
            f"{API}/users/me/change-password",
            json={"current_password": new_pw, "new_password": reset_user["password"]},
            timeout=15,
        )

    def test_verify_invalid_code_returns_400(self, reset_user):
        _seed_known_code(reset_user["email"], "654321")
        r = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": "000000", "new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "invalid" in r.json().get("detail", "").lower()

    def test_verify_expired_code_returns_400(self, reset_user):
        _seed_known_code(reset_user["email"], "111222", ttl_minutes=-1)
        r = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": "111222", "new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "expired" in r.json().get("detail", "").lower()

    def test_verify_too_many_attempts_blocks(self, reset_user):
        _seed_known_code(reset_user["email"], "999888", attempts=5)
        r = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": "999888", "new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 429

    def test_verify_no_active_code_returns_400(self, reset_user):
        # Consume any open code first
        _seed_known_code(reset_user["email"], "777666", consumed=True)
        r = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": "777666", "new_password": "Whatever@2026"},
            timeout=15,
        )
        assert r.status_code == 400
        assert "no active" in r.json().get("detail", "").lower()

    def test_verify_short_password_rejected(self, reset_user):
        _seed_known_code(reset_user["email"], "555444")
        r = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": "555444", "new_password": "abc"},
            timeout=15,
        )
        assert r.status_code == 400

    def test_consumed_code_cannot_be_reused(self, reset_user):
        otp = "112233"
        _seed_known_code(reset_user["email"], otp)
        new_pw = "Replay@98765"
        r1 = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": otp, "new_password": new_pw},
            timeout=15,
        )
        assert r1.status_code == 200
        # Reusing the same code must fail (no active code).
        r2 = requests.post(
            f"{API}/auth/password-reset/verify",
            json={"email": reset_user["email"], "code": otp, "new_password": "Another@98765"},
            timeout=15,
        )
        assert r2.status_code == 400
        # Restore
        s, _ = _login(reset_user["email"], new_pw)
        s.post(
            f"{API}/users/me/change-password",
            json={"current_password": new_pw, "new_password": reset_user["password"]},
            timeout=15,
        )
