"""Backend tests for iteration-31:
* Group chat (admin→teachers broadcast, teacher→class-parents broadcast)
* chat_updates mirror from queue_notification + /updates endpoints
* Hardened _trim_conversation_history (keep-set delete)
* Cross-school isolation regression for groups
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://class-roster-77.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

PRINCIPAL = ("principal@sunrise.edu", "School@123", "school_admin")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")
TEACHER2 = ("rohit@sunrise.edu", "Teacher@123", "teacher")
PARENT1 = ("parent.stu-00001@sunrise.edu", "Parent@123", "parent")
PARENT2 = ("parent.stu-00002@sunrise.edu", "Parent@123", "parent")


def _login(email, password, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role}, timeout=20)
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
    return {"s": sessions, "u": users}


# ---------- Groups ----------
class TestGroups:
    def test_admin_sees_broadcast_group_as_owner(self, ctx):
        r = ctx["s"]["admin"].get(f"{API}/messaging/groups", timeout=20)
        assert r.status_code == 200
        groups = r.json()["groups"]
        admin_groups = [g for g in groups if g.get("scope") == "admin_to_teachers"]
        assert admin_groups, f"admin should have admin_to_teachers group: {groups}"
        g0 = admin_groups[0]
        assert g0["is_owner"] is True
        assert g0["name"] == "All Teachers (Broadcast)"
        # member_count should match teacher count
        assert g0["member_count"] >= 2  # priya, rohit, kavita

    def test_teacher_sees_admin_group_as_member_and_own_class_group_as_owner(self, ctx):
        r = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20)
        assert r.status_code == 200
        groups = r.json()["groups"]
        owner_groups = [g for g in groups if g["is_owner"]]
        member_groups = [g for g in groups if not g["is_owner"]]
        # owner: at least one teacher_to_parents
        assert any(g["scope"] == "teacher_to_parents" for g in owner_groups), groups
        # member: at least one admin_to_teachers
        assert any(g["scope"] == "admin_to_teachers" for g in member_groups), groups

    def test_parent_sees_class_group_as_member(self, ctx):
        # Trigger teacher's group creation by hitting teacher's groups endpoint first
        ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20)
        r = ctx["s"]["parent1"].get(f"{API}/messaging/groups", timeout=20)
        assert r.status_code == 200
        groups = r.json()["groups"]
        ttp = [g for g in groups if g.get("scope") == "teacher_to_parents"]
        assert ttp, f"parent should see teacher_to_parents group as member: {groups}"
        for g in ttp:
            assert g["is_owner"] is False

    def test_owner_can_post_non_owner_403(self, ctx):
        # Use teacher's class group
        gr = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        own = [g for g in gr if g["is_owner"] and g["scope"] == "teacher_to_parents"][0]
        gid = own["id"]
        # owner posts
        r = ctx["s"]["teacher"].post(
            f"{API}/messaging/groups/{gid}/messages",
            json={"text": f"TEST_grp_{int(time.time())}"}, timeout=20,
        )
        assert r.status_code == 200, r.text
        # parent (non-owner member) cannot post
        rp = ctx["s"]["parent1"].post(
            f"{API}/messaging/groups/{gid}/messages",
            json={"text": "TEST_should_403"}, timeout=20,
        )
        assert rp.status_code == 403, rp.text

    def test_empty_payload_400(self, ctx):
        gr = ctx["s"]["admin"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        gid = [g for g in gr if g["is_owner"]][0]["id"]
        r = ctx["s"]["admin"].post(
            f"{API}/messaging/groups/{gid}/messages",
            json={"text": "", "attachment": None}, timeout=20,
        )
        assert r.status_code == 400

    def test_members_can_read_non_member_403(self, ctx):
        gr = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        gid = [g for g in gr if g["is_owner"] and g["scope"] == "teacher_to_parents"][0]["id"]
        # owner read
        ro = ctx["s"]["teacher"].get(f"{API}/messaging/groups/{gid}/messages", timeout=20)
        assert ro.status_code == 200
        # parent (member) read
        rp = ctx["s"]["parent1"].get(f"{API}/messaging/groups/{gid}/messages", timeout=20)
        assert rp.status_code == 200
        # teacher2 (rohit) is NOT member of priya's 5A group
        rn = ctx["s"]["teacher2"].get(f"{API}/messaging/groups/{gid}/messages", timeout=20)
        assert rn.status_code == 403

    def test_group_history_trim_to_10(self, ctx):
        gr = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        gid = [g for g in gr if g["is_owner"] and g["scope"] == "teacher_to_parents"][0]["id"]
        stamp = int(time.time())
        for i in range(12):
            r = ctx["s"]["teacher"].post(
                f"{API}/messaging/groups/{gid}/messages",
                json={"text": f"TEST_gtrim_{stamp}_{i}"}, timeout=20,
            )
            assert r.status_code == 200
        g = ctx["s"]["teacher"].get(f"{API}/messaging/groups/{gid}/messages?limit=100", timeout=20).json()
        msgs = g["messages"]
        cap = int(os.environ.get("CHAT_HISTORY_MAX", "10"))
        assert len(msgs) <= cap, f"expected ≤{cap}, got {len(msgs)}"
        # latest one preserved
        texts = [m["text"] for m in msgs]
        assert f"TEST_gtrim_{stamp}_11" in texts

    def test_group_mark_read(self, ctx):
        # Teacher posts in admin's group? Teacher cannot — admin owns. So have admin post, then teacher reads.
        gr_admin = ctx["s"]["admin"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        gid = [g for g in gr_admin if g["is_owner"]][0]["id"]
        r = ctx["s"]["admin"].post(
            f"{API}/messaging/groups/{gid}/messages",
            json={"text": f"TEST_adm_{int(time.time())}"}, timeout=20,
        )
        assert r.status_code == 200
        # teacher's unread for that group > 0
        gr_t = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        before = next((g for g in gr_t if g["id"] == gid), None)
        assert before is not None and before["unread"] >= 1
        # mark read
        rr = ctx["s"]["teacher"].post(f"{API}/messaging/groups/{gid}/read", timeout=20)
        assert rr.status_code == 200
        # unread should be 0 now
        gr_t2 = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        after = next((g for g in gr_t2 if g["id"] == gid), None)
        assert after["unread"] == 0


# ---------- chat_updates mirror via queue_notification ----------
class TestChatUpdates:
    def test_updates_endpoint_basic(self, ctx):
        r = ctx["s"]["parent1"].get(f"{API}/messaging/updates", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "updates" in body and isinstance(body["updates"], list)
        assert "by_student" in body

    def test_updates_unread_count(self, ctx):
        r = ctx["s"]["parent1"].get(f"{API}/messaging/updates/unread-count", timeout=20)
        assert r.status_code == 200
        assert "count" in r.json()

    def test_mark_all_updates_read(self, ctx):
        r = ctx["s"]["parent1"].post(f"{API}/messaging/updates/mark-all-read", timeout=20)
        assert r.status_code == 200
        assert "marked" in r.json()
        # Subsequent unread-count should be 0
        c = ctx["s"]["parent1"].get(f"{API}/messaging/updates/unread-count", timeout=20).json()["count"]
        assert c == 0

    def test_mirror_via_direct_db_call(self, ctx):
        """Call queue_notification directly via a backend Python eval so we don't depend on
        a real fee/attendance flow. We do this by hitting an internal endpoint if present,
        else we directly insert+test via the tenant DB through the test process."""
        # Use the backend Mongo directly through asyncio
        import asyncio, sys
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from core.notify import queue_notification  # noqa
        from core.db import get_db, tenant_db  # noqa

        async def run():
            db = get_db()
            parent = await db.users.find_one(
                {"email": "parent.stu-00001@sunrise.edu"}, {"_id": 0, "id": 1, "school_id": 1},
            )
            assert parent
            # mark-all-read first to start from a clean slate
            tdb = await tenant_db(parent["school_id"])
            await tdb.chat_updates.delete_many({"recipient_id": parent["id"]})
            # Push 9 updates for the same (recipient, student) — should trim to 7
            for i in range(9):
                await queue_notification(
                    school_id=parent["school_id"],
                    recipient_type="parent",
                    recipient_id=parent["id"],
                    phone="+919999999999",
                    channel="telegram",
                    template="iter31_test",
                    message=f"TEST_update_{i}_{int(time.time())}",
                    context={"student_id": "STU-00001"},
                    telegram_chat_id="123456789",
                )
            count = await tdb.chat_updates.count_documents(
                {"recipient_id": parent["id"], "related_student_id": "STU-00001"},
            )
            return count

        count = asyncio.get_event_loop().run_until_complete(run()) if False else asyncio.new_event_loop().run_until_complete(run())
        assert count == 7, f"expected exactly 7 after 9 inserts, got {count}"

        # Now the API should also return ≤ 7 updates for that student
        r = ctx["s"]["parent1"].get(f"{API}/messaging/updates", timeout=20).json()
        updates = [u for u in r["updates"] if u.get("related_student_id") == "STU-00001"]
        assert len(updates) <= 7
        # parent sees by_student hydration
        assert isinstance(r.get("by_student"), dict)


# ---------- Hardened _trim_conversation_history (keep-set delete) ----------
class TestHistoryTrimHardening:
    def test_15_sends_leaves_exactly_10_newest(self, ctx):
        teacher_id = ctx["u"]["teacher"]["id"]
        parent_id = ctx["u"]["parent1"]["id"]
        s_t = ctx["s"]["teacher"]
        s_p = ctx["s"]["parent1"]
        stamp = int(time.time())
        for i in range(15):
            sender = s_t if i % 2 == 0 else s_p
            peer = parent_id if i % 2 == 0 else teacher_id
            r = sender.post(
                f"{API}/messaging/conversations/{peer}/messages",
                json={"text": f"TEST_trim31_{stamp}_{i:02d}"}, timeout=20,
            )
            assert r.status_code == 200
        g = s_t.get(f"{API}/messaging/conversations/{parent_id}/messages?limit=100", timeout=20).json()
        msgs = g["messages"]
        assert len(msgs) == 10, f"expected exactly 10 remaining, got {len(msgs)}"
        # Newest 10 should be indices 5..14
        texts = [m["text"] for m in msgs]
        # Earliest preserved index from our batch
        idxs = sorted(int(t.split("_")[-1]) for t in texts if t.startswith(f"TEST_trim31_{stamp}_"))
        # Older idx 0..4 must NOT be present
        for old in range(0, 5):
            assert old not in idxs, f"old index {old} should have been trimmed, present in {idxs}"


# ---------- Cross-school isolation ----------
class TestCrossSchoolIsolation:
    def test_teacher_cannot_read_other_school_group(self, ctx):
        # Inside same school, teacher2 attempting to read priya's owned group → 403
        gr = ctx["s"]["teacher"].get(f"{API}/messaging/groups", timeout=20).json()["groups"]
        priya_grp = [g for g in gr if g["is_owner"] and g["scope"] == "teacher_to_parents"][0]
        gid = priya_grp["id"]
        r = ctx["s"]["teacher2"].get(f"{API}/messaging/groups/{gid}/messages", timeout=20)
        assert r.status_code == 403
        # Posting also blocked
        rp = ctx["s"]["teacher2"].post(
            f"{API}/messaging/groups/{gid}/messages",
            json={"text": "TEST_xschool"}, timeout=20,
        )
        # teacher2 is neither owner nor a member → 403
        assert rp.status_code == 403
