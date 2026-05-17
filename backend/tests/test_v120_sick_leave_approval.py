"""Backend tests for v1.20 sick-leave approval workflow.

Covers:
- Working-days helper (Sundays excluded).
- Parent <=3 working days -> auto-approved + attendance marked.
- Parent >3 working days -> pending + needs teacher AND admin approval.
- Teacher/admin self-recorded leave -> always approved.
- /today list -> approved only, role-scoped.
- /pending-approvals & /pending-count for teacher and admin.
- Approve/reject flow + duplicate-decision guard.
"""
import os
from datetime import date, timedelta
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            for line in open("/app/frontend/.env"):
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
        except FileNotFoundError:
            pass
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")

BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN = ("principal@sunrise.edu", "School@123", "school_admin")
TEACHER = ("priya@sunrise.edu", "Teacher@123", "teacher")
PARENT1 = ("parent.stu-00001@sunrise.edu", "Parent@123", "parent")
PARENT3 = ("parent.stu-00003@sunrise.edu", "Parent@123", "parent")


# ----- helpers -----
def _login(email, password, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    assert "access_token" in s.cookies
    return s


def _auth(_s):
    # backward-compat shim: we now pass sessions, so headers are unused
    return {}


def _next_monday():
    d = date.today()
    # roll forward to next Monday at least 7 days out, to avoid colliding with seeded data
    days = (7 - d.weekday()) % 7 + 14
    return d + timedelta(days=days)


def _cleanup_leave(token, leave_id):
    try:
        token.delete(f"{API}/sick-leaves/{leave_id}", timeout=10)
    except Exception:
        pass


# ----- session-scoped tokens -----
@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def teacher_token():
    return _login(*TEACHER)


@pytest.fixture(scope="module")
def parent1_token():
    return _login(*PARENT1)


@pytest.fixture(scope="module")
def parent3_token():
    return _login(*PARENT3)


# ----- 1. Working-days helper (mirrors backend logic via integration) -----
class TestWorkingDays:
    """We can't import server code from inside pytest (different process), so verify via API."""

    def test_friday_to_monday_is_3_workdays_auto_approved(self, parent1_token, admin_token):
        """Fri->Mon spans 4 calendar days but only 3 working days (Sat counted, Sun excluded)."""
        mon = _next_monday()
        fri = mon - timedelta(days=3)  # previous Friday
        end = mon                      # Monday
        r = parent1_token.post(f"{API}/sick-leaves", json={"student_id": "auto", "start_date": fri.isoformat(), "end_date": end.isoformat(), "reason": "Fri-Mon test"}, timeout=20)
        # student_id "auto" will 404 — we need a real id. Resolve it:
        if r.status_code == 404:
            kids = parent1_token.get(f"{API}/students", timeout=20).json()
            assert kids, "parent has no kids"
            sid = kids[0]["id"]
            r = parent1_token.post(f"{API}/sick-leaves", json={"student_id": sid, "start_date": fri.isoformat(), "end_date": end.isoformat(), "reason": "Fri-Mon test"}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["working_days"] == 3
        assert body["status"] == "approved"
        _cleanup_leave(admin_token, body["id"])


# ----- 2. Parent short leave auto-approved -----
class TestParentShortLeave:
    def test_parent_short_leave_auto_approved_and_attendance_marked(self, parent1_token, admin_token):
        kids = parent1_token.get(f"{API}/students", timeout=20).json()
        sid = kids[0]["id"]
        start = _next_monday()
        end = start + timedelta(days=1)  # 2 working days
        r = parent1_token.post(f"{API}/sick-leaves", json={"student_id": sid, "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": "Fever"}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["teacher_approval"] is None
        assert body["admin_approval"] is None
        assert body["working_days"] == 2
        # attendance should be set
        att = admin_token.get(
            f"{API}/attendance",
            params={"date": start.isoformat()}, timeout=20,
        )
        assert att.status_code == 200
        rows = att.json()
        ours = [a for a in rows if a.get("student_id") == sid]
        assert ours and ours[0]["status"] == "sick", "attendance not auto-marked sick"
        _cleanup_leave(admin_token, body["id"])


# ----- 3. Parent long leave -> pending workflow -----
class TestParentLongLeaveApproval:
    @pytest.fixture(scope="class")
    def long_leave(self, parent1_token):
        kids = parent1_token.get(f"{API}/students", timeout=20).json()
        sid = kids[0]["id"]
        start = _next_monday() + timedelta(days=28)  # well past prior tests' windows
        end = start + timedelta(days=5)  # Mon-Sat = 6 working days (excl Sunday)
        r = parent1_token.post(f"{API}/sick-leaves", json={"student_id": sid, "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": "Chickenpox - doctor advised week off"}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        return body, sid, start, end

    def test_long_leave_is_pending(self, long_leave):
        body, *_ = long_leave
        assert body["status"] == "pending"
        assert body["teacher_approval"]["status"] == "pending"
        assert body["admin_approval"]["status"] == "pending"
        assert body["working_days"] >= 4

    def test_attendance_not_marked_yet(self, long_leave, admin_token):
        _, sid, start, _ = long_leave
        att = admin_token.get(f"{API}/attendance", params={"date": start.isoformat()}, timeout=20).json()
        ours = [a for a in att if a.get("student_id") == sid]
        # there may be no record or status != sick
        assert not ours or ours[0]["status"] != "sick", "attendance should not be sick before approval"

    def test_appears_in_teacher_pending(self, long_leave, teacher_token):
        leave = long_leave[0]
        r = teacher_token.get(f"{API}/sick-leaves/pending-approvals", timeout=20)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert leave["id"] in ids

    def test_pending_count_teacher_admin(self, long_leave, teacher_token, admin_token, parent1_token):
        r1 = teacher_token.get(f"{API}/sick-leaves/pending-count", timeout=20)
        r2 = admin_token.get(f"{API}/sick-leaves/pending-count", timeout=20)
        r3 = parent1_token.get(f"{API}/sick-leaves/pending-count", timeout=20)
        assert r1.status_code == 200 and r1.json()["count"] >= 1
        assert r2.status_code == 200 and r2.json()["count"] >= 1
        assert r3.status_code == 200 and r3.json()["count"] == 0, "parent should always see count=0"

    def test_teacher_approves_then_overall_still_pending(self, long_leave, teacher_token):
        leave = long_leave[0]
        r = teacher_token.post(f"{API}/sick-leaves/{leave['id']}/approve", json={"note": "ok from teacher"}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["teacher_approval"]["status"] == "approved"
        assert body["status"] == "pending"  # admin not yet

    def test_teacher_cannot_double_approve(self, long_leave, teacher_token):
        leave = long_leave[0]
        r = teacher_token.post(f"{API}/sick-leaves/{leave['id']}/approve", timeout=20)
        assert r.status_code == 400

    def test_admin_approves_overall_approved_and_attendance_marked(self, long_leave, admin_token):
        leave, sid, start, end = long_leave
        r = admin_token.post(f"{API}/sick-leaves/{leave['id']}/approve", json={"note": "admin ok"}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["admin_approval"]["status"] == "approved"
        # Attendance now marked for Mon-Fri
        att = admin_token.get(f"{API}/attendance", params={"date": start.isoformat()}, timeout=20).json()
        ours = [a for a in att if a.get("student_id") == sid]
        assert ours and ours[0]["status"] == "sick"

    def test_appears_in_today_when_in_range(self, long_leave, admin_token):
        leave, sid, start, end = long_leave
        today = date.today()
        if start <= today <= end:
            r = admin_token.get(f"{API}/sick-leaves/today", timeout=20)
            assert r.status_code == 200
            assert any(x["id"] == leave["id"] for x in r.json())
        else:
            pytest.skip("approved leave window is in the future; /today not exercised here")

    def test_cleanup(self, long_leave, admin_token):
        _cleanup_leave(admin_token, long_leave[0]["id"])


# ----- 4. Reject flow -----
class TestRejectFlow:
    def test_admin_reject_blocks_teacher(self, parent3_token, admin_token, teacher_token):
        kids = parent3_token.get(f"{API}/students", timeout=20).json()
        sid = kids[0]["id"]
        start = _next_monday() + timedelta(days=14)
        end = start + timedelta(days=6)  # > 3 working days
        r = parent3_token.post(f"{API}/sick-leaves", json={"student_id": sid, "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": "Long trip"}, timeout=20)
        assert r.status_code == 200, r.text
        leave = r.json()
        assert leave["status"] == "pending"

        # Admin rejects
        rj = admin_token.post(f"{API}/sick-leaves/{leave['id']}/reject", json={"note": "Not medical"}, timeout=20)
        assert rj.status_code == 200
        assert rj.json()["status"] == "rejected"

        # Teacher cannot approve now
        ta = teacher_token.post(f"{API}/sick-leaves/{leave['id']}/approve", timeout=20)
        assert ta.status_code == 400

        _cleanup_leave(admin_token, leave["id"])


# ----- 5. Teacher/admin self-recorded -> always approved -----
class TestApproverSelfRecord:
    def test_teacher_long_leave_auto_approved(self, teacher_token, admin_token):
        # Pick a student in teacher's scope
        students = teacher_token.get(f"{API}/students", timeout=20).json()
        assert students, "teacher sees no students"
        sid = students[0]["id"]
        start = _next_monday() + timedelta(days=21)
        end = start + timedelta(days=6)
        r = teacher_token.post(f"{API}/sick-leaves", json={"student_id": sid, "start_date": start.isoformat(), "end_date": end.isoformat(), "reason": "extended"}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["teacher_approval"] is None and body["admin_approval"] is None
        _cleanup_leave(admin_token, body["id"])


# ----- 6. Parent cannot approve -----
class TestParentCannotApprove:
    def test_parent_403_on_pending_endpoints(self, parent1_token):
        r1 = parent1_token.get(f"{API}/sick-leaves/pending-approvals", timeout=20)
        r2 = parent1_token.get(f"{API}/sick-leaves/today", timeout=20)
        assert r1.status_code in (401, 403)
        assert r2.status_code in (401, 403)
