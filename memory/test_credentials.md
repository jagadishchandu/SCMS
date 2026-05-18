# SCMS — Test credentials

Seeded on first backend boot by `seed_demo_data()` in `backend/server.py`.

## Platform Super Admin
- **Email**: `jagadishchandu789@gmail.com`
- **Password**: `Manasa@123`
- Source: `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars (backend/.env, docker-compose).

## Demo school — "Sunrise Public School" (code `DEMO`)
| Role | Email | Password |
|------|-------|----------|
| School Super Admin | `principal@sunrise.edu` | `School@123` |
| Accounts | `accounts@sunrise.edu` | `Accounts@123` |
| Teacher 1 (Grade 5-A class teacher) | `priya@sunrise.edu` | `Teacher@123` |
| Teacher 2 (Grade 6-A class teacher) | `rohit@sunrise.edu` | `Teacher@123` |
| Teacher 3 | `kavita@sunrise.edu` | `Teacher@123` |
| Parent (any of STU-00001..STU-00008) | `parent.stu-00001@sunrise.edu` … `parent.stu-00008@sunrise.edu` | `Parent@123` |

## Login flow
The login page also asks for a **role**. The selected role MUST match the
account's role exactly (no exceptions). Example: for `priya@sunrise.edu`, pick
"Teacher" in the dropdown.

## Chat eligibility (used by new in-app messaging)
- **School admin** can chat with any **teacher** of the same school.
- **Teacher** can chat with **school admins** + **parents** of students whose
  (class_id, section) appears in `class_teacher_map` for that teacher.
- **Parent** can chat with the **class teacher(s)** of their child(ren).

For the seeded DEMO school:
- `priya@sunrise.edu` (class teacher of Grade 5-A) ↔ parents of STU-00001…STU-00008 and `principal@sunrise.edu`.
- `rohit@sunrise.edu` (class teacher of Grade 6-A) ↔ `principal@sunrise.edu` (no students seeded in Grade 6-A).
- `parent.stu-00001@sunrise.edu` ↔ `priya@sunrise.edu` (their class teacher).
