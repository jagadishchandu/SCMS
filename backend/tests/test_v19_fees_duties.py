"""Tests for v1.19: Fee Items catalog, per-student fee summary, Teacher Duties."""
import os
import uuid
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://class-access-hub.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = ("jagadishchandu789@gmail.com", "Manasa@123")
SCHOOL = ("principal@sunrise.edu", "School@123")
ACCOUNTS = ("accounts@sunrise.edu", "Accounts@123")
TEACHER = ("priya@sunrise.edu", "Teacher@123")


def _login(email, password, expect=200):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == expect, f"{email}: {r.status_code} {r.text}"
    return s


# ─────────────── Fee Items Catalog ───────────────

def test_school_admin_can_create_and_list_fee_items():
    sa = _login(*SCHOOL)
    suffix = uuid.uuid4().hex[:6]
    r = sa.post(f"{API}/fee-items", json={
        "name": f"Tuition {suffix}", "category": "tuition",
        "default_amount": 12000, "frequency": "yearly",
    })
    assert r.status_code == 200, r.text
    item = r.json()
    assert item["id"]
    # List
    r = sa.get(f"{API}/fee-items")
    assert r.status_code == 200
    assert any(it["id"] == item["id"] for it in r.json())


def test_accounts_can_create_fee_items():
    a = _login(*ACCOUNTS)
    suffix = uuid.uuid4().hex[:6]
    r = a.post(f"{API}/fee-items", json={
        "name": f"Books {suffix}", "category": "books",
        "default_amount": 2500, "frequency": "yearly",
    })
    assert r.status_code == 200


def test_teacher_blocked_from_fee_items():
    t = _login(*TEACHER)
    r = t.post(f"{API}/fee-items", json={
        "name": "X", "category": "other", "default_amount": 100,
    })
    assert r.status_code == 403
    r = t.get(f"{API}/fee-items")
    assert r.status_code == 403


def test_invalid_category_rejected():
    sa = _login(*SCHOOL)
    r = sa.post(f"{API}/fee-items", json={
        "name": "Bogus", "category": "garbage", "default_amount": 100,
    })
    assert r.status_code == 422


def test_negative_amount_rejected():
    sa = _login(*SCHOOL)
    r = sa.post(f"{API}/fee-items", json={
        "name": "Bogus", "category": "tuition", "default_amount": -1,
    })
    assert r.status_code == 422


def test_update_fee_item():
    sa = _login(*SCHOOL)
    r = sa.post(f"{API}/fee-items", json={
        "name": f"X-{uuid.uuid4().hex[:5]}", "category": "lab", "default_amount": 1000,
    })
    item_id = r.json()["id"]
    r2 = sa.patch(f"{API}/fee-items/{item_id}", json={"default_amount": 1500})
    assert r2.status_code == 200
    assert r2.json()["default_amount"] == 1500


def test_accounts_cannot_delete_fee_item():
    sa = _login(*SCHOOL)
    item = sa.post(f"{API}/fee-items", json={
        "name": f"Y-{uuid.uuid4().hex[:5]}", "category": "sports", "default_amount": 800,
    }).json()
    a = _login(*ACCOUNTS)
    r = a.delete(f"{API}/fee-items/{item['id']}")
    assert r.status_code == 403


def test_delete_soft_deactivates():
    sa = _login(*SCHOOL)
    item = sa.post(f"{API}/fee-items", json={
        "name": f"Z-{uuid.uuid4().hex[:5]}", "category": "uniform", "default_amount": 500,
    }).json()
    r = sa.delete(f"{API}/fee-items/{item['id']}")
    assert r.status_code == 200
    # Now invisible by default
    visible = sa.get(f"{API}/fee-items").json()
    assert not any(it["id"] == item["id"] for it in visible)
    # But visible when include_inactive=true
    all_items = sa.get(f"{API}/fee-items?include_inactive=true").json()
    assert any(it["id"] == item["id"] for it in all_items)


# ─────────────── Per-student fee summary ───────────────

