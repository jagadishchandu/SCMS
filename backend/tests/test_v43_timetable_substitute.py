"""V43 timetable backend tests:
  - Repair pass (intra-section swap + cross-subject substitute) reaches 0 unfilled with 4-teacher demo
  - repair_stats present per section
  - swapped_from / is_substitute markers on repaired slots
  - No teacher double-booking across the whole batch
  - /save-batch persists unfilled rows (teacher_id="")
  - GET /api/timetable/coverage shape + correctness
  - POST /api/timetable/substitute-suggest ranking + exclusion rules
  - POST /api/timetable/substitute-apply happy path + 409 conflict
"""
import os
import pytest
import requests


def _backend_url() -> str:
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


# ---------------- Module-scoped fixtures ----------------

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

    # Seed Anita Sharma — teacher who covers ALL 5 subjects — required for 0% unfilled
    all_subject_ids = [s["id"] for s in subjects]
    anita = next((t for t in teachers if (t.get("email") or "").lower() == "anita@sunrise.edu"), None)
    if not anita:
        payload = {
            "email": "anita@sunrise.edu",
            "password": "Teacher@123",
            "name": "Anita Sharma",
            "role": "teacher",
            "subjects": all_subject_ids,
        }
        r = admin_session.post(f"{BASE_URL}/users", json=payload, timeout=20)
        # 200 created OR 400 already exists -> tolerate
        if r.status_code not in (200, 201):
            assert r.status_code == 400 and "already exists" in r.text, r.text
        teachers = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()
    else:
        # Ensure Anita's subjects cover all 5 (idempotent update)
        if set(anita.get("subjects") or []) != set(all_subject_ids):
            admin_session.patch(
                f"{BASE_URL}/users/{anita['id']}",
                json={"subjects": all_subject_ids},
                timeout=20,
            )
            teachers = admin_session.get(f"{BASE_URL}/users?role=teacher", timeout=20).json()

    return {
        "classes": classes,
        "subjects": subjects,
        "teachers": teachers,
        "sub_by_name": {s["name"]: s for s in subjects},
        "cls_by_name": {c["name"]: c for c in classes},
        "anita": next((t for t in teachers if (t.get("email") or "").lower() == "anita@sunrise.edu"), None),
    }


def _g5_g6(school_data):
    g5 = school_data["cls_by_name"].get("Grade 5") or school_data["classes"][0]
    g6 = school_data["cls_by_name"].get("Grade 6") or school_data["classes"][1]
    return g5, g6


def _typical_batch_payload(g5, g6):
    return {
        "sections": [
            {"class_id": g5["id"], "section": "A"},
            {"class_id": g5["id"], "section": "B"},
            {"class_id": g6["id"], "section": "A"},
            {"class_id": g6["id"], "section": "B"},
        ],
        "defaults": {
            "class_id": g5["id"], "section": "A",
            # 6 periods with lunch at p6 → 5 teaching slots/day × 5 days × 4 sections = 100
            "periods_per_day": 6, "lunch_break_period": 6,
        },
        "reset_existing": True,
    }


