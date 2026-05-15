"""SCMS — School Child Monitoring System
FastAPI main entrypoint.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

from core.db import get_db, ensure_indexes
from core.auth import hash_password, verify_password
from core.utils import new_id, utc_now

from routes.auth import router as auth_router
from routes.schools import router as schools_router
from routes.users import router as users_router
from routes.academic import router as academic_router
from routes.students import router as students_router
from routes.attendance import router as attendance_router
from routes.marks import router as marks_router
from routes.holidays import router as holidays_router
from routes.fees import router as fees_router
from routes.timetable import router as timetable_router
from routes.notifications import router as notifications_router
from routes.analytics import router as analytics_router
from routes.uploads import router as uploads_router


async def seed_platform_admin():
    db = get_db()
    email = os.environ.get("ADMIN_EMAIL", "platform@scms.com").lower()
    password = os.environ.get("ADMIN_PASSWORD", "Platform@123")
    existing = await db.users.find_one({"email": email})
    if not existing:
        await db.users.insert_one({
            "id": new_id(),
            "email": email,
            "password_hash": hash_password(password),
            "name": "Platform Super Admin",
            "role": "platform_admin",
            "school_id": None,
            "is_active": True,
            "created_at": utc_now(),
        })
        print(f"[seed] Platform admin created: {email}")
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_password(password)}})
        print(f"[seed] Platform admin password refreshed: {email}")


async def seed_demo_data():
    """Seed a demo school with admin, teachers, accounts, parents, students, classes,
    subjects, attendance, marks, fees, exam, holidays — for instant demo experience."""
    db = get_db()
    if await db.schools.find_one({"code": "DEMO"}):
        return  # already seeded

    school_id = new_id()
    await db.schools.insert_one({
        "id": school_id,
        "name": "Sunrise Public School",
        "code": "DEMO",
        "address": "12 Maple Avenue, Bengaluru",
        "phone": "+91-80-4444-1111",
        "email": "info@sunrise.edu",
        "academic_year": "2025-2026",
        "is_active": True,
        "created_at": utc_now(),
    })

    pw = hash_password
    # school admin
    sadmin = {"id": new_id(), "email": "principal@sunrise.edu", "password_hash": pw("School@123"),
              "name": "Anjali Mehta", "role": "school_admin", "school_id": school_id,
              "phone": "+91-9999900001", "is_active": True, "created_at": utc_now()}
    await db.users.insert_one(sadmin)

    # accounts
    acc = {"id": new_id(), "email": "accounts@sunrise.edu", "password_hash": pw("Accounts@123"),
           "name": "Sneha Iyer", "role": "accounts", "school_id": school_id,
           "phone": "+91-9999900002", "is_active": True, "created_at": utc_now()}
    await db.users.insert_one(acc)

    # teachers
    teachers = []
    for n, name in enumerate([
        ("priya@sunrise.edu", "Priya Verma"),
        ("rohit@sunrise.edu", "Rohit Khanna"),
        ("kavita@sunrise.edu", "Kavita Singh"),
    ], start=1):
        t = {"id": new_id(), "email": name[0], "password_hash": pw("Teacher@123"),
             "name": name[1], "role": "teacher", "school_id": school_id,
             "employee_id": f"EMP-{n:03d}", "qualifications": "M.Sc., B.Ed.",
             "phone": f"+91-99999100{n:02d}", "is_active": True,
             "joining_date": "2022-06-01", "subjects": [], "created_at": utc_now()}
        await db.users.insert_one(t)
        teachers.append(t)

    # classes & subjects
    class_docs = []
    for grade in ["Grade 5", "Grade 6"]:
        c = {"id": new_id(), "school_id": school_id, "name": grade, "sections": ["A", "B"], "created_at": utc_now()}
        await db.classes.insert_one(c)
        class_docs.append(c)

    subject_docs = []
    for sname in ["Mathematics", "Science", "English", "Social Studies", "Hindi"]:
        sub = {"id": new_id(), "school_id": school_id, "name": sname, "code": sname[:3].upper(), "created_at": utc_now()}
        await db.subjects.insert_one(sub)
        subject_docs.append(sub)

    # update teacher subjects
    await db.users.update_one({"id": teachers[0]["id"]}, {"$set": {"subjects": [subject_docs[0]["id"], subject_docs[1]["id"]]}})
    await db.users.update_one({"id": teachers[1]["id"]}, {"$set": {"subjects": [subject_docs[2]["id"]]}})
    await db.users.update_one({"id": teachers[2]["id"]}, {"$set": {"subjects": [subject_docs[3]["id"], subject_docs[4]["id"]]}})

    # class teacher mapping
    await db.class_teacher_map.insert_one({"id": new_id(), "school_id": school_id,
                                            "class_id": class_docs[0]["id"], "section": "A",
                                            "teacher_id": teachers[0]["id"], "created_at": utc_now()})
    await db.class_teacher_map.insert_one({"id": new_id(), "school_id": school_id,
                                            "class_id": class_docs[1]["id"], "section": "A",
                                            "teacher_id": teachers[1]["id"], "created_at": utc_now()})

    # timetable for grade 5 A
    days = ["mon", "tue", "wed", "thu", "fri"]
    slots = []
    for di, day in enumerate(days):
        for p in range(1, 5):
            subj = subject_docs[(di + p) % len(subject_docs)]
            teacher = teachers[(di + p) % len(teachers)]
            slots.append({
                "id": new_id(), "school_id": school_id,
                "class_id": class_docs[0]["id"], "section": "A",
                "day": day, "period": p,
                "subject_id": subj["id"], "teacher_id": teacher["id"],
                "start_time": f"{8 + p}:00", "end_time": f"{8 + p}:45",
                "created_at": utc_now(),
            })
    await db.timetable.insert_many(slots)

    # students (8 in Grade 5 A)
    students = []
    student_names = [
        ("Aarav Sharma", "M", "+91-9000000001", "Rakesh Sharma"),
        ("Ananya Reddy", "F", "+91-9000000002", "Suresh Reddy"),
        ("Vihaan Patel", "M", "+91-9000000003", "Kiran Patel"),
        ("Ishaan Kapoor", "M", "+91-9000000004", "Manish Kapoor"),
        ("Saanvi Iyer", "F", "+91-9000000005", "Lakshmi Iyer"),
        ("Arjun Nair", "M", "+91-9000000006", "Suresh Nair"),
        ("Diya Joshi", "F", "+91-9000000007", "Rekha Joshi"),
        ("Kabir Singh", "M", "+91-9000000008", "Harpreet Singh"),
    ]
    for i, (name, gender, phone, parent_name) in enumerate(student_names, start=1):
        uid = f"STU-{i:05d}"
        pid = new_id()
        parent_email = f"parent.{uid.lower()}@sunrise.edu"
        await db.users.insert_one({
            "id": pid, "email": parent_email, "password_hash": pw("Parent@123"),
            "name": parent_name, "role": "parent", "school_id": school_id,
            "phone": phone, "is_active": True, "created_at": utc_now(),
        })
        s = {
            "id": new_id(), "school_id": school_id, "student_uid": uid,
            "name": name, "class_id": class_docs[0]["id"], "section": "A",
            "roll_number": str(i), "gender": gender,
            "dob": "2014-04-10",
            "admission_date": "2020-06-01",
            "parent": {"name": parent_name, "relationship": "father", "phone": phone, "whatsapp": phone, "email": parent_email},
            "parent_user_id": pid,
            "status": "active", "created_at": utc_now(),
        }
        await db.students.insert_one(s)
        students.append(s)

    # attendance for last 20 days
    from datetime import date, timedelta
    import random
    random.seed(7)
    today = date.today()
    statuses = ["present"] * 8 + ["absent", "sick"]
    for d in range(20):
        day = today - timedelta(days=d)
        if day.weekday() >= 5:
            continue
        for s in students:
            st = random.choice(statuses)
            await db.attendance.insert_one({
                "id": new_id(), "school_id": school_id, "student_id": s["id"],
                "class_id": s["class_id"], "section": s["section"],
                "date": day.isoformat(), "status": st,
                "marked_by": teachers[0]["id"], "marked_at": utc_now(),
            })

    # exam + marks
    exam = {
        "id": new_id(), "school_id": school_id, "name": "Mid-Term", "term": "Term 1",
        "class_id": class_docs[0]["id"], "section": "A",
        "start_date": (today - timedelta(days=20)).isoformat(),
        "end_date": (today - timedelta(days=15)).isoformat(),
        "schedule": [
            {"subject_id": s["id"], "date": (today - timedelta(days=20 - i)).isoformat(), "time": "9:00", "duration": 90}
            for i, s in enumerate(subject_docs)
        ],
        "is_published": True, "created_at": utc_now(),
    }
    await db.exams.insert_one(exam)

    exam2 = {
        "id": new_id(), "school_id": school_id, "name": "Unit Test 2", "term": "Term 1",
        "class_id": class_docs[0]["id"], "section": "A",
        "start_date": (today - timedelta(days=5)).isoformat(),
        "end_date": (today - timedelta(days=2)).isoformat(),
        "schedule": [],
        "is_published": True, "created_at": utc_now(),
    }
    await db.exams.insert_one(exam2)

    for s in students:
        for sub in subject_docs:
            for ex in (exam, exam2):
                obtained = random.randint(40, 95)
                await db.marks.insert_one({
                    "id": new_id(), "school_id": school_id,
                    "exam_id": ex["id"], "subject_id": sub["id"], "student_id": s["id"],
                    "marks_obtained": obtained, "max_marks": 100, "percentage": obtained,
                    "entered_by": teachers[0]["id"], "entered_at": utc_now(),
                })

    # fee structure + fees
    fs = {
        "id": new_id(), "school_id": school_id, "class_id": class_docs[0]["id"],
        "name": "Term 1 Fees", "items": [
            {"type": "tuition", "amount": 12000},
            {"type": "transport", "amount": 3000},
            {"type": "activity", "amount": 1000},
        ], "total": 16000, "due_date": (today + timedelta(days=15)).isoformat(),
        "created_at": utc_now(),
    }
    await db.fee_structures.insert_one(fs)

    for i, s in enumerate(students):
        paid = 16000 if i % 3 == 0 else (8000 if i % 3 == 1 else 0)
        await db.fees.insert_one({
            "id": new_id(), "school_id": school_id, "structure_id": fs["id"],
            "student_id": s["id"], "class_id": s["class_id"],
            "name": fs["name"], "total": 16000, "paid": paid,
            "due": 16000 - paid, "due_date": fs["due_date"],
            "status": "paid" if paid == 16000 else ("partial" if paid > 0 else "pending"),
            "created_at": utc_now(),
        })

    # holidays
    for title, d in [("Republic Day", "2025-01-26"), ("Holi", "2025-03-14"), ("Independence Day", "2025-08-15")]:
        await db.holidays.insert_one({
            "id": new_id(), "school_id": school_id, "title": title,
            "date": d, "type": "public", "created_at": utc_now(),
        })

    print(f"[seed] Demo data complete. School: {school_id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_indexes()
        await seed_platform_admin()
        await seed_demo_data()
    except Exception as e:
        print(f"[startup] error: {e}")
    yield


app = FastAPI(title="SCMS API", version="1.0.0", lifespan=lifespan)

# CORS
cors_origins = os.environ.get("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",")] if cors_origins != "*" else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"name": "SCMS API", "status": "ok"}


@api.get("/health")
async def health():
    db = get_db()
    try:
        await db.command("ping")
        return {"status": "ok", "db": "ok"}
    except Exception as e:
        return {"status": "degraded", "db": str(e)}


api.include_router(auth_router)
api.include_router(schools_router)
api.include_router(users_router)
api.include_router(academic_router)
api.include_router(students_router)
api.include_router(attendance_router)
api.include_router(marks_router)
api.include_router(holidays_router)
api.include_router(fees_router)
api.include_router(timetable_router)
api.include_router(notifications_router)
api.include_router(analytics_router)
api.include_router(uploads_router)

app.include_router(api)
