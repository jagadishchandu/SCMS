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
    "platform_admin":     ("jagadishchandu789@gmail.com", "Manasa@123"),
    "platform_admin_old": ("platform@scms.com", "Platform@123"),
    "school_admin":       ("principal@sunrise.edu", "School@123"),
    "teacher":            ("priya@sunrise.edu", "Teacher@123"),
    "accounts":           ("accounts@sunrise.edu", "Accounts@123"),
    "parent":             ("parent.stu-00001@sunrise.edu", "Parent@123"),
    "parent2":            ("parent.stu-00002@sunrise.edu", "Parent@123"),
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
@pytest.fixture(scope="session")
def parent2_session():   return login("parent2")


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

    @pytest.mark.parametrize("role", [r for r in CREDS.keys() if r != "platform_admin_old"])
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



# =========================================================================
# Iteration 2: New admin, Twilio scaffolding, Audit, Subscriptions,
# Receipts (PDF), Photo upload, Calendar, RBAC regression
# =========================================================================

class TestNewAdmin:
    """New default admin + legacy admin backward compatibility."""

    def test_new_admin_login_role(self):
        s = login("platform_admin")  # new email
        me = s.get(f"{API}/auth/me", timeout=15).json()
        assert me["email"] == "jagadishchandu789@gmail.com"
        assert me["role"] == "platform_admin"

    def test_legacy_admin_deactivated(self):
        """Iter5: Only ONE Platform Super Admin allowed. Legacy admin must be deactivated."""
        email, pwd = CREDS["platform_admin_old"]
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
        assert r.status_code in (400, 401, 403), r.status_code
        body = r.text.lower()
        assert "deactivated" in body or "disabled" in body or "invalid" in body, body


