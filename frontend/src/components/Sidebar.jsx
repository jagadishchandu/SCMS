import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { ROLE_LABELS } from "../lib/utils";
import {
  House, Buildings, GraduationCap, UsersThree, ClipboardText, ChartLineUp,
  Calendar, BookOpen, Receipt, BellRinging, UploadSimple, IdentificationBadge,
  Gauge, ChalkboardTeacher, SignOut, ChartPieSlice, FileText, MagnifyingGlass,
} from "@phosphor-icons/react";

const NAV_BY_ROLE = {
  platform_admin: [
    { to: "/platform", label: "Overview", icon: Gauge, end: true },
    { to: "/platform/schools", label: "Schools", icon: Buildings },
    { to: "/platform/notifications", label: "Notifications", icon: BellRinging },
  ],
  school_admin: [
    { to: "/school", label: "Dashboard", icon: Gauge, end: true },
    { to: "/school/students", label: "Students", icon: GraduationCap },
    { to: "/school/teachers", label: "Teachers & Staff", icon: ChalkboardTeacher },
    { to: "/school/classes", label: "Classes & Subjects", icon: BookOpen },
    { to: "/school/attendance", label: "Attendance", icon: ClipboardText },
    { to: "/school/exams", label: "Exams & Marks", icon: FileText },
    { to: "/school/syllabus", label: "Syllabus", icon: BookOpen },
    { to: "/school/holidays", label: "Holidays", icon: Calendar },
    { to: "/school/fees", label: "Fees", icon: Receipt },
    { to: "/school/timetable", label: "Timetable", icon: Calendar },
    { to: "/school/performance", label: "Teacher Performance", icon: ChartLineUp },
    { to: "/school/notifications", label: "Notifications", icon: BellRinging },
    { to: "/school/uploads", label: "Bulk Uploads", icon: UploadSimple },
    { to: "/student-search", label: "Student Analytics", icon: MagnifyingGlass },
  ],
  teacher: [
    { to: "/teacher", label: "My Dashboard", icon: Gauge, end: true },
    { to: "/teacher/attendance", label: "Mark Attendance", icon: ClipboardText },
    { to: "/teacher/marks", label: "Enter Marks", icon: FileText },
    { to: "/teacher/students", label: "My Students", icon: GraduationCap },
    { to: "/teacher/timetable", label: "My Timetable", icon: Calendar },
    { to: "/teacher/performance", label: "My Performance", icon: ChartLineUp },
    { to: "/student-search", label: "Student Search", icon: MagnifyingGlass },
  ],
  accounts: [
    { to: "/accounts", label: "Fee Dashboard", icon: Gauge, end: true },
    { to: "/accounts/fees", label: "Fee Structures", icon: Receipt },
    { to: "/accounts/payments", label: "Payments", icon: ChartPieSlice },
    { to: "/student-search", label: "Student Search", icon: MagnifyingGlass },
  ],
  parent: [
    { to: "/parent", label: "My Child", icon: House, end: true },
  ],
};

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  const items = NAV_BY_ROLE[user.role] || [];

  return (
    <aside className="hidden lg:flex flex-col w-60 shrink-0 bg-bg border-r border-line h-screen sticky top-0" data-testid="app-sidebar">
      <div className="px-5 py-6 border-b border-line">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary text-primary-foreground grid place-items-center font-display font-semibold">S</div>
          <div>
            <div className="font-display text-base font-semibold leading-none">SCMS</div>
            <div className="text-[10px] uppercase tracking-widest text-ink-muted mt-1">Child Monitoring</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1" data-testid="sidebar-nav">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            data-testid={`nav-${to.replace(/\//g, "-").replace(/^-+/, "")}`}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? "bg-primary-light text-primary font-medium"
                  : "text-ink-soft hover:bg-bg-subtle hover:text-ink"
              }`
            }
          >
            <Icon size={18} weight="regular" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-line p-3">
        <div className="px-3 py-2 mb-2">
          <div className="text-sm font-medium text-ink truncate" data-testid="sidebar-user-name">{user.name}</div>
          <div className="text-[11px] text-ink-muted truncate">{ROLE_LABELS[user.role]}</div>
        </div>
        <button
          onClick={async () => { await logout(); navigate("/login"); }}
          className="w-full btn-ghost justify-start gap-2 text-ink-soft hover:text-status-danger"
          data-testid="sidebar-logout-btn"
        >
          <SignOut size={16} /> Sign out
        </button>
      </div>
    </aside>
  );
}
