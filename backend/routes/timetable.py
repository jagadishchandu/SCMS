"""Teacher timetable + calendar."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from core.models import TimetableBulk
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now
from core.notify import queue_notification

router = APIRouter(prefix="/timetable", tags=["timetable"])


async def _notify_teachers_of_timetable_change(
    school_id: str,
    class_id: str,
    section: str,
    new_slots: list,
    actor: dict,
):
    """Telegram-notify every distinct teacher who appears in the new schedule.

    Falls back gracefully — if a teacher hasn't linked Telegram yet, the helper
    still creates a notification row (queued with delivery_note=telegram_not_configured
    or no_chat_id) so it shows up in the admin notifications log.
    """
    from core.db import get_db as _root_db
    rdb = _root_db()
    tdb = await tenant_db(school_id)
    teacher_ids = sorted({s.get("teacher_id") for s in new_slots if s.get("teacher_id")})
    if not teacher_ids:
        return
    cls = await tdb.classes.find_one({"id": class_id, "school_id": school_id}, {"_id": 0, "name": 1})
    class_name = (cls or {}).get("name") or class_id
    teachers = await rdb.users.find(
        {"school_id": school_id, "role": "teacher", "id": {"$in": teacher_ids}},
        {"_id": 0, "id": 1, "name": 1, "telegram_chat_id": 1, "phone": 1},
    ).to_list(2000)
    actor_name = actor.get("name") or actor.get("email") or "School Admin"
    for t in teachers:
        own_periods = sum(1 for s in new_slots if s.get("teacher_id") == t["id"])
        msg = (
            f"📅 Timetable updated by {actor_name}\n"
            f"Class: {class_name} · Section {section}\n"
            f"You have {own_periods} period(s) in this schedule.\n"
            f"Open the app to view your weekly plan."
        )
        await queue_notification(
            school_id=school_id,
            recipient_type="teacher",
            recipient_id=t["id"],
            phone=t.get("phone"),
            channel="telegram",
            template="timetable_updated",
            message=msg,
            context={"class_id": class_id, "section": section, "own_periods": own_periods},
            telegram_chat_id=t.get("telegram_chat_id"),
        )


@router.post("/bulk")
async def set_timetable(payload: TimetableBulk, user: dict = Depends(require_roles("school_admin"))):
    tdb = await tenant_db(user["school_id"])
    await tdb.timetable.delete_many({"school_id": user["school_id"], "class_id": payload.class_id, "section": payload.section})
    docs = []
    for s in payload.slots:
        d = {
            "id": new_id(),
            "school_id": user["school_id"],
            "class_id": payload.class_id,
            "section": payload.section,
            "day": s.day,
            "period": s.period,
            "subject_id": s.subject_id,
            "teacher_id": s.teacher_id,
            "start_time": s.start_time,
            "end_time": s.end_time,
            "created_at": utc_now(),
        }
        docs.append(d)
    if docs:
        await tdb.timetable.insert_many(docs)
        # Fire-and-await Telegram notifications to affected teachers (doesn't fail the save if telegram is down).
        try:
            await _notify_teachers_of_timetable_change(
                user["school_id"], payload.class_id, payload.section, docs, user,
            )
        except Exception as e:
            # never block timetable save on a notification failure
            import logging
            logging.getLogger("scms.timetable").warning("teacher notify failed: %s", e)
    notified = len({d["teacher_id"] for d in docs if d.get("teacher_id")})
    return {"inserted": len(docs), "notified_teachers": notified}


@router.get("")
async def list_timetable(class_id: str | None = None, section: str | None = None, teacher_id: str | None = None,
                          user: dict = Depends(get_current_user)):
    tdb = await tenant_db(user["school_id"])
    flt = {"school_id": user["school_id"]}
    if user["role"] == "teacher":
        flt["teacher_id"] = user["id"]
    elif teacher_id:
        flt["teacher_id"] = teacher_id
    if class_id:
        flt["class_id"] = class_id
    if section:
        flt["section"] = section
    return await tdb.timetable.find(flt, {"_id": 0}).to_list(2000)


@router.get("/class-subject-coverage")
async def class_subject_coverage(user: dict = Depends(require_roles("school_admin"))):
    """Matrix view: for every (class, section) in the school, list which subjects
    are scheduled in the timetable + how many periods/week each gets + who teaches them.
    Also surfaces:
      • `missing_subjects` per row — subjects that exist in the school but are NOT scheduled in that class/section.
      • `unscheduled_subjects` at root — subjects that are not scheduled anywhere in the school.

    Used by the Academic page to spot coverage gaps.
    """
    from core.db import get_db as _root_db
    tdb = await tenant_db(user["school_id"])
    rdb = _root_db()
    classes = await tdb.classes.find({"school_id": user["school_id"]}, {"_id": 0}).sort("name", 1).to_list(500)
    subjects = await tdb.subjects.find({"school_id": user["school_id"]}, {"_id": 0}).sort("name", 1).to_list(500)
    slots = await tdb.timetable.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(10000)
    teachers = await rdb.users.find(
        {"school_id": user["school_id"], "role": "teacher"},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(2000)

    subject_map = {s["id"]: s for s in subjects}
    teacher_map = {t["id"]: t for t in teachers}
    scheduled_subject_ids = set()

    # Group slots by (class_id, section)
    bucket: dict[tuple[str, str], list[dict]] = {}
    for sl in slots:
        bucket.setdefault((sl["class_id"], sl["section"]), []).append(sl)
        scheduled_subject_ids.add(sl["subject_id"])

    matrix = []
    for c in classes:
        for sec in (c.get("sections") or []):
            slots_here = bucket.get((c["id"], sec), [])
            per_subj: dict[str, dict] = {}
            for sl in slots_here:
                sid = sl["subject_id"]
                if sid not in per_subj:
                    per_subj[sid] = {
                        "subject_id": sid,
                        "subject_name": subject_map.get(sid, {}).get("name") or sid,
                        "code": subject_map.get(sid, {}).get("code"),
                        "period_count": 0,
                        "teacher_ids": set(),
                    }
                per_subj[sid]["period_count"] += 1
                if sl.get("teacher_id"):
                    per_subj[sid]["teacher_ids"].add(sl["teacher_id"])
            subject_coverage = []
            for sid, row in per_subj.items():
                subject_coverage.append({
                    "subject_id": row["subject_id"],
                    "subject_name": row["subject_name"],
                    "code": row["code"],
                    "period_count": row["period_count"],
                    "teachers": [
                        {"id": tid, "name": teacher_map.get(tid, {}).get("name") or tid}
                        for tid in row["teacher_ids"]
                    ],
                })
            subject_coverage.sort(key=lambda x: x["subject_name"])
            covered_ids = {r["subject_id"] for r in subject_coverage}
            missing = [
                {"subject_id": s["id"], "subject_name": s["name"], "code": s.get("code")}
                for s in subjects if s["id"] not in covered_ids
            ]
            matrix.append({
                "class_id": c["id"],
                "class_name": c["name"],
                "section": sec,
                "subject_coverage": subject_coverage,
                "missing_subjects": missing,
                "total_periods": len(slots_here),
                "has_timetable": len(slots_here) > 0,
            })

    unscheduled = [
        {"subject_id": s["id"], "subject_name": s["name"], "code": s.get("code")}
        for s in subjects if s["id"] not in scheduled_subject_ids
    ]
    return {
        "matrix": matrix,
        "subjects_total": len(subjects),
        "classes_total": len(classes),
        "sections_total": len(matrix),
        "sections_with_timetable": sum(1 for r in matrix if r["has_timetable"]),
        "unscheduled_subjects": unscheduled,
    }


# ---- Auto-suggest timetable ----
DAYS_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat"]


class SuggestTimetableRequest(BaseModel):
    class_id: str
    section: str
    days: Optional[List[Literal["mon", "tue", "wed", "thu", "fri", "sat"]]] = None
    periods_per_day: int = Field(6, ge=1, le=12)
    start_time: str = "09:00"  # HH:MM 24h
    period_minutes: int = Field(45, ge=15, le=120)
    subject_periods: Optional[dict] = None  # {subject_id: int} optional override
    # --- Soft/hard constraints ---
    lunch_break_period: Optional[int] = Field(default=None, ge=1, le=12)  # 1-indexed; that period is left blank every day
    no_last_period_subjects: Optional[List[str]] = None  # subject ids forbidden in the last period
    subject_day_pins: Optional[dict] = None  # {subject_id: [day, day, ...]} — restrict subject to those days only


def _add_minutes(hhmm: str, mins: int) -> str:
    try:
        h, m = [int(x) for x in hhmm.split(":")]
    except Exception:
        h, m = 9, 0
    total = h * 60 + m + mins
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def _compute_subject_counts(
    subjects: list,
    total_slots: int,
    overrides: dict | None,
    day_pins: dict[str, set],
    num_days: int,
    periods_to_fill_per_day: int,
) -> dict[str, int]:
    """Return {subject_id: target_count} totalling total_slots.

    Honors caller-supplied `overrides` ({sid: int}) exactly; auto-balances the
    remainder across non-overridden subjects respecting per-subject capacity caps
    derived from day_pins (a subject pinned to N days can be scheduled at most
    `N * periods_to_fill_per_day` times).
    """
    overrides = overrides or {}
    counts: dict[str, int] = {}
    fixed = 0
    for s in subjects:
        c = overrides.get(s["id"])
        if c is not None and c >= 0:
            counts[s["id"]] = int(c)
            fixed += int(c)
    if fixed > total_slots:
        raise HTTPException(
            status_code=400,
            detail=f"subject_periods sum ({fixed}) exceeds total available slots ({total_slots}).",
        )
    remaining = total_slots - fixed

    def cap_for(sid: str) -> int:
        pinned = day_pins.get(sid)
        if pinned:
            return len(pinned) * periods_to_fill_per_day
        return num_days * periods_to_fill_per_day

    auto_subjects = [s for s in subjects if s["id"] not in counts]
    # Iteratively distribute respecting caps to avoid impossible plans
    pool = {s["id"]: 0 for s in auto_subjects}
    while remaining > 0 and any(pool[sid] < cap_for(sid) for sid in pool):
        eligible = [sid for sid in pool if pool[sid] < cap_for(sid)]
        if not eligible:
            break
        # Spread one period to each eligible subject
        for sid in eligible:
            if remaining <= 0:
                break
            if pool[sid] < cap_for(sid):
                pool[sid] += 1
                remaining -= 1
    counts.update(pool)
    # If still remaining (all caps full), push leftovers into the first override-only subject
    # that has spare capacity, or into the first subject (best-effort).
    if remaining > 0:
        ordered = list(counts.keys()) or [s["id"] for s in subjects[:1]]
        idx = 0
        guard = 10000
        while remaining > 0 and ordered and guard > 0:
            sid = ordered[idx % len(ordered)]
            if counts.get(sid, 0) < cap_for(sid):
                counts[sid] = counts.get(sid, 0) + 1
                remaining -= 1
            idx += 1
            guard -= 1
        # If we couldn't fit (caps too tight), raise.
        if remaining > 0:
            raise HTTPException(
                status_code=400,
                detail="Subject day-pins are too restrictive — no valid distribution exists. Relax day-pins or add more days/periods.",
            )
    return counts



@router.post("/suggest")
async def suggest_timetable(
    payload: SuggestTimetableRequest,
    user: dict = Depends(require_roles("school_admin")),
):
    """Generate a suggested weekly timetable for a class+section.

    Uses existing Subject⇄Teacher assignments. For each generated slot we pick a
    teacher who teaches the subject AND who is not already busy in another class
    at the same (day, period) in the existing timetable. If no such teacher exists
    the slot is returned with teacher_id="" and a warning is added.

    Response: { slots: [TimetableSlot-shape], warnings: [str], subject_distribution: {subject_id: count} }

    The admin can review the suggested grid in the UI and persist it via
    the existing POST /api/timetable/bulk endpoint.
    """
    from core.db import get_db as _root_db
    tdb = await tenant_db(user["school_id"])
    rdb = _root_db()

    cls = await tdb.classes.find_one({"id": payload.class_id, "school_id": user["school_id"]})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if payload.section.upper() not in [s.upper() for s in (cls.get("sections") or [])]:
        raise HTTPException(status_code=400, detail=f"Section '{payload.section}' not found in class")

    days = payload.days or DAYS_ORDER[:5]  # default Mon–Fri
    days = [d for d in DAYS_ORDER if d in days]  # canonical order
    periods_per_day = payload.periods_per_day
    lunch = payload.lunch_break_period
    if lunch and lunch > periods_per_day:
        raise HTTPException(status_code=400, detail=f"lunch_break_period ({lunch}) cannot exceed periods_per_day ({periods_per_day}).")
    periods_to_fill_per_day = periods_per_day - (1 if lunch else 0)
    total_slots = len(days) * periods_to_fill_per_day
    if total_slots == 0:
        raise HTTPException(status_code=400, detail="No teaching periods after configuring lunch break")

    subjects = await tdb.subjects.find({"school_id": user["school_id"]}, {"_id": 0}).sort("name", 1).to_list(500)
    if not subjects:
        raise HTTPException(status_code=400, detail="No subjects defined for this school. Add subjects first.")

    teachers = await rdb.users.find(
        {"school_id": user["school_id"], "role": "teacher", "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "subjects": 1},
    ).to_list(2000)
    subject_to_teachers: dict[str, list[dict]] = {}
    for t in teachers:
        for sid in (t.get("subjects") or []):
            subject_to_teachers.setdefault(sid, []).append(t)

    # Existing busy map across the whole school: (day, period, teacher_id) -> True
    existing = await tdb.timetable.find(
        {"school_id": user["school_id"]},
        {"_id": 0, "day": 1, "period": 1, "teacher_id": 1, "class_id": 1, "section": 1},
    ).to_list(20000)
    busy: set = set()
    for sl in existing:
        # Skip slots for THIS class/section (we'll be regenerating it anyway)
        if sl.get("class_id") == payload.class_id and sl.get("section") == payload.section.upper():
            continue
        busy.add((sl["day"], sl["period"], sl.get("teacher_id")))

    # Validate constraints reference real subjects
    valid_sids = {s["id"] for s in subjects}
    no_last_set = {sid for sid in (payload.no_last_period_subjects or []) if sid in valid_sids}
    day_pins_raw = payload.subject_day_pins or {}
    day_pins: dict[str, set] = {}
    for sid, pinned in day_pins_raw.items():
        if sid not in valid_sids:
            continue
        if not pinned:
            continue
        day_pins[sid] = {d for d in pinned if d in DAYS_ORDER}

    # Compute target counts per subject (respecting overrides + day-pin capacity).
    counts = _compute_subject_counts(subjects, total_slots, payload.subject_periods, day_pins, len(days), periods_to_fill_per_day)

    # Build positions list (excluding lunch break) in canonical order
    positions: list[tuple[str, int]] = []
    for day in days:
        for period in range(1, periods_per_day + 1):
            if lunch and period == lunch:
                continue
            positions.append((day, period))

    # Greedy assignment respecting constraints
    remaining = dict(counts)
    last_subject_per_day: dict[str, str | None] = {}
    assignment: list[str] = []
    warnings_set: set = set()
    for (day, period) in positions:
        is_last = period == periods_per_day
        last_subj = last_subject_per_day.get(day)
        candidates = [sid for sid, c in remaining.items() if c > 0]
        # 1. day-pin filter
        pinned = [sid for sid in candidates if (sid not in day_pins) or (day in day_pins[sid])]
        cand1 = pinned if pinned else candidates
        # 2. no-last-period filter
        if is_last and no_last_set:
            non_last = [sid for sid in cand1 if sid not in no_last_set]
            cand2 = non_last if non_last else cand1
        else:
            cand2 = cand1
        # 3. avoid repeating last subject in same day
        non_repeat = [sid for sid in cand2 if sid != last_subj]
        cand3 = non_repeat if non_repeat else cand2
        if not cand3:
            # Should not happen — counts sum equals positions length
            raise HTTPException(status_code=400, detail="Constraint solver failed — relax constraints and retry.")
        # Greedy heuristic: prioritise subjects that MUST go on this day (day-pinned and current day is in their pin set)
        # so their limited capacity isn't wasted, then by remaining count, then stable by subject_id.
        def _pri(sid: str) -> tuple:
            pin = day_pins.get(sid)
            pinned_here = 0 if (pin and day in pin) else 1  # 0 = highest priority
            return (pinned_here, -remaining[sid], sid)
        cand3.sort(key=_pri)
        chosen_sid = cand3[0]
        # Surface a warning if we had to relax day-pin
        if chosen_sid in day_pins and day not in day_pins[chosen_sid]:
            warnings_set.add(
                f"Day-pin for '{next((s['name'] for s in subjects if s['id']==chosen_sid), chosen_sid)}' was relaxed to fit the grid."
            )
        if is_last and chosen_sid in no_last_set:
            warnings_set.add(
                f"'{next((s['name'] for s in subjects if s['id']==chosen_sid), chosen_sid)}' had to be placed in the last period despite the no-last-period constraint."
            )
        assignment.append(chosen_sid)
        remaining[chosen_sid] -= 1
        last_subject_per_day[day] = chosen_sid

    # Round-robin teacher index per subject (for load balancing)
    rr_index: dict[str, int] = {sid: 0 for sid in counts}

    slots = []
    pos_idx = 0
    for day in days:
        for period in range(1, periods_per_day + 1):
            slot_start = _add_minutes(payload.start_time, (period - 1) * payload.period_minutes)
            slot_end = _add_minutes(payload.start_time, period * payload.period_minutes)
            if lunch and period == lunch:
                # Surface lunch as a slot but mark it as break (subject_id and teacher_id empty)
                slots.append({
                    "day": day,
                    "period": period,
                    "subject_id": "",
                    "teacher_id": "",
                    "class_id": payload.class_id,
                    "section": payload.section.upper(),
                    "start_time": slot_start,
                    "end_time": slot_end,
                    "is_break": True,
                    "break_label": "Lunch",
                })
                continue
            sid = assignment[pos_idx]
            pos_idx += 1
            candidates = subject_to_teachers.get(sid) or []
            chosen = None
            if candidates:
                n = len(candidates)
                start = rr_index.get(sid, 0)
                for k in range(n):
                    idx = (start + k) % n
                    t = candidates[idx]
                    if (day, period, t["id"]) in busy:
                        continue
                    chosen = t
                    rr_index[sid] = (idx + 1) % n
                    break
                if chosen is None:
                    warnings_set.add(
                        f"All teachers of '{next((s['name'] for s in subjects if s['id']==sid), sid)}' are busy elsewhere at {day.upper()} period {period}."
                    )
            else:
                warnings_set.add(
                    f"No teacher assigned to '{next((s['name'] for s in subjects if s['id']==sid), sid)}' — please assign teachers first."
                )

            slots.append({
                "day": day,
                "period": period,
                "subject_id": sid,
                "teacher_id": (chosen or {}).get("id", ""),
                "class_id": payload.class_id,
                "section": payload.section.upper(),
                "start_time": slot_start,
                "end_time": slot_end,
            })
            if chosen:
                busy.add((day, period, chosen["id"]))

    subject_distribution = {sid: counts.get(sid, 0) for sid in counts}
    return {
        "slots": slots,
        "warnings": sorted(warnings_set),
        "subject_distribution": subject_distribution,
        "days": days,
        "periods_per_day": periods_per_day,
        "total_slots": total_slots,
        "lunch_break_period": lunch,
    }
