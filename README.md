# SCMS (School Child Monitoring system)
School Management, Parent Communication, Student Analytics, and Teacher Tracking Platform
1. Product Overview
This product is a multi-school full stack web application for schools to manage students, attendance, sick leaves, holidays, marks, exams, syllabus, fees, teachers, calendars, timetables, and parent communication.
The platform should support:

a default Platform Super Admin to create and manage schools
a School Super Admin for each school
strict role-based access
automatic WhatsApp alerts to parents
student performance dashboards in graphical view
teacher calendars and class timetables
teacher performance tracking based on student outcomes and operational compliance
manual data entry and Excel upload/import


2. Main Goals
The system should help schools:

monitor student attendance
monitor sick leaves and holidays
track marks and academic improvement
identify subjects needing improvement
send timely updates to parents
manage exam schedules and syllabus
manage fee details and payment status
manage teacher schedules and calendars
monitor teacher performance
enforce strict visibility and access control


3. User Roles and Access Control
3.1 Platform Super Admin
This is the default admin of the entire platform.
Responsibilities:

create schools
create School Super Admin accounts
activate/deactivate schools
monitor overall system usage
monitor uploads, errors, and logs
monitor notification delivery
manage subscription/package if needed

Access:

can view all schools
can view all school-level data if required
can manage system-wide settings


3.2 School Super Admin
This should be the highest role inside each school.
Responsibilities:

manage school users
create teacher accounts and other staff users
manage classes, sections, subjects, terms, exams, holidays, fees
upload students, parents, attendance, marks, syllabus, exam schedules
monitor school reports and dashboards
manage teacher assignments and class teacher mappings

Important access rule:

Only the School Super Admin should be able to view full details of teachers and other users within that school.
Teachers should not be able to view teacher details or user-management details.

Access:

full access within that school
can view teacher profiles, user profiles, permissions, and operational data
can assign class teachers
can see teacher performance dashboards


3.3 Teacher
Teachers should have restricted access.
Responsibilities:

mark attendance
upload attendance sheets
enter marks
add remarks
view assigned class timetable/calendar
manage assigned academic tasks
monitor assigned students

Important access rule:

Teachers should only be able to see student status and student-related academic/attendance information relevant to their assigned class or students.
Teachers should not be able to see:

teacher details of other staff
user management data
school-wide admin settings
fee management data unless specifically allowed
confidential staff records



Teacher can see:

student attendance status
student marks status
student improvement status
weak subjects
assigned class/student dashboards
exam schedule relevant to their class
syllabus-related information
their own calendar/timetable


3.4 Class Teacher
Each child should have one assigned class teacher.
Responsibilities:

monitor assigned students closely
track attendance, marks, remarks, and improvement
review students needing intervention
act as primary teacher for that class
support parent communication where needed

Access:

can see only assigned students and their status
cannot see other teachers’ profiles or school user details
can view own performance status


3.5 Accounts / Fee Manager
Responsibilities:

manage fee structures
assign fees
record payments
manage due and overdue amounts
generate receipts
send fee reminders if permission is granted

Access:

fee-related data only
limited student fee view
no access to teacher confidential details unless School Super Admin allows it


3.6 Parent
Responsibilities:

receive WhatsApp updates
optionally log into a portal/app
view their own child’s attendance, marks, fees, exams, syllabus, holidays, and updates

Access:

only their child’s data


3.7 Student (Optional Later)
Responsibilities:

view own attendance
view marks
view exam schedule and syllabus
track own progress

Access:

only own data


4. Access Control Summary
Visibility Rules

Platform Super Admin: full platform visibility
School Super Admin: full visibility inside that school
Teacher/Class Teacher: only student status and class-related academic data
Teachers cannot see teacher/user details
Only School Super Admin can see teacher details and school user details
Parents can see only their child’s records
Accounts users can see fee-related records only

This is a strong design choice because it improves privacy, reduces misuse, and keeps the system simple.

5. Core Modules
5.1 School Management Module
Features:

create school
school profile setup
academic year setup
term/semester setup
class and section setup
subject setup
grading rules
fee term setup


5.2 User and Role Management Module
Features:

Platform Super Admin login
School Super Admin login
teacher login
class teacher assignment
accounts login
role-based permissions
password reset
login activity logs
user activation/deactivation
school-wise tenant isolation


