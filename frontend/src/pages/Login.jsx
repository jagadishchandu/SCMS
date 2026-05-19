import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate, Navigate, Link, useSearchParams } from "react-router-dom";
import { ROLE_HOME, ROLE_LABELS } from "../lib/utils";
import toast from "react-hot-toast";
import { GraduationCap, ArrowRight, IdentificationCard } from "@phosphor-icons/react";

// Roles available for login. The role chosen here MUST match the role on the account —
// otherwise the login is rejected (even for the Platform Super Admin).
const ROLES = [
  { value: "platform_admin", label: ROLE_LABELS.platform_admin,
    hint: "Operate the SCMS platform across all schools.",
    placeholder: "admin@yourorg.com" },
  { value: "school_admin", label: ROLE_LABELS.school_admin,
    hint: "Manage your school: students, teachers, fees, attendance.",
    placeholder: "principal@yourschool.edu" },
  { value: "teacher", label: ROLE_LABELS.teacher,
    hint: "Take attendance, enter marks, manage your class.",
    placeholder: "teacher@yourschool.edu" },
  { value: "accounts", label: ROLE_LABELS.accounts,
    hint: "Manage fees, payments, and receipts.",
    placeholder: "accounts@yourschool.edu" },
  { value: "parent", label: ROLE_LABELS.parent,
    hint: "View your child's attendance, marks and fees.",
    placeholder: "you@example.com" },
];

export default function Login() {
  const { user, login, logout } = useAuth();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const [role, setRole] = useState("school_admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  // Pre-fill from URL params — used by the QR code on the parent credential slip
  // (e.g. /login?role=parent&email=parent.stu-00010@xyz.school).
  useEffect(() => {
    const qrRole = search.get("role");
    const qrEmail = search.get("email");
    if (qrRole && ROLES.find((r) => r.value === qrRole)) setRole(qrRole);
    if (qrEmail) setEmail(qrEmail);
  }, [search]);

  useEffect(() => {
    if (user && user.role) navigate(ROLE_HOME[user.role] || "/", { replace: true });
  }, [user, navigate]);

  if (user === null) return null;
  if (user) return <Navigate to={ROLE_HOME[user.role] || "/"} replace />;

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const u = await login(email, password);
      // Strict role validation: the role chosen at login MUST match the account role.
      // No exceptions — even the Platform Super Admin must pick "Platform Super Admin".
      if (u.role !== role) {
        // Clear the cookie + auth state so the user isn't silently logged in.
        await logout();
        toast.error(
          `Wrong role selected. This account is not a "${ROLE_LABELS[role] || role}". ` +
          `Please select the correct role and try again.`,
        );
        setLoading(false);
        return;
      }
      toast.success(`Welcome, ${u.name}`);
      navigate(ROLE_HOME[u.role] || "/", { replace: true });
    } catch (err) {
      toast.error(err.message || "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  const current = ROLES.find((r) => r.value === role) || ROLES[0];

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-bg" data-testid="login-page">
      {/* Left side: form */}
      <div className="flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 mb-12">
            <div className="w-9 h-9 rounded-lg bg-primary text-primary-foreground grid place-items-center">
              <GraduationCap size={20} weight="duotone" />
            </div>
            <div>
              <div className="font-display text-lg font-semibold leading-none">SCMS</div>
              <div className="text-[10px] uppercase tracking-widest text-ink-muted mt-0.5">School Child Monitoring</div>
            </div>
          </div>

          <div className="overline mb-2">Sign in</div>
          <h1 className="font-display text-3xl lg:text-4xl font-medium tracking-tight mb-3">
            Welcome back to your school dashboard.
          </h1>
          <p className="text-ink-soft mb-8">
            Manage students, parents, teachers, attendance, exams, fees and notifications — all from one place.
          </p>

          <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
            <div>
              <label className="label">I'm signing in as</label>
              <div className="relative">
                <IdentificationCard
                  size={16}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none"
                />
                <select
                  className="input pl-9"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  data-testid="login-role-select"
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-ink-muted mt-1.5" data-testid="role-hint">{current.hint}</p>
            </div>

            <div>
              <label className="label">Email or Login ID</label>
              <input
                type="text" autoComplete="username" required
                className="input" placeholder={current.placeholder}
                value={email} onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
                autoCapitalize="none"
                spellCheck={false}
              />
              <p className="text-[11px] text-ink-muted mt-1">
                Use your full email (e.g. principal@school.edu) or the short login id your administrator gave you. Case doesn't matter.
              </p>
            </div>
            <div>
              <label className="label">Password</label>
              <input
                type="password" autoComplete="current-password" required
                className="input" placeholder="••••••••"
                value={password} onChange={(e) => setPassword(e.target.value)}
                data-testid="login-password-input"
              />
              <div className="flex justify-end mt-1.5">
                <Link to="/forgot-password" className="text-xs text-ink-muted hover:text-primary" data-testid="forgot-password-link">
                  Forgot password?
                </Link>
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full" data-testid="login-submit-btn">
              {loading ? "Signing in…" : (<>Sign in <ArrowRight size={16} /></>)}
            </button>
          </form>

          <p className="text-xs text-ink-muted mt-8" data-testid="no-account-help">
            Don't have an account? Your school administrator creates accounts for teachers, parents and
            accounts staff. Please ask them to send you an invite.
          </p>
        </div>
      </div>

      {/* Right side: hero */}
      <div className="hidden lg:block relative overflow-hidden bg-bg-subtle hero-grain">
        <img
          src="https://static.prod-images.emergentagent.com/jobs/41728215-3124-4536-9339-78ba88e973ed/images/a7e28c82e63311bdeda4dbc3d20ccb1c4ffcff86be9ad6000b3399e70e73be91.png"
          alt="" className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-tr from-primary/30 via-transparent to-terracotta/20" />
        <div className="relative h-full flex flex-col justify-end p-12 text-white">
          <div className="max-w-md backdrop-blur-sm bg-black/40 rounded-lg p-6 border border-white/10">
            <div className="text-xs uppercase tracking-widest opacity-80 mb-2">Built for schools</div>
            <h2 className="font-display text-2xl font-medium mb-2">
              One calm place for attendance, marks, fees and parent updates.
            </h2>
            <p className="text-sm opacity-90">
              Multi-school, role-based access, automatic WhatsApp-style alerts, and graphical student analytics.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