class TestTwilioQueued:
    """Twilio not configured -> notifications stay queued with delivery_note."""

    def test_attendance_bulk_triggers_queued_whatsapp(self, school_session):
        students = school_session.get(f"{API}/students", timeout=15).json()
        from datetime import date
        entries = [{"student_id": s["id"], "status": "absent"} for s in students[:2]]
        payload = {
            "class_id": students[0]["class_id"], "section": students[0]["section"],
            "date": date.today().isoformat(), "entries": entries,
        }
        r = school_session.post(f"{API}/attendance/bulk", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        notifs = school_session.get(f"{API}/notifications", timeout=15).json()
        assert isinstance(notifs, list) and len(notifs) > 0
        wa = [n for n in notifs if n.get("channel") == "whatsapp"]
        assert len(wa) > 0, "Expected at least one whatsapp notification"
        # at least one queued / not configured
        assert any(n.get("status") == "queued" for n in wa), [n.get("status") for n in wa[:5]]
        assert any((n.get("delivery_note") or "").lower().startswith("twilio") or "twilio_not_configured" in (n.get("delivery_note") or "") for n in wa), \
            [n.get("delivery_note") for n in wa[:5]]


class TestCalendar:
    def test_events_school_admin(self, school_session):
        r = school_session.get(f"{API}/calendar/events", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        types = {e.get("type") for e in data}
        assert "holiday" in types, types
        assert "exam" in types, types

    def test_events_month_filter(self, school_session):
        r = school_session.get(f"{API}/calendar/events", params={"month": "2025-01"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        for e in data:
            assert (e.get("date") or "").startswith("2025-01"), e


class TestAudit:
    def test_audit_returns_list(self, school_session):
        r = school_session.get(f"{API}/audit", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_audit_after_create_student(self, school_session):
        # Capture current count
        before = school_session.get(f"{API}/audit", timeout=15).json()
        before_n = len(before)

        classes = school_session.get(f"{API}/academic/classes", timeout=15).json()
        uid = f"STU-AUD{uuid.uuid4().hex[:5].upper()}"
        payload = {
            "name": "TEST Audit Student", "student_uid": uid,
            "class_id": classes[0]["id"], "section": "A", "roll_number": "199",
            "gender": "M", "dob": "2014-01-01", "admission_date": "2024-06-01",
            "parent": {"name": "TEST Audit Parent", "relationship": "father",
                       "phone": "+91-9000088888", "whatsapp": "+91-9000088888",
                       "email": f"test.aud.{uid.lower()}@sunrise.edu"},
        }
        r = school_session.post(f"{API}/students", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text

        after = school_session.get(f"{API}/audit", timeout=15).json()
        assert len(after) > before_n, f"audit should grow, before={before_n} after={len(after)}"
        # at least one create / student entry
        match = [a for a in after if a.get("action") == "create" and a.get("resource") == "student"
                 and a.get("actor_role") == "school_admin"]
        assert len(match) > 0, after[:3]

    def test_audit_non_admin_empty(self, teacher_session, parent_session):
        for s in (teacher_session, parent_session):
            r = s.get(f"{API}/audit", timeout=15)
            assert r.status_code == 200
            assert r.json() == []


class TestSubscriptionsLegacy:
    """Iter5: /plans and /assign endpoints removed. Verify gone."""
    def test_plans_endpoint_removed(self, platform_session):
        r = platform_session.get(f"{API}/subscriptions/plans", timeout=15)
        assert r.status_code in (404, 405), r.status_code

    def test_assign_endpoint_removed(self, platform_session):
        r = platform_session.post(f"{API}/subscriptions/assign", json={"school_id": "x", "plan_id": "y"}, timeout=15)
        assert r.status_code in (404, 405), r.status_code


class TestReceipts:
    def _get_payment(self, session):
        # ensure we have at least one payment by paying a fee
        fees = session.get(f"{API}/fees", timeout=15).json()
        target = next((f for f in fees if f["due"] > 0), None)
        if not target:
            return None
        r = session.post(f"{API}/fees/payments", json={
            "fee_id": target["id"], "student_id": target["student_id"],
            "amount": min(1000, target["due"]), "method": "cash"
        }, timeout=20)
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_payment_receipt_pdf(self, school_session):
        p = self._get_payment(school_session)
        assert p, "no fee with due"
        pid = p.get("id")
        r = school_session.get(f"{API}/receipts/payment/{pid}.pdf", timeout=20)
        assert r.status_code == 200, r.text[:200]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"

    def test_payment_receipt_cross_school_forbidden(self, school_session, platform_session):
        # create another school + admin, login as that admin and try fetch DEMO payment
        p = self._get_payment(school_session)
        assert p
        code = f"X{uuid.uuid4().hex[:5].upper()}"
        admin_email = f"adminx.{code.lower()}@test.edu"
        payload = {"name": f"X {code}", "code": code, "address": "x", "phone": "+91",
                   "email": f"info-{code.lower()}@x.edu", "academic_year": "2025-2026",
                   "admin_email": admin_email, "admin_password": "Admin@123",
                   "admin_name": "X Admin"}
        rs = platform_session.post(f"{API}/schools", json=payload, timeout=20)
        assert rs.status_code in (200, 201), rs.text
        # login as new admin
        s2 = requests.Session()
        lr = s2.post(f"{API}/auth/login", json={"email": admin_email, "password": "Admin@123"}, timeout=15)
        assert lr.status_code == 200, lr.text
        rcross = s2.get(f"{API}/receipts/payment/{p['id']}.pdf", timeout=15)
        assert rcross.status_code == 403, rcross.status_code

    def test_student_report_pdf_school_admin(self, school_session):
        r = school_session.get(f"{API}/receipts/student/STU-00001/report.pdf", timeout=25)
        assert r.status_code == 200, r.text[:200]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"

    def test_student_report_parent_own_child(self, parent_session):
        r = parent_session.get(f"{API}/receipts/student/STU-00001/report.pdf", timeout=25)
        assert r.status_code == 200, r.text[:200]
        assert r.content[:4] == b"%PDF"

    def test_student_report_other_parent_404(self, parent_session):
        r = parent_session.get(f"{API}/receipts/student/STU-00002/report.pdf", timeout=15)
        assert r.status_code == 404


class TestPhotoUpload:
    # minimal valid PNG 1x1
    PNG_BYTES = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
    )

    def _stu_id(self, session, uid="STU-00001"):
        students = session.get(f"{API}/students", timeout=15).json()
        s = next(s for s in students if s["student_uid"] == uid)
        return s["id"]

    def test_admin_upload_and_read_back(self, school_session):
        sid = self._stu_id(school_session)
        files = {"file": ("p.png", self.PNG_BYTES, "image/png")}
        r = school_session.post(f"{API}/students/{sid}/photo", files=files, timeout=20)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("photo", "").startswith("data:image/png;base64,")
        # read back
        students = school_session.get(f"{API}/students", timeout=15).json()
        match = next(s for s in students if s["id"] == sid)
        assert (match.get("photo") or "").startswith("data:image/png;base64,")

    def test_reject_non_image(self, school_session):
        sid = self._stu_id(school_session)
        files = {"file": ("p.txt", b"hello", "text/plain")}
        r = school_session.post(f"{API}/students/{sid}/photo", files=files, timeout=15)
        assert r.status_code == 400, r.status_code

    def test_parent_upload_own_child(self, parent_session, school_session):
        sid = self._stu_id(school_session, "STU-00001")
        files = {"file": ("p.png", self.PNG_BYTES, "image/png")}
        r = parent_session.post(f"{API}/students/{sid}/photo", files=files, timeout=15)
        assert r.status_code in (200, 201), r.text

    def test_parent_cannot_upload_other_child(self, parent_session, school_session):
        sid_other = self._stu_id(school_session, "STU-00002")
        files = {"file": ("p.png", self.PNG_BYTES, "image/png")}
        r = parent_session.post(f"{API}/students/{sid_other}/photo", files=files, timeout=15)
        assert r.status_code == 403, r.status_code


# =========================================================================
# Iteration 3: Monthly parent digest (preview + run-monthly)
# =========================================================================

class TestDigests:
    """Monthly digest preview + run-monthly across roles."""

    def test_preview_school_admin(self, school_session):
        r = school_session.get(f"{API}/digests/preview/STU-00001", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("label", "start", "end", "data", "message"):
            assert k in body, body
        data = body["data"]
        for k in ("att_total", "att_pct", "absent", "sick", "marks_pct", "fee_due"):
            assert k in data, data
        msg = body["message"]
        assert isinstance(msg, str) and "\n" in msg, msg
        assert "Sunrise Public School" in msg
        assert "Aarav Sharma" in msg or "STU-00001" in msg
        assert body["label"] in msg  # period mentioned in message

    def test_preview_parent_own_child(self, parent_session):
        r = parent_session.get(f"{API}/digests/preview/STU-00001", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "message" in body and "data" in body

    def test_preview_parent_other_child_404(self, parent_session):
        r = parent_session.get(f"{API}/digests/preview/STU-00002", timeout=15)
        assert r.status_code == 404, r.status_code

    def test_run_monthly_school_admin(self, school_session):
        r = school_session.post(f"{API}/digests/run-monthly", timeout=60)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert "period" in body and "totals" in body and "by_school" in body
        totals = body["totals"]
        for k in ("sent", "queued", "failed"):
            assert k in totals, totals
        assert isinstance(body["by_school"], list)
        assert len(body["by_school"]) == 1, body["by_school"]
        bs = body["by_school"][0]
        for k in ("school_id", "school_name", "students", "sent", "queued", "failed"):
            assert k in bs, bs
        assert bs["students"] > 0, bs
        # Twilio not configured => queued count should match students count
        assert bs["queued"] == bs["students"], bs

    def test_notifications_have_monthly_digest_after_run(self, school_session):
        # ensure run was called
        school_session.post(f"{API}/digests/run-monthly", timeout=60)
        notifs = school_session.get(f"{API}/notifications", params={"limit": 200}, timeout=20).json()
        assert isinstance(notifs, list)
        md = [n for n in notifs if n.get("template") == "monthly_digest"]
        assert len(md) > 0, f"No monthly_digest notifications found; sample={notifs[:2]}"
        # all should be whatsapp + queued + twilio_not_configured
        assert all(n.get("channel") == "whatsapp" for n in md), [n.get("channel") for n in md[:5]]
        assert all(n.get("status") == "queued" for n in md), [n.get("status") for n in md[:5]]
        assert all("twilio_not_configured" in (n.get("delivery_note") or "") for n in md), \
            [n.get("delivery_note") for n in md[:5]]

    def test_run_monthly_platform_admin_all_schools(self, platform_session):
        r = platform_session.post(f"{API}/digests/run-monthly", timeout=120)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert isinstance(body["by_school"], list)
        assert len(body["by_school"]) >= 1, body["by_school"]

    def test_run_monthly_rbac_teacher_forbidden(self, teacher_session):
        r = teacher_session.post(f"{API}/digests/run-monthly", timeout=15)
        assert r.status_code == 403, r.status_code

    def test_run_monthly_rbac_parent_forbidden(self, parent_session):
        r = parent_session.post(f"{API}/digests/run-monthly", timeout=15)
        assert r.status_code == 403, r.status_code

    def test_run_monthly_rbac_accounts_forbidden(self, accounts_session):
        r = accounts_session.post(f"{API}/digests/run-monthly", timeout=15)
        assert r.status_code == 403, r.status_code

    def test_audit_logged_after_run_monthly(self, school_session):
        before = school_session.get(f"{API}/audit", timeout=15).json()
        before_latest = max(
            (a.get("created_at", "") for a in before
             if a.get("action") == "run_monthly_digest"
             and a.get("resource") == "digest"
             and a.get("actor_role") == "school_admin"),
            default="",
        )
        r = school_session.post(f"{API}/digests/run-monthly", timeout=60)
        assert r.status_code in (200, 201), r.text
        after = school_session.get(f"{API}/audit", timeout=15).json()
        match = [a for a in after if a.get("action") == "run_monthly_digest"
                 and a.get("resource") == "digest"
                 and a.get("actor_role") == "school_admin"
                 and a.get("created_at", "") > before_latest]
        assert len(match) > 0, f"Expected new run_monthly_digest audit entry after {before_latest}; got {after[:3]}"



# =========================================================================
# Iteration 4: per-school DB, risk-students, activities, not_in_class, scheduler
# =========================================================================

class TestPerSchoolDB:
    def test_demo_school_has_db_name(self, platform_session):
        schools = platform_session.get(f"{API}/schools", timeout=15).json()
        demo = next(s for s in schools if s["code"] == "DEMO")
        # After startup backfill, db_name should be set
        assert demo.get("db_name", "").startswith("scms_db_school_"), demo

    def test_create_school_returns_db_name(self, platform_session):
        code = f"DBT{uuid.uuid4().hex[:6].upper()}"
        payload = {
            "name": f"TEST DB {code}", "code": code, "address": "a", "phone": "+91",
            "email": f"info-{code.lower()}@x.edu", "academic_year": "2025-2026",
            "admin_email": f"adb.{code.lower()}@test.edu",
            "admin_password": "Admin@123", "admin_name": "DB Admin",
        }
        r = platform_session.post(f"{API}/schools", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        # Either the response contains db_name OR fetching the school list reflects it
        if "db_name" not in body:
            schools = platform_session.get(f"{API}/schools", timeout=15).json()
            s = next((x for x in schools if x["code"] == code), None)
            assert s is not None
            assert s.get("db_name", "").startswith("scms_db_school_"), s
        else:
            assert body["db_name"].startswith("scms_db_school_"), body


class TestRiskStudents:
    def test_risk_school_admin(self, school_session):
        r = school_session.get(f"{API}/analytics/risk-students", params={"limit": 5}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) <= 5
        # validate shape if any
        for item in data:
            for k in ("student", "score", "cur_attendance_pct", "prev_attendance_pct",
                      "att_drop", "cur_marks_pct", "prev_marks_pct", "mark_drop", "reasons"):
                assert k in item, item
            for sk in ("id", "student_uid", "name", "class_name", "section"):
                assert sk in item["student"], item["student"]
            assert isinstance(item["reasons"], list)
        # sorted desc by score
        scores = [i["score"] for i in data]
        assert scores == sorted(scores, reverse=True), scores

    def test_risk_teacher_forbidden(self, teacher_session):
        r = teacher_session.get(f"{API}/analytics/risk-students", timeout=15)
        assert r.status_code == 403

    def test_risk_accounts_forbidden(self, accounts_session):
        r = accounts_session.get(f"{API}/analytics/risk-students", timeout=15)
        assert r.status_code == 403

    def test_risk_parent_forbidden(self, parent_session):
        r = parent_session.get(f"{API}/analytics/risk-students", timeout=15)
        assert r.status_code == 403


class TestActivities:
    def test_list_seeded(self, school_session):
        r = school_session.get(f"{API}/activities", timeout=15)
        assert r.status_code == 200
        data = r.json()
        names = {a["name"] for a in data}
        assert {"Cricket", "Football", "Chess Club", "Violin", "Painting"} <= names, names

    def test_create_as_school_admin(self, school_session):
        name = f"TEST Activity {uuid.uuid4().hex[:5]}"
        r = school_session.post(f"{API}/activities", json={
            "name": name, "category": "club", "coach": "T", "schedule": "Mon 5pm"
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["name"] == name
        assert "id" in body
        assert "_id" not in body
        return body

    def test_teacher_cannot_create(self, teacher_session):
        r = teacher_session.post(f"{API}/activities", json={"name": "X", "category": "club"}, timeout=15)
        assert r.status_code == 403

    def test_parent_cannot_create(self, parent_session):
        r = parent_session.post(f"{API}/activities", json={"name": "X", "category": "club"}, timeout=15)
        assert r.status_code == 403

    def test_enroll_roster_unenroll_and_dup_ignored(self, school_session):
        # create activity
        name = f"TEST Enroll {uuid.uuid4().hex[:5]}"
        cr = school_session.post(f"{API}/activities", json={"name": name, "category": "sport"}, timeout=15)
        assert cr.status_code in (200, 201)
        aid = cr.json()["id"]
        students = school_session.get(f"{API}/students", timeout=15).json()
        sids = [s["id"] for s in students[:3]]
        # enroll 3
        r1 = school_session.post(f"{API}/activities/{aid}/enroll", json={"student_ids": sids}, timeout=15)
        assert r1.status_code in (200, 201), r1.text
        assert r1.json()["enrolled"] == 3
        # duplicate enroll => 0 added
        r2 = school_session.post(f"{API}/activities/{aid}/enroll", json={"student_ids": sids}, timeout=15)
        assert r2.status_code in (200, 201)
        assert r2.json()["enrolled"] == 0, r2.json()
        # roster
        rr = school_session.get(f"{API}/activities/{aid}/roster", timeout=15)
        assert rr.status_code == 200
        roster = rr.json()
        assert isinstance(roster, list)
        assert len(roster) == 3
        # unenroll one
        du = school_session.delete(f"{API}/activities/{aid}/enroll/{sids[0]}", timeout=15)
        assert du.status_code in (200, 204)
        rr2 = school_session.get(f"{API}/activities/{aid}/roster", timeout=15).json()
        assert len(rr2) == 2

    def test_stats_summary(self, school_session):
        r = school_session.get(f"{API}/activities/stats/summary", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("total_activities", "active_activities", "by_category", "per_activity"):
            assert k in body, body
        assert body["total_activities"] >= 5
        # per_activity sorted by enrolled desc
        enrolled = [p["enrolled"] for p in body["per_activity"]]
        assert enrolled == sorted(enrolled, reverse=True), enrolled


class TestNotInClassAttendance:
    def test_bulk_accepts_not_in_class(self, school_session):
        students = school_session.get(f"{API}/students", timeout=15).json()
        from datetime import date, timedelta
        # use a past date to avoid collisions; tomorrow not allowed maybe — use 30 days back
        d = (date.today() - timedelta(days=30)).isoformat()
        entries = [{"student_id": students[0]["id"], "status": "not_in_class"}]
        payload = {
            "class_id": students[0]["class_id"],
            "section": students[0]["section"],
            "date": d, "entries": entries,
        }
        r = school_session.post(f"{API}/attendance/bulk", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        # fetch and ensure record exists with that status
        ar = school_session.get(f"{API}/attendance", params={"date": d}, timeout=15)
        assert ar.status_code == 200
        rows = ar.json()
        match = [x for x in rows if x.get("student_id") == students[0]["id"] and x.get("status") == "not_in_class"]
        assert len(match) >= 1, rows[:5]


class TestSchedulerDisabled:
    def test_health_still_ok(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_scheduler_module_imports(self):
        # If backend is up, scheduler module must have imported without crash.
        # Confirm by hitting any auth route — no 500.
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200, r.text


# =========================================================================
# Iteration 5: Per-child subscription pricing + payment confirmation workflow
#              + Single Super Admin policy
# =========================================================================

PRICE_M = 30
PRICE_Y = 300


class TestPerChildPricing:
    def test_pricing_constants(self, school_session):
        r = school_session.get(f"{API}/subscriptions/pricing", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["per_child_monthly"] == PRICE_M
        assert body["per_child_yearly"] == PRICE_Y
        assert body["currency"] == "INR"

    def test_pricing_accessible_to_all_roles(self, teacher_session, parent_session, accounts_session, platform_session):
        for s in (teacher_session, parent_session, accounts_session, platform_session):
            r = s.get(f"{API}/subscriptions/pricing", timeout=15)
            assert r.status_code == 200, r.text

    def test_pricing_unauth_rejected(self):
        r = requests.get(f"{API}/subscriptions/pricing", timeout=15)
        assert r.status_code in (401, 403), r.status_code


class TestSubscriptionQuote:
    def test_my_school_admin(self, school_session):
        r = school_session.get(f"{API}/subscriptions/my", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("school", "subscription", "quote"):
            assert k in body, body
        q = body["quote"]
        n = q["students_active"]
        assert n > 0
        assert q["monthly"]["amount"] == n * PRICE_M
        assert q["yearly"]["amount"] == n * PRICE_Y
        # savings = n*360 - n*300
        assert q["yearly"]["savings_vs_monthly"] == n * (PRICE_M * 12) - n * PRICE_Y

    def test_my_rejects_other_roles(self, teacher_session, parent_session, accounts_session, platform_session):
        for s in (teacher_session, parent_session, accounts_session, platform_session):
            r = s.get(f"{API}/subscriptions/my", timeout=15)
            assert r.status_code == 403, r.status_code


class TestSubscriptionPaymentFlow:
    def _cleanup_pending(self, platform_session, school_session):
        # Reject any leftover pending payments for DEMO so tests start clean.
        pays = school_session.get(f"{API}/subscriptions/payments", timeout=15).json()
        for p in pays:
            if p.get("status") == "pending_confirmation":
                platform_session.post(f"{API}/subscriptions/payments/{p['id']}/reject", timeout=15)

    def test_submit_monthly_then_block_duplicate(self, school_session, platform_session):
        self._cleanup_pending(platform_session, school_session)
        r = school_session.post(f"{API}/subscriptions/payments",
                                json={"billing_cycle": "monthly", "payment_reference": "TEST-UTR-1"},
                                timeout=15)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["status"] == "pending_confirmation"
        assert body["billing_cycle"] == "monthly"
        assert body["rate_per_child"] == PRICE_M
        assert body["amount"] == body["students_count"] * PRICE_M

        # 2nd should be blocked
        r2 = school_session.post(f"{API}/subscriptions/payments",
                                 json={"billing_cycle": "yearly"}, timeout=15)
        assert r2.status_code == 400, r2.text
        # cleanup: reject it
        platform_session.post(f"{API}/subscriptions/payments/{body['id']}/reject", timeout=15)

    def test_school_admin_lists_only_own(self, school_session):
        r = school_session.get(f"{API}/subscriptions/payments", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # all entries should be for own school
        me = school_session.get(f"{API}/auth/me", timeout=15).json()
        for p in data:
            assert p["school_id"] == me["school_id"], p

    def test_platform_admin_lists_all(self, platform_session):
        r = platform_session.get(f"{API}/subscriptions/payments", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_confirm_payment_activates_subscription(self, school_session, platform_session):
        self._cleanup_pending(platform_session, school_session)
        # submit yearly
        sr = school_session.post(f"{API}/subscriptions/payments",
                                 json={"billing_cycle": "yearly", "payment_reference": "TEST-UTR-Y"},
                                 timeout=15)
        assert sr.status_code in (200, 201), sr.text
        pid = sr.json()["id"]

        # platform confirms
        cr = platform_session.post(f"{API}/subscriptions/payments/{pid}/confirm", timeout=15)
        assert cr.status_code in (200, 201), cr.text
        body = cr.json()
        assert body["ok"] is True
        sub = body["subscription"]
        assert sub["status"] == "active"
        assert sub["billing_cycle"] == "yearly"

        # verify school.subscription updated via /my
        my = school_session.get(f"{API}/subscriptions/my", timeout=15).json()
        assert my["subscription"]["status"] == "active"
        assert my["subscription"]["billing_cycle"] == "yearly"

        # already confirmed -> 400
        c2 = platform_session.post(f"{API}/subscriptions/payments/{pid}/confirm", timeout=15)
        assert c2.status_code == 400

    def test_reject_payment(self, school_session, platform_session):
        self._cleanup_pending(platform_session, school_session)
        sr = school_session.post(f"{API}/subscriptions/payments",
                                 json={"billing_cycle": "monthly"}, timeout=15)
        assert sr.status_code in (200, 201)
        pid = sr.json()["id"]
        rr = platform_session.post(f"{API}/subscriptions/payments/{pid}/reject", timeout=15)
        assert rr.status_code in (200, 201), rr.text
        # verify status
        pays = platform_session.get(f"{API}/subscriptions/payments", timeout=15).json()
        match = next(p for p in pays if p["id"] == pid)
        assert match["status"] == "rejected"

    def test_rbac_other_roles_forbidden(self, teacher_session, parent_session, accounts_session):
        for s in (teacher_session, parent_session, accounts_session):
            r = s.post(f"{API}/subscriptions/payments",
                       json={"billing_cycle": "monthly"}, timeout=15)
            assert r.status_code == 403, r.status_code
            r2 = s.get(f"{API}/subscriptions/payments", timeout=15)
            assert r2.status_code == 403, r2.status_code

    def test_confirm_reject_only_platform_admin(self, school_session, teacher_session):
        for s in (school_session, teacher_session):
            r = s.post(f"{API}/subscriptions/payments/nope/confirm", timeout=15)
            assert r.status_code == 403, r.status_code
            r2 = s.post(f"{API}/subscriptions/payments/nope/reject", timeout=15)
            assert r2.status_code == 403, r2.status_code


class TestSingleSuperAdmin:
    def test_create_school_admin_blocked(self, school_session):
        r = school_session.post(f"{API}/users", json={
            "email": f"newsuper.{uuid.uuid4().hex[:5]}@x.edu",
            "password": "X@12345678", "name": "New Admin", "role": "school_admin",
        }, timeout=15)
        assert r.status_code == 403, r.status_code
        assert "Super Admin" in r.text or "super admin" in r.text.lower(), r.text

    def test_create_platform_admin_rejected_schema(self, school_session):
        r = school_session.post(f"{API}/users", json={
            "email": f"newplat.{uuid.uuid4().hex[:5]}@x.edu",
            "password": "X@12345678", "name": "Plat", "role": "platform_admin",
        }, timeout=15)
        # Either schema 422 or policy 403 — both acceptable
        assert r.status_code in (403, 422), r.status_code

    def test_create_teacher_still_works(self, school_session):
        r = school_session.post(f"{API}/users", json={
            "email": f"t.{uuid.uuid4().hex[:6]}@sunrise.edu",
            "password": "T@12345678", "name": "T", "role": "teacher",
        }, timeout=15)
        assert r.status_code in (200, 201), r.text

    def test_create_accounts_still_works(self, school_session):
        r = school_session.post(f"{API}/users", json={
            "email": f"a.{uuid.uuid4().hex[:6]}@sunrise.edu",
            "password": "A@12345678", "name": "A", "role": "accounts",
        }, timeout=15)
        assert r.status_code in (200, 201), r.text

    def test_create_parent_still_works(self, school_session):
        r = school_session.post(f"{API}/users", json={
            "email": f"p.{uuid.uuid4().hex[:6]}@sunrise.edu",
            "password": "P@12345678", "name": "P", "role": "parent",
        }, timeout=15)
        assert r.status_code in (200, 201), r.text

    def test_new_platform_admin_logs_in(self):
        s = login("platform_admin")
        me = s.get(f"{API}/auth/me", timeout=15).json()
        assert me["email"] == "jagadishchandu789@gmail.com"
        assert me["role"] == "platform_admin"

