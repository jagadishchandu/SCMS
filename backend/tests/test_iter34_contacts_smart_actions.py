"""Backend tests for iteration-34: expanded contact matrix + smart-action execution.

Covers:
  * GET /messaging/contacts:
      - parent → includes principal (school_admin) + accounts + class teacher (w/ student context)
      - accounts → returns all parents (with kid context) + school_admins (NOT empty)
      - school_admin → includes teacher + accounts + parent rows
  * Allowed peers (1-1):
      - accounts → parent OK; parent → accounts OK
      - parent → school_admin OK
      - school_admin → accounts OK
      - teacher↔parent restriction unchanged (parent of unmapped student still 403)
  * /system/reply now embeds smart_actions[] on the outbound 1-1 message:
      - attendance + "My child is unwell" → mark_absent_today + approve_sick_leave + send_wellness_check
      - fee + "Will pay today" → send_payment_link + acknowledge_reply
      - fee + "extension" → grant_fee_extension + acknowledge_reply
  * POST /messaging/messages/{id}/smart-action:
      - mark_absent_today inserts/updates an attendance row for today/absent; second call → 409
      - 403 if caller role not permitted (parent calling)
      - 404 for an unknown message id
      - approve_sick_leave inserts a sick_leaves row status=approved with from/to dates
      - send_payment_link sends a 1-1 follow-up message to the parent
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests


_LOOP = asyncio.new_event_loop()


def _arun(coro):
    return _LOOP.run_until_complete(coro)


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://classroom-messenger-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
SYSTEM_PEER = "system::school-notifications"

PRINCIPAL = ("principal@sunrise.edu", "School@123", "school_admin")
ACCOUNTS = ("accounts@sunrise.edu", "Accounts@123", "accounts")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")  # class teacher Grade 5-A
TEACHER2 = ("rohit@sunrise.edu", "Teacher@123", "teacher")  # Grade 6-A — NOT class teacher of STU-00001
PARENT1 = ("parent.stu-00001@sunrise.edu", "Parent@123", "parent")


def _login(email, password, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ctx():
    sessions = {
        "admin": _login(*PRINCIPAL),
        "accounts": _login(*ACCOUNTS),
        "teacher": _login(*TEACHER),
        "teacher2": _login(*TEACHER2),
        "parent1": _login(*PARENT1),
    }
    users = {k: s.get(f"{API}/auth/me", timeout=20).json() for k, s in sessions.items()}
    return {"s": sessions, "u": users}


@pytest.fixture(scope="module")
def backend_modules():
    try:
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        notify_mod = importlib.import_module("core.notify")
        messaging_mod = importlib.import_module("routes.messaging")
        db_mod = importlib.import_module("core.db")
        return {"notify": notify_mod, "messaging": messaging_mod, "db": db_mod}
    except Exception as e:
        pytest.skip(f"backend imports unavailable: {e}")


@pytest.fixture(scope="module")
def stu00001_id(backend_modules, ctx):
    school_id = ctx["u"]["parent1"]["school_id"]

    async def _fetch():
        tdb = await backend_modules["db"].tenant_db(school_id)
        s = await tdb.students.find_one({"student_uid": "STU-00001"}, {"_id": 0, "id": 1})
        return s["id"] if s else None

    sid = _arun(_fetch())
    assert sid, "STU-00001 not found in DEMO tenant"
    return sid


async def _seed_update(notify_mod, *, school_id, recipient_id, template, subject, body, student_id=None):
    ctx_dict = {"student_id": student_id, "related_student_id": student_id} if student_id else None
    await notify_mod.queue_notification(
        school_id=school_id,
        recipient_type="parent",
        recipient_id=recipient_id,
        phone=None,
        channel="telegram",
        template=template,
        message=body,
        subject=subject,
        context=ctx_dict,
    )


def _seed_reply(ctx, backend_modules, *, template, student_id, reply_text):
    """Seed a chat_updates row owned by parent1, then POST /system/reply.
    Return the resulting 1-1 message dict from the recipient's inbox."""
    parent_id = ctx["u"]["parent1"]["id"]
    school_id = ctx["u"]["parent1"]["school_id"]
    ts = int(time.time() * 1000)
    subj = f"TEST_iter34_{template}_{ts}"
    _arun(_seed_update(
        backend_modules["notify"], school_id=school_id, recipient_id=parent_id,
        template=template, subject=subj, body=f"body {template}", student_id=student_id,
    ))
    # Locate it
    r = ctx["s"]["parent1"].get(f"{API}/messaging/conversations/{SYSTEM_PEER}/messages?limit=50", timeout=20)
    assert r.status_code == 200
    upd = next((m for m in r.json()["messages"] if m.get("subject") == subj), None)
    assert upd, f"seeded update {subj} not visible"
    upd_id = upd["id"]
    # Send reply
    r2 = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                  json={"update_id": upd_id, "text": reply_text}, timeout=20)
    assert r2.status_code == 200, r2.text
    recipient_id = r2.json()["recipient"]["id"]
    recipient_role = r2.json()["recipient"]["role"]
    # Fetch recipient's inbox to find the composed message
    sess = ctx["s"]["teacher"] if recipient_role == "teacher" else ctx["s"]["admin"]
    rr = sess.get(f"{API}/messaging/conversations/{parent_id}/messages?limit=20", timeout=20)
    assert rr.status_code == 200
    composed = next((m for m in rr.json()["messages"]
                     if m.get("is_quick_reply") and m.get("system_update_id") == upd_id), None)
    assert composed, "1-1 quick-reply message not found in recipient inbox"
    return composed, sess, recipient_id, recipient_role