def test_per_student_summary_shape_and_fields():
    sa = _login(*SCHOOL)
    r = sa.get(f"{API}/fees/per-student-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rows" in body and "summary" in body and "totals" in body
    for k in ("paid", "partial", "not_paid", "no_fees"):
        assert k in body["summary"]
    if body["rows"]:
        row = body["rows"][0]
        for f in ("student_id", "student_name", "total_fee", "paid_amount",
                  "balance_due", "percent_paid", "status"):
            assert f in row


def test_per_student_summary_status_filter():
    sa = _login(*SCHOOL)
    r = sa.get(f"{API}/fees/per-student-summary?status=not_paid")
    assert r.status_code == 200
    body = r.json()
    for row in body["rows"]:
        assert row["status"] == "not_paid"
    assert all(r["balance_due"] >= r["total_fee"] * 0.999 for r in body["rows"])


def test_per_student_summary_search_query():
    sa = _login(*SCHOOL)
    r = sa.get(f"{API}/fees/per-student-summary?q=STU-")
    assert r.status_code == 200
    rows = r.json()["rows"]
    for row in rows:
        assert "STU-" in (row.get("student_uid") or "")


def test_per_student_summary_percent_paid_calc():
    """If a student has total=2000 paid=500 → percent should be 25.0."""
    sa = _login(*SCHOOL)
    r = sa.get(f"{API}/fees/per-student-summary?status=partial").json()
    for row in r["rows"]:
        if row["total_fee"] > 0:
            expected = round((row["paid_amount"] / row["total_fee"]) * 100, 1)
            assert abs(row["percent_paid"] - expected) < 0.2


def test_accounts_can_access_fee_summary():
    a = _login(*ACCOUNTS)
    r = a.get(f"{API}/fees/per-student-summary")
    assert r.status_code == 200


def test_teacher_blocked_from_fee_summary():
    t = _login(*TEACHER)
    r = t.get(f"{API}/fees/per-student-summary")
    assert r.status_code == 403


# ─────────────── Teacher Duties ───────────────

def _get_teacher_id(sa):
    r = sa.get(f"{API}/users?role=teacher")
    return r.json()[0]["id"]


def test_school_admin_creates_duty_for_teacher():
    sa = _login(*SCHOOL)
    tid = _get_teacher_id(sa)
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = sa.post(f"{API}/teacher-duties", json={
        "teacher_ids": [tid], "title": f"Test duty {uuid.uuid4().hex[:5]}",
        "type": "duty", "start_at": when, "notify": False,
    })
    assert r.status_code == 200, r.text
    created = r.json()
    assert len(created) == 1
    assert created[0]["teacher_id"] == tid


def test_duty_create_multiple_teachers_creates_multiple_rows():
    sa = _login(*SCHOOL)
    teachers = sa.get(f"{API}/users?role=teacher").json()[:2]
    if len(teachers) < 2:
        return  # skip if school has only one teacher
    ids = [t["id"] for t in teachers]
    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = sa.post(f"{API}/teacher-duties", json={
        "teacher_ids": ids, "title": f"Group {uuid.uuid4().hex[:5]}",
        "type": "meeting", "start_at": when, "notify": False,
    })
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_unknown_teacher_id_rejected():
    sa = _login(*SCHOOL)
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = sa.post(f"{API}/teacher-duties", json={
        "teacher_ids": ["does-not-exist-zzz"], "title": "X",
        "type": "duty", "start_at": when, "notify": False,
    })
    assert r.status_code == 400


def test_teacher_sees_only_own_duties():
    sa = _login(*SCHOOL)
    tid = _get_teacher_id(sa)
    when = (datetime.now(timezone.utc) + timedelta(days=4)).isoformat()
    sa.post(f"{API}/teacher-duties", json={
        "teacher_ids": [tid], "title": f"Own duty {uuid.uuid4().hex[:5]}",
        "type": "duty", "start_at": when, "notify": False,
    })
    t = _login(*TEACHER)
    r = t.get(f"{API}/teacher-duties")
    assert r.status_code == 200
    rows = r.json()
    # All visible rows must be assigned to this teacher only
    me = t.get(f"{API}/auth/me").json()
    for row in rows:
        assert row["teacher_id"] == me["id"]


def test_school_admin_can_delete_duty():
    sa = _login(*SCHOOL)
    tid = _get_teacher_id(sa)
    when = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    created = sa.post(f"{API}/teacher-duties", json={
        "teacher_ids": [tid], "title": f"To delete {uuid.uuid4().hex[:5]}",
        "type": "duty", "start_at": when, "notify": False,
    }).json()
    duty_id = created[0]["id"]
    r = sa.delete(f"{API}/teacher-duties/{duty_id}")
    assert r.status_code == 200


def test_teacher_cannot_create_or_delete_duty():
    sa = _login(*SCHOOL)
    tid = _get_teacher_id(sa)
    when = (datetime.now(timezone.utc) + timedelta(days=6)).isoformat()
    created = sa.post(f"{API}/teacher-duties", json={
        "teacher_ids": [tid], "title": f"RBAC {uuid.uuid4().hex[:5]}",
        "type": "duty", "start_at": when, "notify": False,
    }).json()
    t = _login(*TEACHER)
    r = t.post(f"{API}/teacher-duties", json={
        "teacher_ids": [tid], "title": "x", "type": "duty", "start_at": when,
    })
    assert r.status_code == 403
    r = t.delete(f"{API}/teacher-duties/{created[0]['id']}")
    assert r.status_code == 403


def test_date_range_filter():
    sa = _login(*SCHOOL)
    from_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    to_iso = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r = sa.get(f"{API}/teacher-duties?from_date={from_iso}&to_date={to_iso}")
    assert r.status_code == 200
