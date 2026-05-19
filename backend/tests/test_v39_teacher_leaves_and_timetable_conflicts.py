"""End-to-end tests for v39 features:
1) POST /api/timetable/bulk strict conflict detection (intra-payload + cross-class).
2) Teacher leaves CRUD (create/list/pending-count/approve/reject/delete/active).
3) Auto-marking teacher_attendance as 'leave' after approval.
4) POST /api/timetable/suggest leave-aware filter.
"""
import os
import uuid
import pytest
import requests
from datetime import date, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


def _login(email: str, password: str, role: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role})
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return s


# -------------------- shared fixtures --------------------
@pytest.fixture(scope="module")
def admin():
    return _login("principal@sunrise.edu", "School@123", "school_admin")


@pytest.fixture(scope="module")
def priya():
    return _login("priya@sunrise.edu", "Teacher@123", "teacher")


@pytest.fixture(scope="module")
def rohit():
    return _login("rohit@sunrise.edu", "Teacher@123", "teacher")


@pytest.fixture(scope="module")
def me_priya(priya):
    r = priya.get(f"{API}/auth/me")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def me_rohit(rohit):
    r = rohit.get(f"{API}/auth/me")
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def school_meta(admin):
    classes = admin.get(f"{API}/academic/classes").json()
    subjects = admin.get(f"{API}/academic/subjects").json()
    teachers = admin.get(f"{API}/users?role=teacher").json()
    return {"classes": classes, "subjects": subjects, "teachers": teachers}


def _future_dates(offset_days: int = 60, span_days: int = 2):
    """Return (start_iso, end_iso) for a future leave that doesn't collide with smoke-test."""
    start = date.today() + timedelta(days=offset_days)
    end = start + timedelta(days=span_days)
    return start.isoformat(), end.isoformat()


def _next_monday(offset_weeks: int = 9) -> str:
    """Return ISO date for a Monday a few weeks out (further than the leave 60d to be safe)."""
    today = date.today()
    base = today + timedelta(days=offset_weeks * 7)
    # walk forward to a Monday
    while base.weekday() != 0:
        base += timedelta(days=1)
    return base.isoformat()


# ===========================================================
# Teacher Leaves: create / list / pending-count / active
# ===========================================================
class TestTeacherLeaveCRUD:
    def test_teacher_creates_leave_working_days(self, priya):
        # 3-day span Mon..Wed (any 3 weekdays guaranteed): use 60..62 days out
        s, e = _future_dates(60, 2)  # 3-day inclusive
        r = priya.post(f"{API}/teacher-leaves", json={
            "start_date": s, "end_date": e, "leave_type": "casual", "reason": "Family event"
        })
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "pending"
        assert doc["start_date"] == s and doc["end_date"] == e
        assert doc["leave_type"] == "casual"
        # working_days excludes Sundays
        wd_expected = 0
        d = date.fromisoformat(s)
        end = date.fromisoformat(e)
        while d <= end:
            if d.weekday() != 6:
                wd_expected += 1
            d += timedelta(days=1)
        assert doc["working_days"] == wd_expected
        assert "id" in doc
        pytest.shared_leave_pending_id = doc["id"]

    def test_create_rejects_invalid_range(self, priya):
        r = priya.post(f"{API}/teacher-leaves", json={
            "start_date": "2026-06-10", "end_date": "2026-06-05", "leave_type": "sick"
        })
        assert r.status_code == 400

    def test_admin_cannot_create_leave(self, admin):
        s, e = _future_dates(70, 0)
        r = admin.post(f"{API}/teacher-leaves", json={"start_date": s, "end_date": e})
        assert r.status_code == 403

    def test_teacher_sees_only_own(self, priya, rohit):
        r1 = priya.get(f"{API}/teacher-leaves")
        assert r1.status_code == 200
        rows1 = r1.json()
        assert isinstance(rows1, list)
        assert all(x["teacher_id"] == rows1[0]["teacher_id"] for x in rows1) if rows1 else True

        # Rohit should not see Priya's leaves
        r2 = rohit.get(f"{API}/teacher-leaves")
        assert r2.status_code == 200
        rows2 = r2.json()
        assert not any(x["id"] == pytest.shared_leave_pending_id for x in rows2)

    def test_pending_count_admin(self, admin):
        r = admin.get(f"{API}/teacher-leaves/pending-count")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data and isinstance(data["count"], int)
        assert data["count"] >= 1

    def test_pending_count_nonadmin_zero(self, priya):
        r = priya.get(f"{API}/teacher-leaves/pending-count")
        assert r.status_code == 200
        assert r.json() == {"count": 0}

    def test_status_filter(self, admin, priya):
        # admin filter by status=pending should include ours
        r = admin.get(f"{API}/teacher-leaves?status=pending")
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert pytest.shared_leave_pending_id in ids

        # teacher filter by status=approved (should not include the pending one)
        r2 = priya.get(f"{API}/teacher-leaves?status=approved")
        assert r2.status_code == 200
        ids2 = [x["id"] for x in r2.json()]
        assert pytest.shared_leave_pending_id not in ids2


