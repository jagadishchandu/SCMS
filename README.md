# SCMS — School Child Monitoring System

Multi-school management platform with strict role-based access control. Built with **React + FastAPI + MongoDB**.

## Features
- **Roles**: Platform Super Admin, School Super Admin, Teacher (incl. Class Teacher), Accounts, Parent
- **Modules**: Students, Parents, Attendance (with auto WhatsApp-style alerts), Marks & Exams, Syllabus, Holidays, Fees & Payments, Timetable, Teacher Performance scoring (40/30/15/15)
- **Analytics**: Student dashboard with donut/line/bar charts, school KPIs, accounts collection summary
- **Bulk import**: Excel templates and uploads for students, attendance, holidays
- **Strict tenant isolation**: school_id partitioning, teachers cannot view other staff or admin data
- **Notification log**: Every parent message stored (pluggable to Twilio/WhatsApp Business API)

## Run locally with Docker

```bash
docker compose up --build
```

Then visit:
- Frontend: <http://localhost:3000>
- Backend API: <http://localhost:8001/api/health>

## Demo accounts (seeded automatically on first run)

| Role | Email | Password |
| --- | --- | --- |
| Platform Super Admin | `platform@scms.com` | `Platform@123` |
| School Super Admin | `principal@sunrise.edu` | `School@123` |
| Teacher (Class Teacher) | `priya@sunrise.edu` | `Teacher@123` |
| Accounts | `accounts@sunrise.edu` | `Accounts@123` |
| Parent | `parent.stu-00001@sunrise.edu` | `Parent@123` |

## Local development (without Docker)

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn server:app --reload --port 8001

# frontend (new terminal)
cd frontend
yarn install
yarn start
```

## Tech stack
- Frontend: React 18, React Router, Recharts, Tailwind, Phosphor Icons
- Backend: FastAPI, Motor (MongoDB), PyJWT, bcrypt, openpyxl
- Storage: MongoDB
- Containers: Docker + Docker Compose
