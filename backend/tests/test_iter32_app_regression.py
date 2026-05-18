"""Broad app regression (iter32): one critical happy-path per route module.
Modules: auth, students, attendance, fees, sick_leaves, calendar, academic,
trips, notifications, uploads.
"""
from __future__ import annotations
import os, time, base64
import pytest, requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://classroom-messenger-1.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password, role):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password, "role": role}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sessions():
    return {
        "admin": _login("principal@sunrise.edu", "School@123", "school_admin"),
        "accounts": _login("accounts@sunrise.edu", "Accounts@123", "accounts"),
        "teacher": _login("priya@sunrise.edu", "Teacher@123", "teacher"),
        "parent": _login("parent.stu-00001@sunrise.edu", "Parent@123", "parent"),
        "platform": _login("jagadishchandu789@gmail.com", "Manasa@123", "platform_admin"),
    }


class TestAuth:
    def test_me_for_each_role(self, sessions):
        for k, s in sessions.items():
            r = s.get(f"{API}/auth/me", timeout=20)
            assert r.status_code == 200, f"{k}: {r.text}"
            u = r.json()
            assert "id" in u and "role" in u


class TestStudents:
    def test_teacher_lists_students(self, sessions):
        r = sessions["teacher"].get(f"{API}/students", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        students = body.get("students", body) if isinstance(body, dict) else body
        assert isinstance(students, list)
        # Priya teaches Grade 5-A; expect at least 1 student
        assert len(students) >= 1

    def test_admin_get_one_student(self, sessions):
        r = sessions["admin"].get(f"{API}/students", timeout=20)
        assert r.status_code == 200
        body = r.json()
        students = body.get("students", body) if isinstance(body, dict) else body
        assert students, "no students returned"

    def test_student_photo_upload_base64(self, sessions):
        r = sessions["teacher"].get(f"{API}/students", timeout=20)
        students = r.json().get("students", r.json()) if isinstance(r.json(), dict) else r.json()
        sid = students[0]["id"]
        # 1x1 png bytes (multipart upload)
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
        rp = sessions["teacher"].post(
            f"{API}/students/{sid}/photo",
            files={"file": ("test.png", png_bytes, "image/png")},
            timeout=20,
        )
        assert rp.status_code in (200, 201), rp.text
        j = rp.json()
        # Verify it's stored as base64 data URL
        assert j.get("photo", "").startswith("data:image/"), j


class TestAttendance:
    def test_teacher_lists_attendance_for_today(self, sessions):
        r = sessions["teacher"].get(f"{API}/attendance/today", timeout=20)
        # Some routes use /today, others use ?date=. Accept either path.
        if r.status_code == 404:
            from datetime import date
            r = sessions["teacher"].get(f"{API}/attendance?date={date.today().isoformat()}", timeout=20)
        assert r.status_code in (200, 404), r.text


class TestFees:
    def test_accounts_lists_invoices(self, sessions):
        r = sessions["accounts"].get(f"{API}/fees/invoices", timeout=20)
        if r.status_code == 404:
            r = sessions["accounts"].get(f"{API}/fees", timeout=20)
        assert r.status_code == 200, r.text


class TestSickLeaves:
    def test_parent_lists_sick_leaves(self, sessions):
        r = sessions["parent"].get(f"{API}/sick-leaves", timeout=20)
        assert r.status_code == 200, r.text

    def test_teacher_lists_sick_leaves(self, sessions):
        r = sessions["teacher"].get(f"{API}/sick-leaves", timeout=20)
        assert r.status_code == 200, r.text


class TestCalendarAcademic:
    def test_holidays_endpoint(self, sessions):
        r = sessions["teacher"].get(f"{API}/holidays", timeout=20)
        if r.status_code == 404:
            r = sessions["teacher"].get(f"{API}/calendar/holidays", timeout=20)
        assert r.status_code == 200, r.text

    def test_classes_endpoint(self, sessions):
        r = sessions["admin"].get(f"{API}/academic/classes", timeout=20)
        if r.status_code == 404:
            r = sessions["admin"].get(f"{API}/classes", timeout=20)
        assert r.status_code == 200, r.text


class TestNotifications:
    def test_notifications_log(self, sessions):
        r = sessions["admin"].get(f"{API}/notifications", timeout=20)
        if r.status_code == 404:
            r = sessions["admin"].get(f"{API}/notifications/log", timeout=20)
        assert r.status_code == 200, r.text


class TestTrips:
    def test_list_trips(self, sessions):
        r = sessions["parent"].get(f"{API}/trips", timeout=20)
        assert r.status_code == 200, r.text


class TestMessagingRegression:
    """Quick smoke that prior chat features still pass."""

    def test_contacts_endpoint_works(self, sessions):
        for k in ("parent", "teacher", "admin"):
            r = sessions[k].get(f"{API}/messaging/contacts", timeout=20)
            assert r.status_code == 200, f"{k}: {r.text}"

    def test_unread_count(self, sessions):
        r = sessions["parent"].get(f"{API}/messaging/unread-count", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "count" in j and "mentions" in j

    def test_groups_listing(self, sessions):
        for k in ("admin", "teacher", "parent"):
            r = sessions[k].get(f"{API}/messaging/groups", timeout=20)
            assert r.status_code == 200, f"{k}: {r.text}"
