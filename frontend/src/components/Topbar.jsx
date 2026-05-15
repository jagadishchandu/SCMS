import React, { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import { ROLE_LABELS } from "../lib/utils";
import { List, SignOut, Sun, Moon, GraduationCap, Key } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { api, formatApiError } from "../lib/api";
import { Modal } from "./Modal";
import toast from "react-hot-toast";

export default function Topbar({ schoolName, onToggleMobile }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();
  const [branding, setBranding] = useState(null);
  const [pwOpen, setPwOpen] = useState(false);

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
          <button
            onClick={() => setPwOpen(true)}
            className="btn-ghost p-2"
            aria-label="Change password"
            title="Change password"
            data-testid="change-password-btn"
          >
            <Key size={18} weight="bold" />
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
      <ChangePasswordModal open={pwOpen} onClose={() => setPwOpen(false)} />
    </header>
  );
}

function ChangePasswordModal({ open, onClose }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const reset = () => { setCurrent(""); setNext(""); setConfirm(""); };

  const submit = async (e) => {
    e.preventDefault();
    if (next.length < 6) { toast.error("New password must be at least 6 characters"); return; }
    if (next !== confirm) { toast.error("New password and confirmation do not match"); return; }
    if (next === current) { toast.error("New password must be different from current"); return; }
    setBusy(true);
    try {
      await api.post("/users/me/change-password", { current_password: current, new_password: next });
      toast.success("Password updated. Please sign in again.");
      reset();
      onClose();
      // Force re-login so the new password is the source of truth for the session.
      await logout();
      navigate("/login", { replace: true });
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title="Change your password" size="sm" testId="change-password-modal">
      <form onSubmit={submit} className="space-y-3" data-testid="change-password-form">
        <div>
          <label className="label">Current password</label>
          <input type="password" required className="input" value={current} onChange={(e) => setCurrent(e.target.value)} data-testid="cp-current-input" />
        </div>
        <div>
          <label className="label">New password</label>
          <input type="password" required minLength={6} className="input" value={next} onChange={(e) => setNext(e.target.value)} data-testid="cp-new-input" />
          <p className="text-xs text-ink-muted mt-1">At least 6 characters.</p>
        </div>
        <div>
          <label className="label">Confirm new password</label>
          <input type="password" required minLength={6} className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} data-testid="cp-confirm-input" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={() => { reset(); onClose(); }}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="cp-submit-btn">
            {busy ? "Updating…" : "Update password"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
