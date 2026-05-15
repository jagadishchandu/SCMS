import React from "react";
import { NavLink } from "react-router-dom";
import { House, Calendar, Receipt, BellRinging } from "@phosphor-icons/react";
import { useAuth } from "../contexts/AuthContext";

const ITEMS = {
  parent: [
    { to: "/parent", label: "Home", icon: House, end: true },
    { to: "/parent/calendar", label: "Calendar", icon: Calendar },
    { to: "/student-search", label: "Reports", icon: Receipt },
  ],
};

export default function MobileBottomNav() {
  const { user } = useAuth();
  if (!user) return null;
  const items = ITEMS[user.role];
  if (!items) return null;

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-bg-surface border-t border-line" data-testid="mobile-bottom-nav">
      <ul className="grid grid-cols-3">
        {items.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center gap-1 py-2.5 text-[11px] ${
                  isActive ? "text-primary font-medium" : "text-ink-muted"
                }`
              }
              data-testid={`bottom-nav-${to.replace(/\//g,"-").replace(/^-+/,"")}`}
            >
              <Icon size={20} weight="regular" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
