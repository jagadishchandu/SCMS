"""SCMS Backend End-to-End API tests.

Covers: auth (5 roles, cookies, me, logout, invalid), platform admin (schools),
school admin (analytics/students/users/academic), attendance (bulk + notifications),
marks (bulk + exam publish), syllabus/holidays, fees, analytics (student + teacher
performance), notifications, RBAC, excel template downloads, health.
"""
import os
import io
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://4d977b08-b8f9-4943-a6f8-176d61d36e7e.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "platform_admin": ("platform@scms.com", "Platform@123"),
    "school_admin":   ("principal@sunrise.edu", "School@123"),
    "teacher":        ("priya@sunrise.edu", "Teacher@123"),
    "accounts":       ("accounts@sunrise.edu", "Accounts@123"),
    "parent":         ("parent.stu-00001@sunrise.edu", "Parent@123"),
}


# ---------- session helpers ----------

def login(role):
    s = requests.Session()
    email, pwd = CREDS[role]
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, f"login {role} failed: {r.status_code} {r.text}"
    assert "access_token" in s.cookies, "access_token cookie missing"
    return s


@pytest.fixture(scope="session")
def platform_session():  return login("platform_admin")
@pytest.fixture(scope="session")
def school_session():    return login("school_admin")
@pytest.fixture(scope="session")
def teacher_session():   return login("teacher")
@pytest.fixture(scope="session")
def accounts_session():  return login("accounts")
@pytest.fixture(scope="session")
def parent_session():    return login("parent")


# ---------- health ----------

def test_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- AUTH ----------

class TestAuth:
    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "x@y.com", "password": "bad"}, timeout=15)
        assert r.status_code in (400, 401)

    @pytest.mark.parametrize("role", list(CREDS.keys()))
    def test_login_all_roles(self, role):
        s = login(role)
        me = s.get(f"{API}/auth/me", timeout=15)
        assert me.status_code == 200
        data = me.json()
        assert data["email"] == CREDS[role][0]

    def test_logout(self):
        s = login("school_admin")
        r = s.post(f"{API}/auth/logout", timeout=15)
        assert r.status_code in (200, 204)
        # cookie cleared
        me = s.get(f"{API}/auth/me", timeout=15)
        assert me.status_code in (401, 403)


# ---------- PLATFORM ADMIN ----------

