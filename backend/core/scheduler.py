"""In-process APScheduler for monthly digest cron.
Gated by env var ENABLE_DIGEST_SCHEDULER=true. Times in IST.
"""
import os
import logging
from datetime import date

log = logging.getLogger("scms.scheduler")

_scheduler = None


def is_enabled() -> bool:
    return os.environ.get("ENABLE_DIGEST_SCHEDULER", "").strip().lower() in ("1", "true", "yes")


async def _run_digest_for_all_schools():
    from core.db import get_db
    from routes.digests import _previous_month_range, _compute_digest, _compose_message
    from core.notify import queue_notification
    from core.audit import log_action

    db = get_db()
    label, start_iso, end_iso = _previous_month_range()
    schools = await db.schools.find({"is_active": True}, {"_id": 0}).to_list(500)
    total = 0
    for school in schools:
        students = await db.students.find({"school_id": school["id"], "status": "active"}, {"_id": 0}).to_list(5000)
        for s in students:
            digest = await _compute_digest(db, school, s, start_iso, end_iso)
            msg = _compose_message(school, s, label, digest)
            phone = (s.get("parent", {}) or {}).get("whatsapp") or (s.get("parent", {}) or {}).get("phone")
            await queue_notification(
                school["id"], "parent", s.get("parent_user_id"), phone,
                "whatsapp", "monthly_digest", msg,
                context={"student_id": s["id"], "period": label, "source": "scheduler"},
            )
            total += 1
        await log_action("system", "platform_admin", school["id"], "run_monthly_digest", "digest",
                         meta={"period": label, "students": len(students), "source": "scheduler"})
    log.info("[scheduler] Monthly digest run for %d students across %d schools", total, len(schools))


def start():
    global _scheduler
    if _scheduler is not None or not is_enabled():
        return
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        log.warning("APScheduler not installed; scheduler disabled")
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    # 1st of each month at 09:00 IST
    _scheduler.add_job(_run_digest_for_all_schools, CronTrigger(day=1, hour=9, minute=0), id="monthly_digest")
    _scheduler.start()
    log.info("[scheduler] Started — monthly digest on 1st @ 09:00 IST")


def shutdown():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