# =====================================================================
# 1. Contact matrix (parent / accounts / school_admin)
# =====================================================================
class TestContacts:
    def test_parent_contacts_include_admin_accounts_and_class_teacher(self, ctx):
        r = ctx["s"]["parent1"].get(f"{API}/messaging/contacts", timeout=20)
        assert r.status_code == 200, r.text
        contacts = r.json()["contacts"]
        # System contact must be first
        assert contacts[0]["id"] == SYSTEM_PEER
        roles_present = {c["role"] for c in contacts if c["id"] != SYSTEM_PEER}
        ids_present = {c["id"] for c in contacts}
        # Principal (school_admin)
        assert ctx["u"]["admin"]["id"] in ids_present, "parent should see school_admin (principal)"
        # Accounts
        assert ctx["u"]["accounts"]["id"] in ids_present, "parent should see accounts user"
        # Class teacher
        assert ctx["u"]["teacher"]["id"] in ids_present, "parent should see class teacher"
        assert {"school_admin", "accounts", "teacher"}.issubset(roles_present)
        # Class teacher row carries student-name context
        t_row = next(c for c in contacts if c["id"] == ctx["u"]["teacher"]["id"])
        assert "context" in t_row and ("Aarav" in t_row["context"] or "STU-00001" in t_row["context"])

    def test_accounts_contacts_returns_parents_and_admins(self, ctx):
        r = ctx["s"]["accounts"].get(f"{API}/messaging/contacts", timeout=20)
        assert r.status_code == 200, r.text
        contacts = r.json()["contacts"]
        non_sys = [c for c in contacts if c["id"] != SYSTEM_PEER]
        assert non_sys, "accounts contact list should NOT be empty"
        roles = {c["role"] for c in non_sys}
        assert "parent" in roles, "accounts must see parents"
        assert "school_admin" in roles, "accounts must see school_admins"
        # at least one parent has student-name context
        parent_rows = [c for c in non_sys if c["role"] == "parent"]
        assert any("Parent of" in (c.get("context") or "") for c in parent_rows), \
            "at least one parent row should carry kid-name context"

    def test_admin_contacts_include_teachers_accounts_parents(self, ctx):
        r = ctx["s"]["admin"].get(f"{API}/messaging/contacts", timeout=20)
        assert r.status_code == 200, r.text
        contacts = r.json()["contacts"]
        roles = {c["role"] for c in contacts if c["id"] != SYSTEM_PEER}
        assert {"teacher", "accounts", "parent"}.issubset(roles), \
            f"admin contacts missing roles, got: {roles}"


