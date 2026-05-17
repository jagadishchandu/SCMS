"""Backend tests for v1.36 sick-leave APPEAL workflow.

Covers:
- POST /api/sick-leaves/{id}/appeal validation:
  * parent only (403 for teacher/admin/accounts)
  * leave must belong to that parent (403 otherwise)
  * leave must be rejected (400 otherwise)
  * appeal_note required (400 if empty/whitespace)
- On success:
  * status flips to 'pending'
  * teacher_approval/admin_approval reset to {status:'pending'}
  * appeals[] grows, preserving previous_reason/previous_teacher_approval/previous_admin_approval
  * last_appeal_at + last_appeal_note set
  * optional reason / diagnosis updated
- Appealed leave reappears in pending-approvals for BOTH teacher and admin and pending-count grows
- Full chain: appeal -> teacher approves -> admin approves -> approved + attendance marked
- Re-appeal after second rejection -> appeals[] length grows to 2
- Prior v1.20 endpoints still work
"""
import os
from datetime import date, timedelta
import pytest
import requests


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip()
                break
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN = ("principal@sunrise.edu", "School@123", "school_admin")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")
ACCOUNTS = ("accounts@sunrise.edu", "Accounts@123", "accounts")
PARENT1 = ("parent.stu-00001@sunrise.edu", "Parent@123", "parent")
PARENT2 = ("parent.stu-00002@sunrise.edu", "Parent@123", "parent")