# ---------------- Repair pass + 0% unfilled ----------------
class TestRepairZeroUnfilled:
    def test_zero_unfilled_typical_4_teacher_setup(self, admin_session, school_data):
        """4 teachers × 4 sections × 5 periods × 5 days = 100 teaching slots, all should fill."""
        assert school_data["anita"], "Anita Sharma seed missing"
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()

        total_unfilled = 0
        for sec in data["sections"]:
            unfilled = [
                sl for sl in sec["slots"]
                if not sl.get("is_break") and sl.get("subject_id") and not sl.get("teacher_id")
            ]
            total_unfilled += len(unfilled)
        assert total_unfilled == 0, f"Expected 0 unfilled; got {total_unfilled}"

    def test_every_section_has_repair_stats(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        for sec in r.json()["sections"]:
            rs = sec.get("repair_stats")
            assert rs is not None, f"missing repair_stats in section {sec.get('section')}"
            for k in ("attempts", "swap_repairs", "substitute_repairs"):
                assert k in rs, f"missing repair_stats.{k}"
                assert isinstance(rs[k], int), f"repair_stats.{k} must be int"

    def test_substitute_slot_has_teacher_and_flag(self, admin_session, school_data):
        """When repair_stats.substitute_repairs > 0 in at least one batch, the marked
        slot must carry is_substitute=True AND a non-empty teacher_id."""
        g5, g6 = _g5_g6(school_data)
        # Force substitute usage by *tightening* per-day cap so swap alone can't fix everything.
        payload = _typical_batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 4
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        sub_slots = []
        for sec in data["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_substitute"):
                    sub_slots.append(sl)
        # may or may not happen depending on greedy result — but if any substitute was
        # ever recorded across the batch, validate its shape.
        total_sub = sum(s["repair_stats"]["substitute_repairs"] for s in data["sections"])
        if total_sub > 0:
            assert sub_slots, "substitute_repairs reported but no slot has is_substitute=True"
            for sl in sub_slots:
                assert sl.get("teacher_id"), f"substitute slot has empty teacher_id: {sl}"

    def test_swap_slot_has_swapped_from(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 5
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        total_swaps = sum(s["repair_stats"]["swap_repairs"] for s in data["sections"])
        swapped_slots = [sl for sec in data["sections"] for sl in sec["slots"] if sl.get("swapped_from")]
        if total_swaps > 0:
            assert swapped_slots, "swap_repairs reported but no slot has swapped_from"
            for sl in swapped_slots:
                sf = sl["swapped_from"]
                assert "day" in sf and "period" in sf, f"swapped_from missing day/period: {sf}"

    def test_no_teacher_double_booking_across_batch(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        r = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        seen: dict[tuple, tuple] = {}
        for sec in r.json()["sections"]:
            for sl in sec["slots"]:
                if sl.get("is_break"):
                    continue
                tid = sl.get("teacher_id")
                if not tid:
                    continue
                key = (sl["day"], sl["period"], tid)
                where = (sec["class_id"], sec["section"], sl.get("subject_id"))
                assert key not in seen, (
                    f"double-booking: teacher {tid} at {key} in {where} AND {seen[key]}"
                )
                seen[key] = where


# ---------------- save-batch persists unfilled ----------------
class TestSaveBatchUnfilled:
    def test_save_persists_unfilled_slots(self, admin_session, school_data):
        """Force unfilled slots with cap=1 (3 teachers can't cover 5 slots/day) and then
        verify GET /api/timetable returns rows with empty teacher_id AND a subject_id."""
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 1  # cap so low repair pass can't fully solve

        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90).json()

        # Count unfilled in suggest output
        unfilled_pre = 0
        for sec in sg["sections"]:
            for sl in sec["slots"]:
                if (not sl.get("is_break") and sl.get("subject_id") and not sl.get("teacher_id")):
                    unfilled_pre += 1

        # Save it
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        r = admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)
        assert r.status_code == 200, r.text

        if unfilled_pre == 0:
            pytest.skip("cap=1 still produced 0 unfilled; cannot assert persistence of empty rows")

        # GET timetable rows for any saved section; look for unfilled rows
        g5_a_rows = admin_session.get(
            f"{BASE_URL}/timetable",
            params={"class_id": g5["id"], "section": "A"},
            timeout=20,
        ).json()
        # Some implementations return list directly, some wrap in {slots: [...]}
        if isinstance(g5_a_rows, dict) and "slots" in g5_a_rows:
            g5_a_rows = g5_a_rows["slots"]
        # Look at all 4 sections together
        all_rows = []
        for (cid, sec) in [(g5["id"], "A"), (g5["id"], "B"), (g6["id"], "A"), (g6["id"], "B")]:
            resp = admin_session.get(
                f"{BASE_URL}/timetable", params={"class_id": cid, "section": sec}, timeout=20,
            ).json()
            if isinstance(resp, dict) and "slots" in resp:
                resp = resp["slots"]
            if isinstance(resp, list):
                all_rows.extend(resp)
        empty_rows = [r for r in all_rows if (r.get("teacher_id") in ("", None)) and r.get("subject_id")]
        assert empty_rows, (
            f"expected unfilled rows persisted (had {unfilled_pre} unfilled in suggest); none found in /timetable"
        )


# ---------------- /coverage ----------------
class TestCoverage:
    def test_coverage_zero_after_fully_repaired_save(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90).json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)

        r = admin_session.get(f"{BASE_URL}/timetable/coverage", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("sections_with_unfilled", "total_unfilled", "details"):
            assert k in d, f"missing key {k} in /coverage response"
        assert d["total_unfilled"] == 0, f"expected 0; got {d}"
        assert d["sections_with_unfilled"] == 0
        assert d["details"] == []

    def test_coverage_nonzero_after_intentionally_unfillable_save(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 1
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90).json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)
        r = admin_session.get(f"{BASE_URL}/timetable/coverage", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_unfilled"] > 0, f"expected unfilled > 0 with cap=1; got {d}"
        assert d["sections_with_unfilled"] >= 1
        for det in d["details"]:
            assert "class_id" in det and "section" in det and "unfilled" in det
            assert det["unfilled"] > 0


# ---------------- /substitute-suggest ----------------
class TestSubstituteSuggest:
    def _seed_with_unfilled(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 1
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90).json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)
        return sg, save_payload

    def _find_unfilled(self, sg):
        for sec in sg["sections"]:
            for sl in sec["slots"]:
                if (not sl.get("is_break") and sl.get("subject_id") and not sl.get("teacher_id")):
                    return sec["class_id"], sec["section"], sl
        return None

    def test_suggest_ranking_and_shape(self, admin_session, school_data):
        sg, _ = self._seed_with_unfilled(admin_session, school_data)
        unfilled = self._find_unfilled(sg)
        if not unfilled:
            pytest.skip("could not produce unfilled with cap=1")
        class_id, section, slot = unfilled
        body = {
            "class_id": class_id, "section": section,
            "day": slot["day"], "period": slot["period"],
            "prefer_subject_id": slot.get("subject_id"),
        }
        r = admin_session.post(f"{BASE_URL}/timetable/substitute-suggest", json=body, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "suggestions" in data
        # Shape
        for s in data["suggestions"]:
            for k in ("teacher_id", "teacher_name", "teaches_subject", "daily_load", "on_leave_today"):
                assert k in s, f"missing key {k} in suggestion: {s}"
        # Ranking: teaches_subject=True must come before False
        seen_false = False
        for s in data["suggestions"]:
            if not s["teaches_subject"]:
                seen_false = True
            elif s["teaches_subject"] and seen_false:
                pytest.fail(f"teaches_subject=True appeared AFTER False: {data['suggestions']}")

    def test_busy_teacher_excluded(self, admin_session, school_data):
        """A teacher already booked at (day, period) elsewhere must NOT appear in suggestions."""
        # First seed timetable and find any FILLED slot to discover a busy teacher
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90).json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)

        busy_slot = None
        for sec in sg["sections"]:
            for sl in sec["slots"]:
                if not sl.get("is_break") and sl.get("teacher_id"):
                    busy_slot = (sec["class_id"], sec["section"], sl)
                    break
            if busy_slot:
                break
        assert busy_slot, "no filled slot found"
        cid, sec, sl = busy_slot
        r = admin_session.post(
            f"{BASE_URL}/timetable/substitute-suggest",
            json={"class_id": cid, "section": sec, "day": sl["day"], "period": sl["period"]},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        suggested_ids = {s["teacher_id"] for s in r.json()["suggestions"]}
        assert sl["teacher_id"] not in suggested_ids, (
            f"busy teacher {sl['teacher_id']} leaked into suggestions at ({sl['day']},{sl['period']})"
        )


# ---------------- /substitute-apply ----------------
class TestSubstituteApply:
    def _seed(self, admin_session, school_data):
        g5, g6 = _g5_g6(school_data)
        payload = _typical_batch_payload(g5, g6)
        payload["defaults"]["max_periods_per_day_per_teacher"] = 1
        sg = admin_session.post(f"{BASE_URL}/timetable/suggest-batch", json=payload, timeout=90).json()
        save_payload = {
            "sections": [
                {"class_id": s["class_id"], "section": s["section"], "slots": s["slots"]}
                for s in sg["sections"]
            ]
        }
        admin_session.post(f"{BASE_URL}/timetable/save-batch", json=save_payload, timeout=60)
        return sg

    def test_apply_persists_substitute(self, admin_session, school_data):
        sg = self._seed(admin_session, school_data)
        # find an unfilled slot
        target = None
        for sec in sg["sections"]:
            for sl in sec["slots"]:
                if not sl.get("is_break") and sl.get("subject_id") and not sl.get("teacher_id"):
                    target = (sec["class_id"], sec["section"], sl)
                    break
            if target:
                break
        if not target:
            pytest.skip("no unfilled slot to apply substitute on")
        cid, sec, sl = target

        # pick a free teacher via /substitute-suggest
        sugg = admin_session.post(
            f"{BASE_URL}/timetable/substitute-suggest",
            json={"class_id": cid, "section": sec, "day": sl["day"], "period": sl["period"],
                  "prefer_subject_id": sl.get("subject_id")},
            timeout=30,
        ).json()
        assert sugg["suggestions"], "no free teacher available"
        chosen = sugg["suggestions"][0]

        r = admin_session.post(
            f"{BASE_URL}/timetable/substitute-apply",
            json={
                "class_id": cid, "section": sec,
                "day": sl["day"], "period": sl["period"],
                "teacher_id": chosen["teacher_id"],
                "subject_id": sl.get("subject_id"),
                "notify": False,
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("slot_id"), f"missing slot_id: {d}"

        # Verify persistence
        rows = admin_session.get(
            f"{BASE_URL}/timetable", params={"class_id": cid, "section": sec}, timeout=20,
        ).json()
        if isinstance(rows, dict) and "slots" in rows:
            rows = rows["slots"]
        match = next(
            (r for r in rows if r.get("day") == sl["day"] and r.get("period") == sl["period"]),
            None,
        )
        assert match, f"slot not found after apply: ({sl['day']},{sl['period']})"
        assert match.get("teacher_id") == chosen["teacher_id"]
        assert match.get("is_substitute") is True

    def test_apply_409_when_teacher_busy(self, admin_session, school_data):
        sg = self._seed(admin_session, school_data)

        # Pick a FILLED slot in section A → teacher T busy at (day, period) in A
        # Then try applying T to an UNFILLED slot at the SAME (day, period) in another section
        busy = None
        for sec in sg["sections"]:
            for sl in sec["slots"]:
                if not sl.get("is_break") and sl.get("teacher_id"):
                    busy = (sec["class_id"], sec["section"], sl)
                    break
            if busy:
                break
        assert busy, "no filled slot found"
        b_cid, b_sec, b_slot = busy
        b_tid = b_slot["teacher_id"]

        # Find unfilled slot at SAME (day, period) in a different (class_id, section)
        target = None
        for sec in sg["sections"]:
            if sec["class_id"] == b_cid and sec["section"] == b_sec:
                continue
            for sl in sec["slots"]:
                if (sl["day"] == b_slot["day"] and sl["period"] == b_slot["period"]
                        and not sl.get("is_break") and sl.get("subject_id")
                        and not sl.get("teacher_id")):
                    target = (sec["class_id"], sec["section"], sl)
                    break
            if target:
                break
        if not target:
            pytest.skip("could not construct overlapping unfilled scenario")
        t_cid, t_sec, t_slot = target
        r = admin_session.post(
            f"{BASE_URL}/timetable/substitute-apply",
            json={
                "class_id": t_cid, "section": t_sec,
                "day": t_slot["day"], "period": t_slot["period"],
                "teacher_id": b_tid,
                "subject_id": t_slot.get("subject_id"),
                "notify": False,
            },
            timeout=20,
        )
        assert r.status_code == 409, f"expected 409; got {r.status_code} {r.text}"
        body = r.json()
        # FastAPI wraps detail
        detail = body.get("detail") if isinstance(body, dict) else None
        assert detail and isinstance(detail, dict), f"unexpected 409 body: {body}"
        cw = detail.get("conflict_with") or {}
        for k in ("class_id", "section", "subject_id"):
            assert k in cw, f"conflict_with missing {k}: {cw}"
        assert cw["class_id"] == b_cid
        assert (cw["section"] or "").upper() == b_sec.upper()