# =====================================================================
# 2. Allowed peers (1-1 send permissions)
# =====================================================================
class TestAllowedPeers:
    def _send(self, sess, peer_id, text="hello"):
        return sess.post(f"{API}/messaging/conversations/{peer_id}/messages",
                         json={"text": text}, timeout=20)

    def test_accounts_to_parent_and_back(self, ctx):
        parent_id = ctx["u"]["parent1"]["id"]
        accounts_id = ctx["u"]["accounts"]["id"]
        r1 = self._send(ctx["s"]["accounts"], parent_id, text="TEST_iter34 fee due")
        assert r1.status_code == 200, r1.text
        r2 = self._send(ctx["s"]["parent1"], accounts_id, text="TEST_iter34 paid")
        assert r2.status_code == 200, r2.text

    def test_parent_to_school_admin(self, ctx):
        r = self._send(ctx["s"]["parent1"], ctx["u"]["admin"]["id"], text="TEST_iter34 hello principal")
        assert r.status_code == 200, r.text

    def test_school_admin_to_accounts(self, ctx):
        r = self._send(ctx["s"]["admin"], ctx["u"]["accounts"]["id"], text="TEST_iter34 admin->accounts")
        assert r.status_code == 200, r.text

    def test_teacher_unmapped_parent_blocked(self, ctx):
        # teacher2 (rohit, Grade 6-A) has no STU-00001 in his class → should be 403
        r = self._send(ctx["s"]["teacher2"], ctx["u"]["parent1"]["id"], text="x")
        assert r.status_code == 403, f"teacher of unmapped parent should be 403, got {r.status_code}"


# =====================================================================
# 3. smart_actions on quick-reply outbound message
# =====================================================================
class TestSmartActionsSuggestion:
    def test_attendance_unwell_produces_three_actions(self, ctx, backend_modules, stu00001_id):
        composed, _sess, _rid, role = _seed_reply(
            ctx, backend_modules, template="attendance_alert",
            student_id=stu00001_id, reply_text="My child is unwell",
        )
        assert role == "teacher"
        actions = [a["action"] for a in composed.get("smart_actions") or []]
        for a in ("mark_absent_today", "approve_sick_leave", "send_wellness_check"):
            assert a in actions, f"missing {a} in {actions}"

    def test_fee_pay_today_produces_payment_link(self, ctx, backend_modules, stu00001_id):
        composed, _sess, _rid, role = _seed_reply(
            ctx, backend_modules, template="fee_due_reminder",
            student_id=stu00001_id, reply_text="Will pay today",
        )
        assert role == "school_admin"
        actions = [a["action"] for a in composed.get("smart_actions") or []]
        assert "send_payment_link" in actions, actions
        assert "acknowledge_reply" in actions, actions

    def test_fee_extension_produces_grant_extension(self, ctx, backend_modules, stu00001_id):
        composed, _sess, _rid, role = _seed_reply(
            ctx, backend_modules, template="fee_due_reminder",
            student_id=stu00001_id, reply_text="Please grant an extension",
        )
        assert role == "school_admin"
        actions = [a["action"] for a in composed.get("smart_actions") or []]
        assert "grant_fee_extension" in actions, actions
        assert "acknowledge_reply" in actions, actions