5.3 Student Management Module
Features:

unique student ID
student profile
class and section assignment
roll number
parent/guardian details
WhatsApp contact number
medical notes
emergency contact
admission details
status: active / inactive / transferred
class teacher assignment

Input methods:

manual entry
Excel upload


5.4 Parent Management Module
Features:

parent profile
relationship to student
primary and secondary contact number
WhatsApp-enabled number
consent tracking
optional portal login later


5.5 Attendance Module
Features:

daily attendance entry
weekly attendance entry
daily/weekly Excel upload
attendance correction workflow
status options:

present
absent
sick leave
half day
late
excused leave



Reports:

student-wise attendance
class-wise attendance
monthly attendance
term-wise attendance
low attendance alerts

Automation:

absent alert to parents
sick leave alert to parents


5.6 Leave and Sick Leave Module
Features:

record sick leave
record general leave
leave reason
medical certificate upload
leave history
recurring absence tracking
health-related absence trends


5.7 Marks and Academic Performance Module
Features:

exam setup
term/semester setup
subject-wise marks entry
Excel marks upload
grading rules
average score calculation
percentage calculation
pass/fail rules
teacher remarks

Analytics:

strongest subject
weakest subject
class average comparison
exam-over-exam trend
improvement status: improving / declining / stable


5.8 Holiday Management Module
Features:

school holiday calendar
special closure entry
public holiday entry
Excel upload for holiday list
holiday notification to parents
holiday calendar view for staff and parents


5.9 Exam Schedule Module
Features:

create exam timetable by class/section
assign subject, date, time, duration
exam instructions
room or hall details if needed
publish exam schedule
edit/reschedule exam
class-wise exam calendar

Notifications:

exam schedule published
exam rescheduled
exam reminder before exam date

Parents should receive:

exam schedule
changes to schedule
reminders

Teachers should receive:

class exam schedule
exam-related reminders


5.10 Exam Syllabus Module
Features:

upload syllabus by class, subject, and exam
upload text, PDF, or document reference
version history
syllabus visibility for parents/students
class-wise syllabus tracker

Notifications:

syllabus published
syllabus updated
reminder with exam syllabus reference

Parents should receive:

exam syllabus
updates to syllabus
reminder before exams


5.11 Fee Management Module
Features:

fee structure by class
monthly / quarterly / annual fee setup
tuition fee
admission fee
exam fee
transport fee
activity fee
special charges
discounts and scholarships
late fee rules

Operations:

assign fee plan to student
generate due schedule
record payments
payment modes:

cash
bank transfer
card
online


pending due tracking
receipt generation
refund and adjustment support

Notifications:

fee invoice generated
due reminder
overdue reminder
payment received confirmation


5.12 Teacher Management Module
Features:

teacher profile
employee ID
subject assignment
class assignment
class teacher assignment
joining date
qualifications
contact details
leave status
active/inactive status

Visibility rule:

full teacher details visible only to School Super Admin
teachers cannot browse other teacher profiles


5.13 Teacher Calendar and Timetable Module
Features:

teacher daily calendar
weekly calendar
monthly calendar
assigned class timetable
subject timetable
exam duty schedule
meeting reminders
school event calendar
leave calendar
substitution/cover teacher schedule

Teachers should receive:

class timetable
exam schedule
holiday calendar
meeting reminders
marks submission deadlines
syllabus deadlines


5.14 Teacher Performance Tracking Module
Teacher performance should be measured carefully, especially for class teachers.
For every child, there should be one assigned class teacher.
Teacher performance should be based on:
Student-linked indicators

attendance percentage of assigned class
absentee reduction trend
marks improvement trend
pass percentage
weak subject recovery
student improvement rate

Operational indicators

attendance submission timeliness
marks entry timeliness
syllabus upload timeliness
task completion rate
class data completeness

Recommended model
Do not base teacher performance only on marks and attendance.
Recommended scoring:

40% student attendance trends
30% marks/performance trends
15% timely submission/compliance
15% School Super Admin review

Teacher performance status:

Excellent
Good
Needs Attention
Critical Review

Access rule:

only School Super Admin can see full teacher performance details
teacher can see only their own performance summary/status


