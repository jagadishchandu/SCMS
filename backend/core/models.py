"""Pydantic schemas for request/response models."""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Literal
from datetime import date


def _blank_to_none(v):
    """Normalise empty / whitespace-only strings to None so Optional[EmailStr]
    and similar fields don't reject UI defaults like email="" from a form.
    """
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


# ---------- Auth ----------
class LoginRequest(BaseModel):
    # `email` here is actually a "login id" — it can be a full email
    # (e.g. principal@sunrise.edu) OR a simple identifier with no '@'
    # (e.g. principal01). We do NOT use EmailStr so admins can create
    # short login ids for staff/parents. Case-insensitive (lowercased) lookup
    # is enforced at the auth router.
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    school_id: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True


# ---------- Schools ----------
class SchoolCreate(BaseModel):
    name: str
    code: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    academic_year: Optional[str] = "2025-2026"
    admin_name: str
    admin_email: str  # login id — can be email-style or a simple id (no '@')
    admin_password: str
    admin_phone: Optional[str] = None
    auto_approve: Optional[bool] = False  # If True, skip approval lockdown (Platform admin pre-approves)
    initial_children_count: Optional[int] = None  # Capacity when auto-approving


class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    academic_year: Optional[str] = None
    is_active: Optional[bool] = None


class SchoolBranding(BaseModel):
    logo: Optional[str] = None  # data URL or http URL
    primary_color: Optional[str] = None  # CSS color string e.g. #4E5B3A
    tagline: Optional[str] = None


# ---------- Users / Teachers ----------
class UserCreate(BaseModel):
    # `email` is a login id — full email OR a simple id (no '@'). Backend
    # lowercases & enforces uniqueness across all roles in the same school.
    email: str
    password: str
    name: str
    role: Literal["school_admin", "teacher", "accounts", "parent"]
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    qualifications: Optional[str] = None
    joining_date: Optional[str] = None  # YYYY-MM-DD
    subjects: Optional[List[str]] = None  # subject ids
    monthly_salary: Optional[float] = None  # for teacher/accounts


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    qualifications: Optional[str] = None
    is_active: Optional[bool] = None
    subjects: Optional[List[str]] = None
    monthly_salary: Optional[float] = None


# ---------- Class / Section / Subject ----------
class ClassCreate(BaseModel):
    name: str  # e.g. "Grade 5"
    sections: List[str] = Field(default_factory=lambda: ["A"])  # ["A","B"]


class SubjectCreate(BaseModel):
    name: str
    code: Optional[str] = None


class ClassTeacherAssign(BaseModel):
    teacher_id: str
    class_id: str
    section: str


# ---------- Student / Parent ----------
class ParentInfo(BaseModel):
    name: str
    relationship: str = "guardian"
    phone: str
    whatsapp: Optional[str] = None
    # Parent login id — accepts full email OR a simple identifier (no '@').
    email: Optional[str] = None

    @field_validator("email", "whatsapp", mode="before")
    @classmethod
    def _blank_email(cls, v):
        return _blank_to_none(v)


class StudentCreate(BaseModel):
    name: str
    student_uid: Optional[str] = None  # auto if not provided
    class_id: str
    section: str
    roll_number: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None  # YYYY-MM-DD
    admission_date: Optional[str] = None
    medical_notes: Optional[str] = None
    emergency_contact: Optional[str] = None
    parent: ParentInfo

    @field_validator("roll_number", "gender", "dob", "admission_date", "medical_notes", "emergency_contact", mode="before")
    @classmethod
    def _blank_optional(cls, v):
        return _blank_to_none(v)


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    class_id: Optional[str] = None
    section: Optional[str] = None
    roll_number: Optional[str] = None
    gender: Optional[str] = None
    dob: Optional[str] = None
    medical_notes: Optional[str] = None
    emergency_contact: Optional[str] = None
    parent: Optional[ParentInfo] = None
    status: Optional[Literal["active", "inactive", "transferred"]] = None

    @field_validator("roll_number", "gender", "dob", "medical_notes", "emergency_contact", mode="before")
    @classmethod
    def _blank_optional(cls, v):
        return _blank_to_none(v)


# ---------- Attendance ----------
AttendanceStatus = Literal["present", "absent", "sick", "late", "half_day", "excused", "not_in_class"]


class AttendanceEntry(BaseModel):
    student_id: str
    status: AttendanceStatus
    remark: Optional[str] = None


class AttendanceBulkCreate(BaseModel):
    class_id: str
    section: str
    date: str  # YYYY-MM-DD
    entries: List[AttendanceEntry]


# ---------- Marks / Exam / Syllabus ----------
class ExamCreate(BaseModel):
    name: str
    term: str
    class_id: str
    section: Optional[str] = None
    start_date: str
    end_date: str
    schedule: List[dict] = Field(default_factory=list)  # [{subject_id, date, time, duration, room}]


class SyllabusCreate(BaseModel):
    exam_id: str
    class_id: str
    subject_id: str
    title: str
    content: str
    version: int = 1


class MarkEntry(BaseModel):
    student_id: str
    marks_obtained: float
    max_marks: float
    remark: Optional[str] = None


class MarksBulkCreate(BaseModel):
    exam_id: str
    subject_id: str
    entries: List[MarkEntry]


# ---------- Holidays ----------
class HolidayCreate(BaseModel):
    title: str
    date: str
    end_date: Optional[str] = None
    type: Literal["public", "school", "closure"] = "school"
    description: Optional[str] = None


# ---------- Fees ----------
class FeeStructureCreate(BaseModel):
    class_id: str
    name: str  # Term 1, Annual etc
    items: List[dict]  # [{type, amount}]
    due_date: str
    section: Optional[str] = None  # If set, applies to that section only; None = whole class (all sections)
    term: Optional[str] = None  # e.g. "Term 1", "Term 2", "Term 3", "Annual", custom


class FeePaymentCreate(BaseModel):
    student_id: str
    fee_id: str
    amount: float
    mode: Literal["cash", "bank_transfer", "card", "online"] = "cash"
    note: Optional[str] = None


# ---------- Timetable ----------
class TimetableSlot(BaseModel):
    day: Literal["mon", "tue", "wed", "thu", "fri", "sat"]
    period: int
    subject_id: str
    teacher_id: str
    class_id: str
    section: str
    start_time: str
    end_time: str


class TimetableBulk(BaseModel):
    class_id: str
    section: str
    slots: List[TimetableSlot]
