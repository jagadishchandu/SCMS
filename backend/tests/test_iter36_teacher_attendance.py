"""Iteration 36 — Teacher attendance + Absentees panel.

Covers:
- POST /api/teacher-attendance/bulk (school_admin + accounts), 4 statuses, upsert idempotency, role restrictions
- GET /api/teacher-attendance/today (counts + roster)
- GET /api/teacher-attendance with date / month / teacher filters
- GET /api/attendance/absentees with period=day/week/month and class/section filters
"""
import os
import datetime as _dt
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

CRED = {
    "school_admin": ("principal@sunrise.edu", "School@123"),
    "accounts": ("accounts@sunrise.edu", "Accounts@123"),
    "teacher": ("priya@sunrise.edu", "Teacher@123"),
    "parent": ("parent.stu-00001@sunrise.edu", "Parent@123"),
}


def _login(email: str, pwd: str) -> requests.Session:
    """Return a logged-in Session (cookie-based auth)."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


def _hdr(_s):  # kept for signature symmetry; cookies are on session already
    return {}


@pytest.fixture(scope="module")
def tokens():
    return {k: _login(*v) for k, v in CRED.items()}


@pytest.fixture(scope="module")
def teachers(tokens):
    r = tokens["school_admin"].get(f"{API}/users", params={"role": "teacher"},  timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2, "need >=2 teachers for status tests"
    return data


@pytest.fixture(scope="module")
def today_iso():
    return _dt.date.today().isoformat()


# ---------- Teacher attendance ----------

class TestTeacherAttendanceAuth:
    def test_teacher_cannot_bulk_mark(self, tokens, today_iso):
        r = tokens["teacher"].post(f"{API}/teacher-attendance/bulk",
            json={"date": today_iso, "entries": []},
            
            timeout=30,
        )
        assert r.status_code in (401, 403), r.text

    def test_parent_cannot_bulk_mark(self, tokens, today_iso):
        r = tokens["parent"].post(f"{API}/teacher-attendance/bulk",
            json={"date": today_iso, "entries": []},
            
            timeout=30,
        )
        assert r.status_code in (401, 403), r.text

    def test_parent_cannot_view_absentees(self, tokens):
        r = tokens["parent"].get(f"{API}/attendance/absentees",
            params={"period": "day"},
            
            timeout=30,
        )
        assert r.status_code in (401, 403)


class TestTeacherAttendanceBulkAndUpsert:
    def test_school_admin_marks_all_four_statuses(self, tokens, teachers, today_iso):
        # cycle through 4 statuses for the first 4 (or fewer) teachers
        statuses = ["present", "absent", "leave", "half_day"]
        n = min(len(teachers), len(statuses))
        entries = [{"teacher_id": teachers[i]["id"], "status": statuses[i]} for i in range(n)]
        r = tokens["school_admin"].post(f"{API}/teacher-attendance/bulk",
            json={"date": today_iso, "entries": entries},
            
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["marked"] == n
        assert body["date"] == today_iso

        # verify persisted via GET
        r2 = tokens["school_admin"].get(f"{API}/teacher-attendance",
            params={"date": today_iso},
            
            timeout=30,
        )
        assert r2.status_code == 200
        rows = r2.json()
        by_tid = {row["teacher_id"]: row["status"] for row in rows}
        for i in range(n):
            assert by_tid.get(teachers[i]["id"]) == statuses[i], f"{teachers[i]['id']}: got {by_tid.get(teachers[i]['id'])} expected {statuses[i]}"

    def test_upsert_no_duplicate(self, tokens, teachers, today_iso):
        tid = teachers[0]["id"]
        # mark twice with different statuses
        for st in ["leave", "present"]:
            r = tokens["school_admin"].post(f"{API}/teacher-attendance/bulk",
                json={"date": today_iso, "entries": [{"teacher_id": tid, "status": st}]},
                
                timeout=30,
            )
            assert r.status_code == 200
        # final state should be 'present' and only ONE row for (tid, today)
        r2 = tokens["school_admin"].get(f"{API}/teacher-attendance",
            params={"date": today_iso, "teacher_id": tid},
            
            timeout=30,
        )
        rows = [x for x in r2.json() if x["teacher_id"] == tid]
        assert len(rows) == 1, f"expected 1 row after upsert, got {len(rows)}"
        assert rows[0]["status"] == "present"

    def test_accounts_can_mark(self, tokens, teachers, today_iso):
        tid = teachers[0]["id"]
        r = tokens["accounts"].post(f"{API}/teacher-attendance/bulk",
            json={"date": today_iso, "entries": [{"teacher_id": tid, "status": "present", "remark": "ok"}]},
            
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["marked"] == 1


class TestTeacherAttendanceToday:
    def test_today_returns_roster_with_counts(self, tokens):
        r = tokens["school_admin"].get(f"{API}/teacher-attendance/today",
            
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "date" in body and "teachers" in body and "counts" in body
        assert isinstance(body["teachers"], list) and len(body["teachers"]) >= 1
        for t in body["teachers"]:
            assert "id" in t and "name" in t and "status" in t
            assert t["status"] in ("present", "absent", "leave", "half_day", "unmarked")
        # counts keys must cover all 5 buckets
        for k in ("present", "absent", "leave", "half_day", "unmarked"):
            assert k in body["counts"]
        # total counts must equal teacher count
        assert sum(body["counts"].values()) == len(body["teachers"])


class TestTeacherAttendanceListFilters:
    def test_teacher_sees_only_own_rows(self, tokens):
        r = tokens["teacher"].get(f"{API}/teacher-attendance",
            
            timeout=30,
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        # all rows should belong to that teacher
        # decode teacher id from /auth/me
        me = tokens["teacher"].get(f"{API}/auth/me",  timeout=30).json()
        for row in rows:
            assert row["teacher_id"] == me["id"]

    def test_month_filter(self, tokens, today_iso):
        month = today_iso[:7]
        r = tokens["school_admin"].get(f"{API}/teacher-attendance",
            params={"month": month},
            
            timeout=30,
        )
        assert r.status_code == 200
        for row in r.json():
            assert row["date"].startswith(month + "-")


# ---------- Student absentees panel ----------

class TestAbsenteesPanel:
    def test_day_absentees_shape(self, tokens, today_iso):
        r = tokens["school_admin"].get(f"{API}/attendance/absentees",
            params={"period": "day", "date": today_iso},
            
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["period"] == "day"
        assert "absentees" in body and "summary" in body
        # each absentee should expose the key UI fields (parent_phone may be None)
        for a in body["absentees"]:
            assert "student_id" in a
            assert "absent_days" in a
            assert "last_absent_date" in a
            assert "attendance_percentage" in a

    def test_week_aggregation(self, tokens, today_iso):
        r = tokens["school_admin"].get(f"{API}/attendance/absentees",
            params={"period": "week", "date": today_iso},
            
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["period"] == "week"
        for a in body["absentees"]:
            assert a["total_days"] >= 1

    def test_month_includes_percentage(self, tokens, today_iso):
        r = tokens["school_admin"].get(f"{API}/attendance/absentees",
            params={"period": "month", "date": today_iso},
            
            timeout=30,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["period"] == "month"
        for a in body["absentees"]:
            assert isinstance(a["attendance_percentage"], (int, float))
            assert 0 <= a["attendance_percentage"] <= 100
            assert a["total_days"] >= 1

    def test_class_section_filter_narrows(self, tokens, today_iso):
        # Get a class with sections from the demo data
        r = tokens["school_admin"].get(f"{API}/academic/classes",  timeout=30)
        assert r.status_code == 200
        classes = r.json()
        assert len(classes) > 0
        cls = next((c for c in classes if c.get("sections")), classes[0])
        params = {"period": "month", "date": today_iso, "class_id": cls["id"]}
        if cls.get("sections"):
            params["section"] = cls["sections"][0]
        r2 = tokens["school_admin"].get(f"{API}/attendance/absentees",
            params=params,
            
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
        for a in r2.json()["absentees"]:
            assert a["class_id"] == cls["id"]
            if params.get("section"):
                assert a["section"] == params["section"]


# ---------- Cleanup: restore everyone to 'present' so the next user
# does not see stale absent state. ----------
def test_zz_cleanup_restore_present(tokens, teachers, today_iso):
    entries = [{"teacher_id": t["id"], "status": "present"} for t in teachers]
    r = tokens["school_admin"].post(f"{API}/teacher-attendance/bulk",
        json={"date": today_iso, "entries": entries},
        
        timeout=30,
    )
    assert r.status_code == 200