5.15 Student Search and Analytics Dashboard
When a school user searches by unique student ID, the system should show a full dashboard.
Student profile

name
unique ID
class
section
roll number
class teacher
parent contacts

Attendance analytics

total school days
present days
absent days
absent percentage
sick leaves
late arrivals
attendance trend by month

Academic analytics

subject-wise marks
total percentage
exam trend
class average comparison
best subject
subject needing improvement
improvement trend

Leave analytics

total leaves
sick leaves
leave trend

Fee analytics

total fees assigned
paid amount
due amount
overdue amount
next due date
last payment date

Graphical view

donut chart for attendance split
line chart for marks trend
bar chart for subject-wise marks
comparison chart for student vs class average
fee summary card
improvement indicator card

Insight examples

attendance below expected level
mathematics improving steadily
science needs attention
high sick leave affecting performance
fee overdue for current term


5.16 Teacher Dashboard
Teachers should see only what is relevant to them.
Features:

today’s classes
weekly timetable
assigned students
attendance pending
marks pending
upcoming exams
syllabus deadlines
assigned class attendance average
assigned class marks average
student risk alerts
own performance summary/status

Restriction:

no access to teacher directory
no access to other users’ details
no access to admin settings


5.17 School Super Admin Dashboard
Features:

total students
total teachers
total users
attendance by class
teacher performance summary
fee collection summary
upcoming exams
upcoming holidays
pending uploads
notification delivery rate
students at risk
classes with low performance

This role is the only school-level role that can see:

teacher details
user details
full teacher performance reports


5.18 Accounts Dashboard
Features:

total billed amount
total collected amount
overdue fees
class-wise fee collection
unpaid students list
daily/monthly collection trends


5.19 Parent Communication / Notification Module
Automatic WhatsApp messages should be sent for:

student absent
student on sick leave
holiday announcement
exam schedule published
exam rescheduled
exam syllabus shared
exam reminder
marks published
fee invoice generated
fee due reminder
overdue fee reminder
payment received confirmation
important school notice

Important capabilities:

approved message templates
school-specific template customization
delivery logs
failed message retry
consent tracking
multilingual support later


5.20 Excel Upload and Bulk Import Module
The system should support both manual entry and Excel upload.
Supported uploads:

students
parents
attendance
marks
holidays
exam schedules
syllabus reference data
fee structure
fee dues
payment updates
teacher data
timetable data

Upload process:

download sample template
fill Excel
upload file
validate file
preview import
import valid rows
show invalid rows with reasons

Validation examples:

duplicate student ID
duplicate teacher ID
invalid class/section
missing phone number
invalid exam date
invalid mark range
duplicate attendance entry
duplicate fee record
missing subject mapping
invalid timetable format


6. Main Workflows
Workflow 1: School onboarding
Platform Super Admin creates school -> School Super Admin account created -> school configures classes, subjects, teachers, fee structure
Workflow 2: Student onboarding
School Super Admin adds students manually or through Excel -> parent details added -> class teacher assigned -> unique ID generated
Workflow 3: Teacher onboarding
School Super Admin adds teacher -> assigns classes/subjects -> assigns class teacher role -> timetable/calendar created
Workflow 4: Attendance process
Teacher marks attendance or uploads sheet -> system validates -> absent and sick leave alerts sent to parents
Workflow 5: Marks process
Teacher enters marks/upload Excel -> system calculates performance -> student dashboard updates -> teacher own summary updates
Workflow 6: Exam process
School publishes exam schedule and syllabus -> parents and teachers receive updates -> reminders sent automatically
Workflow 7: Fee process
Accounts team creates dues -> reminders sent -> payments recorded -> receipts generated
Workflow 8: Student search
Search using student unique ID -> full dashboard opens with graphs, trends, fee details, and insights
Workflow 9: Teacher performance process
System reviews class attendance, marks improvement, submission timeliness, and class performance -> teacher score updated -> visible fully to School Super Admin, partially to teacher

7. Reporting and Analytics
Student reports

attendance report
marks report
improvement report
weak subjects report
fee due report
leave report

Teacher reports

class attendance performance
average class marks
student improvement rate
pending tasks
performance score

School reports

school attendance summary
class performance summary
teacher performance summary
fee collection report
notification delivery report


8. Functional Requirements Summary
The application must support:

