import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import "./App.css";

import { useAuth } from "./contexts/AuthContext";
import { ROLE_HOME } from "./lib/utils";

import { ProtectedRoute } from "./components/ProtectedRoute";
import AppLayout from "./layouts/AppLayout";

// Pages
import Login from "./pages/Login";

// Platform
import PlatformOverview from "./pages/platform/PlatformOverview";

// Shared
import StudentAnalytics from "./pages/shared/StudentAnalytics";
import NotificationsLog from "./pages/shared/NotificationsLog";

// School Admin
import SchoolDashboard from "./pages/school/SchoolDashboard";
import StudentsPage from "./pages/school/StudentsPage";
import TeachersPage from "./pages/school/TeachersPage";
import ClassesPage from "./pages/school/ClassesPage";
import AttendancePage from "./pages/school/AttendancePage";
import ExamsPage from "./pages/school/ExamsPage";
import SyllabusPage from "./pages/school/SyllabusPage";
import HolidaysPage from "./pages/school/HolidaysPage";
import FeesPage from "./pages/school/FeesPage";
import TimetablePage from "./pages/school/TimetablePage";
import TeacherPerformancePage from "./pages/school/TeacherPerformancePage";
import UploadsPage from "./pages/school/UploadsPage";

// Teacher
import TeacherDashboard from "./pages/teacher/TeacherDashboard";
import MyTimetable from "./pages/teacher/MyTimetable";

// Accounts
import AccountsDashboard from "./pages/accounts/AccountsDashboard";

// Parent
import ParentPortal from "./pages/parent/ParentPortal";

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
      <Route path="/" element={<Home />} />

      {/* Platform Admin */}
      <Route path="/platform" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(PlatformOverview)}</ProtectedRoute>} />
      <Route path="/platform/schools" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(PlatformOverview)}</ProtectedRoute>} />
      <Route path="/platform/notifications" element={<ProtectedRoute allow={["platform_admin"]}>{withLayout(NotificationsLog)}</ProtectedRoute>} />

      {/* School Admin */}
      <Route path="/school" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(SchoolDashboard)}</ProtectedRoute>} />
      <Route path="/school/students" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(StudentsPage)}</ProtectedRoute>} />
      <Route path="/school/teachers" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TeachersPage)}</ProtectedRoute>} />
      <Route path="/school/classes" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(ClassesPage)}</ProtectedRoute>} />
      <Route path="/school/attendance" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(AttendancePage)}</ProtectedRoute>} />
      <Route path="/school/exams" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(ExamsPage)}</ProtectedRoute>} />
      <Route path="/school/syllabus" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(SyllabusPage)}</ProtectedRoute>} />
      <Route path="/school/holidays" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(HolidaysPage)}</ProtectedRoute>} />
      <Route path="/school/fees" element={<ProtectedRoute allow={["school_admin","accounts"]}>{withLayout(FeesPage)}</ProtectedRoute>} />
      <Route path="/school/timetable" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TimetablePage)}</ProtectedRoute>} />
      <Route path="/school/performance" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(TeacherPerformancePage)}</ProtectedRoute>} />
      <Route path="/school/notifications" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(NotificationsLog)}</ProtectedRoute>} />
      <Route path="/school/uploads" element={<ProtectedRoute allow={["school_admin"]}>{withLayout(UploadsPage)}</ProtectedRoute>} />

      {/* Teacher */}
      <Route path="/teacher" element={<ProtectedRoute allow={["teacher"]}>{withLayout(TeacherDashboard)}</ProtectedRoute>} />
      <Route path="/teacher/attendance" element={<ProtectedRoute allow={["teacher"]}>{withLayout(AttendancePage)}</ProtectedRoute>} />
      <Route path="/teacher/marks" element={<ProtectedRoute allow={["teacher"]}>{withLayout(ExamsPage)}</ProtectedRoute>} />
      <Route path="/teacher/students" element={<ProtectedRoute allow={["teacher"]}>{withLayout(StudentsPage)}</ProtectedRoute>} />
      <Route path="/teacher/timetable" element={<ProtectedRoute allow={["teacher"]}>{withLayout(MyTimetable)}</ProtectedRoute>} />
      <Route path="/teacher/performance" element={<ProtectedRoute allow={["teacher"]}>{withLayout(() => <TeacherPerformancePage self />)}</ProtectedRoute>} />

      {/* Accounts */}
      <Route path="/accounts" element={<ProtectedRoute allow={["accounts"]}>{withLayout(AccountsDashboard)}</ProtectedRoute>} />
      <Route path="/accounts/fees" element={<ProtectedRoute allow={["accounts"]}>{withLayout(FeesPage)}</ProtectedRoute>} />
      <Route path="/accounts/payments" element={<ProtectedRoute allow={["accounts"]}>{withLayout(AccountsDashboard)}</ProtectedRoute>} />

      {/* Parent */}
      <Route path="/parent" element={<ProtectedRoute allow={["parent"]}>{withLayout(ParentPortal)}</ProtectedRoute>} />

      {/* Shared analytics */}
      <Route path="/student-search" element={<ProtectedRoute allow={["platform_admin","school_admin","teacher","accounts"]}>{withLayout(StudentAnalytics)}</ProtectedRoute>} />
      <Route path="/student/:uid" element={<ProtectedRoute allow={["platform_admin","school_admin","teacher","accounts","parent"]}>{withLayout(StudentAnalytics)}</ProtectedRoute>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
