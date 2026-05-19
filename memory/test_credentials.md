# SCMS Test Credentials

Backend: `https://class-access-hub.preview.emergentagent.com/api`

## Platform Super Admin (from backend/.env)
- email: `jagadishchandu789@gmail.com`
- password: `Manasa@123`
- role: `platform_admin`

## DEMO school — seeded automatically on startup

### School Super Admin
- email: `principal@sunrise.edu`
- password: `School@123`

### Accounts
- email: `accounts@sunrise.edu`
- password: `Accounts@123`

### Teachers (Teacher@123 for all)
- `priya@sunrise.edu` (Priya Verma)
- `rohit@sunrise.edu` (Rohit Khanna)
- `kavita@sunrise.edu` (Kavita Singh)

### Parents (Parent@123 for all)
- `parent.stu-00001@sunrise.edu` ... `parent.stu-00008@sunrise.edu`

## Notes (post v1.31)
- **Login IDs are case-insensitive** — `PRINCIPAL@SUNRISE.EDU` works.
- **Login IDs do not require `@`** — short identifiers like `teacher_001` are allowed
  for school_admin/teacher/parent/accounts.
- **Per-school parent-login kill-switch** — Platform admin can disable parent login
  for any specific school from the School Detail drawer in Platform Overview.
  Endpoints:
  - `GET /api/schools/{school_id}/parent-login` -> `{enabled: bool}`
  - `PATCH /api/schools/{school_id}/parent-login` body `{enabled: bool}` (platform_admin only)