def _login(email, password, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


def _next_monday_offset(offset_weeks=8):
    """Pick a Monday far in the future so we don't collide with other test runs."""
    d = date.today()
    days = (7 - d.weekday()) % 7 + 7 * offset_weeks
    return d + timedelta(days=days)


def _cleanup(sess, leave_id):
    try:
        sess.delete(f"{API}/sick-leaves/{leave_id}", timeout=10)
    except Exception:
        pass


# -------- session fixtures --------
@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def teacher_token():
    return _login(*TEACHER)


@pytest.fixture(scope="module")
def accounts_token():
    return _login(*ACCOUNTS)


@pytest.fixture(scope="module")
def parent1_token():
    return _login(*PARENT1)


@pytest.fixture(scope="module")
def parent2_token():
    return _login(*PARENT2)


def _create_rejected_leave(parent_sess, admin_sess, weeks_offset=8):
    """Helper: parent creates >3 workday leave; admin rejects -> returns leave id."""
    kids = parent_sess.get(f"{API}/students", timeout=20).json()
    sid = kids[0]["id"]
    start = _next_monday_offset(weeks_offset)
    end = start + timedelta(days=6)  # 6 working days (Mon-Sat)
    r = parent_sess.post(
        f"{API}/sick-leaves",
        json={"student_id": sid, "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": "Original reason"},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    leave = r.json()
    assert leave["status"] == "pending"

    rj = admin_sess.post(f"{API}/sick-leaves/{leave['id']}/reject", json={"note": "Not medical enough"}, timeout=20)
    assert rj.status_code == 200, rj.text
    assert rj.json()["status"] == "rejected"
    return leave["id"], sid, start, end


# -------- 1. Validation --------
class TestAppealValidation:
    def test_non_parent_roles_403(self, parent1_token, admin_token, teacher_token, accounts_token):
        leave_id, *_ = _create_rejected_leave(parent1_token, admin_token, weeks_offset=8)
        try:
            for sess in (admin_token, teacher_token, accounts_token):
                r = sess.post(f"{API}/sick-leaves/{leave_id}/appeal", json={"appeal_note": "test"}, timeout=20)
                assert r.status_code in (401, 403), f"expected 403 got {r.status_code} {r.text}"
        finally:
            _cleanup(admin_token, leave_id)

    def test_only_owning_parent_can_appeal(self, parent1_token, parent2_token, admin_token):
        leave_id, *_ = _create_rejected_leave(parent1_token, admin_token, weeks_offset=9)
        try:
            r = parent2_token.post(f"{API}/sick-leaves/{leave_id}/appeal", json={"appeal_note": "I want to appeal"}, timeout=20)
            assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"
        finally:
            _cleanup(admin_token, leave_id)

    def test_cannot_appeal_pending_leave(self, parent1_token, admin_token):
        kids = parent1_token.get(f"{API}/students", timeout=20).json()
        sid = kids[0]["id"]
        start = _next_monday_offset(10)
        end = start + timedelta(days=5)
        r = parent1_token.post(
            f"{API}/sick-leaves",
            json={"student_id": sid, "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": "p"},
            timeout=20,
        )
        leave = r.json()
        try:
            ap = parent1_token.post(f"{API}/sick-leaves/{leave['id']}/appeal", json={"appeal_note": "x"}, timeout=20)
            assert ap.status_code == 400
        finally:
            _cleanup(admin_token, leave["id"])

    def test_empty_appeal_note_400(self, parent1_token, admin_token):
        leave_id, *_ = _create_rejected_leave(parent1_token, admin_token, weeks_offset=11)
        try:
            r = parent1_token.post(f"{API}/sick-leaves/{leave_id}/appeal", json={"appeal_note": "   "}, timeout=20)
            assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text}"
        finally:
            _cleanup(admin_token, leave_id)


# -------- 2. Happy path / history preservation --------
class TestAppealHappyPath:
    def test_appeal_resets_state_and_records_history(self, parent1_token, admin_token, teacher_token):
        leave_id, sid, start, end = _create_rejected_leave(parent1_token, admin_token, weeks_offset=12)
        try:
            # capture the rejected snapshot first
            mine = parent1_token.get(f"{API}/sick-leaves", params={"student_id": sid}, timeout=20).json()
            before = next(x for x in mine if x["id"] == leave_id)
            assert before["status"] == "rejected"
            assert before.get("admin_approval", {}).get("status") == "rejected"

            r = parent1_token.post(
                f"{API}/sick-leaves/{leave_id}/appeal",
                json={"appeal_note": "Doctor confirmed it was chickenpox. Please re-review.", "reason": "Updated: chickenpox confirmed"},
                timeout=20,
            )
            assert r.status_code == 200, r.text
            body = r.json()

            # status reset
            assert body["status"] == "pending"
            assert body["teacher_approval"] == {"status": "pending"}
            assert body["admin_approval"] == {"status": "pending"}

            # appeals[] populated
            assert isinstance(body.get("appeals"), list) and len(body["appeals"]) == 1
            entry = body["appeals"][0]
            assert entry["appeal_note"].startswith("Doctor confirmed")
            assert entry["previous_reason"] == "Original reason"
            assert entry["previous_admin_approval"]["status"] == "rejected"
            assert entry["previous_admin_approval"].get("note") == "Not medical enough"
            assert entry.get("appealed_at")

            # last_appeal_at / last_appeal_note
            assert body.get("last_appeal_at")
            assert body.get("last_appeal_note", "").startswith("Doctor confirmed")
            # reason updated
            assert body.get("reason") == "Updated: chickenpox confirmed"

            # appears back in pending-approvals for both teacher and admin
            t_pa = teacher_token.get(f"{API}/sick-leaves/pending-approvals", timeout=20).json()
            a_pa = admin_token.get(f"{API}/sick-leaves/pending-approvals", timeout=20).json()
            assert leave_id in [x["id"] for x in t_pa], "appealed leave missing from teacher pending"
            assert leave_id in [x["id"] for x in a_pa], "appealed leave missing from admin pending"
            # appeals[] populated for approver views too
            t_entry = next(x for x in t_pa if x["id"] == leave_id)
            assert len(t_entry.get("appeals", [])) == 1

            # pending-count for both approvers > 0
            assert teacher_token.get(f"{API}/sick-leaves/pending-count", timeout=20).json()["count"] >= 1
            assert admin_token.get(f"{API}/sick-leaves/pending-count", timeout=20).json()["count"] >= 1
        finally:
            _cleanup(admin_token, leave_id)


# -------- 3. End-to-end: appeal -> approve -> approve -> attendance --------
class TestAppealApprovalChain:
    def test_appeal_then_double_approve_marks_attendance(self, parent1_token, admin_token, teacher_token):
        leave_id, sid, start, end = _create_rejected_leave(parent1_token, admin_token, weeks_offset=13)
        try:
            ap = parent1_token.post(f"{API}/sick-leaves/{leave_id}/appeal", json={"appeal_note": "Please reconsider"}, timeout=20)
            assert ap.status_code == 200
            # teacher approves
            t = teacher_token.post(f"{API}/sick-leaves/{leave_id}/approve", json={"note": "ok"}, timeout=20)
            assert t.status_code == 200
            assert t.json()["status"] == "pending"
            # admin approves -> overall approved
            a = admin_token.post(f"{API}/sick-leaves/{leave_id}/approve", json={"note": "ok"}, timeout=20)
            assert a.status_code == 200
            assert a.json()["status"] == "approved"
            # attendance auto-marked on Monday (start is a Monday)
            att = admin_token.get(f"{API}/attendance", params={"date": start.isoformat()}, timeout=20).json()
            ours = [x for x in att if x.get("student_id") == sid]
            assert ours and ours[0]["status"] == "sick"
        finally:
            _cleanup(admin_token, leave_id)


# -------- 4. Re-appeal after second rejection --------
class TestReAppeal:
    def test_can_appeal_again_after_second_rejection(self, parent1_token, admin_token, teacher_token):
        leave_id, *_ = _create_rejected_leave(parent1_token, admin_token, weeks_offset=14)
        try:
            # first appeal
            r1 = parent1_token.post(f"{API}/sick-leaves/{leave_id}/appeal", json={"appeal_note": "First appeal"}, timeout=20)
            assert r1.status_code == 200
            assert len(r1.json()["appeals"]) == 1
            # teacher rejects this time
            tr = teacher_token.post(f"{API}/sick-leaves/{leave_id}/reject", json={"note": "Still not enough info"}, timeout=20)
            assert tr.status_code == 200
            assert tr.json()["status"] == "rejected"
            # second appeal
            r2 = parent1_token.post(f"{API}/sick-leaves/{leave_id}/appeal", json={"appeal_note": "Second appeal with cert"}, timeout=20)
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert body["status"] == "pending"
            assert len(body["appeals"]) == 2
            # latest entry captures the teacher rejection that just happened
            latest = body["appeals"][-1]
            assert latest["previous_teacher_approval"]["status"] == "rejected"
            assert latest["previous_teacher_approval"].get("note") == "Still not enough info"
        finally:
            _cleanup(admin_token, leave_id)


# -------- 5. v1.20 regression smoke --------
class TestPriorEndpointsStillWork:
    def test_pending_approvals_and_count(self, teacher_token, admin_token):
        assert teacher_token.get(f"{API}/sick-leaves/pending-approvals", timeout=20).status_code == 200
        assert admin_token.get(f"{API}/sick-leaves/pending-approvals", timeout=20).status_code == 200
        assert teacher_token.get(f"{API}/sick-leaves/pending-count", timeout=20).status_code == 200
        assert admin_token.get(f"{API}/sick-leaves/pending-count", timeout=20).status_code == 200

    def test_today_endpoint(self, teacher_token, admin_token):
        assert teacher_token.get(f"{API}/sick-leaves/today", timeout=20).status_code == 200
        assert admin_token.get(f"{API}/sick-leaves/today", timeout=20).status_code == 200
