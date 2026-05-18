import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import "./App.css";

import { useAuth } from "./contexts/AuthContext";
import { ROLE_HOME } from "./lib/utils";

import { ProtectedRoute } from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";

// Pages
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";

// Platform
import PlatformOverview from "./pages/platform/PlatformOverview";
import SubscriptionsPage from "./pages/platform/SubscriptionsPage";
import CompliancePage from "./pages/platform/CompliancePage";

// Shared
import StudentAnalytics from "./pages/shared/StudentAnalytics";
import NotificationsLog from "./pages/shared/NotificationsLog";
import CalendarPage from "./pages/shared/CalendarPage";
import AuditLogPage from "./pages/shared/AuditLogPage";
import SickLeavesPage from "./pages/shared/SickLeavesPage";
import ChatPage from "./pages/shared/ChatPage";

// School Admin
import SchoolDashboard from "./pages/school/SchoolDashboard";
import StudentsPage from "./pages/school/StudentsPage";
import TeachersPage from "./pages/school/TeachersPage";
import ClassesPage from "./pages/school/ClassesPage";
import StaffPage from "./pages/school/StaffPage";
import ExpensesPage from "./pages/ExpensesPage";
import AttendancePage from "./pages/school/AttendancePage";
import ExamsPage from "./pages/school/ExamsPage";
import SyllabusPage from "./pages/school/SyllabusPage";
import HolidaysPage from "./pages/school/HolidaysPage";
import FeesPage from "./pages/school/FeesPage";
import TimetablePage from "./pages/school/TimetablePage";
import TeacherPerformancePage from "./pages/school/TeacherPerformancePage";
import UploadsPage from "./pages/school/UploadsPage";
import ActivitiesPage from "./pages/school/ActivitiesPage";
import SchoolSettings from "./pages/school/SchoolSettings";
import SchoolSubscription from "./pages/school/SchoolSubscription";
import FeeItemsPage from "./pages/school/FeeItemsPage";
import FeeTrackerPage from "./pages/school/FeeTrackerPage";
import TeacherDutiesPage from "./pages/school/TeacherDutiesPage";
import TripsPage from "./pages/school/TripsPage";
import TripsViewPage from "./pages/shared/TripsViewPage";

// Teacher
import TeacherDashboard from "./pages/teacher/TeacherDashboard";
import MyTimetable from "./pages/teacher/MyTimetable";
import TeacherAttendanceCards from "./pages/teacher/TeacherAttendanceCards";

// Accounts
import AccountsDashboard from "./pages/accounts/AccountsDashboard";

// Parent
import ParentPortal from "./pages/parent/ParentPortal";

// Shared profile (telegram-linking + reachability)
import Profile from "./pages/Profile";

function Home() {
  const { user } = useAuth();
  if (user === null) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={ROLE_HOME[user.role] || "/login"} replace />;
}

