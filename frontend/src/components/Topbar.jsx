import React, { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import { ROLE_LABELS } from "../lib/utils";
import { List, SignOut, Sun, Moon, GraduationCap } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

export default function Topbar({ schoolName, onToggleMobile }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const [branding, setBranding] = useState(null);

  useEffect(() => {
    if (user?.school_id) {
      api.get(`/schools/${user.school_id}`).then((r) => setBranding(r.data?.branding || null)).catch(() => {});
    }
  }, [user?.school_id]);

  const accent = branding?.primary_color;

  return (
    <header className="sticky top-0 z-30 bg-bg-surface border-b border-line backdrop-blur-sm">
      <div className="flex items-center justify-between px-4 lg:px-8 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <button className="lg:hidden btn-ghost p-2" onClick={onToggleMobile} data-testid="mobile-menu-toggle">
            <List size={20} />
          </button>
          {branding?.logo ? (
            <img src={branding.logo} alt="logo" className="w-9 h-9 rounded-lg object-cover border border-line shrink-0" data-testid="topbar-school-logo" />
          ) : user?.school_id ? (
            <div className="w-9 h-9 rounded-lg grid place-items-center text-white shrink-0" style={{ background: accent || "var(--primary)" }}>
              <GraduationCap size={18} weight="duotone" />
            </div>
          ) : null}
          <div className="min-w-0">
            <div className="font-display text-base font-medium text-ink truncate" data-testid="topbar-school">
              {schoolName || (user?.role === "platform_admin" ? "Platform Console" : "SCMS")}
            </div>
            <div className="text-[11px] uppercase tracking-widest text-ink-muted truncate">
              {branding?.tagline || ROLE_LABELS[user?.role] || ""}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={toggle} className="btn-ghost p-2" aria-label="Toggle theme" data-testid="theme-toggle-btn" title={theme === "dark" ? "Switch to light" : "Switch to dark"}>
            {theme === "dark" ? <Sun size={18} weight="bold" /> : <Moon size={18} weight="bold" />}
          </button>
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
