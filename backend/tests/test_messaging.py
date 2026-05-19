"""Backend tests for the new in-app messaging (chat) feature.

Covers REST endpoints (contacts, conversations, messages, read, typing, unread-count)
and the WebSocket endpoint (connect + receive `message`/`read` events).
"""
from __future__ import annotations

import asyncio
import json
import os
import time

import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://case-insensitive-id.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRINCIPAL = ("principal@sunrise.edu", "School@123", "school_admin")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")
TEACHER2 = ("rohit@sunrise.edu", "Teacher@123", "teacher")  # not class teacher of parent's kids
PARENT1 = ("parent.stu-00001@sunrise.edu", "Parent@123", "parent")
PARENT2 = ("parent.stu-00002@sunrise.edu", "Parent@123", "parent")


def _login(email: str, password: str, role: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sessions():
    return {
        "admin": _login(*PRINCIPAL),
        "teacher": _login(*TEACHER),
        "teacher2": _login(*TEACHER2),
        "parent1": _login(*PARENT1),
        "parent2": _login(*PARENT2),
    }


@pytest.fixture(scope="module")
def users(sessions):
    # Fetch user IDs via /auth/me
    out = {}
    for key, s in sessions.items():
        r = s.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 200, f"/auth/me failed for {key}: {r.text}"
        out[key] = r.json()
    return out


# ---------- /contacts ----------
class TestContacts:
    def test_admin_sees_all_teachers(self, sessions, users):
        r = sessions["admin"].get(f"{API}/messaging/contacts", timeout=20)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["contacts"]]
        assert users["teacher"]["id"] in ids
        assert users["teacher2"]["id"] in ids
        # iter34: admin contact matrix expanded — admin now also sees parents
        # and accounts users (in addition to teachers). Verify parents are
        # included (was previously asserted absent).
        assert users["parent1"]["id"] in ids

    def test_teacher_sees_admin_and_own_class_parents(self, sessions, users):
        r = sessions["teacher"].get(f"{API}/messaging/contacts", timeout=20)
        assert r.status_code == 200
        contacts = r.json()["contacts"]
        ids = [c["id"] for c in contacts]
        assert users["admin"]["id"] in ids
        assert users["parent1"]["id"] in ids  # Grade 5-A parent
        # priya is class teacher of 5-A only — must not see teacher2/admin's-class parents
        # parent2 also in 5-A → also expected
        assert users["parent2"]["id"] in ids

    def test_parent_sees_only_class_teacher(self, sessions, users):
        r = sessions["parent1"].get(f"{API}/messaging/contacts", timeout=20)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()["contacts"]]
        assert users["teacher"]["id"] in ids
        assert users["teacher2"]["id"] not in ids
        # iter34: parent contact matrix expanded — parents now ALSO see the
        # principal (school_admin). Previously this asserted admin not in ids.
        assert users["admin"]["id"] in ids


# ---------- send / list messages ----------
class TestMessaging:
    def test_teacher_send_to_allowed_parent_persists(self, sessions, users):
        peer = users["parent1"]["id"]
        text = f"TEST_msg_{int(time.time())}"
        r = sessions["teacher"].post(f"{API}/messaging/conversations/{peer}/messages", json={"text": text}, timeout=20)
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg["text"] == text
        assert msg["sender_id"] == users["teacher"]["id"]
        assert msg["recipient_id"] == peer
        # GET back
        g = sessions["teacher"].get(f"{API}/messaging/conversations/{peer}/messages", timeout=20)
        assert g.status_code == 200
        msgs = g.json()["messages"]
        assert any(m["text"] == text for m in msgs)
        # chronological order
        times = [m["created_at"] for m in msgs]
        assert times == sorted(times)

    def test_teacher_cannot_send_to_disallowed_parent(self, sessions, users):
        # teacher2 (rohit) has no students -> cannot chat with parent1
        peer = users["parent1"]["id"]
        r = sessions["teacher2"].post(f"{API}/messaging/conversations/{peer}/messages", json={"text": "nope"}, timeout=20)
        assert r.status_code == 403

    def test_parent_cannot_send_to_non_class_teacher(self, sessions, users):
        peer = users["teacher2"]["id"]
        r = sessions["parent1"].post(f"{API}/messaging/conversations/{peer}/messages", json={"text": "nope"}, timeout=20)
        assert r.status_code == 403

    def test_parent_can_send_to_class_teacher(self, sessions, users):
        peer = users["teacher"]["id"]
        r = sessions["parent1"].post(f"{API}/messaging/conversations/{peer}/messages", json={"text": "TEST_parent_hello"}, timeout=20)
        assert r.status_code == 200

    def test_conversations_sorted_by_last_message_desc(self, sessions, users):
        r = sessions["teacher"].get(f"{API}/messaging/conversations", timeout=20)
        assert r.status_code == 200
        convs = r.json()["conversations"]
        times = [c["last_message_at"] for c in convs if c["last_message_at"]]
        assert times == sorted(times, reverse=True)


