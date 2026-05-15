# SCMS Test Credentials

Login URL: <https://4d977b08-b8f9-4943-a6f8-176d61d36e7e.preview.emergentagent.com/login>

All accounts are seeded automatically on backend startup (idempotent).

| Role | Email | Password | Notes |
| --- | --- | --- | --- |
| Platform Super Admin | `platform@scms.com` | `Platform@123` | Can create schools & school admins |
| School Super Admin | `principal@sunrise.edu` | `School@123` | Full access inside `Sunrise Public School` |
| Teacher (Class Teacher of Grade 5 A) | `priya@sunrise.edu` | `Teacher@123` | Restricted to own classes |
| Teacher | `rohit@sunrise.edu` | `Teacher@123` | Subject teacher |
| Teacher | `kavita@sunrise.edu` | `Teacher@123` | Subject teacher |
| Accounts | `accounts@sunrise.edu` | `Accounts@123` | Fees only |
| Parent of STU-00001 (Aarav Sharma) | `parent.stu-00001@sunrise.edu` | `Parent@123` | Sees only own child |
| Parent of STU-00002 | `parent.stu-00002@sunrise.edu` | `Parent@123` | |

## API endpoints
- `POST /api/auth/login` — `{email, password}` returns user + sets httpOnly `access_token` & `refresh_token` cookies
- `GET /api/auth/me` — current user (requires cookie or `Authorization: Bearer <token>`)
- `POST /api/auth/logout`
- `GET /api/health`

## Seeded demo data (school: Sunrise Public School, code DEMO)
- 2 classes: Grade 5 (sections A, B), Grade 6 (sections A, B)
- 5 subjects: Mathematics, Science, English, Social Studies, Hindi
- 3 teachers, 1 accounts user, 1 school admin
- 8 students in Grade 5 Section A (STU-00001 to STU-00008)
- 20 days of attendance (mostly present, some absent/sick)
- 2 exams (Mid-Term + Unit Test 2) with marks for every subject and student
- Fee structure (Term 1, ₹16,000) with mixed paid/partial/pending statuses
- 3 holidays (Republic Day, Holi, Independence Day)
- Full timetable for Grade 5 Section A (5 days × 4 periods)

## Notable rules
- Teachers cannot list other teachers' details (the `/api/users` endpoint with role=teacher only works for `school_admin`/`platform_admin`; teachers calling `/api/users` get only themselves)
- Teachers cannot see fees (`/api/fees` returns 403 for `teacher`)
- Parents see only their own child via filters by `parent_user_id`
- Cookies are httpOnly + samesite=lax. Frontend uses `withCredentials: true`.
