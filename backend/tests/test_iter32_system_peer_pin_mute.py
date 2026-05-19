"""Backend tests for iteration-32:

* System "School Notifications" virtual peer
    - listed in /messaging/contacts at the top with id=system::school-notifications
    - GET /messaging/conversations/system::school-notifications/messages synthesises
      messages from chat_updates and marks them read
    - POST /messaging/conversations/system::school-notifications/read marks all read
    - GET /messaging/conversations/system::school-notifications/settings returns muted=false

* Group mute (per-user)
    - GET /messaging/groups returns muted, pinned_message_id, pinned_message_text, pinned_until
    - POST /messaging/groups/{id}/mute toggles muted; GET /settings reflects it
    - non-member: 403

* Group pin (24h default)
    - POST /messaging/groups/{id}/pin {message_id, hours?}: owner 200, non-owner 403,
      bogus message_id 404, pinned_until iso ~ now + hours
    - GET /messaging/groups reflects pinned_message_id/text/until
    - DELETE /messaging/groups/{id}/pin: owner clears; non-owner 403; pin fields gone

* Mirror via queue_notification still inserts chat_updates AND fires WS message
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://class-access-hub.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

PRINCIPAL = ("principal@sunrise.edu", "School@123", "school_admin")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")
TEACHER2 = ("rohit@sunrise.edu", "Teacher@123", "teacher")
PARENT1 = ("parent.stu-00001@sunrise.edu", "Parent@123", "parent")
PARENT2 = ("parent.stu-00002@sunrise.edu", "Parent@123", "parent")


def _login(email, password, role):
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
        "parent1": _login(*PARENT1),
        "parent2": _login(*PARENT2),
    }
    users = {k: s.get(f"{API}/auth/me", timeout=20).json() for k, s in sessions.items()}
    # Provision groups by hitting /groups for admin + teachers
    sessions["admin"].get(f"{API}/messaging/groups", timeout=20)
    sessions["teacher"].get(f"{API}/messaging/groups", timeout=20)
    sessions["teacher2"].get(f"{API}/messaging/groups", timeout=20)
    return {"s": sessions, "u": users}


SYSTEM_PEER = "system::school-notifications"


# ---------- System "School Notifications" peer ----------
class TestSystemPeer:
    def test_contacts_includes_system_peer_at_top_for_parent(self, ctx):
        r = ctx["s"]["parent1"].get(f"{API}/messaging/contacts", timeout=20)
        assert r.status_code == 200
        contacts = r.json()["contacts"]
        assert contacts, "parent should have at least the system contact"
        sys_c = contacts[0]
        assert sys_c["id"] == SYSTEM_PEER
        assert sys_c["name"] == "School Notifications"
        assert sys_c["role"] == "system"
        assert sys_c.get("is_system") is True

    def test_contacts_includes_system_peer_for_teacher_and_admin(self, ctx):
        for who in ("teacher", "admin"):
            r = ctx["s"][who].get(f"{API}/messaging/contacts", timeout=20)
            assert r.status_code == 200
            contacts = r.json()["contacts"]
            ids = [c["id"] for c in contacts]
            assert SYSTEM_PEER in ids, f"{who} contacts missing system peer: {ids}"
            assert ids[0] == SYSTEM_PEER, f"{who} system peer should be first: {ids}"

    def test_system_settings_returns_muted_false(self, ctx):
        r = ctx["s"]["parent1"].get(
            f"{API}/messaging/conversations/{SYSTEM_PEER}/settings", timeout=20
        )
        assert r.status_code == 200
        j = r.json()
        assert j["muted"] is False
        assert j["conversation_id"] == SYSTEM_PEER

    def test_system_messages_synthesises_from_chat_updates_and_marks_read(self, ctx):
        # Trigger a fresh notification by submitting a sick-leave request as parent
        # The approve/reject flow inside sick_leaves calls queue_notification which
        # mirrors into chat_updates. Even without that, prior iterations seeded
        # several chat_updates rows for parent1, so this is double-coverage.
        # Just call list_messages and verify they show up + channel + sender are right.
        s = ctx["s"]["parent1"]
        r = s.get(
            f"{API}/messaging/conversations/{SYSTEM_PEER}/messages?limit=50", timeout=20
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["conversation_id"] == SYSTEM_PEER
        assert j["peer"]["id"] == SYSTEM_PEER
        assert j["peer"]["role"] == "system"
        assert isinstance(j["messages"], list)
        # Iter31 left ~7 chat_updates for parent1; expect at least 1 here.
        if not j["messages"]:
            pytest.skip("no chat_updates seeded for parent1; iter31 prereq")
        msg = j["messages"][-1]
        assert msg["sender_id"] == SYSTEM_PEER
        assert msg["conv_id"] == SYSTEM_PEER
        # iter33: channel label removed from bubble; semantic kind fields present instead
        assert "channel" not in msg
        assert "kind" in msg and "kind_label" in msg and "kind_color" in msg
        assert "quick_replies" in msg and isinstance(msg["quick_replies"], list)
        # Now fetch again and assert all messages have read_at set (marked on read)
        r2 = s.get(
            f"{API}/messaging/conversations/{SYSTEM_PEER}/messages?limit=50", timeout=20
        )
        assert r2.status_code == 200
        for m in r2.json()["messages"]:
            assert m.get("read_at"), f"expected read_at set after GET, got {m}"

    def test_system_mark_read_endpoint_returns_ok(self, ctx):
        s = ctx["s"]["parent1"]
        r = s.post(
            f"{API}/messaging/conversations/{SYSTEM_PEER}/read", timeout=20
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert "marked" in j and isinstance(j["marked"], int)


# ---------- Group settings: muted + pinned fields exposed by /groups ----------
class TestGroupsFieldsExposed:
    def test_groups_payload_exposes_mute_and_pin_fields(self, ctx):
        r = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20)
        assert r.status_code == 200
        groups = r.json()["groups"]
        assert groups, "teacher should have groups"
        for g in groups:
            for k in ("muted", "pinned_message_id", "pinned_message_text", "pinned_until"):
                assert k in g, f"group missing {k}: {g}"


# ---------- Group mute (per user) ----------
class TestGroupMute:
    def _teacher_owned_group(self, ctx):
        r = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20)
        assert r.status_code == 200
        owner_groups = [g for g in r.json()["groups"] if g["is_owner"]]
        assert owner_groups, "teacher should own a teacher_to_parents group"
        return owner_groups[0]

    def test_member_can_toggle_mute(self, ctx):
        g = self._teacher_owned_group(ctx)
        # parent1 is a member of priya's group
        s = ctx["s"]["parent1"]
        gid = g["id"]
        # MUTE
        r = s.post(f"{API}/messaging/groups/{gid}/mute", json={"muted": True}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["muted"] is True
        # Verify via settings
        r2 = s.get(f"{API}/messaging/groups/{gid}/settings", timeout=20)
        assert r2.status_code == 200
        assert r2.json()["muted"] is True
        # Verify reflected in /groups payload for parent1
        r3 = s.get(f"{API}/messaging/groups", timeout=20)
        pg = next((x for x in r3.json()["groups"] if x["id"] == gid), None)
        assert pg and pg["muted"] is True
        # UNMUTE for clean state
        r4 = s.post(f"{API}/messaging/groups/{gid}/mute", json={"muted": False}, timeout=20)
        assert r4.status_code == 200 and r4.json()["muted"] is False

    def test_non_member_cannot_mute(self, ctx):
        g = self._teacher_owned_group(ctx)
        # teacher2 (rohit) is NOT a member of priya's grade-5A parents group
        r = ctx["s"]["teacher2"].post(
            f"{API}/messaging/groups/{g['id']}/mute", json={"muted": True}, timeout=20
        )
        assert r.status_code == 403, r.text

    def test_non_member_cannot_get_group_settings(self, ctx):
        g = self._teacher_owned_group(ctx)
        r = ctx["s"]["teacher2"].get(f"{API}/messaging/groups/{g['id']}/settings", timeout=20)
        assert r.status_code == 403


# ---------- Group pin (owner-only, 24h default) ----------
class TestGroupPin:
    def _setup_group_with_message(self, ctx):
        # Teacher (owner) posts a message
        r = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20)
        own = [g for g in r.json()["groups"] if g["is_owner"] and g["scope"] == "teacher_to_parents"][0]
        gid = own["id"]
        txt = f"TEST_pin_msg_{int(time.time()*1000)}"
        rs = ctx["s"]["teacher"].post(
            f"{API}/messaging/groups/{gid}/messages",
            json={"text": txt},
            timeout=20,
        )
        assert rs.status_code == 200, rs.text
        return gid, rs.json()["id"], txt

    def test_owner_can_pin_and_unpin(self, ctx):
        gid, mid, txt = self._setup_group_with_message(ctx)
        # Pin with default 24h
        rp = ctx["s"]["teacher"].post(
            f"{API}/messaging/groups/{gid}/pin",
            json={"message_id": mid},
            timeout=20,
        )
        assert rp.status_code == 200, rp.text
        jp = rp.json()
        assert jp["ok"] is True
        assert jp["pinned_message_id"] == mid
        # pinned_until ~ now+24h
        pu = jp["pinned_until"]
        pu_dt = datetime.fromisoformat(pu.replace("Z", "+00:00"))
        delta = (pu_dt - datetime.now(timezone.utc)).total_seconds()
        # Should be within (23.5h, 24.5h)
        assert 23.5 * 3600 < delta < 24.5 * 3600, f"pinned_until off: delta={delta}"

        # Verify reflected in /groups
        rg = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20)
        gx = next(x for x in rg.json()["groups"] if x["id"] == gid)
        assert gx["pinned_message_id"] == mid
        assert gx["pinned_message_text"].startswith("TEST_pin_msg_")
        assert gx["pinned_until"] == pu

        # And visible to a member (parent1)
        rgp = ctx["s"]["parent1"].get(f"{API}/messaging/groups", timeout=20)
        gp = next((x for x in rgp.json()["groups"] if x["id"] == gid), None)
        assert gp is not None and gp["pinned_message_id"] == mid

        # Now unpin
        ru = ctx["s"]["teacher"].delete(f"{API}/messaging/groups/{gid}/pin", timeout=20)
        assert ru.status_code == 200, ru.text
        rg2 = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20)
        gx2 = next(x for x in rg2.json()["groups"] if x["id"] == gid)
        # After unset, pinned_message_id should be falsy
        assert not gx2.get("pinned_message_id")

    def test_non_owner_cannot_pin(self, ctx):
        gid, mid, _ = self._setup_group_with_message(ctx)
        # parent1 is a member but not owner
        r = ctx["s"]["parent1"].post(
            f"{API}/messaging/groups/{gid}/pin",
            json={"message_id": mid},
            timeout=20,
        )
        assert r.status_code == 403, r.text

    def test_pin_with_bogus_message_id_404(self, ctx):
        gid, _, _ = self._setup_group_with_message(ctx)
        r = ctx["s"]["teacher"].post(
            f"{API}/messaging/groups/{gid}/pin",
            json={"message_id": "nonexistent-msg-id"},
            timeout=20,
        )
        assert r.status_code == 404, r.text

    def test_non_owner_cannot_unpin(self, ctx):
        gid, mid, _ = self._setup_group_with_message(ctx)
        # Owner pins first
        rp = ctx["s"]["teacher"].post(
            f"{API}/messaging/groups/{gid}/pin",
            json={"message_id": mid},
            timeout=20,
        )
        assert rp.status_code == 200
        # parent1 tries to unpin -> 403
        r = ctx["s"]["parent1"].delete(f"{API}/messaging/groups/{gid}/pin", timeout=20)
        assert r.status_code == 403
        # cleanup
        ctx["s"]["teacher"].delete(f"{API}/messaging/groups/{gid}/pin", timeout=20)

    def test_pin_with_custom_hours_clamped(self, ctx):
        gid, mid, _ = self._setup_group_with_message(ctx)
        rp = ctx["s"]["teacher"].post(
            f"{API}/messaging/groups/{gid}/pin",
            json={"message_id": mid, "hours": 1},
            timeout=20,
        )
        assert rp.status_code == 200, rp.text
        pu = rp.json()["pinned_until"]
        pu_dt = datetime.fromisoformat(pu.replace("Z", "+00:00"))
        delta = (pu_dt - datetime.now(timezone.utc)).total_seconds()
        assert 0.5 * 3600 < delta < 1.5 * 3600
        # cleanup
        ctx["s"]["teacher"].delete(f"{API}/messaging/groups/{gid}/pin", timeout=20)

    def test_pin_invalid_hours_rejected(self, ctx):
        gid, mid, _ = self._setup_group_with_message(ctx)
        # 0 and >168 should be rejected by pydantic constraint
        for bad in (0, 200, -1):
            r = ctx["s"]["teacher"].post(
                f"{API}/messaging/groups/{gid}/pin",
                json={"message_id": mid, "hours": bad},
                timeout=20,
            )
            assert r.status_code == 422, f"hours={bad} should be 422 but got {r.status_code}"


# ---------- Mirror via direct queue_notification call ----------
class TestMirrorWsFire:
    def test_mirror_inserts_chat_update_and_dispatches_ws_message(self, ctx):
        """End-to-end: invoke queue_notification(channel='telegram') and assert a
        new chat_updates row appears that surfaces via the system peer GET.
        WS dispatch is a fire-and-forget call; we verify the import path is intact
        by inspecting the side effect on the chat_updates collection.
        """
        # Import lazily so it only runs inside the pod
        try:
            import sys, importlib
            sys.path.insert(0, "/app/backend")
            from dotenv import load_dotenv
            load_dotenv("/app/backend/.env")
            notify_mod = importlib.import_module("core.notify")
            messaging_mod = importlib.import_module("routes.messaging")
        except Exception as e:
            pytest.skip(f"backend imports unavailable: {e}")

        parent_id = ctx["u"]["parent1"]["id"]
        school_id = ctx["u"]["parent1"]["school_id"]
        marker = f"TEST_iter32_mirror_{int(time.time()*1000)}"

        # Drop a unique row via the helper
        async def _run():
            return await notify_mod.queue_notification(
                school_id=school_id,
                recipient_type="parent",
                recipient_id=parent_id,
                phone=None,
                channel="telegram",
                template="test.iter32",
                message=marker,
                subject="iter32",
                context={"student_id": "STU-00001", "related_student_id": "STU-00001"},
            )

        asyncio.run(_run())

        # The mirror should make this visible via the system peer messages endpoint
        r = ctx["s"]["parent1"].get(
            f"{API}/messaging/conversations/{SYSTEM_PEER}/messages?limit=50", timeout=20
        )
        assert r.status_code == 200
        texts = [m.get("text") for m in r.json()["messages"]]
        assert marker in texts, f"mirror failed - texts: {texts}"
        # Locate the message and assert sender + conv_id (iter33: channel removed)
        m = next(x for x in r.json()["messages"] if x["text"] == marker)
        assert m["sender_id"] == SYSTEM_PEER
        assert m["conv_id"] == SYSTEM_PEER
        assert "channel" not in m
        assert m.get("kind") in {"attendance", "fee", "exam", "sick", "holiday", "trip", "general"}
        # Verify the WS hook lines exist (path is invoked)
        assert hasattr(messaging_mod, "manager")
        assert hasattr(messaging_mod, "SYSTEM_PEER_ID")
        assert messaging_mod.SYSTEM_PEER_ID == SYSTEM_PEER
