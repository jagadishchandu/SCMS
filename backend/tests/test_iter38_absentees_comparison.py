"""Iteration 38 — Absentees Month view 'Compare to last month' ribbon.
Validates the new `comparison` block on the month response, per-row prev_/delta_
fields, regression guards for day/week (no comparison key), filter consistency
between current and prior month, empty-month handling, and RBAC.
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

COMPARISON_KEYS = {
    "prev_month", "prev_summary", "delta_students",
    "delta_absent_days", "delta_sick_days",
}
PREV_SUMMARY_KEYS = {"students", "total_absent_days", "total_sick_days"}
ROW_DELTA_KEYS = {
    "prev_absent_days", "prev_sick_days", "prev_total_days",
    "prev_attendance_percentage", "delta_absent_days",
    "delta_total_absences", "delta_attendance_percentage",
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


def _prev_month_str(iso: str) -> str:
    d = _dt.date.fromisoformat(iso)
    prev_first = (d.replace(day=1) - _dt.timedelta(days=1)).replace(day=1)
    return prev_first.strftime("%Y-%m")


# ----- regression guards: day/week do NOT include comparison -----
class TestNoComparisonOnDayOrWeek:
    def test_day_no_comparison_key(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "day", "date": today}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "comparison" not in body
        # rows should NOT have prev_/delta_ keys either
        for row in body.get("absentees", []):
            assert ROW_DELTA_KEYS.isdisjoint(row.keys()), row

    def test_week_no_comparison_key(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "week", "date": today}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "comparison" not in body
        for row in body.get("absentees", []):
            assert ROW_DELTA_KEYS.isdisjoint(row.keys()), row


# ----- month: comparison block present and correctly shaped -----
class TestMonthComparison:
    def test_month_has_comparison(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "comparison" in body, body
        cmp = body["comparison"]
        assert set(cmp.keys()) >= COMPARISON_KEYS, cmp
        assert cmp["prev_month"] == _prev_month_str(today)
        assert set(cmp["prev_summary"].keys()) >= PREV_SUMMARY_KEYS

    def test_summary_deltas_match_math(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        body = r.json()
        s = body["summary"]
        cmp = body["comparison"]
        ps = cmp["prev_summary"]
        assert cmp["delta_students"] == s["students"] - ps["students"]
        assert cmp["delta_absent_days"] == s["total_absent_days"] - ps["total_absent_days"]
        assert cmp["delta_sick_days"] == s["total_sick_days"] - ps["total_sick_days"]

    def test_rows_have_prev_and_delta_fields(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        rows = r.json()["absentees"]
        if not rows:
            pytest.skip("no absentees in current month")
        for row in rows:
            missing = ROW_DELTA_KEYS - set(row.keys())
            assert not missing, f"row missing keys {missing}: {row}"
            # types
            assert isinstance(row["prev_absent_days"], int)
            assert isinstance(row["prev_sick_days"], int)
            assert isinstance(row["prev_total_days"], int)
            assert isinstance(row["delta_absent_days"], int)
            assert isinstance(row["delta_total_absences"], int)
            # prev_attendance_percentage is float or null
            if row["prev_total_days"] == 0:
                assert row["prev_attendance_percentage"] is None
                assert row["delta_attendance_percentage"] is None
            else:
                assert isinstance(row["prev_attendance_percentage"], (int, float))
                assert 0 <= row["prev_attendance_percentage"] <= 100
                assert isinstance(row["delta_attendance_percentage"], (int, float))

    def test_delta_math_per_row(self, admin, today):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        rows = r.json()["absentees"]
        if not rows:
            pytest.skip("no absentees in current month")
        for row in rows:
            # delta_absent_days
            assert row["delta_absent_days"] == row["absent_days"] - row["prev_absent_days"]
            # delta_total_absences = (cur.absent+sick) - (prev.absent+prev.sick)
            expected_total = (
                (row["absent_days"] + row["sick_days"])
                - (row["prev_absent_days"] + row["prev_sick_days"])
            )
            assert row["delta_total_absences"] == expected_total
            # delta_attendance_percentage = cur pct - prev pct rounded to 1dp
            if row["prev_attendance_percentage"] is None:
                assert row["delta_attendance_percentage"] is None
            else:
                expected_pct = round(row["attendance_percentage"] - row["prev_attendance_percentage"], 1)
                assert row["delta_attendance_percentage"] == expected_pct


# ----- empty month must still ship comparison block with zeros -----
class TestEmptyMonth:
    def test_far_past_month_returns_zero_comparison(self, admin):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": "2000-01-15"}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["absentees"] == []
        assert body["summary"] == {"students": 0, "total_absent_days": 0, "total_sick_days": 0}
        assert "comparison" in body
        cmp = body["comparison"]
        assert cmp["prev_month"] == "1999-12"
        assert cmp["prev_summary"] == {"students": 0, "total_absent_days": 0, "total_sick_days": 0}
        assert cmp["delta_students"] == 0
        assert cmp["delta_absent_days"] == 0
        assert cmp["delta_sick_days"] == 0

    def test_far_future_month_returns_zero_comparison(self, admin):
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": "2099-06-15"}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["absentees"] == []
        assert "comparison" in body
        assert body["comparison"]["prev_month"] == "2099-05"


# ----- filter consistency across both months -----
class TestFilterConsistency:
    def test_class_filter_applied_to_prior_month(self, admin, today):
        # Get class filter
        r = admin.get(f"{API}/attendance/absentees",
                      params={"period": "month", "date": today}, timeout=30)
        rows = r.json()["absentees"]
        pick = next((x for x in rows if x.get("class_id")), None)
        if not pick:
            pytest.skip("no class_id to filter by")
        params = {"period": "month", "date": today, "class_id": pick["class_id"]}
        if pick.get("section"):
            params["section"] = pick["section"]
        r2 = admin.get(f"{API}/attendance/absentees", params=params, timeout=30)
        assert r2.status_code == 200
        body = r2.json()
        # all rows are in chosen class/section
        for row in body["absentees"]:
            assert row["class_id"] == pick["class_id"]
            if "section" in params:
                assert row["section"] == params["section"]
        # comparison block still present and prev_summary should be <= unfiltered
        assert "comparison" in body
        # Sanity: filtered prev_summary totals must be <= unfiltered ones
        r3 = admin.get(f"{API}/attendance/absentees",
                       params={"period": "month", "date": today}, timeout=30)
        unfiltered_ps = r3.json()["comparison"]["prev_summary"]
        filtered_ps = body["comparison"]["prev_summary"]
        assert filtered_ps["total_absent_days"] <= unfiltered_ps["total_absent_days"]
        assert filtered_ps["total_sick_days"] <= unfiltered_ps["total_sick_days"]
        assert filtered_ps["students"] <= unfiltered_ps["students"]


# ----- RBAC: accounts allowed, parent forbidden -----
class TestRBAC:
    def test_accounts_sees_comparison(self, accounts, today):
        r = accounts.get(f"{API}/attendance/absentees",
                         params={"period": "month", "date": today}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "comparison" in body
        assert set(body["comparison"].keys()) >= COMPARISON_KEYS

    def test_parent_forbidden(self, parent, today):
        r = parent.get(f"{API}/attendance/absentees",
                       params={"period": "month", "date": today}, timeout=30)
        assert r.status_code in (401, 403)
