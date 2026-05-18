import React from "react";
import { NavLink } from "react-router-dom";
import { House, Calendar, Receipt, ChatCircleDots } from "@phosphor-icons/react";
import { useAuth } from "../contexts/AuthContext";
import { useUnreadChat } from "../hooks/useUnreadChat";

const ITEMS = {
  parent: [
    { to: "/parent", label: "Home", icon: House, end: true },
    { to: "/chat", label: "Chat", icon: ChatCircleDots, badgeKey: "chat" },
    { to: "/parent/calendar", label: "Calendar", icon: Calendar },
    { to: "/student-search", label: "Reports", icon: Receipt },
  ],
  teacher: [
    { to: "/teacher", label: "Home", icon: House, end: true },
    { to: "/chat", label: "Chat", icon: ChatCircleDots, badgeKey: "chat" },
    { to: "/teacher/attendance-cards", label: "Attend", icon: Receipt },
    { to: "/teacher/timetable", label: "Schedule", icon: Calendar },
  ],
  school_admin: [
    { to: "/school", label: "Home", icon: House, end: true },
    { to: "/chat", label: "Chat", icon: ChatCircleDots, badgeKey: "chat" },
    { to: "/school/students", label: "Students", icon: Receipt },
    { to: "/school/calendar", label: "Calendar", icon: Calendar },
  ],
};

export default function MobileBottomNav() {
  const { user } = useAuth();
  const { count: unreadChat } = useUnreadChat();
  if (!user) return null;
  const items = ITEMS[user.role];
  if (!items) return null;

  const badgeFor = (key) => {
    if (key === "chat") return unreadChat;
    return 0;
  };

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-bg-surface border-t border-line" data-testid="mobile-bottom-nav">
      <ul className={`grid`} style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {items.map(({ to, label, icon: Icon, end, badgeKey }) => {
          const count = badgeKey ? badgeFor(badgeKey) : 0;
          return (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex flex-col items-center justify-center gap-1 py-2.5 text-[11px] relative ${
                    isActive ? "text-primary font-medium" : "text-ink-muted"
                  }`
                }
                data-testid={`bottom-nav-${to.replace(/\//g,"-").replace(/^-+/,"")}`}
              >
                <span className="relative">
                  <Icon size={20} weight="regular" />
                  {count > 0 ? (
                    <span
                      className="absolute -top-1.5 -right-2 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full text-[9px] font-semibold bg-status-danger text-white chat-unread-badge"
                      data-testid={`bottom-nav-badge-${badgeKey}`}
                    >
                      {count > 9 ? "9+" : count}
                    </span>
                  ) : null}
                </span>
                {label}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
