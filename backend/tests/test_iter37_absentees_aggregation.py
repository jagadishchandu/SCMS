"""Iteration 37 — Absentees endpoint switched from Python loop to Mongo
aggregation pipeline. Validate shape, sort order, filters, empty case.
"""
import os
import datetime as _dt
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

SCHOOL_ADMIN = ("principal@sunrise.edu", "School@123")
ACCOUNTS = ("accounts@sunrise.edu", "Accounts@123")
PARENT = ("parent.stu-00001@sunrise.edu", "Parent@123")

REQUIRED_KEYS = {
    "student_id", "absent_days", "sick_days", "present_days", "late_days",
    "half_day_days", "excused_days", "total_days", "last_absent_date",
    "last_absent_status", "name", "student_uid", "class_id", "class_name",
    "section", "parent_phone", "attendance_percentage",
}


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*SCHOOL_ADMIN)


@pytest.fixture(scope="module")
def accounts():
    return _login(*ACCOUNTS)


@pytest.fixture(scope="module")
def parent():
    return _login(*PARENT)


@pytest.fixture(scope="module")
def today():
    return _dt.date.today().isoformat()


class TestShape:
    def test_day_shape(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "day", "date": today}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) >= {"period", "date", "absentees", "summary"}
        assert body["period"] == "day"
        assert body["date"] == today
        s = body["summary"]
        for k in ("students", "total_absent_days", "total_sick_days"):
            assert k in s

    def test_week_shape(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "week", "date": today}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["period"] == "week"
        assert isinstance(body["absentees"], list)

    def test_month_shape_and_keys(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["period"] == "month"
        for row in body["absentees"]:
            missing = REQUIRED_KEYS - set(row.keys())
            assert not missing, f"row missing keys {missing}: {row}"
            # absent or sick > 0
            assert (row["absent_days"] + row["sick_days"]) > 0
            # if last_absent_date is set, last_absent_status must be one of absent|sick
            if row["last_absent_date"]:
                assert row["last_absent_status"] in ("absent", "sick"), row
            # attendance_percentage in 0..100
            assert 0 <= row["attendance_percentage"] <= 100
            # total_days >= absent_days + sick_days
            assert row["total_days"] >= row["absent_days"] + row["sick_days"]

    def test_summary_matches_rows(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        body = r.json()
        s = body["summary"]
        assert s["students"] == len(body["absentees"])
        assert s["total_absent_days"] == sum(a["absent_days"] for a in body["absentees"])
        assert s["total_sick_days"] == sum(a["sick_days"] for a in body["absentees"])


class TestSortOrder:
    def test_month_sorted_by_absent_then_sick_desc(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        rows = r.json()["absentees"]
        if len(rows) <= 1:
            pytest.skip("not enough absentees to verify sort order")
        for a, b in zip(rows, rows[1:]):
            assert (a["absent_days"], a["sick_days"]) >= (b["absent_days"], b["sick_days"]), \
                f"sort violation: {a['absent_days']},{a['sick_days']} -> {b['absent_days']},{b['sick_days']}"


class TestFilters:
    def test_class_section_narrows(self, admin, today):
        # fetch some absentees first; use one's class/section as filter
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        rows = r.json()["absentees"]
        if not rows:
            pytest.skip("no absentees in month to derive a filter")
        pick = next((x for x in rows if x.get("class_id")), None)
        if not pick:
            pytest.skip("no class_id on absentees")
        params = {"period": "month", "date": today, "class_id": pick["class_id"]}
        if pick.get("section"):
            params["section"] = pick["section"]
        r2 = admin.get(f"{API}/attendance/absentees", params=params, timeout=30)
        assert r2.status_code == 200
        for row in r2.json()["absentees"]:
            assert row["class_id"] == pick["class_id"]
            if "section" in params:
                assert row["section"] == params["section"]

    def test_empty_period_returns_zeros(self, admin):
        # use far past date — should yield empty
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "day", "date": "2000-01-01"}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["absentees"] == []
        assert body["summary"] == {"students": 0, "total_absent_days": 0, "total_sick_days": 0}
        assert body["date"] == "2000-01-01"
        assert body["period"] == "day"

    def test_accounts_can_view(self, accounts, today):
        r = accounts.get(f"{API}/attendance/absentees",
                         params={"period": "day", "date": today}, timeout=30)
        assert r.status_code == 200

    def test_parent_forbidden(self, parent, today):
        r = parent.get(f"{API}/attendance/absentees",
                       params={"period": "day", "date": today}, timeout=30)
        assert r.status_code in (401, 403)
