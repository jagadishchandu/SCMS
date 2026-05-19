"""Tests for v1.17: HR/Finance — staff, salaries, expenses, teacher reimbursements."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://case-insensitive-id.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"{email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def ctx():
    plat = _login(*PLATFORM)
    suffix = uuid.uuid4().hex[:6].upper()
    admin_email = f"v17.admin.{suffix.lower()}@v17.example.com"
    admin_pw = "Admin@2026"
    r = plat.post(f"{API}/schools", json={
        "name": f"V17 School {suffix}", "code": f"V17{suffix}",
        "address": "x", "phone": "+910", "email": f"info.{suffix.lower()}@v17.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email, "admin_password": admin_pw, "admin_name": "V17 Admin",
        "auto_approve": True,
    }, timeout=20)
    assert r.status_code == 200
    school = r.json()["school"]
    sa = _login(admin_email, admin_pw)

    # Pre-create a subject so teacher creation can succeed
    sub = sa.post(f"{API}/academic/subjects", json={"name": "Math V17"}, timeout=15).json()

    # Teacher with subjects + salary
    teacher_email = f"v17.t.{suffix.lower()}@v17.example.com"
    teacher_pw = "Teach@2026"
    sa.post(f"{API}/users", json={
        "email": teacher_email, "password": teacher_pw, "name": f"V17 T",
        "role": "teacher", "subjects": [sub["id"]], "monthly_salary": 30000,
    }, timeout=15)
    ts = _login(teacher_email, teacher_pw)

    # Accounts user
    accounts_email = f"v17.acc.{suffix.lower()}@v17.example.com"
    accounts_pw = "Acc@2026"
    sa.post(f"{API}/users", json={
        "email": accounts_email, "password": accounts_pw, "name": "V17 Acc",
        "role": "accounts", "monthly_salary": 25000,
    }, timeout=15)
    ac = _login(accounts_email, accounts_pw)

    yield {
        "platform": plat, "school_admin": sa, "teacher": ts, "accounts": ac,
        "school": school, "subject": sub,
        "teacher_email": teacher_email,
    }


class TestTeacherRequiresSubject:
    def test_create_teacher_without_subjects_rejected(self, ctx):
        suffix = uuid.uuid4().hex[:5]
        r = ctx["school_admin"].post(f"{API}/users", json={
            "email": f"v17.nosub.{suffix}@v17.example.com",
            "password": "Pw@2026", "name": "NoSub T", "role": "teacher",
            "subjects": [],
        }, timeout=15)
        assert r.status_code == 400
        assert "subject" in r.json()["detail"].lower()

    def test_create_teacher_without_subjects_field_rejected(self, ctx):
        suffix = uuid.uuid4().hex[:5]
        r = ctx["school_admin"].post(f"{API}/users", json={
            "email": f"v17.miss.{suffix}@v17.example.com",
            "password": "Pw@2026", "name": "Miss T", "role": "teacher",
        }, timeout=15)
        assert r.status_code == 400

    def test_create_accounts_without_subjects_allowed(self, ctx):
        suffix = uuid.uuid4().hex[:5]
        r = ctx["school_admin"].post(f"{API}/users", json={
            "email": f"v17.acc2.{suffix}@v17.example.com",
            "password": "Pw@2026", "name": "Acc2", "role": "accounts",
        }, timeout=15)
        assert r.status_code == 200


class TestStaffCRUD:
    def test_school_admin_can_create_staff(self, ctx):
        r = ctx["school_admin"].post(f"{API}/staff", json={
            "name": "Ramesh (Driver)", "role": "bus_driver",
            "phone": "+919000050001", "monthly_salary": 18000,
        }, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "bus_driver"
        assert body["monthly_salary"] == 18000
        ctx["staff_id"] = body["id"]

    def test_teacher_cannot_create_staff(self, ctx):
        r = ctx["teacher"].post(f"{API}/staff", json={
            "name": "X", "role": "cleaner", "monthly_salary": 10000,
        }, timeout=15)
        assert r.status_code == 403

    def test_accounts_can_list_staff(self, ctx):
        r = ctx["accounts"].get(f"{API}/staff", timeout=15)
        assert r.status_code == 200
        assert any(s["id"] == ctx.get("staff_id") for s in r.json())

    def test_teacher_cannot_list_staff(self, ctx):
        r = ctx["teacher"].get(f"{API}/staff", timeout=15)
        assert r.status_code == 403

    def test_school_admin_can_update_staff(self, ctx):
        r = ctx["school_admin"].patch(f"{API}/staff/{ctx['staff_id']}",
                                       json={"monthly_salary": 20000}, timeout=15)
        assert r.status_code == 200

    def test_school_admin_can_deactivate_staff(self, ctx):
        r = ctx["school_admin"].delete(f"{API}/staff/{ctx['staff_id']}", timeout=15)
        assert r.status_code == 200

    def test_payroll_summary_includes_teacher_and_staff(self, ctx):
        # Re-add a fresh active staff so we have payroll > 0
        r = ctx["school_admin"].post(f"{API}/staff", json={
            "name": "Sita (Cook)", "role": "cook", "monthly_salary": 15000,
        }, timeout=15)
        assert r.status_code == 200
        summary = ctx["school_admin"].get(f"{API}/staff/summary/payroll", timeout=15).json()
        assert summary["monthly_total"] >= (30000 + 25000 + 15000)  # teacher + accounts + cook
        assert "by_role" in summary
        assert "teacher" in summary["by_role"]
        assert "accounts" in summary["by_role"]
        assert "cook" in summary["by_role"]


class TestExpensesAdminDirect:
    def test_school_admin_records_expense_directly_approved(self, ctx):
        r = ctx["school_admin"].post(f"{API}/expenses", json={
            "category": "utilities", "description": "Electricity bill", "amount": 5000,
            "vendor": "Power Co",
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved"
        assert body["submitted_by_role"] == "school_admin"
        ctx["admin_expense_id"] = body["id"]

    def test_accounts_can_record_expense(self, ctx):
        r = ctx["accounts"].post(f"{API}/expenses", json={
            "category": "supplies", "description": "Chalk + dusters", "amount": 1500,
        }, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_expense_rejects_zero_amount(self, ctx):
        r = ctx["school_admin"].post(f"{API}/expenses", json={
            "category": "other", "description": "x", "amount": 0,
        }, timeout=15)
        assert r.status_code == 400


class TestExpensesTeacherReimburse:
    def test_teacher_submits_reimbursement_pending(self, ctx):
        r = ctx["teacher"].post(f"{API}/expenses", json={
            "category": "supplies", "description": "Bought poster paper",
            "amount": 350, "reimburse_with_salary": True,
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "pending"
        assert body["submitted_by_role"] == "teacher"
        assert body["reimburse_with_salary"] is True
        ctx["teacher_expense_id"] = body["id"]

    def test_teacher_sees_only_own_expenses(self, ctx):
        r = ctx["teacher"].get(f"{API}/expenses", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        # All entries should be submitted by this teacher
        assert all(e["submitted_by_role"] == "teacher" for e in rows)
        # Must NOT include the admin-direct expenses
        assert ctx["admin_expense_id"] not in [e["id"] for e in rows]

    def test_school_admin_sees_all_expenses(self, ctx):
        r = ctx["school_admin"].get(f"{API}/expenses", timeout=15)
        ids = [e["id"] for e in r.json()]
        assert ctx["admin_expense_id"] in ids
        assert ctx["teacher_expense_id"] in ids

    def test_school_admin_approves_teacher_expense(self, ctx):
        r = ctx["school_admin"].post(f"{API}/expenses/{ctx['teacher_expense_id']}/decide",
                                       json={"decision": "approve", "note": "ok"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_cannot_approve_already_approved(self, ctx):
        r = ctx["school_admin"].post(f"{API}/expenses/{ctx['teacher_expense_id']}/decide",
                                       json={"decision": "approve"}, timeout=15)
        assert r.status_code == 400

    def test_accounts_marks_paid(self, ctx):
        r = ctx["accounts"].post(f"{API}/expenses/{ctx['teacher_expense_id']}/decide",
                                  json={"decision": "mark_paid"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "paid"

    def test_teacher_cannot_decide(self, ctx):
        # Create a fresh pending one as teacher
        sub = ctx["teacher"].post(f"{API}/expenses", json={
            "category": "other", "description": "Snacks for event", "amount": 200,
        }, timeout=15).json()
        r = ctx["teacher"].post(f"{API}/expenses/{sub['id']}/decide",
                                  json={"decision": "approve"}, timeout=15)
        assert r.status_code == 403

    def test_reject_teacher_expense(self, ctx):
        sub = ctx["teacher"].post(f"{API}/expenses", json={
            "category": "other", "description": "Personal coffee", "amount": 150,
        }, timeout=15).json()
        r = ctx["school_admin"].post(f"{API}/expenses/{sub['id']}/decide",
                                       json={"decision": "reject", "note": "not school-related"},
                                       timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"


class TestExpenseSummary:
    def test_summary_returns_totals_by_category_and_status(self, ctx):
        r = ctx["school_admin"].get(f"{API}/expenses/summary", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "by_status" in body
        assert "by_category" in body
        assert "pending_teacher_reimbursements" in body
        assert "total_spent" in body
        # We had at least the 5000 electricity + 1500 supplies + 350 teacher approval+paid = 6850 minimum
        assert body["total_spent"] >= 6850

    def test_summary_requires_role(self, ctx):
        r = ctx["teacher"].get(f"{API}/expenses/summary", timeout=15)
        assert r.status_code == 403


class TestSalaryOnUser:
    def test_school_admin_can_update_teacher_salary(self, ctx):
        # Get the teacher user id
        users = ctx["school_admin"].get(f"{API}/users", params={"role": "teacher"}, timeout=15).json()
        t = next(u for u in users if u["email"] == ctx["teacher_email"])
        r = ctx["school_admin"].patch(f"{API}/users/{t['id']}",
                                       json={"monthly_salary": 35000}, timeout=15)
        assert r.status_code == 200
        # Verify
        verified = ctx["school_admin"].get(f"{API}/users/{t['id']}", timeout=15).json()
        assert verified["monthly_salary"] == 35000
