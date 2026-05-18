import React, { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { ROLE_LABELS } from "../lib/utils";
import { useSickLeavePending } from "../hooks/useSickLeavePending";
import { useUnreadNotifications } from "../hooks/useUnreadNotifications";
import { useUnreadChat } from "../hooks/useUnreadChat";
import {
  House, Buildings, GraduationCap, ClipboardText, ChartLineUp,
  Calendar, BookOpen, Receipt, BellRinging, UploadSimple,
  Gauge, ChalkboardTeacher, SignOut, ChartPieSlice, FileText, MagnifyingGlass,
  ShieldCheck, Package, X, Heartbeat, Users, MoneyWavy, UserCircle, Bus,
  ChatCircleDots,
} from "@phosphor-icons/react";

const NAV_BY_ROLE = {
  platform_admin: [
    { to: "/platform", label: "Overview", icon: Gauge, end: true },
    { to: "/platform/schools", label: "Schools", icon: Buildings },
    { to: "/platform/subscriptions", label: "Subscriptions", icon: Package },
    { to: "/platform/compliance", label: "Compliance", icon: ShieldCheck },
    { to: "/platform/notifications", label: "Notifications", icon: BellRinging },
    { to: "/platform/audit", label: "Audit log", icon: ShieldCheck },
  ],
  school_admin: [
    { to: "/school", label: "Dashboard", icon: Gauge, end: true },
    { to: "/chat", label: "Chat", icon: ChatCircleDots },
    { to: "/school/students", label: "Students", icon: GraduationCap },
    { to: "/school/teachers", label: "Teachers & Staff", icon: ChalkboardTeacher },
    { to: "/school/staff", label: "Support Staff", icon: Users },
    { to: "/school/teacher-duties", label: "Teacher Schedule", icon: Calendar },
    { to: "/school/expenses", label: "Expenses & Payroll", icon: MoneyWavy },
    { to: "/school/classes", label: "Classes & Subjects", icon: BookOpen },
    { to: "/school/attendance", label: "Attendance", icon: ClipboardText },
    { to: "/school/exams", label: "Exams & Marks", icon: FileText },
    { to: "/school/syllabus", label: "Syllabus", icon: BookOpen },
    { to: "/school/calendar", label: "Calendar", icon: Calendar },
    { to: "/school/holidays", label: "Holidays", icon: Calendar },
    { to: "/school/fee-items", label: "Fee Catalog", icon: Receipt },
    { to: "/school/fees", label: "Fee Structures", icon: Receipt },
    { to: "/school/fee-tracker", label: "Fee Tracker", icon: ChartPieSlice },
    { to: "/school/timetable", label: "Timetable", icon: Calendar },
    { to: "/school/activities", label: "Activities", icon: ChartLineUp },
    { to: "/school/trips", label: "Educational Trips", icon: Bus },
    { to: "/school/sick-leaves", label: "Sick Leaves", icon: Heartbeat },
    { to: "/school/performance", label: "Teacher Performance", icon: ChartLineUp },
    { to: "/school/notifications", label: "Notifications", icon: BellRinging },
    { to: "/school/uploads", label: "Bulk Uploads", icon: UploadSimple },
    { to: "/school/subscription", label: "Subscription", icon: Package },
    { to: "/school/settings", label: "Branding", icon: ShieldCheck },
    { to: "/school/audit", label: "Audit log", icon: ShieldCheck },
    { to: "/student-search", label: "Student Analytics", icon: MagnifyingGlass },
    { to: "/profile", label: "My Profile", icon: UserCircle },
  ],
  teacher: [
    { to: "/teacher", label: "My Dashboard", icon: Gauge, end: true },
    { to: "/chat", label: "Chat", icon: ChatCircleDots },
    { to: "/teacher/attendance-cards", label: "Take Attendance", icon: ClipboardText },
    { to: "/teacher/attendance", label: "Attendance (grid)", icon: ClipboardText },
    { to: "/teacher/marks", label: "Enter Marks", icon: FileText },
    { to: "/teacher/students", label: "My Students", icon: GraduationCap },
    { to: "/teacher/classes", label: "Classes & Subjects", icon: BookOpen },
    { to: "/teacher/expenses", label: "My Expenses", icon: MoneyWavy },
    { to: "/teacher/uploads", label: "Bulk Uploads", icon: UploadSimple },
    { to: "/teacher/sick-leaves", label: "Sick Leaves", icon: Heartbeat },
    { to: "/teacher/timetable", label: "My Timetable", icon: Calendar },
    { to: "/teacher/duties", label: "My Schedule", icon: Calendar },
    { to: "/teacher/calendar", label: "Calendar", icon: Calendar },
    { to: "/teacher/trips", label: "Educational Trips", icon: Bus },
    { to: "/teacher/performance", label: "My Performance", icon: ChartLineUp },
    { to: "/profile", label: "My Profile", icon: UserCircle },
    { to: "/student-search", label: "Student Search", icon: MagnifyingGlass },
  ],
  accounts: [
    { to: "/accounts", label: "Fee Dashboard", icon: Gauge, end: true },
    { to: "/accounts/fee-items", label: "Fee Catalog", icon: Receipt },
    { to: "/accounts/fees", label: "Fee Structures", icon: Receipt },
    { to: "/accounts/fee-tracker", label: "Fee Tracker", icon: ChartPieSlice },
    { to: "/accounts/payments", label: "Payments", icon: ChartPieSlice },
    { to: "/accounts/expenses", label: "Expenses & Reimbursements", icon: MoneyWavy },
    { to: "/student-search", label: "Student Search", icon: MagnifyingGlass },
    { to: "/profile", label: "My Profile", icon: UserCircle },
  ],
  parent: [
    { to: "/parent", label: "My Child", icon: House, end: true },
    { to: "/chat", label: "Chat", icon: ChatCircleDots },
    { to: "/parent/calendar", label: "Calendar", icon: Calendar },
    { to: "/parent/trips", label: "Educational Trips", icon: Bus },
    { to: "/parent/sick-leaves", label: "Sick Leaves", icon: Heartbeat },
    { to: "/profile", label: "My Profile", icon: UserCircle },
  ],
};

function NavList({ items, onItemClick, badges = {} }) {
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
          <span className="flex-1">{label}</span>
          {badges[to] > 0 ? (
            <span
              className="ml-auto inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-semibold bg-status-danger text-white"
              data-testid={`nav-badge-${to.replace(/\//g, "-").replace(/^-+/, "")}`}
            >
              {badges[to] > 99 ? "99+" : badges[to]}
            </span>
          ) : null}
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
  const sickPending = useSickLeavePending();
  const { count: unreadNotifs } = useUnreadNotifications();
  const { count: unreadChat } = useUnreadChat();
  if (!user) return null;
  let items = NAV_BY_ROLE[user.role] || [];

  // Lockdown: when a school is awaiting approval (or rejected, or no request yet),
  // only show the Dashboard overview + Subscription page so the admin can submit/track the request.
  const approvalStatus = user?.subscription_state?.approval_status;
  if (user.role === "school_admin" && approvalStatus && approvalStatus !== "approved") {
    items = items.filter((it) => it.to === "/school" || it.to === "/school/subscription");
  }

  const badges = {
    "/school/sick-leaves": user.role === "school_admin" ? sickPending : 0,
    "/teacher/sick-leaves": user.role === "teacher" ? sickPending : 0,
    "/school/notifications": user.role === "school_admin" ? unreadNotifs : 0,
    "/platform/notifications": user.role === "platform_admin" ? unreadNotifs : 0,
    "/chat": ["school_admin", "teacher", "parent"].includes(user.role) ? unreadChat : 0,
  };

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-60 shrink-0 bg-bg border-r border-line h-screen sticky top-0" data-testid="app-sidebar">
        <Header />
        <NavList items={items} badges={badges} />
        <Footer />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" data-testid="mobile-drawer">
          <div className="absolute inset-0 bg-black/40" onClick={onCloseMobile} />
          <aside className="relative w-72 max-w-[85vw] h-full bg-bg border-r border-line flex flex-col">
            <button onClick={onCloseMobile} className="absolute top-3 right-3 btn-ghost p-1.5" data-testid="mobile-drawer-close"><X size={16} /></button>
            <Header />
            <NavList items={items} onItemClick={onCloseMobile} badges={badges} />
            <Footer />
          </aside>
        </div>
      )}
    </>
  );
}
