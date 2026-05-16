"""Tests for v1.18: subscription approval workflow + monthly payroll PDF."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://student-tracker-478.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"{email}: {r.status_code} {r.text}"
    return s


def _new_school(plat, auto_approve=False):
    """Create a fresh school + admin. Returns (school_id, admin_email, admin_pw, school_code)."""
    suffix = uuid.uuid4().hex[:6].upper()
    admin_email = f"v18.admin.{suffix.lower()}@v18.example.com"
    admin_pw = "Admin@2026"
    payload = {
        "name": f"V18 School {suffix}", "code": f"V18{suffix}",
        "address": "x", "phone": "+910", "email": f"info.{suffix.lower()}@v18.example.com",
        "academic_year": "2025-2026",
        "admin_email": admin_email, "admin_password": admin_pw, "admin_name": "V18 Admin",
    }
    if auto_approve:
        payload["auto_approve"] = True
        payload["initial_children_count"] = 100
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["school"]["id"], admin_email, admin_pw, payload["code"]


# ------------------ Approval Workflow ------------------

def test_new_school_starts_not_started():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    me = sa.get(f"{API}/auth/me", timeout=10).json()
    assert me["subscription_state"]["approval_status"] == "not_started"


def test_new_school_locked_out_of_features():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    # Reads of operational endpoints are blocked
    r = sa.get(f"{API}/students", timeout=10)
    assert r.status_code == 423, r.text
    assert r.json()["code"] in ("approval_pending", "approval_required")
    # Writes also blocked
    r = sa.post(f"{API}/academic/classes", json={"name": "X"}, timeout=10)
    assert r.status_code == 423


def test_locked_school_can_still_access_overview_and_subscription():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    # /auth/me always works
    r = sa.get(f"{API}/auth/me", timeout=10)
    assert r.status_code == 200
    # /subscriptions/my works
    r = sa.get(f"{API}/subscriptions/my", timeout=10)
    assert r.status_code == 200
    assert r.json()["subscription_approval"]["status"] == "not_started"
    # Overview KPIs accessible
    r = sa.get(f"{API}/analytics/school", timeout=15)
    assert r.status_code == 200, r.text
    # Schools/{id}/people drawer accessible
    r = sa.get(f"{API}/schools/{sid}/people", timeout=15)
    assert r.status_code == 200


def test_submit_approval_request_changes_status_to_pending():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    r = sa.post(f"{API}/subscriptions/approval-request",
                 json={"requested_children_count": 250, "note": "Starting fresh"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subscription_approval"]["status"] == "pending"
    assert body["subscription_approval"]["requested_children_count"] == 250
    # /auth/me reflects it
    me = sa.get(f"{API}/auth/me", timeout=10).json()
    assert me["subscription_state"]["approval_status"] == "pending"
    assert me["subscription_state"]["requested_children_count"] == 250


def test_pending_school_still_locked():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    sa.post(f"{API}/subscriptions/approval-request",
             json={"requested_children_count": 50}, timeout=15)
    r = sa.get(f"{API}/students", timeout=10)
    assert r.status_code == 423
    assert r.json()["code"] == "approval_pending"


def test_platform_admin_can_list_pending_approvals():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    sa.post(f"{API}/subscriptions/approval-request",
             json={"requested_children_count": 75}, timeout=15)
    r = plat.get(f"{API}/subscriptions/approval-requests", timeout=15)
    assert r.status_code == 200
    ids = [row["school_id"] for row in r.json()]
    assert sid in ids


def test_approve_unlocks_school():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    sa.post(f"{API}/subscriptions/approval-request",
             json={"requested_children_count": 60}, timeout=15)
    r = plat.post(f"{API}/subscriptions/approval/{sid}/decide",
                   json={"decision": "approve", "approved_children_count": 60}, timeout=15)
    assert r.status_code == 200, r.text
    # Now school admin can access /students
    r = sa.get(f"{API}/students", timeout=10)
    assert r.status_code == 200


def test_reject_keeps_school_locked_with_status_rejected():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat)
    sa = _login(email, pw)
    sa.post(f"{API}/subscriptions/approval-request",
             json={"requested_children_count": 60}, timeout=15)
    r = plat.post(f"{API}/subscriptions/approval/{sid}/decide",
                   json={"decision": "reject", "note": "Need more info"}, timeout=15)
    assert r.status_code == 200
    me = sa.get(f"{API}/auth/me", timeout=10).json()
    assert me["subscription_state"]["approval_status"] == "rejected"
    # Still locked
    r = sa.get(f"{API}/students", timeout=10)
    assert r.status_code == 423


def test_school_admin_cannot_approve_other_school():
    plat = _login(*PLATFORM)
    sid_a, email_a, pw_a, _ = _new_school(plat)
    sid_b, email_b, pw_b, _ = _new_school(plat)
    sa_a = _login(email_a, pw_a)
    r = sa_a.post(f"{API}/subscriptions/approval/{sid_b}/decide",
                   json={"decision": "approve"}, timeout=15)
    assert r.status_code == 403


def test_auto_approve_skips_lockdown():
    plat = _login(*PLATFORM)
    sid, email, pw, _ = _new_school(plat, auto_approve=True)
    sa = _login(email, pw)
    me = sa.get(f"{API}/auth/me", timeout=10).json()
    assert me["subscription_state"]["approval_status"] == "approved"
    # No lockdown — full access
    r = sa.get(f"{API}/students", timeout=10)
    assert r.status_code == 200


# ------------------ Monthly Payroll PDF ------------------

def test_monthly_payroll_pdf_renders_for_existing_school():
    sa = _login("principal@sunrise.edu", "School@123")
    r = sa.get(f"{API}/staff/payroll/monthly-pdf", timeout=30)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:5] == b"%PDF-"


def test_monthly_payroll_pdf_accepts_month_param():
    sa = _login("principal@sunrise.edu", "School@123")
    r = sa.get(f"{API}/staff/payroll/monthly-pdf?month=2026-02", timeout=30)
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_monthly_payroll_pdf_rejects_invalid_month():
    sa = _login("principal@sunrise.edu", "School@123")
    r = sa.get(f"{API}/staff/payroll/monthly-pdf?month=invalid", timeout=15)
    assert r.status_code == 400


def test_monthly_payroll_pdf_accounts_can_access():
    sa = _login("accounts@sunrise.edu", "Accounts@123")
    r = sa.get(f"{API}/staff/payroll/monthly-pdf", timeout=30)
    assert r.status_code == 200


def test_monthly_payroll_pdf_teacher_rejected():
    sa = _login("priya@sunrise.edu", "Teacher@123")
    r = sa.get(f"{API}/staff/payroll/monthly-pdf", timeout=15)
    assert r.status_code == 403
