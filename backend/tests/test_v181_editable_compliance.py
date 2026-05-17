"""Tests for v1.18.1: editable approval count + Platform Compliance view."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://school-admin-fix.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"{email}: {r.status_code} {r.text}"
    return s


def _new_school(plat, auto_approve=False, initial_count=None):
    suffix = uuid.uuid4().hex[:6].upper()
    email = f"v181.admin.{suffix.lower()}@v181.example.com"
    pw = "Admin@2026"
    payload = {
        "name": f"V181 {suffix}", "code": f"V181{suffix}",
        "admin_email": email, "admin_password": pw, "admin_name": "V181 Admin",
    }
    if auto_approve:
        payload["auto_approve"] = True
        if initial_count:
            payload["initial_children_count"] = initial_count
    r = plat.post(f"{API}/schools", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["school"]["id"], email, pw


# ------------------ Editable count after approval ------------------

def test_edit_count_after_approval_keeps_status_approved():
    plat = _login(*PLATFORM)
    sid, email, pw = _new_school(plat, auto_approve=True, initial_count=100)
    sa = _login(email, pw)
    # Edit count — should stay approved
    r = sa.post(f"{API}/subscriptions/approval-request",
                 json={"requested_children_count": 200, "note": "Expansion"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("edited") is True
    assert body["subscription_approval"]["status"] == "approved"
    assert body["subscription_approval"]["requested_children_count"] == 200
    # And full feature access still works
    r2 = sa.get(f"{API}/students", timeout=10)
    assert r2.status_code == 200


def test_edit_count_when_pending_resets_to_pending():
    """If status is pending, submitting again should NOT flip status — kept pending."""
    plat = _login(*PLATFORM)
    sid, email, pw = _new_school(plat)
    sa = _login(email, pw)
    sa.post(f"{API}/subscriptions/approval-request",
             json={"requested_children_count": 50}, timeout=15)
    # Resubmit
    r = sa.post(f"{API}/subscriptions/approval-request",
                 json={"requested_children_count": 80}, timeout=15)
    assert r.status_code == 200
    assert r.json()["subscription_approval"]["status"] == "pending"
    assert r.json()["subscription_approval"]["requested_children_count"] == 80


# ------------------ Compliance endpoint ------------------

def test_compliance_endpoint_returns_summary_and_rows():
    plat = _login(*PLATFORM)
    r = plat.get(f"{API}/subscriptions/compliance", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body and "summary" in body and "total" in body
    assert isinstance(body["rows"], list)
    for k in ("compliant", "over_capacity", "pending_review", "rejected", "no_request"):
        assert k in body["summary"]


def test_compliance_filter_works():
    plat = _login(*PLATFORM)
    r = plat.get(f"{API}/subscriptions/compliance?filter=no_request", timeout=30)
    assert r.status_code == 200
    body = r.json()
    for row in body["rows"]:
        assert row["compliance"] == "no_request"


def test_compliance_rejects_non_platform_admin():
    sa = _login("principal@sunrise.edu", "School@123")
    r = sa.get(f"{API}/subscriptions/compliance", timeout=15)
    assert r.status_code == 403


def test_compliance_flags_over_capacity_school():
    plat = _login(*PLATFORM)
    sid, email, pw = _new_school(plat, auto_approve=True, initial_count=1)
    sa = _login(email, pw)
    # Create a class + section so students can be added
    cls = sa.post(f"{API}/academic/classes", json={"name": "Grade A", "sections": ["A"]}, timeout=15).json()
    # Add 3 students -> over capacity (cap=1)
    for i in range(3):
        sa.post(f"{API}/students", json={
            "name": f"Student {i}", "class_id": cls["id"], "section": "A",
            "gender": "m", "parent": {"name": f"P{i}", "phone": f"+91900000{i}000"},
        }, timeout=15)
    r = plat.get(f"{API}/subscriptions/compliance?filter=over_capacity", timeout=20)
    assert r.status_code == 200
    ids = [row["school_id"] for row in r.json()["rows"]]
    assert sid in ids
    # Variance for this school should be >= 2
    row = next(row for row in r.json()["rows"] if row["school_id"] == sid)
    assert row["actual_active_students"] >= 3
    assert row["variance"] is not None and row["variance"] >= 2
    assert row["compliance"] == "over_capacity"


def test_compliance_within_capacity():
    plat = _login(*PLATFORM)
    sid, email, pw = _new_school(plat, auto_approve=True, initial_count=500)
    sa = _login(email, pw)
    cls = sa.post(f"{API}/academic/classes", json={"name": "G1", "sections": ["A"]}, timeout=15).json()
    sa.post(f"{API}/students", json={
        "name": "Solo", "class_id": cls["id"], "section": "A",
        "gender": "m", "parent": {"name": "P", "phone": "+919000099009"},
    }, timeout=15)
    r = plat.get(f"{API}/subscriptions/compliance", timeout=20)
    assert r.status_code == 200
    row = next((row for row in r.json()["rows"] if row["school_id"] == sid), None)
    assert row is not None
    assert row["compliance"] == "compliant"
    assert row["variance"] is not None and row["variance"] <= 0
