"""Backend tests for iteration-33: School Notifications semantic kind classification + quick-reply round-trip.

Covers:
  * GET /messaging/conversations/system::school-notifications/messages now surfaces
    kind / kind_label / kind_color / quick_replies / subject / replied_at / reply_text
    and NO longer surfaces a `channel` label on the bubble payload.
  * _classify_update correctness for every template:
      attendance_alert  → kind=attendance, label='Attendance Alert', color='warning',
                          quick_replies=['Acknowledged','My child is unwell','Will be there tomorrow']
      fee_due_reminder  → kind=fee,        color='danger',  quick_replies includes 'Will pay today'
      holiday_alert     → kind=holiday,    color='success', quick_replies=['Got it, thanks']
      unknown template  → kind=general,    quick_replies=['Acknowledged','Need more info']
  * POST /messaging/system/reply:
      - 200 with {ok,update_id,replied_at,reply_text,recipient}
      - persists a 1-1 message from parent → resolved staff user
      - stamps chat_updates.replied_at + reply_text + reply_recipient_id
      - composed text begins with '↩︎ Re: <subject> · <student> (uid)'
      - attendance/sick + related_student_id → class teacher
      - fee → school_admin
      - unknown → school_admin
      - second reply → 409
      - update id not owned by caller → 404
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import time

import pytest
import requests


# Module-level persistent loop so motor/pymongo async clients (created lazily on
# first call inside backend code) bind to the same loop for the entire test run.
_LOOP = asyncio.new_event_loop()


def _arun(coro):
    return _LOOP.run_until_complete(coro)


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://case-insensitive-id.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

SYSTEM_PEER = "system::school-notifications"

PRINCIPAL = ("principal@sunrise.edu", "School@123", "school_admin")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")  # class teacher Grade 5-A
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
        "parent1": _login(*PARENT1),
        "parent2": _login(*PARENT2),
    }
    users = {k: s.get(f"{API}/auth/me", timeout=20).json() for k, s in sessions.items()}
    return {"s": sessions, "u": users}


@pytest.fixture(scope="module")
def backend_modules():
    """Lazy import of backend internals to seed chat_updates via queue_notification."""
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
    """Real mongo id of student STU-00001 (callers in real routes pass student.id, not the uid)."""
    school_id = ctx["u"]["parent1"]["school_id"]

    async def _fetch():
        tdb = await backend_modules["db"].tenant_db(school_id)
        s = await tdb.students.find_one({"student_uid": "STU-00001"}, {"_id": 0, "id": 1})
        return s["id"] if s else None

    sid = _arun(_fetch())
    assert sid, "STU-00001 not found in DEMO tenant"
    return sid


async def _seed_update(notify_mod, *, school_id, recipient_id, template, subject, body,
                        student_id=None, channel="telegram"):
    ctx = {"student_id": student_id, "related_student_id": student_id} if student_id else None
    await notify_mod.queue_notification(
        school_id=school_id,
        recipient_type="parent",
        recipient_id=recipient_id,
        phone=None,
        channel=channel,
        template=template,
        message=body,
        subject=subject,
        context=ctx,
    )


def _fetch_update(session, *, marker_subject) -> dict | None:
    r = session.get(f"{API}/messaging/conversations/{SYSTEM_PEER}/messages?limit=50", timeout=20)
    assert r.status_code == 200, r.text
    for m in r.json()["messages"]:
        if m.get("subject") == marker_subject:
            return m
    return None


# ---------- Classification & shape of system bubble payload ----------
class TestClassification:
    def test_classify_unit_attendance(self, backend_modules):
        c = backend_modules["messaging"]._classify_update({"template": "attendance_alert"})
        assert c["kind"] == "attendance"
        assert c["label"] == "Attendance Alert"
        assert c["color"] == "warning"
        assert c["quick_replies"] == ["Acknowledged", "My child is unwell", "Will be there tomorrow"]

    def test_classify_unit_fee(self, backend_modules):
        c = backend_modules["messaging"]._classify_update({"template": "fee_due_reminder"})
        assert c["kind"] == "fee"
        assert c["color"] == "danger"
        assert "Will pay today" in c["quick_replies"]

    def test_classify_unit_holiday(self, backend_modules):
        c = backend_modules["messaging"]._classify_update({"template": "holiday_alert"})
        assert c["kind"] == "holiday"
        assert c["color"] == "success"
        assert c["quick_replies"] == ["Got it, thanks"]

    def test_classify_unit_unknown_falls_back_to_general(self, backend_modules):
        c = backend_modules["messaging"]._classify_update({"template": "ZZZ_unknown_template_xyz"})
        assert c["kind"] == "general"
        assert c["quick_replies"] == ["Acknowledged", "Need more info"]

    def test_classify_unit_exam(self, backend_modules):
        c = backend_modules["messaging"]._classify_update({"template": "exam_alert"})
        assert c["kind"] == "exam"
        assert c["color"] == "info"


class TestSystemBubblePayload:
    def test_messages_have_kind_fields_and_no_channel(self, ctx, backend_modules, stu00001_id):
        # Seed one of each kind for parent1
        parent_id = ctx["u"]["parent1"]["id"]
        school_id = ctx["u"]["parent1"]["school_id"]
        ts = int(time.time() * 1000)
        templates = [
            ("attendance_alert", "attendance"),
            ("fee_due_reminder", "fee"),
            ("holiday_alert", "holiday"),
            ("exam_alert", "exam"),
        ]
        markers = {}
        for tpl, kind in templates:
            subj = f"TEST_iter33_{kind}_{ts}"
            markers[kind] = subj
            _arun(
                _seed_update(
                    backend_modules["notify"],
                    school_id=school_id,
                    recipient_id=parent_id,
                    template=tpl,
                    subject=subj,
                    body=f"body for {kind}",
                    student_id=stu00001_id,
                )
            )
        # Now fetch and assert shape
        r = ctx["s"]["parent1"].get(
            f"{API}/messaging/conversations/{SYSTEM_PEER}/messages?limit=50", timeout=20
        )
        assert r.status_code == 200
        msgs = r.json()["messages"]
        found = {k: None for k in markers}
        for m in msgs:
            for k, s in markers.items():
                if m.get("subject") == s:
                    found[k] = m
        for k, m in found.items():
            assert m is not None, f"seeded {k} bubble missing"
            assert m["sender_id"] == SYSTEM_PEER
            assert "channel" not in m, f"channel must not be on bubble payload: {m}"
            assert m["kind"] == k
            assert m["kind_label"]
            assert m["kind_color"]
            assert isinstance(m["quick_replies"], list) and m["quick_replies"]
            assert "replied_at" in m and "reply_text" in m
            assert "subject" in m


# ---------- /system/reply endpoint ----------
class TestQuickReply:
    def _seed_and_get_update_id(self, ctx, backend_modules, *, template, subject_marker, student_id=None):
        parent_id = ctx["u"]["parent1"]["id"]
        school_id = ctx["u"]["parent1"]["school_id"]
        _arun(
            _seed_update(
                backend_modules["notify"],
                school_id=school_id,
                recipient_id=parent_id,
                template=template,
                subject=subject_marker,
                body=f"body for {template}",
                student_id=student_id,
            )
        )
        # Fetch and locate
        for _ in range(3):
            m = _fetch_update(ctx["s"]["parent1"], marker_subject=subject_marker)
            if m:
                return m["id"], m
            time.sleep(0.5)
        pytest.fail(f"could not find seeded update with subject {subject_marker}")

    def test_attendance_reply_routes_to_class_teacher(self, ctx, backend_modules, stu00001_id):
        ts = int(time.time() * 1000)
        subj = f"TEST_iter33_reply_att_{ts}"
        upd_id, _bubble = self._seed_and_get_update_id(
            ctx, backend_modules, template="attendance_alert",
            subject_marker=subj, student_id=stu00001_id
        )
        text = "My child is unwell"
        r = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                     json={"update_id": upd_id, "text": text}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["update_id"] == upd_id
        assert j["reply_text"] == text
        assert j["replied_at"]
        # Class teacher for Grade 5-A is priya
        assert j["recipient"]["id"] == ctx["u"]["teacher"]["id"]
        assert j["recipient"]["role"] == "teacher"

        # Bubble should no longer have quick_replies usable — re-fetch and check replied_at
        time.sleep(0.4)
        r2 = ctx["s"]["parent1"].get(
            f"{API}/messaging/conversations/{SYSTEM_PEER}/messages?limit=50", timeout=20
        )
        upd_msg = next((m for m in r2.json()["messages"] if m["id"] == upd_id), None)
        assert upd_msg is not None
        assert upd_msg.get("replied_at"), "replied_at must be persisted"
        assert upd_msg.get("reply_text") == text

        # Teacher should see a new 1-1 message in their inbox starting with "↩︎ Re:"
        teacher_msgs = ctx["s"]["teacher"].get(
            f"{API}/messaging/conversations/{ctx['u']['parent1']['id']}/messages?limit=20",
            timeout=20,
        )
        assert teacher_msgs.status_code == 200, teacher_msgs.text
        texts = [m["text"] for m in teacher_msgs.json()["messages"]]
        composed_lead = "↩︎ Re:"
        match = next((t for t in texts if t.startswith(composed_lead) and text in t), None)
        assert match, f"teacher inbox missing composed reply: {texts}"
        assert "Aarav" in match or "STU-00001" in match, f"composed missing student label: {match}"

    def test_fee_reply_routes_to_school_admin(self, ctx, backend_modules, stu00001_id):
        ts = int(time.time() * 1000)
        subj = f"TEST_iter33_reply_fee_{ts}"
        upd_id, _ = self._seed_and_get_update_id(
            ctx, backend_modules, template="fee_due_reminder", subject_marker=subj,
            student_id=stu00001_id,
        )
        text = "Will pay today"
        r = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                     json={"update_id": upd_id, "text": text}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["recipient"]["id"] == ctx["u"]["admin"]["id"]
        assert j["recipient"]["role"] == "school_admin"

    def test_general_reply_routes_to_school_admin(self, ctx, backend_modules):
        ts = int(time.time() * 1000)
        subj = f"TEST_iter33_reply_gen_{ts}"
        # Use an unknown template (falls through to "general")
        upd_id, _ = self._seed_and_get_update_id(
            ctx, backend_modules, template="some_unknown_random_template",
            subject_marker=subj, student_id=None,
        )
        text = "Acknowledged"
        r = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                     json={"update_id": upd_id, "text": text}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["recipient"]["role"] == "school_admin"
        assert j["recipient"]["id"] == ctx["u"]["admin"]["id"]

    def test_second_reply_attempt_returns_409(self, ctx, backend_modules):
        ts = int(time.time() * 1000)
        subj = f"TEST_iter33_reply_dup_{ts}"
        upd_id, _ = self._seed_and_get_update_id(
            ctx, backend_modules, template="holiday_alert",
            subject_marker=subj, student_id=None,
        )
        r1 = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                      json={"update_id": upd_id, "text": "Got it, thanks"}, timeout=20)
        assert r1.status_code == 200, r1.text
        r2 = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                      json={"update_id": upd_id, "text": "Again"}, timeout=20)
        assert r2.status_code == 409, f"expected 409 on dup reply, got {r2.status_code} {r2.text}"

    def test_reply_for_other_user_update_returns_404(self, ctx, backend_modules, stu00001_id):
        # Seed an update belonging to parent1, but try replying as parent2
        ts = int(time.time() * 1000)
        subj = f"TEST_iter33_reply_xowner_{ts}"
        upd_id, _ = self._seed_and_get_update_id(
            ctx, backend_modules, template="attendance_alert",
            subject_marker=subj, student_id=stu00001_id,
        )
        r = ctx["s"]["parent2"].post(f"{API}/messaging/system/reply",
                                     json={"update_id": upd_id, "text": "Acknowledged"}, timeout=20)
        assert r.status_code == 404, f"expected 404 cross-owner, got {r.status_code} {r.text}"

    def test_reply_with_bogus_update_id_returns_404(self, ctx):
        r = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                     json={"update_id": "NOPE_does_not_exist_xyz", "text": "Hi"}, timeout=20)
        assert r.status_code == 404

    def test_reply_validation_rejects_empty(self, ctx):
        r = ctx["s"]["parent1"].post(f"{API}/messaging/system/reply",
                                     json={"update_id": "x", "text": ""}, timeout=20)
        assert r.status_code == 422

    def test_unknown_template_quick_replies_in_bubble(self, ctx, backend_modules):
        # An unknown template should still classify as general w/ generic quick replies
        ts = int(time.time() * 1000)
        subj = f"TEST_iter33_bubble_unknown_{ts}"
        upd_id, bubble = self._seed_and_get_update_id(
            ctx, backend_modules, template="totally_unknown_ZZZ",
            subject_marker=subj, student_id=None,
        )
        assert bubble["kind"] == "general"
        assert bubble["quick_replies"] == ["Acknowledged", "Need more info"]
