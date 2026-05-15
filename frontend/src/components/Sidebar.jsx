import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { ROLE_LABELS } from "../lib/utils";
import {
  House, Buildings, GraduationCap, ClipboardText, ChartLineUp,
  Calendar, BookOpen, Receipt, BellRinging, UploadSimple,
  Gauge, ChalkboardTeacher, SignOut, ChartPieSlice, FileText, MagnifyingGlass,
  ShieldCheck, Package, X, Heartbeat,
} from "@phosphor-icons/react";

const NAV_BY_ROLE = {
  platform_admin: [
    { to: "/platform", label: "Overview", icon: Gauge, end: true },
    { to: "/platform/schools", label: "Schools", icon: Buildings },
    { to: "/platform/subscriptions", label: "Subscriptions", icon: Package },
    { to: "/platform/notifications", label: "Notifications", icon: BellRinging },
    { to: "/platform/audit", label: "Audit log", icon: ShieldCheck },
  ],
  school_admin: [
    { to: "/school", label: "Dashboard", icon: Gauge, end: true },
    { to: "/school/students", label: "Students", icon: GraduationCap },
    { to: "/school/teachers", label: "Teachers & Staff", icon: ChalkboardTeacher },
    { to: "/school/classes", label: "Classes & Subjects", icon: BookOpen },
    { to: "/school/attendance", label: "Attendance", icon: ClipboardText },
    { to: "/school/exams", label: "Exams & Marks", icon: FileText },
    { to: "/school/syllabus", label: "Syllabus", icon: BookOpen },
    { to: "/school/calendar", label: "Calendar", icon: Calendar },
    { to: "/school/holidays", label: "Holidays", icon: Calendar },
    { to: "/school/fees", label: "Fees", icon: Receipt },
    { to: "/school/timetable", label: "Timetable", icon: Calendar },
    { to: "/school/activities", label: "Activities", icon: ChartLineUp },
    { to: "/school/sick-leaves", label: "Sick Leaves", icon: Heartbeat },
    { to: "/school/performance", label: "Teacher Performance", icon: ChartLineUp },
    { to: "/school/notifications", label: "Notifications", icon: BellRinging },
    { to: "/school/uploads", label: "Bulk Uploads", icon: UploadSimple },
    { to: "/school/subscription", label: "Subscription", icon: Package },
    { to: "/school/settings", label: "Branding", icon: ShieldCheck },
    { to: "/school/audit", label: "Audit log", icon: ShieldCheck },
    { to: "/student-search", label: "Student Analytics", icon: MagnifyingGlass },
  ],
  teacher: [
    { to: "/teacher", label: "My Dashboard", icon: Gauge, end: true },
    { to: "/teacher/attendance-cards", label: "Take Attendance", icon: ClipboardText },
    { to: "/teacher/attendance", label: "Attendance (grid)", icon: ClipboardText },
    { to: "/teacher/marks", label: "Enter Marks", icon: FileText },
    { to: "/teacher/students", label: "My Students", icon: GraduationCap },
    { to: "/teacher/uploads", label: "Bulk Uploads", icon: UploadSimple },
    { to: "/teacher/sick-leaves", label: "Sick Leaves", icon: Heartbeat },
    { to: "/teacher/timetable", label: "My Timetable", icon: Calendar },
    { to: "/teacher/calendar", label: "Calendar", icon: Calendar },
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
    { to: "/parent/calendar", label: "Calendar", icon: Calendar },
    { to: "/parent/sick-leaves", label: "Sick Leaves", icon: Heartbeat },
  ],
};

function NavList({ items, onItemClick }) {
  return (
    <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1" data-testid="sidebar-nav">
      {items.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onItemClick}
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
  );
}

function Header() {
  return (
    <div className="px-5 py-6 border-b border-line">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-primary text-primary-foreground grid place-items-center font-display font-semibold">S</div>
        <div>
          <div className="font-display text-base font-semibold leading-none">SCMS</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-muted mt-1">Child Monitoring</div>
        </div>
      </div>
    </div>
  );
}

function Footer() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
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
  );
}

export default function Sidebar({ mobileOpen, onCloseMobile }) {
  const { user } = useAuth();
  if (!user) return null;
  const items = NAV_BY_ROLE[user.role] || [];

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-60 shrink-0 bg-bg border-r border-line h-screen sticky top-0" data-testid="app-sidebar">
        <Header />
        <NavList items={items} />
        <Footer />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" data-testid="mobile-drawer">
          <div className="absolute inset-0 bg-black/40" onClick={onCloseMobile} />
          <aside className="relative w-72 max-w-[85vw] h-full bg-bg border-r border-line flex flex-col">
            <button onClick={onCloseMobile} className="absolute top-3 right-3 btn-ghost p-1.5" data-testid="mobile-drawer-close"><X size={16} /></button>
            <Header />
            <NavList items={items} onItemClick={onCloseMobile} />
            <Footer />
          </aside>
        </div>
      )}
    </>
  );
}
