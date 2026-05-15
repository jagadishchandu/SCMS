"""Pydantic schemas for request/response models."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal
from datetime import date


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
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
    admin_email: EmailStr
    admin_password: str


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
    email: EmailStr
    password: str
    name: str
    role: Literal["school_admin", "teacher", "accounts", "parent"]
    phone: Optional[str] = None
    employee_id: Optional[str] = None
    qualifications: Optional[str] = None
    joining_date: Optional[str] = None  # YYYY-MM-DD
    subjects: Optional[List[str]] = None  # subject ids


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    qualifications: Optional[str] = None
    is_active: Optional[bool] = None
    subjects: Optional[List[str]] = None


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
    email: Optional[EmailStr] = None


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


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    class_id: Optional[str] = None
    section: Optional[str] = None
    roll_number: Optional[str] = None
    medical_notes: Optional[str] = None
    emergency_contact: Optional[str] = None
    parent: Optional[ParentInfo] = None
    status: Optional[Literal["active", "inactive", "transferred"]] = None


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