# ---------- read receipts + unread count ----------
class TestReadReceipts:
    def test_read_and_unread_count(self, sessions, users):
        teacher_id = users["teacher"]["id"]
        parent_id = users["parent1"]["id"]
        # Teacher sends an unread message to parent
        r = sessions["teacher"].post(f"{API}/messaging/conversations/{parent_id}/messages",
                                      json={"text": "TEST_unread"}, timeout=20)
        assert r.status_code == 200

        # Parent unread > 0
        u = sessions["parent1"].get(f"{API}/messaging/unread-count", timeout=20).json()["count"]
        assert u >= 1

        # Parent marks read
        rr = sessions["parent1"].post(f"{API}/messaging/conversations/{teacher_id}/read", timeout=20)
        assert rr.status_code == 200
        assert rr.json()["ok"] is True

        # Parent unread drops
        u2 = sessions["parent1"].get(f"{API}/messaging/unread-count", timeout=20).json()["count"]
        assert u2 < u or u2 == 0

        # Parent still sees the messages (not deleted)
        msgs = sessions["parent1"].get(f"{API}/messaging/conversations/{teacher_id}/messages", timeout=20).json()["messages"]
        assert any(m["text"] == "TEST_unread" for m in msgs)
        # And the read_at is set for those incoming
        incoming = [m for m in msgs if m["recipient_id"] == parent_id]
        assert any(m.get("read_at") for m in incoming)


# ---------- typing ----------
class TestTyping:
    def test_typing_allowed_peer(self, sessions, users):
        r = sessions["teacher"].post(f"{API}/messaging/conversations/{users['parent1']['id']}/typing",
                                      json={"is_typing": True}, timeout=20)
        assert r.status_code == 200

    def test_typing_disallowed_peer(self, sessions, users):
        r = sessions["parent1"].post(f"{API}/messaging/conversations/{users['teacher2']['id']}/typing",
                                      json={"is_typing": True}, timeout=20)
        assert r.status_code == 403


# ---------- WebSocket ----------
def _get_access_token_from_session(s: requests.Session) -> str:
    for c in s.cookies:
        if c.name == "access_token":
            return c.value
    raise AssertionError("access_token cookie not present")


@pytest.mark.asyncio
async def test_ws_connects_and_receives_message(sessions, users):
    teacher_token = _get_access_token_from_session(sessions["teacher"])
    parent_token = _get_access_token_from_session(sessions["parent1"])
    ws_base = BASE_URL.replace("http", "ws", 1)
    parent_url = f"{ws_base}/api/messaging/ws?token={parent_token}"
    teacher_url = f"{ws_base}/api/messaging/ws?token={teacher_token}"

    async with websockets.connect(parent_url, open_timeout=20) as p_ws, \
               websockets.connect(teacher_url, open_timeout=20) as t_ws:
        # Connected events
        p_hello = json.loads(await asyncio.wait_for(p_ws.recv(), 10))
        t_hello = json.loads(await asyncio.wait_for(t_ws.recv(), 10))
        assert p_hello["type"] == "connected"
        assert t_hello["type"] == "connected"
        assert p_hello["user_id"] == users["parent1"]["id"]

        # Teacher sends a message via REST → parent WS should receive it
        text = f"TEST_ws_{int(time.time())}"
        r = sessions["teacher"].post(
            f"{API}/messaging/conversations/{users['parent1']['id']}/messages",
            json={"text": text}, timeout=20,
        )
        assert r.status_code == 200

        # Wait for the message event on parent side
        got_msg = False
        for _ in range(5):
            try:
                raw = await asyncio.wait_for(p_ws.recv(), 5)
            except asyncio.TimeoutError:
                break
            evt = json.loads(raw)
            if evt.get("type") == "message" and evt["message"]["text"] == text:
                got_msg = True
                break
        assert got_msg, "parent WS did not receive expected message event"

        # Parent calls /read → teacher WS receives `read` event
        rr = sessions["parent1"].post(
            f"{API}/messaging/conversations/{users['teacher']['id']}/read", timeout=20,
        )
        assert rr.status_code == 200
        got_read = False
        for _ in range(5):
            try:
                raw = await asyncio.wait_for(t_ws.recv(), 5)
            except asyncio.TimeoutError:
                break
            evt = json.loads(raw)
            if evt.get("type") == "read" and evt.get("by") == users["parent1"]["id"]:
                got_read = True
                break
        assert got_read, "teacher WS did not receive expected read event"
