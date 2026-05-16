"""Teacher timetable + calendar."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from core.models import TimetableBulk
from core.auth import require_roles, get_current_user
from core.db import get_db, tenant_db
from core.utils import new_id, utc_now

router = APIRouter(prefix="/timetable", tags=["timetable"])


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
    return {"inserted": len(docs)}


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


def _add_minutes(hhmm: str, mins: int) -> str:
    try:
        h, m = [int(x) for x in hhmm.split(":")]
    except Exception:
        h, m = 9, 0
    total = h * 60 + m + mins
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def _balance_subject_periods(subjects: list, total_slots: int, overrides: dict | None):
    """Return list of subject_ids of length total_slots, balanced across subjects.
    overrides: {subject_id: int} — explicit counts; remaining slots split evenly.
    """
    overrides = overrides or {}
    fixed = 0
    counts: dict[str, int] = {}
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
    auto_subjects = [s for s in subjects if s["id"] not in counts]
    if auto_subjects and remaining > 0:
        base = remaining // len(auto_subjects)
        extra = remaining - base * len(auto_subjects)
        for i, s in enumerate(auto_subjects):
            counts[s["id"]] = base + (1 if i < extra else 0)
    elif remaining > 0 and not auto_subjects:
        # Distribute leftover proportionally to existing counts (or to first subject if all zero)
        ordered = list(counts.keys()) or [s["id"] for s in subjects[:1]]
        idx = 0
        while remaining > 0 and ordered:
            counts[ordered[idx % len(ordered)]] = counts.get(ordered[idx % len(ordered)], 0) + 1
            remaining -= 1
            idx += 1
    # Flatten into a multiset queue, interleaved to avoid back-to-back same subject.
    queue: list[str] = []
    pools = [(sid, counts.get(sid, 0)) for sid in counts]
    pools = [p for p in pools if p[1] > 0]
    # Sort by count desc so heaviest subjects spread first
    pools.sort(key=lambda x: -x[1])
    pools_dict = {sid: cnt for sid, cnt in pools}
    while sum(pools_dict.values()) > 0:
        # Round-robin pick the subject with the highest remaining count that wasn't the last one
        last = queue[-1] if queue else None
        candidates = sorted(pools_dict.items(), key=lambda x: -x[1])
        picked = None
        for sid, cnt in candidates:
            if cnt > 0 and sid != last:
                picked = sid
                break
        if picked is None:
            # Forced to repeat last to drain
            for sid, cnt in candidates:
                if cnt > 0:
                    picked = sid
                    break
        if picked is None:
            break
        queue.append(picked)
        pools_dict[picked] -= 1
    return queue, counts


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
    total_slots = len(days) * periods_per_day
    if total_slots == 0:
        raise HTTPException(status_code=400, detail="No days/periods configured")

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

    # Build subject queue
    queue, counts = _balance_subject_periods(subjects, total_slots, payload.subject_periods)
    # Pad if short (shouldn't happen, but safe)
    while len(queue) < total_slots:
        queue.append(subjects[0]["id"])

    # Round-robin teacher index per subject (for load balancing)
    rr_index: dict[str, int] = {sid: 0 for sid in counts}

    slots = []
    warnings_set: set = set()
    pos = 0
    for day in days:
        for period in range(1, periods_per_day + 1):
            sid = queue[pos]
            pos += 1
            candidates = subject_to_teachers.get(sid) or []
            chosen = None
            if candidates:
                # Try candidates in round-robin order, pick first not busy at this (day, period)
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

            slot_start = _add_minutes(payload.start_time, (period - 1) * payload.period_minutes)
            slot_end = _add_minutes(payload.start_time, period * payload.period_minutes)
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
                # Mark teacher busy in our generated grid so we don't double-book within this grid
                busy.add((day, period, chosen["id"]))

    subject_distribution = {sid: counts.get(sid, 0) for sid in counts}
    return {
        "slots": slots,
        "warnings": sorted(warnings_set),
        "subject_distribution": subject_distribution,
        "days": days,
        "periods_per_day": periods_per_day,
        "total_slots": total_slots,
    }
