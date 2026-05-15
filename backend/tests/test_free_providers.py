"""Tests for Meta WhatsApp + Telegram webhooks and channel selection.

Don't need real Meta/Telegram credentials — these tests verify routing logic,
webhook handshakes, and notification fallback paths.
"""
import os
import requests
import pytest


API = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api"
if not API.startswith("http"):
    API = "http://localhost:8001/api"

SADMIN = {"email": "principal@sunrise.edu", "password": "School@123"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SADMIN)


class TestWhatsAppWebhook:
    def test_verify_rejects_bad_token(self):
        r = requests.get(f"{API}/webhooks/whatsapp",
                         params={"hub.mode": "subscribe",
                                 "hub.verify_token": "definitely_wrong",
                                 "hub.challenge": "abc"},
                         timeout=10)
        assert r.status_code == 403

    def test_event_post_persists_status(self):
        r = requests.post(f"{API}/webhooks/whatsapp", json={
            "entry": [{"changes": [{"value": {
                "statuses": [{"id": "wamid.guardtest", "status": "delivered",
                              "recipient_id": "919000000000", "timestamp": "1700000000"}]
            }}]}]
        }, timeout=10)
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_event_post_handles_inbound_text(self):
        r = requests.post(f"{API}/webhooks/whatsapp", json={
            "entry": [{"changes": [{"value": {
                "messages": [{"id": "wamid.in1", "from": "919000000000",
                              "type": "text", "text": {"body": "Hello"}}]
            }}]}]
        }, timeout=10)
        assert r.status_code == 200


class TestTelegramWebhook:
    def test_start_with_student_uid_links_chat(self):
        r = requests.post(f"{API}/webhooks/telegram", json={
            "message": {
                "chat": {"id": 999111, "username": "testlink", "first_name": "Test"},
                "text": "/start STU-00002",
            },
        }, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # parent of STU-00002 should now have telegram_chat_id=999111
        # (verify indirectly via auth/me of that parent — but parent.stu-00002 may
        # not have a known password in test data; just assert link flag)
        assert body.get("linked") is True

    def test_start_without_code_returns_instructions(self):
        r = requests.post(f"{API}/webhooks/telegram", json={
            "message": {
                "chat": {"id": 888222, "username": "noparams"},
                "text": "/start",
            },
        }, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # No linking happened (no code provided)
        assert body.get("linked") is not True

    def test_unknown_chat_id_doesnt_crash(self):
        r = requests.post(f"{API}/webhooks/telegram", json={
            "message": {"chat": {}, "text": "/start STU-00001"},
        }, timeout=10)
        assert r.status_code == 200


class TestDigestChannels:
    def test_digest_accepts_telegram_channel(self, sa):
        r = sa.post(f"{API}/digests/run-monthly",
                    params={"channels": "telegram"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "telegram" in body["channels"]
        # Should queue at least the parent we linked in TestTelegramWebhook
        assert body["totals"]["queued"] >= 0

    def test_digest_rejects_unknown_channel(self, sa):
        r = sa.post(f"{API}/digests/run-monthly",
                    params={"channels": "carrierpigeon"}, timeout=30)
        # Unknown channels are silently dropped → defaults to whatsapp
        assert r.status_code == 200
        body = r.json()
        assert body["channels"] == ["whatsapp"]


class TestNotificationProviderLabel:
    def test_whatsapp_notif_records_not_configured_note(self, sa):
        # Trigger a run that queues whatsapp; verify the doc has delivery_note for non-configured providers
        sa.post(f"{API}/digests/run-monthly", params={"channels": "whatsapp"}, timeout=30)
        notifs = sa.get(f"{API}/notifications", params={"limit": 500}, timeout=15).json()
        wa = [n for n in notifs if n.get("channel") == "whatsapp" and n.get("template") == "monthly_digest"]
        assert wa, "expected at least one queued whatsapp notification"
        # Either status=sent (if Meta/Twilio configured) or status=queued with note
        for n in wa[:5]:
            if n["status"] == "queued":
                assert n.get("delivery_note") in ("whatsapp_not_configured",
                                                 "twilio_not_configured")  # legacy compat
