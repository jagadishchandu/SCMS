import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export const ROLE_LABELS = {
  platform_admin: "Platform Super Admin",
  school_admin: "School Super Admin",
  teacher: "Teacher",
  accounts: "Accounts",
  parent: "Parent",
  student: "Student",
};

export const ROLE_HOME = {
  platform_admin: "/platform",
  school_admin: "/school",
  teacher: "/teacher",
  accounts: "/accounts",
  parent: "/parent",
  student: "/parent",
};

export const ATTENDANCE_STATUSES = [
  { value: "present", label: "Present", color: "success" },
  { value: "absent", label: "Absent", color: "danger" },
  { value: "sick", label: "Sick Leave", color: "warning" },
  { value: "late", label: "Late", color: "info" },
  { value: "half_day", label: "Half Day", color: "warning" },
  { value: "excused", label: "Excused", color: "neutral" },
];

export function statusBadge(status) {
  const s = ATTENDANCE_STATUSES.find((x) => x.value === status);
  return s ? `badge-${s.color}` : "badge-neutral";
}

export function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function currency(n) {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);
}

export const CHART_COLORS = ["#4E5B3A", "#B7A77A", "#D4A373", "#8F9C82", "#6B8E23", "#E9C46A"];
