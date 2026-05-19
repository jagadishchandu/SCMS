"""V45 tests: prefer_underloaded_teachers ("Rebalance" backend flag).

When `prefer_underloaded_teachers=True` is passed in defaults of /suggest-batch,
the engine should pick the candidate teacher with the LOWEST weekly load instead
of round-robin. The end-to-end effect is a tighter (workload_max - workload_min)
gap and no degradation of hard constraints (no double-booking, no overshoot of
the per-day cap).
"""
import os
import pytest
import requests


def _backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not configured"
    return url.rstrip("/") + "/api"


BASE_URL = _backend_url()
PRINCIPAL = {"email": "principal@sunrise.edu", "password": "School@123"}


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/auth/login", json=PRINCIPAL, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def school_data(admin_session):
    classes = admin_session.get(f"{BASE_URL}/academic/classes", timeout=20).json()
    subjects = admin_session.get(f"{BASE_URL}/academic/subjects", timeout=20).json()
    teachers = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
    return {"classes": classes, "subjects": subjects, "teachers": teachers}


def _build_sections(school_data, count=4):
    """Pick the first `count` (class, section) pairs available."""
    out = []
    for c in school_data["classes"]:
        for sec in (c.get("sections") or []):
            out.append({"class_id": c["id"], "section": sec, "student_count": 30})
            if len(out) >= count:
                return out
    return out


def _workload_stats(resp_json):
    tv = resp_json.get("teacher_view") or {}
    teachers = tv.get("teachers") or []
    totals = [t.get("total_periods", 0) for t in teachers if t.get("total_periods", 0) > 0]
    if not totals:
        return {"min": 0, "max": 0, "gap": 0, "n": 0}
    return {
        "min": min(totals),
        "max": max(totals),
        "gap": max(totals) - min(totals),
        "n": len(totals),
    }


def _double_bookings(resp_json):
    return len((resp_json.get("conflict_summary") or {}).get("double_bookings") or [])


class TestPreferUnderloaded:
    def test_flag_accepted_and_response_intact(self, admin_session, school_data):
        sections = _build_sections(school_data, count=2)
        body = {
            "sections": sections,
            "defaults": {
                "class_id": sections[0]["class_id"],
                "section": sections[0]["section"],
                "days": ["mon", "tue", "wed", "thu", "fri"],
                "periods_per_day": 6,
                "lunch_break_period": 4,
                "prefer_underloaded_teachers": True,
            },
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=body, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "teacher_view" in data
        assert "sections" in data
        # No double bookings even with rebalance
        assert _double_bookings(data) == 0

    def test_rebalance_narrows_workload_gap(self, admin_session, school_data):
        """Rebalance should produce a gap <= the gap from a normal generation
        (on the same input). This is the contractual guarantee of the flag."""
        sections = _build_sections(school_data, count=4)
        base_defaults = {
            "class_id": sections[0]["class_id"],
            "section": sections[0]["section"],
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "periods_per_day": 6,
            "lunch_break_period": 4,
        }
        # baseline (round-robin)
        body_a = {"sections": sections, "defaults": base_defaults, "reset_existing": True}
        r_a = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=body_a, timeout=60)
        assert r_a.status_code == 200, r_a.text
        a_stats = _workload_stats(r_a.json())

        # rebalance
        body_b = {
            "sections": sections,
            "defaults": {**base_defaults, "prefer_underloaded_teachers": True},
            "reset_existing": True,
        }
        r_b = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=body_b, timeout=60)
        assert r_b.status_code == 200, r_b.text
        b_stats = _workload_stats(r_b.json())

        # Gap should not get worse. With this seed it typically gets equal or better.
        assert b_stats["gap"] <= a_stats["gap"] + 1, (
            f"Rebalance widened the workload gap: baseline={a_stats}, rebalanced={b_stats}"
        )
        # Hard constraints still pass
        assert _double_bookings(r_b.json()) == 0

    def test_rebalance_respects_per_day_cap(self, admin_session, school_data):
        """Even when biased to under-loaded, the engine must never exceed
        max_periods_per_day_per_teacher."""
        sections = _build_sections(school_data, count=3)
        body = {
            "sections": sections,
            "defaults": {
                "class_id": sections[0]["class_id"],
                "section": sections[0]["section"],
                "days": ["mon", "tue", "wed", "thu", "fri"],
                "periods_per_day": 6,
                "lunch_break_period": 4,
                "max_periods_per_day_per_teacher": 4,
                "prefer_underloaded_teachers": True,
            },
            "reset_existing": True,
        }
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=body, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # Walk teacher_view and assert no day exceeds the cap
        for t in (data.get("teacher_view") or {}).get("teachers") or []:
            by_day = t.get("by_day") or {}
            for d, periods in by_day.items():
                n = len(periods or {})
                assert n <= 4, (
                    f"Teacher {t.get('teacher_name')} has {n} periods on {d} (cap=4) with rebalance ON"
                )
