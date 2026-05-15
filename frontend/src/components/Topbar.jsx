import React from "react";
import { useAuth } from "../contexts/AuthContext";
import { ROLE_LABELS } from "../lib/utils";
import { List, SignOut } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";

export default function Topbar({ schoolName, onToggleMobile }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-30 bg-white border-b border-line">
      <div className="flex items-center justify-between px-4 lg:px-8 py-3">
        <div className="flex items-center gap-3">
          <button className="lg:hidden btn-ghost p-2" onClick={onToggleMobile} data-testid="mobile-menu-toggle">
            <List size={20} />
          </button>
          <div>
            <div className="font-display text-base font-medium text-ink" data-testid="topbar-school">
              {schoolName || (user?.role === "platform_admin" ? "Platform Console" : "SCMS")}
            </div>
            <div className="text-[11px] uppercase tracking-widest text-ink-muted">
              {ROLE_LABELS[user?.role] || ""}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-2 text-sm text-ink-soft">
            <div className="w-8 h-8 rounded-full bg-primary-light text-primary grid place-items-center font-semibold text-xs">
              {user?.name?.[0]?.toUpperCase() || "U"}
            </div>
            <span data-testid="topbar-user-name">{user?.name}</span>
          </div>
          <button
            onClick={async () => { await logout(); navigate("/login"); }}
            className="md:hidden btn-ghost p-2"
            data-testid="topbar-logout-btn"
          >
            <SignOut size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}