# ===========================================================
# Approve / reject / delete + attendance auto-mark
# ===========================================================
class TestTeacherLeaveDecisions:
    def test_reject_flow(self, priya, admin):
        s, e = _future_dates(90, 1)
        r = priya.post(f"{API}/teacher-leaves", json={"start_date": s, "end_date": e})
        leave_id = r.json()["id"]
        rr = admin.post(f"{API}/teacher-leaves/{leave_id}/reject",
                        json={"note": "Try later"})
        assert rr.status_code == 200, rr.text
        assert rr.json()["status"] == "rejected"
        assert rr.json()["decision_note"] == "Try later"

    def test_cannot_decide_twice(self, priya, admin):
        s, e = _future_dates(95, 0)
        r = priya.post(f"{API}/teacher-leaves", json={"start_date": s, "end_date": e})
        leave_id = r.json()["id"]
        assert admin.post(f"{API}/teacher-leaves/{leave_id}/approve").status_code == 200
        again = admin.post(f"{API}/teacher-leaves/{leave_id}/approve")
        assert again.status_code == 400

    def test_approve_marks_attendance(self, priya, admin, me_priya):
        s, e = _future_dates(100, 1)  # 2-day weekday window (most likely)
        r = priya.post(f"{API}/teacher-leaves", json={"start_date": s, "end_date": e, "leave_type": "sick"})
        leave_id = r.json()["id"]
        ar = admin.post(f"{API}/teacher-leaves/{leave_id}/approve")
        assert ar.status_code == 200
        assert ar.json()["status"] == "approved"

        # Confirm teacher_attendance has 'leave' rows for each weekday in the range
        # via the admin attendance endpoint
        tid = me_priya["id"]
        # Check each date individually
        cur = date.fromisoformat(s)
        end = date.fromisoformat(e)
        found_dates = []
        while cur <= end:
            if cur.weekday() != 6:  # not Sunday
                resp = admin.get(f"{API}/teacher-attendance",
                                 params={"date": cur.isoformat(), "teacher_id": tid})
                if resp.status_code == 200:
                    rows = resp.json() if isinstance(resp.json(), list) else resp.json().get("rows", [])
                    if isinstance(rows, list):
                        for rec in rows:
                            if rec.get("teacher_id") == tid and rec.get("date") == cur.isoformat() and rec.get("status") == "leave":
                                found_dates.append(cur.isoformat())
            cur += timedelta(days=1)
        # at least one weekday should be auto-marked
        assert len(found_dates) >= 1, f"No leave attendance rows found for teacher {tid} between {s}..{e}"
        pytest.shared_approved_leave_id = leave_id
        pytest.shared_approved_range = (s, e)

    def test_active_returns_approved_leave(self, admin, me_priya):
        s, e = pytest.shared_approved_range
        # Pick a weekday inside the range
        d = date.fromisoformat(s)
        while d.weekday() == 6:
            d += timedelta(days=1)
        r = admin.get(f"{API}/teacher-leaves/active", params={"date": d.isoformat()})
        assert r.status_code == 200
        data = r.json()
        assert data["date"] == d.isoformat()
        assert me_priya["id"] in data["teacher_ids"]

    def test_delete_own_pending(self, priya):
        s, e = _future_dates(110, 0)
        r = priya.post(f"{API}/teacher-leaves", json={"start_date": s, "end_date": e})
        leave_id = r.json()["id"]
        d = priya.delete(f"{API}/teacher-leaves/{leave_id}")
        assert d.status_code == 200
        # confirm cancelled status
        rows = priya.get(f"{API}/teacher-leaves").json()
        match = [x for x in rows if x["id"] == leave_id]
        assert match and match[0]["status"] == "cancelled"

    def test_teacher_cannot_delete_others(self, rohit, priya):
        # Create with Priya, try delete with Rohit
        s, e = _future_dates(115, 0)
        r = priya.post(f"{API}/teacher-leaves", json={"start_date": s, "end_date": e})
        leave_id = r.json()["id"]
        d = rohit.delete(f"{API}/teacher-leaves/{leave_id}")
        assert d.status_code == 403


