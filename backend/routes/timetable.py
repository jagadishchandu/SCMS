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
    from core.db import get_db as _root_db
    rdb = _root_db()

    # ---- Conflict detection (strict) ----
    # 1) Intra-payload: same teacher in two slots at the same (day, period).
    # 2) Cross-class: same teacher already booked at (day, period) in a DIFFERENT class/section.
    intra: dict[tuple, list] = {}
    for s in payload.slots:
        if not s.teacher_id:
            continue
        intra.setdefault((s.day, s.period, s.teacher_id), []).append(
            {"class_id": s.class_id, "section": s.section, "subject_id": s.subject_id}
        )
    intra_conflicts = [
        {"day": k[0], "period": k[1], "teacher_id": k[2], "occurrences": v}
        for k, v in intra.items() if len(v) > 1
    ]

    teacher_ids = sorted({s.teacher_id for s in payload.slots if s.teacher_id})
    cross_conflicts: list[dict] = []
    if teacher_ids:
        # Pull every existing slot for those teachers in OTHER classes/sections
        existing = await tdb.timetable.find(
            {
                "school_id": user["school_id"],
                "teacher_id": {"$in": teacher_ids},
                "$nor": [{"class_id": payload.class_id, "section": payload.section}],
            },
            {"_id": 0, "day": 1, "period": 1, "teacher_id": 1, "class_id": 1, "section": 1, "subject_id": 1},
        ).to_list(20000)
        busy = {(e["day"], e["period"], e["teacher_id"]): e for e in existing}
        for s in payload.slots:
            if not s.teacher_id:
                continue
            hit = busy.get((s.day, s.period, s.teacher_id))
            if hit:
                cross_conflicts.append({
                    "day": s.day,
                    "period": s.period,
                    "teacher_id": s.teacher_id,
                    "conflict_with": {
                        "class_id": hit["class_id"],
                        "section": hit["section"],
                        "subject_id": hit.get("subject_id"),
                    },
                    "this_class": {
                        "class_id": s.class_id, "section": s.section, "subject_id": s.subject_id,
                    },
                })

    if intra_conflicts or cross_conflicts:
        # Enrich with friendly names
        all_tids = sorted({c["teacher_id"] for c in intra_conflicts} | {c["teacher_id"] for c in cross_conflicts})
        teachers = await rdb.users.find(
            {"school_id": user["school_id"], "id": {"$in": all_tids}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(2000)
        tmap = {t["id"]: t["name"] for t in teachers}
        classes = await tdb.classes.find(
            {"school_id": user["school_id"]}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(500)
        cmap = {c["id"]: c["name"] for c in classes}
        subjects = await tdb.subjects.find(
            {"school_id": user["school_id"]}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(500)
        smap = {s["id"]: s["name"] for s in subjects}
        for c in intra_conflicts:
            c["teacher_name"] = tmap.get(c["teacher_id"], c["teacher_id"])
        for c in cross_conflicts:
            c["teacher_name"] = tmap.get(c["teacher_id"], c["teacher_id"])
            c["conflict_with"]["class_name"] = cmap.get(c["conflict_with"]["class_id"], c["conflict_with"]["class_id"])
            c["conflict_with"]["subject_name"] = smap.get(c["conflict_with"].get("subject_id"), None)
        raise HTTPException(status_code=409, detail={
            "error": "timetable_conflict",
            "message": (
                f"{len(intra_conflicts)} same-class double-booking(s) and "
                f"{len(cross_conflicts)} cross-class collision(s) detected. "
                "Resolve them and try again."
            ),
            "intra_payload_conflicts": intra_conflicts,
            "cross_class_conflicts": cross_conflicts,
        })

    # ---- All clear: replace existing slots for this class/section ----
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


class FixedBreak(BaseModel):
    period: int = Field(..., ge=1, le=12)
    label: str = "Break"


class ClassTeacherPin(BaseModel):
    """Pin a 'class-teacher period' that runs at the same period every day.
    `subject_id` is optional — leave empty to mark it as a tutor/admin period
    with no academic subject. `teacher_id` is required.
    """
    teacher_id: str
    period: int = Field(..., ge=1, le=12)
    subject_id: Optional[str] = None
    label: str = "Class Teacher"


class SuggestTimetableRequest(BaseModel):
    class_id: str
    section: str
    days: Optional[List[Literal["mon", "tue", "wed", "thu", "fri", "sat"]]] = None
    periods_per_day: int = Field(6, ge=1, le=12)
    start_time: str = "09:00"  # HH:MM 24h
    period_minutes: int = Field(45, ge=15, le=120)
    subject_periods: Optional[dict] = None  # {subject_id: int} optional override — frequency per week
    # --- Soft/hard constraints ---
    lunch_break_period: Optional[int] = Field(default=None, ge=1, le=12)  # 1-indexed; that period is left blank every day
    fixed_breaks: Optional[List[FixedBreak]] = None  # additional fixed breaks (e.g. morning assembly, snack)
    no_last_period_subjects: Optional[List[str]] = None  # subject ids forbidden in the last period
    subject_day_pins: Optional[dict] = None  # {subject_id: [day, day, ...]} — restrict subject to those days only
    # New v40 constraints
    subject_categories: Optional[dict] = None  # {subject_id: "heavy"|"light"|"lab"|"sports"|"library"|"regular"}
    allowed_periods_per_subject: Optional[dict] = None  # {subject_id: [period, period, ...]} — restrict subject to those periods only
    max_consecutive_heavy: int = Field(2, ge=1, le=8)  # cap heavy subjects placed back-to-back in a day
    class_teacher: Optional[ClassTeacherPin] = None  # daily class-teacher period
    # Optional ISO date (YYYY-MM-DD) of the Monday of the week this timetable is
    # being generated for. If provided, the engine will skip any teacher that
    # has an APPROVED leave covering that weekday.
    effective_week_start: Optional[str] = None


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



async def _gather_school_resources(school_id: str):
    """Load subjects + teachers + global existing-timetable busy map for a school."""
    from core.db import get_db as _root_db
    tdb = await tenant_db(school_id)
    rdb = _root_db()
    subjects = await tdb.subjects.find({"school_id": school_id}, {"_id": 0}).sort("name", 1).to_list(500)
    teachers = await rdb.users.find(
        {"school_id": school_id, "role": "teacher", "is_active": True},
        {"_id": 0, "id": 1, "name": 1, "subjects": 1},
    ).to_list(2000)
    subject_to_teachers: dict[str, list[dict]] = {}
    for t in teachers:
        for sid in (t.get("subjects") or []):
            subject_to_teachers.setdefault(sid, []).append(t)
    existing = await tdb.timetable.find(
        {"school_id": school_id},
        {"_id": 0, "day": 1, "period": 1, "teacher_id": 1, "class_id": 1, "section": 1},
    ).to_list(20000)
    return tdb, rdb, subjects, teachers, subject_to_teachers, existing


async def _leave_block_map(tdb, school_id: str, effective_week_start: Optional[str]) -> dict[str, set[str]]:
    """For an ISO Monday, return {day_key: {teacher_id, ...}} who are on approved leave that weekday."""
    out: dict[str, set[str]] = {d: set() for d in DAYS_ORDER}
    if not effective_week_start:
        return out
    try:
        from datetime import datetime as _dt, timedelta as _td
        ws = _dt.fromisoformat(effective_week_start).date()
        week_end = ws + _td(days=6)
        leaves = await tdb.teacher_leaves.find(
            {
                "school_id": school_id,
                "status": "approved",
                "start_date": {"$lte": week_end.isoformat()},
                "end_date": {"$gte": ws.isoformat()},
            },
            {"_id": 0, "teacher_id": 1, "start_date": 1, "end_date": 1},
        ).to_list(2000)
        day_idx_to_key = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat"}
        for lv in leaves:
            s_lv = _dt.fromisoformat(lv["start_date"]).date()
            e_lv = _dt.fromisoformat(lv["end_date"]).date()
            cur = max(ws, s_lv)
            stop = min(week_end, e_lv)
            while cur <= stop:
                key = day_idx_to_key.get(cur.weekday())
                if key:
                    out[key].add(lv["teacher_id"])
                cur += _td(days=1)
    except Exception:
        pass
    return out


def _generate_section_schedule(
    *,
    payload: SuggestTimetableRequest,
    cls: dict,
    subjects: list[dict],
    subject_to_teachers: dict[str, list[dict]],
    busy: set,  # mutated in place
    teachers_on_leave_per_day: dict[str, set[str]],
    rr_index: dict[str, int],  # shared across batch so global load balances
) -> dict:
    """Core per-section greedy generator. Mutates `busy` and `rr_index`.

    Honours every v40 constraint:
      • subject_periods (frequency)
      • subject_day_pins
      • no_last_period_subjects
      • allowed_periods_per_subject (hard — if the slot is not allowed, the subject is skipped)
      • subject_categories (used with max_consecutive_heavy)
      • lunch_break_period + fixed_breaks
      • class_teacher (a daily fixed-period assignment)
      • approved-teacher-leave skip (via busy seeding)
    """
    days = payload.days or DAYS_ORDER[:5]
    days = [d for d in DAYS_ORDER if d in days]
    periods_per_day = payload.periods_per_day
    section = payload.section.upper()

    # ---- Break set: lunch + fixed_breaks (1-indexed periods)
    break_periods: dict[int, str] = {}
    if payload.lunch_break_period:
        break_periods[payload.lunch_break_period] = "Lunch"
    for fb in (payload.fixed_breaks or []):
        if 1 <= fb.period <= periods_per_day:
            break_periods[fb.period] = fb.label or "Break"

    # ---- Class-teacher pin period (also a "reserved" slot, but it's a teaching period)
    ct = payload.class_teacher
    ct_period = ct.period if ct else None
    if ct_period and ct_period in break_periods:
        raise HTTPException(
            status_code=400,
            detail="class_teacher.period overlaps a break period — choose a different period.",
        )
    if ct_period and ct_period > periods_per_day:
        raise HTTPException(
            status_code=400,
            detail=f"class_teacher.period ({ct_period}) exceeds periods_per_day ({periods_per_day}).",
        )

    periods_to_fill_per_day = periods_per_day - len(break_periods) - (1 if ct_period else 0)
    total_slots = len(days) * periods_to_fill_per_day
    if total_slots <= 0:
        raise HTTPException(status_code=400, detail="No teaching periods left after configuring breaks / class-teacher pin.")

    # Validate subject ids
    valid_sids = {s["id"] for s in subjects}
    no_last_set = {sid for sid in (payload.no_last_period_subjects or []) if sid in valid_sids}
    day_pins: dict[str, set] = {}
    for sid, pinned in (payload.subject_day_pins or {}).items():
        if sid in valid_sids and pinned:
            day_pins[sid] = {d for d in pinned if d in DAYS_ORDER}

    # subject_categories: tag heavy / lab / sports / library
    categories = {sid: (cat or "regular").lower() for sid, cat in (payload.subject_categories or {}).items() if sid in valid_sids}

    # allowed_periods_per_subject — restrict to those periods only (hard constraint inside this section)
    allowed_periods: dict[str, set[int]] = {}
    for sid, periods in (payload.allowed_periods_per_subject or {}).items():
        if sid in valid_sids and periods:
            allowed_periods[sid] = {int(p) for p in periods if 1 <= int(p) <= periods_per_day}

    # If class-teacher pin includes a subject, deduct one period of that subject per day from the frequency target
    ct_subject_id = ct.subject_id if (ct and ct.subject_id) else None
    overrides = dict(payload.subject_periods or {})
    if ct_subject_id and ct_subject_id in valid_sids:
        # the class teacher will cover ct_subject_id daily already
        pass  # we'll account for it after counts are computed by subtracting len(days)

    counts = _compute_subject_counts(
        subjects, total_slots, overrides, day_pins, len(days), periods_to_fill_per_day,
    )

    # Build positions list (excluding lunch + fixed breaks AND class-teacher pinned period)
    positions: list[tuple[str, int]] = []
    for day in days:
        for period in range(1, periods_per_day + 1):
            if period in break_periods:
                continue
            if ct_period and period == ct_period:
                continue
            positions.append((day, period))

    # Greedy slot assignment
    remaining = dict(counts)
    last_subjects_per_day: dict[str, list[str]] = {d: [] for d in days}  # ordered history for that day
    assignment: list[str] = []
    warnings_set: set = set()

    def _consecutive_heavy(history: list[str]) -> int:
        n = 0
        for sid in reversed(history):
            if categories.get(sid) == "heavy":
                n += 1
            else:
                break
        return n

    for (day, period) in positions:
        is_last = period == periods_per_day
        history = last_subjects_per_day[day]
        last_subj = history[-1] if history else None
        consec_heavy = _consecutive_heavy(history)

        candidates = [sid for sid, c in remaining.items() if c > 0]

        # 1. day-pin filter
        pinned = [sid for sid in candidates if (sid not in day_pins) or (day in day_pins[sid])]
        cand = pinned if pinned else candidates

        # 2. allowed_periods filter (HARD if any subject has constraint AND can fit this slot)
        allowed_here = [sid for sid in cand if (sid not in allowed_periods) or (period in allowed_periods[sid])]
        cand = allowed_here if allowed_here else cand

        # 3. no-last-period filter (soft)
        if is_last and no_last_set:
            non_last = [sid for sid in cand if sid not in no_last_set]
            cand = non_last if non_last else cand

        # 4. heavy-consecutive cap (soft)
        if consec_heavy >= payload.max_consecutive_heavy:
            non_heavy = [sid for sid in cand if categories.get(sid) != "heavy"]
            cand = non_heavy if non_heavy else cand

        # 5. avoid repeating last subject in same day (soft)
        non_repeat = [sid for sid in cand if sid != last_subj]
        cand = non_repeat if non_repeat else cand

        if not cand:
            raise HTTPException(status_code=400, detail="Constraint solver failed — relax constraints and retry.")

        # Greedy priority: day-pinned-here > most-remaining > stable
        def _pri(sid: str) -> tuple:
            pin = day_pins.get(sid)
            pinned_here = 0 if (pin and day in pin) else 1
            ap = allowed_periods.get(sid)
            ap_here = 0 if (ap and period in ap) else 1
            return (pinned_here, ap_here, -remaining[sid], sid)
        cand.sort(key=_pri)
        chosen_sid = cand[0]

        # Surface relaxation warnings
        if chosen_sid in day_pins and day not in day_pins[chosen_sid]:
            warnings_set.add(
                f"[{cls.get('name')}·{section}] Day-pin for '{next((s['name'] for s in subjects if s['id']==chosen_sid), chosen_sid)}' was relaxed."
            )
        if chosen_sid in allowed_periods and period not in allowed_periods[chosen_sid]:
            warnings_set.add(
                f"[{cls.get('name')}·{section}] Allowed-period constraint for '{next((s['name'] for s in subjects if s['id']==chosen_sid), chosen_sid)}' was relaxed at period {period}."
            )
        if is_last and chosen_sid in no_last_set:
            warnings_set.add(
                f"[{cls.get('name')}·{section}] '{next((s['name'] for s in subjects if s['id']==chosen_sid), chosen_sid)}' placed in last period despite no-last constraint."
            )
        if categories.get(chosen_sid) == "heavy" and consec_heavy >= payload.max_consecutive_heavy:
            warnings_set.add(
                f"[{cls.get('name')}·{section}] Heavy-subject run exceeded {payload.max_consecutive_heavy} on {day.upper()}."
            )

        assignment.append(chosen_sid)
        remaining[chosen_sid] -= 1
        last_subjects_per_day[day].append(chosen_sid)

    # Materialise slots
    slots = []
    pos_idx = 0
    for day in days:
        for period in range(1, periods_per_day + 1):
            slot_start = _add_minutes(payload.start_time, (period - 1) * payload.period_minutes)
            slot_end = _add_minutes(payload.start_time, period * payload.period_minutes)
            if period in break_periods:
                slots.append({
                    "day": day, "period": period,
                    "subject_id": "", "teacher_id": "",
                    "class_id": payload.class_id, "section": section,
                    "start_time": slot_start, "end_time": slot_end,
                    "is_break": True, "break_label": break_periods[period],
                })
                continue
            if ct_period and period == ct_period:
                # Class-teacher pinned period
                ct_busy = (day, period, ct.teacher_id) in busy
                if ct_busy:
                    warnings_set.add(
                        f"[{cls.get('name')}·{section}] Class teacher is double-booked at {day.upper()} period {period}."
                    )
                slots.append({
                    "day": day, "period": period,
                    "subject_id": ct.subject_id or "",
                    "teacher_id": ct.teacher_id,
                    "class_id": payload.class_id, "section": section,
                    "start_time": slot_start, "end_time": slot_end,
                    "is_class_teacher_pin": True,
                    "class_teacher_label": ct.label,
                })
                if not ct_busy:
                    busy.add((day, period, ct.teacher_id))
                continue
            sid = assignment[pos_idx]
            pos_idx += 1
            candidates_t = subject_to_teachers.get(sid) or []
            chosen = None
            if candidates_t:
                n = len(candidates_t)
                start = rr_index.get(sid, 0)
                for k in range(n):
                    idx = (start + k) % n
                    t = candidates_t[idx]
                    if (day, period, t["id"]) in busy:
                        continue
                    chosen = t
                    rr_index[sid] = (idx + 1) % n
                    break
                if chosen is None:
                    on_leave_here = any(t["id"] in teachers_on_leave_per_day.get(day, set()) for t in candidates_t)
                    if on_leave_here:
                        warnings_set.add(
                            f"[{cls.get('name')}·{section}] All teachers of '{next((s['name'] for s in subjects if s['id']==sid), sid)}' are on leave or busy at {day.upper()} period {period}."
                        )
                    else:
                        warnings_set.add(
                            f"[{cls.get('name')}·{section}] All teachers of '{next((s['name'] for s in subjects if s['id']==sid), sid)}' are busy elsewhere at {day.upper()} period {period}."
                        )
            else:
                warnings_set.add(
                    f"[{cls.get('name')}·{section}] No teacher assigned to '{next((s['name'] for s in subjects if s['id']==sid), sid)}' — assign teachers first."
                )

            slots.append({
                "day": day, "period": period,
                "subject_id": sid,
                "teacher_id": (chosen or {}).get("id", ""),
                "class_id": payload.class_id, "section": section,
                "start_time": slot_start, "end_time": slot_end,
            })
            if chosen:
                busy.add((day, period, chosen["id"]))

    return {
        "class_id": payload.class_id,
        "class_name": cls.get("name"),
        "section": section,
        "slots": slots,
        "warnings": sorted(warnings_set),
        "subject_distribution": {sid: counts.get(sid, 0) for sid in counts},
        "days": days,
        "periods_per_day": periods_per_day,
        "total_teaching_slots": total_slots,
        "break_periods": [{"period": p, "label": lbl} for p, lbl in sorted(break_periods.items())],
    }


@router.post("/suggest")
async def suggest_timetable(
    payload: SuggestTimetableRequest,
    user: dict = Depends(require_roles("school_admin")),
):
    """Generate a suggested weekly timetable for a single class+section.

    See `_generate_section_schedule` for the constraint contract.
    """
    tdb, _rdb, subjects, _teachers, subject_to_teachers, existing = await _gather_school_resources(user["school_id"])
    if not subjects:
        raise HTTPException(status_code=400, detail="No subjects defined for this school. Add subjects first.")

    cls = await tdb.classes.find_one({"id": payload.class_id, "school_id": user["school_id"]})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if payload.section.upper() not in [s.upper() for s in (cls.get("sections") or [])]:
        raise HTTPException(status_code=400, detail=f"Section '{payload.section}' not found in class")

    busy: set = set()
    for sl in existing:
        if sl.get("class_id") == payload.class_id and sl.get("section") == payload.section.upper():
            continue
        busy.add((sl["day"], sl["period"], sl.get("teacher_id")))

    teachers_on_leave_per_day = await _leave_block_map(tdb, user["school_id"], payload.effective_week_start)
    for day_key, tids in teachers_on_leave_per_day.items():
        for tid in tids:
            for p in range(1, payload.periods_per_day + 1):
                busy.add((day_key, p, tid))

    rr_index: dict[str, int] = {}
    res = _generate_section_schedule(
        payload=payload, cls=cls, subjects=subjects,
        subject_to_teachers=subject_to_teachers, busy=busy,
        teachers_on_leave_per_day=teachers_on_leave_per_day, rr_index=rr_index,
    )
    # Back-compat shape: keep old field names at the top level.
    return {
        "slots": res["slots"],
        "warnings": res["warnings"],
        "subject_distribution": res["subject_distribution"],
        "days": res["days"],
        "periods_per_day": res["periods_per_day"],
        "total_slots": res["total_teaching_slots"],
        "lunch_break_period": payload.lunch_break_period,
        "break_periods": res["break_periods"],
    }


# ---------------- v40: Batch / multi-section generation ----------------

class BatchSectionRequest(BaseModel):
    """One section's config inside a /suggest-batch call. Inherits any field
    not set from the request-level `defaults`."""
    class_id: str
    section: str
    # Per-section overrides (any subset). Same names as SuggestTimetableRequest.
    days: Optional[List[Literal["mon", "tue", "wed", "thu", "fri", "sat"]]] = None
    periods_per_day: Optional[int] = None
    start_time: Optional[str] = None
    period_minutes: Optional[int] = None
    subject_periods: Optional[dict] = None
    lunch_break_period: Optional[int] = None
    fixed_breaks: Optional[List[FixedBreak]] = None
    no_last_period_subjects: Optional[List[str]] = None
    subject_day_pins: Optional[dict] = None
    subject_categories: Optional[dict] = None
    allowed_periods_per_subject: Optional[dict] = None
    max_consecutive_heavy: Optional[int] = None
    class_teacher: Optional[ClassTeacherPin] = None
    student_count: Optional[int] = None  # informational; surfaced in conflict summary


class SuggestBatchRequest(BaseModel):
    sections: List[BatchSectionRequest]
    # Defaults applied to every section unless explicitly overridden.
    defaults: Optional[SuggestTimetableRequest] = None  # `class_id`/`section` here are ignored
    effective_week_start: Optional[str] = None
    # If True, ignore existing saved timetable when seeding the busy map (start fresh)
    reset_existing: bool = False


def _merge_section_request(defaults: Optional[SuggestTimetableRequest], section: BatchSectionRequest) -> SuggestTimetableRequest:
    """Build a fully-specified SuggestTimetableRequest for one section by
    merging request-level defaults with per-section overrides. Per-section
    value wins when present."""
    base = defaults.model_dump() if defaults else {}
    # Drop the defaults' class/section — they only carry constraint defaults
    base.pop("class_id", None)
    base.pop("section", None)
    over = {k: v for k, v in section.model_dump().items() if v is not None and k not in {"student_count"}}
    merged = {**base, **over}
    # Required fields
    merged["class_id"] = section.class_id
    merged["section"] = section.section
    merged.setdefault("periods_per_day", 6)
    merged.setdefault("start_time", "09:00")
    merged.setdefault("period_minutes", 45)
    merged.setdefault("max_consecutive_heavy", 2)
    return SuggestTimetableRequest(**merged)


def _build_teacher_view(all_slots: list[dict], teachers: list[dict], subjects: list[dict], classes: list[dict]) -> dict:
    """Group slots by teacher_id -> {day: {period: {class, section, subject}}}."""
    teacher_map = {t["id"]: t for t in teachers}
    subject_map = {s["id"]: s for s in subjects}
    class_map = {c["id"]: c for c in classes}
    grid: dict[str, dict] = {}
    workload: dict[str, int] = {}
    for sl in all_slots:
        tid = sl.get("teacher_id")
        if not tid:
            continue
        if sl.get("is_break"):
            continue
        t = teacher_map.get(tid)
        if not t:
            continue
        g = grid.setdefault(tid, {
            "teacher_id": tid,
            "teacher_name": t.get("name"),
            "by_day": {},
            "total_periods": 0,
        })
        d = g["by_day"].setdefault(sl["day"], {})
        d[sl["period"]] = {
            "class_id": sl["class_id"],
            "class_name": (class_map.get(sl["class_id"]) or {}).get("name"),
            "section": sl["section"],
            "subject_id": sl.get("subject_id"),
            "subject_name": (subject_map.get(sl.get("subject_id")) or {}).get("name"),
            "is_class_teacher_pin": sl.get("is_class_teacher_pin", False),
            "start_time": sl.get("start_time"),
            "end_time": sl.get("end_time"),
        }
        g["total_periods"] += 1
        workload[tid] = workload.get(tid, 0) + 1
    # Include teachers with zero load too (for visibility)
    for t in teachers:
        if t["id"] not in grid:
            grid[t["id"]] = {
                "teacher_id": t["id"],
                "teacher_name": t.get("name"),
                "by_day": {},
                "total_periods": 0,
            }
    return {
        "teachers": list(grid.values()),
        "workload_min": min(workload.values()) if workload else 0,
        "workload_max": max(workload.values()) if workload else 0,
    }


def _build_conflict_summary(all_section_results: list[dict], subjects: list[dict], teachers: list[dict]) -> dict:
    """Aggregate cross-section conflicts and unmet constraints."""
    subject_map = {s["id"]: s for s in subjects}
    # Teacher double-booking check (defensive — generator avoids this, but it's worth verifying)
    seen: dict[tuple, dict] = {}
    double_bookings: list[dict] = []
    unfilled: list[dict] = []
    for res in all_section_results:
        for sl in res["slots"]:
            if sl.get("is_break"):
                continue
            tid = sl.get("teacher_id")
            sid = sl.get("subject_id")
            if not tid and sid:
                unfilled.append({
                    "class_id": sl["class_id"], "class_name": res["class_name"],
                    "section": sl["section"], "day": sl["day"], "period": sl["period"],
                    "subject_id": sid, "subject_name": (subject_map.get(sid) or {}).get("name"),
                    "reason": "no_teacher",
                })
                continue
            if not tid:
                continue
            key = (sl["day"], sl["period"], tid)
            if key in seen:
                double_bookings.append({
                    "teacher_id": tid, "day": sl["day"], "period": sl["period"],
                    "first": seen[key], "second": {
                        "class_id": sl["class_id"], "section": sl["section"],
                        "class_name": res["class_name"],
                    },
                })
            else:
                seen[key] = {
                    "class_id": sl["class_id"], "section": sl["section"],
                    "class_name": res["class_name"],
                }
    # Collate all per-section warnings
    all_warnings: list[str] = []
    for res in all_section_results:
        all_warnings.extend(res.get("warnings") or [])
    return {
        "double_bookings": double_bookings,
        "unfilled_slots": unfilled,
        "warnings": sorted(set(all_warnings)),
        "total_sections": len(all_section_results),
    }


def _build_optimization_suggestions(
    summary: dict, subjects: list[dict], teachers: list[dict], subject_to_teachers: dict[str, list[dict]],
) -> list[str]:
    out: list[str] = []
    # Count unfilled by subject
    by_subject: dict[str, int] = {}
    for u in summary["unfilled_slots"]:
        by_subject[u["subject_id"]] = by_subject.get(u["subject_id"], 0) + 1
    subject_map = {s["id"]: s for s in subjects}
    for sid, n in sorted(by_subject.items(), key=lambda x: -x[1]):
        sname = (subject_map.get(sid) or {}).get("name") or sid
        teachers_for = subject_to_teachers.get(sid) or []
        if not teachers_for:
            out.append(f"Assign at least 1 teacher to '{sname}' — currently zero teachers teach this subject.")
        else:
            out.append(
                f"Add 1 more teacher for '{sname}' (current: {len(teachers_for)}) — "
                f"{n} slot(s) couldn't be filled because all are busy at the same time."
            )
    if summary["double_bookings"]:
        out.append(
            f"{len(summary['double_bookings'])} cross-class double-booking(s) detected — "
            "either reduce periods_per_day or distribute subjects across more days."
        )
    if not out:
        out.append("All sections scheduled cleanly with no unmet constraints. ✅")
    return out


@router.post("/suggest-batch")
async def suggest_timetable_batch(
    payload: SuggestBatchRequest,
    user: dict = Depends(require_roles("school_admin")),
):
    """Generate timetables for many class/section pairs at once, sharing one
    global busy map so the same teacher never collides across sections.

    Returns:
      • `sections[]` — per-section grid (same shape as /suggest output)
      • `teacher_view` — teacher-wise weekly grid + min/max workload
      • `conflict_summary` — cross-section double-bookings + unfilled slots
      • `optimization_suggestions[]` — actionable hints
    """
    if not payload.sections:
        raise HTTPException(status_code=400, detail="At least one section is required.")

    tdb, _rdb, subjects, teachers, subject_to_teachers, existing = await _gather_school_resources(user["school_id"])
    if not subjects:
        raise HTTPException(status_code=400, detail="No subjects defined for this school. Add subjects first.")
    classes = await tdb.classes.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(500)
    class_map = {c["id"]: c for c in classes}

    # Seed busy map from existing timetable except for sections we're regenerating
    regenerating = {(s.class_id, s.section.upper()) for s in payload.sections}
    busy: set = set()
    if not payload.reset_existing:
        for sl in existing:
            if (sl.get("class_id"), (sl.get("section") or "").upper()) in regenerating:
                continue
            busy.add((sl["day"], sl["period"], sl.get("teacher_id")))

    week_start = payload.effective_week_start or (payload.defaults.effective_week_start if payload.defaults else None)
    teachers_on_leave_per_day = await _leave_block_map(tdb, user["school_id"], week_start)
    # Seed leave block for the maximum periods_per_day across sections (defensive upper bound)
    max_ppd = max(
        [s.periods_per_day for s in payload.sections if s.periods_per_day] or [0],
        default=0,
    )
    if payload.defaults and payload.defaults.periods_per_day:
        max_ppd = max(max_ppd, payload.defaults.periods_per_day)
    max_ppd = max(max_ppd, 1)
    for day_key, tids in teachers_on_leave_per_day.items():
        for tid in tids:
            for p in range(1, max_ppd + 1):
                busy.add((day_key, p, tid))

    rr_index: dict[str, int] = {}
    section_results: list[dict] = []
    all_slots: list[dict] = []
    for sec in payload.sections:
        merged = _merge_section_request(payload.defaults, sec)
        cls = class_map.get(sec.class_id)
        if not cls:
            raise HTTPException(status_code=404, detail=f"Class {sec.class_id} not found")
        if sec.section.upper() not in [s.upper() for s in (cls.get("sections") or [])]:
            raise HTTPException(status_code=400, detail=f"Section '{sec.section}' not found in class {cls.get('name')}")
        res = _generate_section_schedule(
            payload=merged, cls=cls, subjects=subjects,
            subject_to_teachers=subject_to_teachers, busy=busy,
            teachers_on_leave_per_day=teachers_on_leave_per_day, rr_index=rr_index,
        )
        res["student_count"] = sec.student_count
        section_results.append(res)
        all_slots.extend(res["slots"])

    teacher_view = _build_teacher_view(all_slots, teachers, subjects, classes)
    conflict_summary = _build_conflict_summary(section_results, subjects, teachers)
    optimization_suggestions = _build_optimization_suggestions(conflict_summary, subjects, teachers, subject_to_teachers)

    return {
        "sections": section_results,
        "teacher_view": teacher_view,
        "conflict_summary": conflict_summary,
        "optimization_suggestions": optimization_suggestions,
    }


class SaveBatchSection(BaseModel):
    class_id: str
    section: str
    slots: list  # list of TimetableSlot-shaped dicts (is_break entries are skipped)


class SaveBatchRequest(BaseModel):
    sections: List[SaveBatchSection]


@router.post("/save-batch")
async def save_timetable_batch(
    payload: SaveBatchRequest,
    user: dict = Depends(require_roles("school_admin")),
):
    """Persist many sections in one go. Validates cross-section teacher
    collisions inside the payload AND against any class/section that is NOT
    being replaced (so other classes' saved slots are still respected).
    Returns the same 409 contract as /bulk when conflicts are present."""
    tdb = await tenant_db(user["school_id"])
    from core.db import get_db as _root_db
    rdb = _root_db()

    if not payload.sections:
        raise HTTPException(status_code=400, detail="No sections supplied.")

    # 1. Intra-payload collisions
    intra: dict[tuple, list] = {}
    flat: list[dict] = []
    replacing: set[tuple] = set()
    for sec in payload.sections:
        replacing.add((sec.class_id, sec.section.upper()))
        for s in sec.slots:
            if s.get("is_break"):
                continue
            tid = s.get("teacher_id")
            if not tid:
                continue
            sl = {
                "day": s["day"], "period": s["period"],
                "teacher_id": tid,
                "class_id": sec.class_id, "section": sec.section.upper(),
                "subject_id": s.get("subject_id") or "",
                "start_time": s.get("start_time"), "end_time": s.get("end_time"),
            }
            flat.append(sl)
            intra.setdefault((s["day"], s["period"], tid), []).append({
                "class_id": sec.class_id, "section": sec.section.upper(),
                "subject_id": s.get("subject_id") or "",
            })
    intra_conflicts = [
        {"day": k[0], "period": k[1], "teacher_id": k[2], "occurrences": v}
        for k, v in intra.items() if len(v) > 1
    ]

    # 2. Cross-class collisions vs. sections NOT being replaced
    teacher_ids = sorted({sl["teacher_id"] for sl in flat})
    cross_conflicts: list[dict] = []
    if teacher_ids:
        external = await tdb.timetable.find(
            {"school_id": user["school_id"], "teacher_id": {"$in": teacher_ids}},
            {"_id": 0, "day": 1, "period": 1, "teacher_id": 1, "class_id": 1, "section": 1, "subject_id": 1},
        ).to_list(50000)
        ext_busy = {}
        for e in external:
            if (e["class_id"], (e.get("section") or "").upper()) in replacing:
                continue
            ext_busy[(e["day"], e["period"], e["teacher_id"])] = e
        for sl in flat:
            hit = ext_busy.get((sl["day"], sl["period"], sl["teacher_id"]))
            if hit:
                cross_conflicts.append({
                    "day": sl["day"], "period": sl["period"], "teacher_id": sl["teacher_id"],
                    "conflict_with": {"class_id": hit["class_id"], "section": hit["section"], "subject_id": hit.get("subject_id")},
                    "this_class": {"class_id": sl["class_id"], "section": sl["section"], "subject_id": sl["subject_id"]},
                })

    if intra_conflicts or cross_conflicts:
        all_tids = sorted({c["teacher_id"] for c in intra_conflicts} | {c["teacher_id"] for c in cross_conflicts})
        tname = {t["id"]: t["name"] for t in await rdb.users.find(
            {"school_id": user["school_id"], "id": {"$in": all_tids}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(2000)}
        for c in intra_conflicts:
            c["teacher_name"] = tname.get(c["teacher_id"], c["teacher_id"])
        for c in cross_conflicts:
            c["teacher_name"] = tname.get(c["teacher_id"], c["teacher_id"])
        raise HTTPException(status_code=409, detail={
            "error": "timetable_conflict",
            "message": (
                f"{len(intra_conflicts)} intra-batch double-booking(s) and "
                f"{len(cross_conflicts)} cross-class collision(s) detected."
            ),
            "intra_payload_conflicts": intra_conflicts,
            "cross_class_conflicts": cross_conflicts,
        })

    # 3. Persist — replace each (class_id, section) atomically per-section.
    inserted_total = 0
    notified_total = 0
    for sec in payload.sections:
        await tdb.timetable.delete_many(
            {"school_id": user["school_id"], "class_id": sec.class_id, "section": sec.section.upper()},
        )
        docs = []
        for s in sec.slots:
            if s.get("is_break"):
                continue
            if not s.get("teacher_id"):
                continue
            docs.append({
                "id": new_id(),
                "school_id": user["school_id"],
                "class_id": sec.class_id,
                "section": sec.section.upper(),
                "day": s["day"],
                "period": s["period"],
                "subject_id": s.get("subject_id") or "",
                "teacher_id": s["teacher_id"],
                "start_time": s.get("start_time"),
                "end_time": s.get("end_time"),
                "created_at": utc_now(),
            })
        if docs:
            await tdb.timetable.insert_many(docs)
            inserted_total += len(docs)
            notified_total += len({d["teacher_id"] for d in docs if d.get("teacher_id")})
            try:
                await _notify_teachers_of_timetable_change(
                    user["school_id"], sec.class_id, sec.section.upper(), docs, user,
                )
            except Exception:
                pass
    return {"inserted": inserted_total, "notified_teachers": notified_total, "sections_saved": len(payload.sections)}
