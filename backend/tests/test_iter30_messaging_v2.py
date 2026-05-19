"""Backend tests for iteration-30 messaging additions:
mute toggle, @mentions, image/PDF attachments, web-push subscribe/unsubscribe,
push/config, history cap (CHAT_HISTORY_MAX), and unread-count behavior with
muted convs / mentions break-through.
"""
from __future__ import annotations

import base64
import os
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://case-insensitive-id.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

PRINCIPAL = ("principal@sunrise.edu", "School@123", "school_admin")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")
TEACHER2 = ("rohit@sunrise.edu", "Teacher@123", "teacher")  # Grade 6-A — unmapped to STU-00001
PARENT1 = ("parent.stu-00001@sunrise.edu", "Parent@123", "parent")

# 1x1 transparent PNG
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


def _login(email: str, password: str, role: str) -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "role": role},
        timeout=20,
    )
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ctx():
    sessions = {
        "admin": _login(*PRINCIPAL),
        "teacher": _login(*TEACHER),
        "teacher2": _login(*TEACHER2),
        "parent": _login(*PARENT1),
    }
    users = {}
    for k, s in sessions.items():
        users[k] = s.get(f"{API}/auth/me", timeout=20).json()
    return {"s": sessions, "u": users}


# ---------- Mute ----------
class TestMute:
    def test_mute_set_get_unset(self, ctx):
        teacher_id = ctx["u"]["teacher"]["id"]
        s = ctx["s"]["parent"]

        # ensure starting unmuted
        s.post(
            f"{API}/messaging/conversations/{teacher_id}/mute",
            json={"muted": False},
            timeout=20,
        )
        g = s.get(f"{API}/messaging/conversations/{teacher_id}/settings", timeout=20)
        assert g.status_code == 200
        body = g.json()
        assert "conversation_id" in body and body["muted"] is False

        # mute
        r = s.post(
            f"{API}/messaging/conversations/{teacher_id}/mute",
            json={"muted": True},
            timeout=20,
        )
        assert r.status_code == 200 and r.json()["muted"] is True

        # readback
        g2 = s.get(f"{API}/messaging/conversations/{teacher_id}/settings", timeout=20)
        assert g2.status_code == 200 and g2.json()["muted"] is True

        # unmute
        r2 = s.post(
            f"{API}/messaging/conversations/{teacher_id}/mute",
            json={"muted": False},
            timeout=20,
        )
        assert r2.status_code == 200 and r2.json()["muted"] is False
        g3 = s.get(f"{API}/messaging/conversations/{teacher_id}/settings", timeout=20)
        assert g3.json()["muted"] is False

    def test_mute_disallowed_peer(self, ctx):
        # iter34: admin↔parent is now an OPEN_PAIR. Use teacher2 (rohit, Grade
        # 6-A class teacher) muting parent1 (STU-00001 in 5-A) — this teacher
        # has no class-teacher mapping for parent1's child, so muting that
        # disallowed peer must still 403.
        parent_id = ctx["u"]["parent"]["id"]
        r = ctx["s"]["teacher2"].post(
            f"{API}/messaging/conversations/{parent_id}/mute",
            json={"muted": True},
            timeout=20,
        )
        assert r.status_code == 403


# ---------- Unread count w/ mute + mentions ----------
class TestUnreadAndMentions:
    def test_muted_plain_excluded_but_mention_breaks_through(self, ctx):
        teacher_id = ctx["u"]["teacher"]["id"]
        parent_id = ctx["u"]["parent"]["id"]
        s_t = ctx["s"]["teacher"]
        s_p = ctx["s"]["parent"]
        parent_name = ctx["u"]["parent"]["name"]

        # parent clears any pending unreads first
        s_p.post(f"{API}/messaging/conversations/{teacher_id}/read", timeout=20)
        # parent mutes thread
        s_p.post(
            f"{API}/messaging/conversations/{teacher_id}/mute",
            json={"muted": True},
            timeout=20,
        )

        before = s_p.get(f"{API}/messaging/unread-count", timeout=20).json()
        assert "count" in before and "mentions" in before
        base_count = before["count"]
        base_mentions = before["mentions"]

        # Teacher sends a plain (non-mention) message
        r = s_t.post(
            f"{API}/messaging/conversations/{parent_id}/messages",
            json={"text": f"TEST_plain_{int(time.time())}"},
            timeout=20,
        )
        assert r.status_code == 200
        assert r.json().get("mentions") in ([], None) or len(r.json()["mentions"]) == 0

        after_plain = s_p.get(f"{API}/messaging/unread-count", timeout=20).json()
        # count should NOT increase (muted)
        assert after_plain["count"] == base_count, after_plain
        assert after_plain["mentions"] == base_mentions

        # Teacher sends a @mention message — must bypass mute on count
        first = (parent_name or "").split()[0] or parent_name
        text = f"Hello @{first} TEST_mention_{int(time.time())}"
        r2 = s_t.post(
            f"{API}/messaging/conversations/{parent_id}/messages",
            json={"text": text},
            timeout=20,
        )
        assert r2.status_code == 200
        body = r2.json()
        assert isinstance(body.get("mentions"), list) and parent_id in body["mentions"], body

        after_mention = s_p.get(f"{API}/messaging/unread-count", timeout=20).json()
        assert after_mention["mentions"] == base_mentions + 1, after_mention
        assert after_mention["count"] == base_count + 1, after_mention

        # Parent reads -> both zero for the reader on this conv
        rr = s_p.post(f"{API}/messaging/conversations/{teacher_id}/read", timeout=20)
        assert rr.status_code == 200
        cleared = s_p.get(f"{API}/messaging/unread-count", timeout=20).json()
        # count returned to base_count (mute again applies for any leftover unreads)
        assert cleared["mentions"] <= base_mentions
        assert cleared["count"] <= base_count

        # cleanup: unmute
        s_p.post(
            f"{API}/messaging/conversations/{teacher_id}/mute",
            json={"muted": False},
            timeout=20,
        )