# ===========================================================
# Timetable BULK conflict detection
# ===========================================================
class TestTimetableBulkConflicts:
    def _slot(self, cls_id, section, day, period, subject_id, teacher_id, t="09:00", e="09:45"):
        return {
            "day": day, "period": period, "subject_id": subject_id,
            "teacher_id": teacher_id, "class_id": cls_id, "section": section,
            "start_time": t, "end_time": e,
        }

    def _pick(self, school_meta, me_priya):
        # Pick two distinct class/section combinations & a subject Priya can teach
        cls_with_secs = [c for c in school_meta["classes"] if c.get("sections")]
        assert len(cls_with_secs) >= 2, "need at least 2 classes for cross-class test"
        c1 = cls_with_secs[0]
        c2 = cls_with_secs[1]
        sec1 = c1["sections"][0]
        sec2 = c2["sections"][0]
        # Priya teaches Mathematics + Science — find a subject by id from her assignments
        priya_subjects = me_priya.get("subjects") or []
        # Fallback: any subject id present in school
        if priya_subjects:
            sid = priya_subjects[0]
        else:
            sid = school_meta["subjects"][0]["id"]
        return c1["id"], sec1, c2["id"], sec2, sid

    def test_intra_payload_conflict_returns_409(self, admin, school_meta, me_priya):
        c1, sec1, _, _, sid = self._pick(school_meta, me_priya)
        tid = me_priya["id"]
        payload = {
            "class_id": c1, "section": sec1,
            "slots": [
                self._slot(c1, sec1, "mon", 1, sid, tid),
                # Same teacher, same (day,period) within the same submission
                self._slot(c1, sec1, "mon", 1, sid, tid, t="09:00", e="09:45"),
            ],
        }
        r = admin.post(f"{API}/timetable/bulk", json=payload)
        assert r.status_code == 409, r.text
        detail = r.json().get("detail", {})
        assert "intra_payload_conflicts" in detail
        assert len(detail["intra_payload_conflicts"]) >= 1
        assert detail["intra_payload_conflicts"][0]["teacher_id"] == tid

    def test_cross_class_conflict_returns_409(self, admin, school_meta, me_priya):
        c1, sec1, c2, sec2, sid = self._pick(school_meta, me_priya)
        tid = me_priya["id"]
        # First, populate class1/sec1 with a slot via bulk (clean)
        first = {
            "class_id": c1, "section": sec1,
            "slots": [self._slot(c1, sec1, "tue", 2, sid, tid)],
        }
        r1 = admin.post(f"{API}/timetable/bulk", json=first)
        assert r1.status_code == 200, r1.text
        # Now attempt to schedule same teacher at (tue,2) in another class
        second = {
            "class_id": c2, "section": sec2,
            "slots": [self._slot(c2, sec2, "tue", 2, sid, tid)],
        }
        r2 = admin.post(f"{API}/timetable/bulk", json=second)
        assert r2.status_code == 409, r2.text
        detail = r2.json().get("detail", {})
        assert "cross_class_conflicts" in detail
        assert len(detail["cross_class_conflicts"]) >= 1
        cc = detail["cross_class_conflicts"][0]
        assert cc["teacher_id"] == tid
        assert cc["conflict_with"]["class_id"] == c1
        # teacher friendly name enrichment
        assert "teacher_name" in cc

    def test_bulk_success_returns_counts(self, admin, school_meta, me_priya):
        c1, sec1, _, _, sid = self._pick(school_meta, me_priya)
        tid = me_priya["id"]
        # Submit a clean set (single slot, no conflicts because we're overwriting same class/section)
        payload = {
            "class_id": c1, "section": sec1,
            "slots": [self._slot(c1, sec1, "wed", 3, sid, tid)],
        }
        r = admin.post(f"{API}/timetable/bulk", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["inserted"] == 1
        assert body["notified_teachers"] == 1
        # Verify GET returns it
        got = admin.get(f"{API}/timetable", params={"class_id": c1, "section": sec1}).json()
        assert any(s["day"] == "wed" and s["period"] == 3 and s["teacher_id"] == tid for s in got)
        # Previous slots (tue/2) for same class should be wiped because /bulk replaces
        assert not any(s["day"] == "tue" and s["period"] == 2 for s in got)


# ===========================================================
# /suggest leave-aware filter
# ===========================================================
class TestSuggestLeaveAware:
    def test_suggest_skips_teacher_on_leave(self, priya, admin, school_meta, me_priya):
        # Create + approve a leave for Priya covering an entire week (Mon..Sat)
        # Use a far-future Monday to avoid colliding with other tests/data
        monday = _next_monday(20)
        sat = (date.fromisoformat(monday) + timedelta(days=5)).isoformat()
        cr = priya.post(f"{API}/teacher-leaves", json={
            "start_date": monday, "end_date": sat, "leave_type": "earned",
            "reason": "regression test long leave",
        })
        assert cr.status_code == 200, cr.text
        leave_id = cr.json()["id"]
        ap = admin.post(f"{API}/teacher-leaves/{leave_id}/approve")
        assert ap.status_code == 200

        # Now request /suggest for that week
        cls_with_secs = [c for c in school_meta["classes"] if c.get("sections")]
        c1 = cls_with_secs[0]
        sec1 = c1["sections"][0]
        payload = {
            "class_id": c1["id"], "section": sec1,
            "periods_per_day": 5, "period_minutes": 45, "start_time": "09:00",
            "effective_week_start": monday,
        }
        r = admin.post(f"{API}/timetable/suggest", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        # Priya MUST NOT appear in any teaching slot Mon..Fri because she's on approved leave
        priya_id = me_priya["id"]
        leaked = [s for s in body["slots"] if s.get("teacher_id") == priya_id]
        assert not leaked, f"Priya (on leave) was assigned in slots: {leaked}"

    def test_suggest_without_effective_week_does_not_block(self, admin, school_meta, me_priya):
        # Without effective_week_start, leave-aware filter is bypassed.
        cls_with_secs = [c for c in school_meta["classes"] if c.get("sections")]
        c1 = cls_with_secs[0]
        sec1 = c1["sections"][0]
        payload = {
            "class_id": c1["id"], "section": sec1,
            "periods_per_day": 4, "period_minutes": 45, "start_time": "09:00",
        }
        r = admin.post(f"{API}/timetable/suggest", json=payload)
        assert r.status_code == 200, r.text
        # Just shape assertion — Priya may or may not appear depending on subject assignments
        assert "slots" in r.json()