# =====================================================================
# 4. Smart-action endpoint execution
# =====================================================================
class TestSmartActionExec:
    def test_mark_absent_today_inserts_attendance_and_409_on_dup(self, ctx, backend_modules, stu00001_id):
        composed, sess, _rid, role = _seed_reply(
            ctx, backend_modules, template="attendance_alert",
            student_id=stu00001_id, reply_text="My child is unwell",
        )
        assert role == "teacher"
        msg_id = composed["id"]
        school_id = ctx["u"]["parent1"]["school_id"]
        today = datetime.now(timezone.utc).date().isoformat()

        # Clear any pre-existing attendance row for today (test isolation)
        async def _clear():
            tdb = await backend_modules["db"].tenant_db(school_id)
            await tdb.attendance.delete_many({"student_id": stu00001_id, "date": today, "school_id": school_id})
        _arun(_clear())

        r = sess.post(f"{API}/messaging/messages/{msg_id}/smart-action",
                      json={"action": "mark_absent_today"}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True and j["action"] == "mark_absent_today"
        assert "Marked" in j["outcome"]

        # Verify attendance row
        async def _check():
            tdb = await backend_modules["db"].tenant_db(school_id)
            return await tdb.attendance.find_one(
                {"student_id": stu00001_id, "date": today, "school_id": school_id},
                {"_id": 0, "status": 1, "marked_by": 1},
            )
        row = _arun(_check())
        assert row is not None, "attendance row not persisted"
        assert row["status"] == "absent"
        assert row["marked_by"] == ctx["u"]["teacher"]["id"]

        # Second call → 409 (idempotent)
        r2 = sess.post(f"{API}/messaging/messages/{msg_id}/smart-action",
                       json={"action": "mark_absent_today"}, timeout=20)
        assert r2.status_code == 409, f"expected 409 on dup, got {r2.status_code}: {r2.text}"

    def test_unknown_message_id_returns_404(self, ctx):
        r = ctx["s"]["teacher"].post(f"{API}/messaging/messages/NOPE_xyz_123/smart-action",
                                     json={"action": "mark_absent_today"}, timeout=20)
        assert r.status_code == 404, r.text

    def test_parent_role_forbidden(self, ctx, backend_modules, stu00001_id):
        composed, _sess, _rid, _role = _seed_reply(
            ctx, backend_modules, template="attendance_alert",
            student_id=stu00001_id, reply_text="My child is unwell",
        )
        # Parent tries to call smart-action — but parent is not the recipient
        # (recipient is teacher). The route filters by recipient_id == user.id,
        # so a parent (non-recipient) gets 404. That is also a valid "forbidden"
        # outcome per the route's security model. Accept either 403 or 404.
        r = ctx["s"]["parent1"].post(f"{API}/messaging/messages/{composed['id']}/smart-action",
                                     json={"action": "mark_absent_today"}, timeout=20)
        assert r.status_code in (403, 404), f"parent must be blocked, got {r.status_code}: {r.text}"

    def test_approve_sick_leave_creates_row(self, ctx, backend_modules, stu00001_id):
        composed, sess, _rid, role = _seed_reply(
            ctx, backend_modules, template="attendance_alert",
            student_id=stu00001_id, reply_text="My child is unwell",
        )
        assert role == "teacher"
        msg_id = composed["id"]
        school_id = ctx["u"]["parent1"]["school_id"]
        today = datetime.now(timezone.utc).date().isoformat()
        days = 3
        r = sess.post(f"{API}/messaging/messages/{msg_id}/smart-action",
                      json={"action": "approve_sick_leave", "days": days}, timeout=20)
        assert r.status_code == 200, r.text

        async def _check():
            tdb = await backend_modules["db"].tenant_db(school_id)
            return await tdb.sick_leaves.find_one(
                {"student_id": stu00001_id, "from_date": today, "approved_by": ctx["u"]["teacher"]["id"]},
                {"_id": 0, "status": 1, "to_date": 1, "from_date": 1},
                sort=[("created_at", -1)],
            )
        row = _arun(_check())
        assert row, "sick_leaves row not created"
        assert row["status"] == "approved"
        expected_to = (datetime.now(timezone.utc) + timedelta(days=days - 1)).date().isoformat()
        assert row["to_date"] == expected_to, f"to_date {row['to_date']} != {expected_to}"

    def test_send_payment_link_sends_followup_to_parent(self, ctx, backend_modules, stu00001_id):
        composed, sess, _rid, role = _seed_reply(
            ctx, backend_modules, template="fee_due_reminder",
            student_id=stu00001_id, reply_text="Will pay today",
        )
        assert role == "school_admin"
        msg_id = composed["id"]
        admin_id = ctx["u"]["admin"]["id"]
        r = sess.post(f"{API}/messaging/messages/{msg_id}/smart-action",
                      json={"action": "send_payment_link"}, timeout=20)
        assert r.status_code == 200, r.text

        # Parent should see a follow-up message from admin with the payment URL
        time.sleep(0.4)
        rr = ctx["s"]["parent1"].get(
            f"{API}/messaging/conversations/{admin_id}/messages?limit=20", timeout=20,
        )
        assert rr.status_code == 200
        texts = [m["text"] for m in rr.json()["messages"] if m.get("sender_id") == admin_id]
        assert any("/parent/fees" in t or "pay the pending fees" in t for t in texts), \
            f"parent missing follow-up payment link, recent texts: {texts[:5]}"
