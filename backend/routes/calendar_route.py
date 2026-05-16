"""Calendar feed — holidays + exam schedule events for the month."""
from fastapi import APIRouter, Depends
from core.auth import get_current_user
from core.db import get_db, tenant_db

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events")
async def list_events(month: str | None = None, user: dict = Depends(get_current_user)):
    """Returns list of {type, title, date, end_date?, meta} from holidays + exams + teacher duties."""
    holidays = []
    exams = []
    duties = []
    if user["role"] == "platform_admin" and not user.get("school_id"):
        db = get_db()
        async for s in db.schools.find({}, {"_id": 0, "id": 1}):
            tdb = await tenant_db(s["id"])
            holidays.extend(await tdb.holidays.find({}, {"_id": 0}).to_list(500))
            exams.extend(await tdb.exams.find({}, {"_id": 0}).to_list(500))
    else:
        tdb = await tenant_db(user["school_id"])
        holidays = await tdb.holidays.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(2000)
        exams = await tdb.exams.find({"school_id": user["school_id"]}, {"_id": 0}).to_list(2000)
        # Teacher duties — teachers see only their own; admin/accounts see all
        duty_flt = {"school_id": user["school_id"]}
        if user["role"] == "teacher":
            duty_flt["teacher_id"] = user["id"]
        async for d in tdb.teacher_duties.find(duty_flt, {"_id": 0}):
            duties.append(d)

    events = []
    for h in holidays:
        events.append({
            "type": "holiday",
            "title": h["title"],
            "date": h["date"],
            "end_date": h.get("end_date"),
            "meta": {"holiday_type": h.get("type", "school"), "description": h.get("description")},
            "id": h["id"],
        })
    for e in exams:
        events.append({
            "type": "exam",
            "title": e["name"],
            "date": e["start_date"],
            "end_date": e.get("end_date"),
            "meta": {"term": e.get("term"), "class_id": e.get("class_id"), "is_published": e.get("is_published", False)},
            "id": e["id"],
        })
    for d in duties:
        start = d.get("start_at")
        if hasattr(start, "isoformat"):
            start_iso = start.isoformat()
            date_str = start.date().isoformat() if hasattr(start, "date") else str(start)[:10]
        else:
            start_iso = str(start) if start else None
            date_str = (str(start) if start else "")[:10]
        end = d.get("end_at")
        end_iso = end.isoformat() if hasattr(end, "isoformat") else (str(end) if end else None)
        events.append({
            "type": "duty",
            "title": d.get("title", "Duty"),
            "date": date_str,
            "end_date": (end_iso or "")[:10] if end_iso else None,
            "meta": {
                "duty_type": d.get("type"),
                "location": d.get("location"),
                "notes": d.get("notes"),
                "teacher_id": d.get("teacher_id"),
                "teacher_name": d.get("teacher_name"),
                "start_at": start_iso,
                "end_at": end_iso,
            },
            "id": d["id"],
        })
    if month:
        events = [ev for ev in events if (ev["date"] or "").startswith(month)]
    return events