function withLayout(Component) {
  return (
    <AppLayout>
      <Component />
    </AppLayout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/" element={<Home />} />

      {/* Platform Admin */}
      <Route path="/platform" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(PlatformOverview)}</ProtectedRoute>} />
      <Route path="/platform/schools" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(PlatformOverview)}</ProtectedRoute>} />
      <Route path="/platform/subscriptions" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(SubscriptionsPage)}</ProtectedRoute>} />
      <Route path="/platform/compliance" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(CompliancePage)}</ProtectedRoute>} />
      <Route path="/platform/notifications" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(NotificationsLog)}</ProtectedRoute>} />
      <Route path="/platform/audit" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(AuditLogPage)}</ProtectedRoute>} />

      {/* School Admin */}
      <Route path="/school" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(SchoolDashboard)}</ProtectedRoute>} />
      <Route path="/school/students" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(StudentsPage)}</ProtectedRoute>} />
      <Route path="/school/teachers" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TeachersPage)}</ProtectedRoute>} />
      <Route path="/school/classes" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(ClassesPage)}</ProtectedRoute>} />
      <Route path="/teacher/classes" element={<ProtectedRoute allow={["teacher"]}>{withLayout(ClassesPage)}</ProtectedRoute>} />

      <Route path="/school/staff" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(StaffPage)}</ProtectedRoute>} />
      <Route path="/school/expenses" element={<ProtectedRoute allow={["school_admin", "accounts"]}>{withLayout(ExpensesPage)}</ProtectedRoute>} />
      <Route path="/accounts/expenses" element={<ProtectedRoute allow={["accounts"]}>{withLayout(ExpensesPage)}</ProtectedRoute>} />
      <Route path="/teacher/expenses" element={<ProtectedRoute allow={["teacher"]}>{withLayout(ExpensesPage)}</ProtectedRoute>} />
      <Route path="/school/attendance" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(AttendancePage)}</ProtectedRoute>} />
      <Route path="/school/exams" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(ExamsPage)}</ProtectedRoute>} />
      <Route path="/school/syllabus" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(SyllabusPage)}</ProtectedRoute>} />
      <Route path="/school/holidays" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(HolidaysPage)}</ProtectedRoute>} />
      <Route path="/school/fees" element={<ProtectedRoute allow={["school_admin","accounts"]}>{withLayout(FeesPage)}</ProtectedRoute>} />
      <Route path="/school/fee-items" element={<ProtectedRoute allow={["school_admin","accounts"]}>{withLayout(FeeItemsPage)}</ProtectedRoute>} />
      <Route path="/school/fee-tracker" element={<ProtectedRoute allow={["school_admin","accounts"]}>{withLayout(FeeTrackerPage)}</ProtectedRoute>} />
      <Route path="/school/teacher-duties" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TeacherDutiesPage)}</ProtectedRoute>} />
      <Route path="/school/timetable" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TimetablePage)}</ProtectedRoute>} />
      <Route path="/school/performance" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TeacherPerformancePage)}</ProtectedRoute>} />
      <Route path="/school/notifications" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(NotificationsLog)}</ProtectedRoute>} />
      <Route path="/school/uploads" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(UploadsPage)}</ProtectedRoute>} />
      <Route path="/school/activities" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(ActivitiesPage)}</ProtectedRoute>} />
      <Route path="/school/calendar" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(CalendarPage)}</ProtectedRoute>} />
      <Route path="/school/audit" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(AuditLogPage)}</ProtectedRoute>} />
      <Route path="/school/settings" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(SchoolSettings)}</ProtectedRoute>} />
      <Route path="/school/subscription" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(SchoolSubscription)}</ProtectedRoute>} />
      <Route path="/school/sick-leaves" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(SickLeavesPage)}</ProtectedRoute>} />
      <Route path="/school/trips" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TripsPage)}</ProtectedRoute>} />

      {/* Teacher */}
      <Route path="/teacher" element={<ProtectedRoute allow={["teacher"]}>{withLayout(TeacherDashboard)}</ProtectedRoute>} />
      <Route path="/teacher/attendance" element={<ProtectedRoute allow={["teacher"]}>{withLayout(AttendancePage)}</ProtectedRoute>} />
      <Route path="/teacher/attendance-cards" element={<ProtectedRoute allow={["teacher", "school_admin"]}>{withLayout(TeacherAttendanceCards)}</ProtectedRoute>} />
      <Route path="/teacher/marks" element={<ProtectedRoute allow={["teacher"]}>{withLayout(ExamsPage)}</ProtectedRoute>} />
      <Route path="/teacher/students" element={<ProtectedRoute allow={["teacher"]}>{withLayout(StudentsPage)}</ProtectedRoute>} />
      <Route path="/teacher/timetable" element={<ProtectedRoute allow={["teacher"]}>{withLayout(MyTimetable)}</ProtectedRoute>} />
      <Route path="/teacher/performance" element={<ProtectedRoute allow={["teacher"]}>{withLayout(() => <TeacherPerformancePage self />)}</ProtectedRoute>} />
      <Route path="/teacher/calendar" element={<ProtectedRoute allow={["teacher"]}>{withLayout(CalendarPage)}</ProtectedRoute>} />
      <Route path="/teacher/duties" element={<ProtectedRoute allow={["teacher"]}>{withLayout(() => <TeacherDutiesPage readOnly />)}</ProtectedRoute>} />
      <Route path="/teacher/uploads" element={<ProtectedRoute allow={["teacher"]}>{withLayout(UploadsPage)}</ProtectedRoute>} />
      <Route path="/teacher/sick-leaves" element={<ProtectedRoute allow={["teacher"]}>{withLayout(SickLeavesPage)}</ProtectedRoute>} />
      <Route path="/teacher/trips" element={<ProtectedRoute allow={["teacher"]}>{withLayout(TripsViewPage)}</ProtectedRoute>} />

      {/* Parent extras */}
      <Route path="/parent/calendar" element={<ProtectedRoute allow={["parent"]}>{withLayout(CalendarPage)}</ProtectedRoute>} />
      <Route path="/parent/sick-leaves" element={<ProtectedRoute allow={["parent"]}>{withLayout(SickLeavesPage)}</ProtectedRoute>} />
      <Route path="/parent/trips" element={<ProtectedRoute allow={["parent"]}>{withLayout(TripsViewPage)}</ProtectedRoute>} />

      {/* Accounts */}
      <Route path="/accounts" element={<ProtectedRoute allow={["accounts"]}>{withLayout(AccountsDashboard)}</ProtectedRoute>} />
      <Route path="/accounts/fees" element={<ProtectedRoute allow={["accounts"]}>{withLayout(FeesPage)}</ProtectedRoute>} />
      <Route path="/accounts/fee-items" element={<ProtectedRoute allow={["accounts"]}>{withLayout(FeeItemsPage)}</ProtectedRoute>} />
      <Route path="/accounts/fee-tracker" element={<ProtectedRoute allow={["accounts"]}>{withLayout(FeeTrackerPage)}</ProtectedRoute>} />
      <Route path="/accounts/payments" element={<ProtectedRoute allow={["accounts"]}>{withLayout(AccountsDashboard)}</ProtectedRoute>} />

      {/* Parent */}
      <Route path="/parent" element={<ProtectedRoute allow={["parent"]}>{withLayout(ParentPortal)}</ProtectedRoute>} />

      {/* Shared analytics */}
      <Route path="/student-search" element={<ProtectedRoute allow={["platform_admin","school_admin","teacher","accounts"]}>{withLayout(StudentAnalytics)}</ProtectedRoute>} />
      <Route path="/student/:uid" element={<ProtectedRoute allow={["platform_admin","school_admin","teacher","accounts","parent"]}>{withLayout(StudentAnalytics)}</ProtectedRoute>} />

      {/* Self-service profile — Telegram linking + channel reachability */}
      <Route path="/profile" element={<ProtectedRoute allow={["platform_admin","school_admin","teacher","accounts","parent"]}>{withLayout(Profile)}</ProtectedRoute>} />

      {/* In-app chat */}
      <Route path="/chat" element={<ProtectedRoute allow={["school_admin","teacher","parent"]}>{withLayout(ChatPage)}</ProtectedRoute>} />
      <Route path="/chat/:peerId" element={<ProtectedRoute allow={["school_admin","teacher","parent"]}>{withLayout(ChatPage)}</ProtectedRoute>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
