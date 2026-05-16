"""Teacher timetable + calendar."""
from fastapi import APIRouter, Depends, HTTPException
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