# ---------- Attachments ----------
class TestAttachments:
    def test_send_image_attachment(self, ctx):
        parent_id = ctx["u"]["parent"]["id"]
        s = ctx["s"]["teacher"]
        att = {
            "name": "pixel.png",
            "type": "image/png",
            "size": len(PNG_BYTES),
            "data_url": PNG_DATA_URL,
        }
        r = s.post(
            f"{API}/messaging/conversations/{parent_id}/messages",
            json={"text": "", "attachment": att},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg.get("attachment") and msg["attachment"]["type"] == "image/png"
        assert msg["attachment"]["data_url"].startswith("data:image/png")

    def test_reject_unsupported_mime(self, ctx):
        parent_id = ctx["u"]["parent"]["id"]
        att = {
            "name": "evil.txt",
            "type": "text/plain",
            "size": 4,
            "data_url": "data:text/plain;base64,YWJjZA==",
        }
        r = ctx["s"]["teacher"].post(
            f"{API}/messaging/conversations/{parent_id}/messages",
            json={"text": "", "attachment": att},
            timeout=20,
        )
        assert r.status_code == 400, r.text

    def test_reject_empty_message(self, ctx):
        parent_id = ctx["u"]["parent"]["id"]
        r = ctx["s"]["teacher"].post(
            f"{API}/messaging/conversations/{parent_id}/messages",
            json={"text": "", "attachment": None},
            timeout=20,
        )
        assert r.status_code == 400

    def test_reject_mismatched_data_url(self, ctx):
        parent_id = ctx["u"]["parent"]["id"]
        att = {
            "name": "pixel.png",
            "type": "image/png",
            "size": len(PNG_BYTES),
            "data_url": "data:image/jpeg;base64," + base64.b64encode(PNG_BYTES).decode(),
        }
        r = ctx["s"]["teacher"].post(
            f"{API}/messaging/conversations/{parent_id}/messages",
            json={"text": "", "attachment": att},
            timeout=20,
        )
        assert r.status_code == 400


# ---------- History cap ----------
class TestHistoryCap:
    def test_history_trimmed_to_max(self, ctx):
        teacher_id = ctx["u"]["teacher"]["id"]
        parent_id = ctx["u"]["parent"]["id"]
        s_t = ctx["s"]["teacher"]
        s_p = ctx["s"]["parent"]

        # send 15 messages alternating
        stamp = int(time.time())
        for i in range(15):
            sender = s_t if i % 2 == 0 else s_p
            peer = parent_id if i % 2 == 0 else teacher_id
            r = sender.post(
                f"{API}/messaging/conversations/{peer}/messages",
                json={"text": f"TEST_hist_{stamp}_{i}"},
                timeout=20,
            )
            assert r.status_code == 200, r.text

        # GET messages — should be at most CHAT_HISTORY_MAX (10)
        g = s_t.get(
            f"{API}/messaging/conversations/{parent_id}/messages?limit=100",
            timeout=20,
        )
        assert g.status_code == 200
        msgs = g.json()["messages"]
        cap = int(os.environ.get("CHAT_HISTORY_MAX", "10"))
        assert len(msgs) <= cap, f"expected <= {cap}, got {len(msgs)}"


# ---------- Push ----------
class TestPush:
    def test_push_config(self, ctx):
        r = ctx["s"]["teacher"].get(f"{API}/messaging/push/config", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "public_key" in body
        assert body.get("enabled") is True
        assert len(body["public_key"]) > 20

    def test_push_subscribe_and_unsubscribe(self, ctx):
        endpoint = f"https://fcm.googleapis.com/fcm/send/TEST_{int(time.time())}"
        payload = {
            "endpoint": endpoint,
            "keys": {
                "p256dh": "BHt" + "A" * 85,
                "auth": "C" * 22,
            },
        }
        r = ctx["s"]["teacher"].post(
            f"{API}/messaging/push/subscribe", json=payload, timeout=20
        )
        assert r.status_code == 200 and r.json().get("ok") is True

        # Re-subscribe with same endpoint should upsert (no error)
        r2 = ctx["s"]["teacher"].post(
            f"{API}/messaging/push/subscribe", json=payload, timeout=20
        )
        assert r2.status_code == 200

        # Unsubscribe
        r3 = ctx["s"]["teacher"].post(
            f"{API}/messaging/push/unsubscribe",
            json={"endpoint": endpoint},
            timeout=20,
        )
        assert r3.status_code == 200
        assert r3.json().get("removed", 0) >= 1
