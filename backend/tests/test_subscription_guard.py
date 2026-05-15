"""Tests for the subscription expiry guard middleware.

Verifies:
- Healthy subscription (within validity) → writes pass
- Within grace period (valid_until < now < grace_until) → writes still pass
- Beyond grace period → write returns 402 with code='subscription_expired'
- Reads, auth endpoints, and subscription endpoints stay open in all states
- Platform admin is never gated
"""
import os
from datetime import datetime, timezone, timedelta

import pytest
import requests


API = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api"
if not API.startswith("http"):
    API = "http://localhost:8001/api"

PADMIN = {"email": "jagadishchandu789@gmail.com", "password": "Manasa@123"}
SADMIN = {"email": "principal@sunrise.edu", "password": "School@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def pa():
    return _login(PADMIN)


@pytest.fixture(scope="module")
def sa():
    return _login(SADMIN)


@pytest.fixture(scope="module")
def sid(sa):
    return sa.get(f"{API}/auth/me", timeout=10).json()["school_id"]


def _set_vu(pa, sid, days_from_now: float):
    target = (datetime.now(timezone.utc) + timedelta(days=days_from_now)).isoformat()
    r = pa.post(f"{API}/subscriptions/admin/set-valid-until",
                json={"school_id": sid, "valid_until": target,
                      "reason": "test_guard"}, timeout=15)
    assert r.status_code == 200, r.text


@pytest.fixture(autouse=True)
def _restore_after_test(pa, sid):
    yield
    _set_vu(pa, sid, 30)  # leave the demo school in a healthy state for other tests


class TestSubscriptionGuard:
    def test_healthy_subscription_write_passes(self, pa, sa, sid):
        _set_vu(pa, sid, 30)
        r = sa.post(f"{API}/holidays",
                    json={"title": "GuardTest1", "date": "2027-01-02", "type": "public"},
                    timeout=15)
        assert r.status_code == 200, r.text

    def test_grace_window_write_passes(self, pa, sa, sid):
        _set_vu(pa, sid, -1)  # expired 1 day ago — within default 3-day grace
        r = sa.post(f"{API}/holidays",
                    json={"title": "GuardTest2", "date": "2027-01-03", "type": "public"},
                    timeout=15)
        assert r.status_code == 200, r.text

    def test_beyond_grace_write_blocked_402(self, pa, sa, sid):
        _set_vu(pa, sid, -30)
        r = sa.post(f"{API}/holidays",
                    json={"title": "GuardBlocked", "date": "2027-01-04", "type": "public"},
                    timeout=15)
        assert r.status_code == 402, r.text
        body = r.json()
        assert body.get("code") == "subscription_expired"
        assert "renew_url" in body
        assert body["renew_url"].endswith("/school/subscription")

    def test_read_endpoints_pass_when_expired(self, pa, sa, sid):
        _set_vu(pa, sid, -30)
        r = sa.get(f"{API}/holidays", timeout=15)
        assert r.status_code == 200, r.text

    def test_auth_me_passes_when_expired(self, pa, sa, sid):
        _set_vu(pa, sid, -30)
        r = sa.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "subscription_state" in body
        s = body["subscription_state"]
        assert s.get("is_expired") is True
        assert s.get("is_in_grace") is False
        assert s.get("status") == "active"

    def test_subscriptions_my_passes_when_expired(self, pa, sa, sid):
        _set_vu(pa, sid, -30)
        r = sa.get(f"{API}/subscriptions/my", timeout=10)
        assert r.status_code == 200, r.text

    def test_can_submit_payment_when_expired(self, pa, sa, sid):
        _set_vu(pa, sid, -30)
        # Make sure no pending payment is already in the way
        existing = sa.get(f"{API}/subscriptions/payments",
                          params={"status": "pending_confirmation"}, timeout=10).json()
        for p in existing:
            pa.post(f"{API}/subscriptions/payments/{p['id']}/reject", timeout=10)
        r = sa.post(f"{API}/subscriptions/payments",
                    json={"billing_cycle": "monthly"}, timeout=15)
        assert r.status_code == 200, r.text

    def test_platform_admin_never_gated(self, pa, sid):
        _set_vu(pa, sid, -30)
        # platform admin can still hit any write endpoint
        r = pa.post(f"{API}/subscriptions/admin/set-valid-until",
                    json={"school_id": sid,
                          "valid_until": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()},
                    timeout=10)
        assert r.status_code == 200, r.text

    def test_subscription_state_flags(self, pa, sa, sid):
        # Expiring soon (5 days)
        _set_vu(pa, sid, 5)
        s = sa.get(f"{API}/auth/me", timeout=10).json()["subscription_state"]
        assert s["is_expiring_soon"] is True
        assert s["is_in_grace"] is False
        assert s["is_expired"] is False
        # Healthy (30 days)
        _set_vu(pa, sid, 30)
        s = sa.get(f"{API}/auth/me", timeout=10).json()["subscription_state"]
        assert s["is_expiring_soon"] is False
        assert s["days_left"] in (29, 30, 31)
