"""Calendar feed — holidays + exam schedule events for the month."""
from fastapi import APIRouter, Depends
from core.auth import get_current_user
from core.db import get_db, tenant_db

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events")
async def list_events(month: str | None = None, user: dict = Depends(get_current_user)):
    """Returns list of {type, title, date, end_date?, meta} from holidays + exams."""
    holidays = []
    exams = []
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
    if month:
        events = [ev for ev in events if (ev["date"] or "").startswith(month)]
    return events