multi-school architecture
Platform Super Admin
School Super Admin
strict role-based visibility
school creation and management
student management
parent management
teacher management
class teacher assignment
attendance and leave tracking
marks and performance tracking
holiday management
exam schedule management
exam syllabus management
fee management
teacher timetable and calendar
teacher performance tracking
student unique ID search
graphical student dashboard
Excel imports
WhatsApp alerts


9. Non-Functional Requirements
The system should also meet these requirements:

secure authentication
encrypted sensitive data
school-wise tenant isolation
audit logs
backup and restore
mobile-friendly UI
fast student search
scalable import processing
reliable notification queue
strict permission enforcement
consent tracking for parent messaging
approved WhatsApp templates


10. Recommended Technology Stack
Frontend

Next.js / React
Tailwind CSS or Material UI

Backend

NestJS or Django

Database

PostgreSQL

Background jobs

Redis + queue workers

File handling

Excel parser and validation engine

Notifications

WhatsApp Business API integration

Storage

cloud object storage for uploads and attachments

Recommended architecture
Next.js + NestJS + PostgreSQL + Redis + WhatsApp API
This is a strong choice for a scalable multi-school product.

11. Suggested Database Entities
Main entities/tables:

schools
users
roles
teachers
teacher_assignments
teacher_calendars
teacher_timetables
classes
sections
subjects
students
parents
student_teacher_mapping
attendance_records
leave_records
holidays
exams
exam_schedules
exam_syllabus
marks
remarks
fee_structures
student_fee_assignments
fee_dues
fee_payments
receipts
notifications
upload_logs
audit_logs
performance_scores

Important rule:
Every major table should include school_id.

12. MVP Scope
Recommended first release:

Platform Super Admin login
School Super Admin login
teacher login
accounts login
student management
parent management
teacher management
class teacher assignment
attendance management
sick leave management
holiday management
marks entry
exam schedule upload
exam syllabus upload
fee tracking
teacher timetable/calendar
WhatsApp notifications
student dashboard by unique ID
basic teacher performance dashboard
Excel upload support
strict teacher/user visibility control

This is a strong MVP and practical to launch.

13. Phase-wise Development Plan
Phase 1: Discovery and design
Duration: 1-2 weeks
Deliverables:

final requirements
access control matrix
user roles
wireframes
database design
Excel templates
notification templates
dashboard definitions

Phase 2: Core platform
Duration: 3-5 weeks
Deliverables:

authentication
school management
user/role management
student management
teacher management
parent management
access restrictions

Phase 3: Operations modules
Duration: 3-4 weeks
Deliverables:

attendance
leave tracking
holidays
marks
exam schedule
exam syllabus
teacher timetable/calendar

Phase 4: Fees and communication
Duration: 2-3 weeks
Deliverables:

fee management
payment tracking
receipts
WhatsApp automation
notification logs

Phase 5: Analytics and performance
Duration: 2-3 weeks
Deliverables:

student dashboard
teacher dashboard
School Super Admin dashboard
teacher performance metrics
reports

Phase 6: Testing and deployment
Duration: 1-2 weeks
Deliverables:

QA testing
security testing
performance tuning
deployment
training


14. Business Rules
Examples:

if student is absent, send same-day parent alert
if student is on sick leave, send parent update
if holiday is added, notify parents
if exam schedule is published or changed, notify parents and teachers
if syllabus is uploaded, notify parents and students
if fee is due, send reminder before due date
if fee is overdue, send overdue alert
if attendance falls below threshold, flag student
if marks drop across exams, show needs improvement
each student must have one class teacher
only School Super Admin can see teacher details and user details
teachers can only see student status and assigned academic data
teacher performance should update periodically based on class indicators


15. Key Product Differentiators
This product is stronger because it combines:

school administration
parent communication
student analytics
fee tracking
teacher tracking
timetable/calendar management
teacher performance monitoring
strict role-based privacy controls

That makes it much better than a simple attendance app.

16. Final Recommendation
Build this as a multi-school ERP Lite + Parent Engagement + Student and Teacher Analytics platform with strict access control.
Best priority order:

user roles and access control
student, parent, and teacher management
attendance and leave
marks, exams, and syllabus
fees and WhatsApp communication
dashboards and teacher performance

That is the cleanest way to build a useful and secure first version
