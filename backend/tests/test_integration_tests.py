"""Tests for the /integrations/test/* endpoints — credential validation surface
exposed on /school/settings."""
import os
import requests
import pytest


API = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api"
if not API.startswith("http"):
    API = "http://localhost:8001/api"

SADMIN = {"email": "principal@sunrise.edu", "password": "School@123"}
PADMIN = {"email": "jagadishchandu789@gmail.com", "password": "Manasa@123"}
TEACHER = {"email": "priya@sunrise.edu", "password": "Teacher@123"}
PARENT = {"email": "parent.stu-00001@sunrise.edu", "password": "Parent@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SADMIN)


@pytest.fixture(scope="module")
def pa():
    return _login(PADMIN)


class TestIntegrationTestEndpoints:
    def test_status_snapshot_shape(self, sa):
        r = sa.get(f"{API}/integrations/test/status", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("meta_whatsapp", "twilio_whatsapp", "telegram", "smtp"):
            assert k in data, data
            assert "configured" in data[k]
        # Telegram bot may or may not be configured — but the bot's chat link is per-user
        assert "linked_to_me" in data["telegram"]

    def test_status_works_for_platform_admin(self, pa):
        r = pa.get(f"{API}/integrations/test/status", timeout=10)
        assert r.status_code == 200

    def test_whatsapp_returns_clear_error_when_not_configured(self, sa):
        r = sa.post(f"{API}/integrations/test/whatsapp", json={"to": "+919999999999"}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        # In CI Meta + Twilio are both blank, so this should be ok:false with configured:false
        # (or ok:true if someone wired it up — both valid)
        assert "ok" in d
        if not d["ok"]:
            assert d["configured"] is False or d["error"]

    def test_telegram_returns_clear_error_when_not_configured(self, sa):
        r = sa.post(f"{API}/integrations/test/telegram", json={}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["provider"] == "telegram"
        if not d["ok"]:
            assert "error" in d and d["error"]

    def test_email_returns_clear_error_when_not_configured(self, sa):
        r = sa.post(f"{API}/integrations/test/email", json={"to": "validate@example.com"}, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["provider"] == "smtp"
        if not d["ok"]:
            assert d["configured"] is False or d["error"]

    def test_email_rejects_invalid_address(self, sa):
        r = sa.post(f"{API}/integrations/test/email", json={"to": "not-an-email"}, timeout=10)
        # FastAPI validates EmailStr → 422
        assert r.status_code == 422, r.text

    def test_teacher_blocked(self):
        t = _login(TEACHER)
        for path in ("/integrations/test/whatsapp", "/integrations/test/telegram", "/integrations/test/email"):
            payload = {"to": "+919999999999"} if "whatsapp" in path else \
                      ({"to": "x@example.com"} if "email" in path else {})
            r = t.post(f"{API}{path}", json=payload, timeout=10)
            assert r.status_code == 403, f"{path}: {r.status_code} {r.text}"
        r = t.get(f"{API}/integrations/test/status", timeout=10)
        assert r.status_code == 403

    def test_parent_blocked(self):
        p = _login(PARENT)
        r = p.post(f"{API}/integrations/test/whatsapp", json={"to": "+919999999999"}, timeout=10)
        assert r.status_code == 403

    def test_anonymous_blocked(self):
        r = requests.post(f"{API}/integrations/test/whatsapp", json={"to": "+919999999999"}, timeout=10)
        assert r.status_code == 401