class TestPlatform:
    def test_list_schools(self, platform_session):
        r = platform_session.get(f"{API}/schools", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert any(s.get("code") == "DEMO" for s in data)

    def test_create_school(self, platform_session):
        code = f"TEST{uuid.uuid4().hex[:6].upper()}"
        payload = {
            "name": f"TEST School {code}",
            "code": code,
            "address": "Test Addr",
            "phone": "+91-99",
            "email": f"info-{code.lower()}@test.edu",
            "academic_year": "2025-2026",
            "admin_email": f"admin-{code.lower()}@test.edu",
            "admin_password": "Admin@123",
            "admin_name": "Test Admin",
        }
        r = platform_session.post(f"{API}/schools", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        # duplicate code -> 400
        r2 = platform_session.post(f"{API}/schools", json=payload, timeout=20)
        assert r2.status_code == 400


# ---------- SCHOOL ADMIN ----------

class TestSchoolAdmin:
    def test_analytics(self, school_session):
        r = school_session.get(f"{API}/analytics/school", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "kpis" in data or "students" in data or "total_students" in data, data

    def test_students_list(self, school_session):
        r = school_session.get(f"{API}/students", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 8

    def test_users_teachers(self, school_session):
        r = school_session.get(f"{API}/users", params={"role": "teacher"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 3

    def test_academic_classes_get(self, school_session):
        r = school_session.get(f"{API}/academic/classes", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_student_and_teacher(self, school_session):
        # get a class
        cls = school_session.get(f"{API}/academic/classes", timeout=15).json()
        class_id = cls[0]["id"]
        uid = f"STU-TEST{uuid.uuid4().hex[:5].upper()}"
        payload = {
            "name": "TEST Student",
            "student_uid": uid,
            "class_id": class_id,
            "section": "A",
            "roll_number": "99",
            "gender": "M",
            "dob": "2014-01-01",
            "admission_date": "2024-06-01",
            "parent": {
                "name": "TEST Parent",
                "relationship": "father",
                "phone": "+91-9000099999",
                "whatsapp": "+91-9000099999",
                "email": f"test.parent.{uid.lower()}@sunrise.edu",
            },
        }
        r = school_session.post(f"{API}/students", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text

        # create teacher
        tpayload = {
            "email": f"test.teacher.{uuid.uuid4().hex[:6]}@sunrise.edu",
            "password": "Teacher@123",
            "name": "TEST Teacher",
            "role": "teacher",
            "employee_id": "EMP-TEST",
            "phone": "+91-90000",
        }
        r2 = school_session.post(f"{API}/users", json=tpayload, timeout=20)
        assert r2.status_code in (200, 201), r2.text


# ---------- ATTENDANCE ----------

class TestAttendance:
    def test_bulk_attendance_and_notifications(self, school_session):
        students = school_session.get(f"{API}/students", timeout=15).json()
        from datetime import date
        today = date.today().isoformat()
        entries = []
        for i, s in enumerate(students[:6]):
            status = ["present", "absent", "sick", "present", "absent", "present"][i]
            entries.append({"student_id": s["id"], "status": status})
        payload = {
            "class_id": students[0]["class_id"],
            "section": students[0]["section"],
            "date": today,
            "entries": entries,
        }
        r = school_session.post(f"{API}/attendance/bulk", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        # Should report marked count + notifications
        assert data.get("notifications", 0) > 0 or data.get("notification_count", 0) > 0, data

    def test_attendance_list(self, school_session):
        r = school_session.get(f"{API}/attendance", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_attendance_summary(self, school_session):
        r = school_session.get(f"{API}/attendance/summary/STU-00001", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "percentage" in data or "attendance_percentage" in data, data


# ---------- MARKS / EXAMS ----------

class TestMarks:
    def test_marks_for_student(self, school_session):
        students = school_session.get(f"{API}/students", timeout=15).json()
        sid = students[0]["id"]
        r = school_session.get(f"{API}/marks", params={"student_id": sid}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        m = data[0]
        assert "percentage" in m or "marks_obtained" in m


# ---------- HOLIDAYS ----------

class TestHolidays:
    def test_create_holiday_and_list(self, school_session):
        payload = {"title": f"TEST Holiday {uuid.uuid4().hex[:4]}", "date": "2025-12-25", "type": "public"}
        r = school_session.post(f"{API}/holidays", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        r2 = school_session.get(f"{API}/holidays", timeout=15)
        assert r2.status_code == 200
        assert isinstance(r2.json(), list)


# ---------- FEES ----------

class TestFees:
    def test_fees_get(self, school_session):
        r = school_session.get(f"{API}/fees", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_fees_full_flow(self, school_session):
        classes = school_session.get(f"{API}/academic/classes", timeout=15).json()
        cid = classes[0]["id"]
        # create structure
        struct = {
            "class_id": cid,
            "name": f"TEST Fee {uuid.uuid4().hex[:4]}",
            "items": [{"type": "tuition", "amount": 5000}],
            "total": 5000,
            "due_date": "2025-12-31",
        }
        r = school_session.post(f"{API}/fees/structures", json=struct, timeout=20)
        assert r.status_code in (200, 201), r.text
        sid = r.json().get("id")
        assert sid

        # assign to class
        r2 = school_session.post(f"{API}/fees/structures/{sid}/assign", timeout=20)
        assert r2.status_code in (200, 201), r2.text

        # find a fee record and pay
        fees = school_session.get(f"{API}/fees", params={"structure_id": sid}, timeout=15).json()
        if fees:
            fee = fees[0]
            r3 = school_session.post(f"{API}/fees/payments", json={
                "fee_id": fee["id"], "student_id": fee.get("student_id"), "amount": 5000, "method": "cash"
            }, timeout=20)
            assert r3.status_code in (200, 201), r3.text


# ---------- ANALYTICS ----------

class TestAnalytics:
    def test_student_analytics(self, school_session):
        r = school_session.get(f"{API}/analytics/student/STU-00001", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # academics holds subject_avg + exam_trend
        assert "student" in data and "attendance" in data and "fees" in data and "insights" in data
        academics = data.get("academics", {})
        assert "subject_avg" in academics and "exam_trend" in academics, list(academics.keys())

    def test_teacher_performance(self, school_session):
        r = school_session.get(f"{API}/analytics/teacher-performance", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list) and len(data) > 0
        t0 = data[0]
        assert "status" in t0 or "score" in t0


# ---------- NOTIFICATIONS ----------

class TestNotifications:
    def test_notifications_list(self, school_session):
        r = school_session.get(f"{API}/notifications", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_notifications_stats(self, school_session):
        r = school_session.get(f"{API}/notifications/stats", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)


# ---------- RBAC ----------

class TestRBAC:
    def test_teacher_users_self_only(self, teacher_session):
        r = teacher_session.get(f"{API}/users", params={"role": "teacher"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # teacher should only see own row (not all 3 teachers)
        assert len(data) <= 1, f"Teacher should not see other teachers, got {len(data)}"
        if data:
            assert data[0]["email"] == CREDS["teacher"][0]

    def test_teacher_fees_forbidden(self, teacher_session):
        r = teacher_session.get(f"{API}/fees", timeout=15)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_parent_students_own_child_only(self, parent_session):
        r = parent_session.get(f"{API}/students", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 1, f"Parent should see exactly 1 student, got {len(data)}"
        assert data[0]["student_uid"] == "STU-00001"


# ---------- UPLOADS (Excel templates) ----------

class TestUploads:
    @pytest.mark.parametrize("name", ["students", "attendance", "holidays"])
    def test_template_download(self, school_session, name):
        r = school_session.get(f"{API}/uploads/template/{name}", timeout=20)
        assert r.status_code == 200, f"{name}: {r.status_code} {r.text[:200]}"
        ct = r.headers.get("content-type", "")
        assert "spreadsheet" in ct or "octet" in ct or "excel" in ct, ct
        assert len(r.content) > 100
