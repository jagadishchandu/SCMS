import React, { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate, Navigate } from "react-router-dom";
import { ROLE_HOME } from "../lib/utils";
import toast from "react-hot-toast";
import { GraduationCap, ArrowRight } from "@phosphor-icons/react";

const DEMO_ACCOUNTS = [
  { label: "School Admin", email: "principal@sunrise.edu", password: "School@123" },
  { label: "Teacher (Class Teacher)", email: "priya@sunrise.edu", password: "Teacher@123" },
  { label: "Accounts", email: "accounts@sunrise.edu", password: "Accounts@123" },
  { label: "Parent", email: "parent.stu-00001@sunrise.edu", password: "Parent@123" },
];

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

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
      toast.success(`Welcome, ${u.name}`);
      navigate(ROLE_HOME[u.role] || "/", { replace: true });
    } catch (err) {
      toast.error(err.message || "Sign in failed");
    } finally {
      setLoading(false);
    }
  };

  const fill = (acc) => { setEmail(acc.email); setPassword(acc.password); };

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
              <label className="label">Email</label>
              <input
                type="email" autoComplete="email" required
                className="input" placeholder="you@school.edu"
                value={email} onChange={(e) => setEmail(e.target.value)}
                data-testid="login-email-input"
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                type="password" autoComplete="current-password" required
                className="input" placeholder="••••••••"
                value={password} onChange={(e) => setPassword(e.target.value)}
                data-testid="login-password-input"
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full" data-testid="login-submit-btn">
              {loading ? "Signing in…" : (<>Sign in <ArrowRight size={16} /></>)}
            </button>
          </form>

          <div className="mt-10 pt-6 border-t border-line">
            <div className="overline mb-3">Demo accounts</div>
            <div className="grid grid-cols-1 gap-2">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.email}
                  onClick={() => fill(a)}
                  className="text-left bg-white border border-line rounded-lg px-3 py-2 text-sm hover:border-primary/40 transition flex items-center justify-between group"
                  data-testid={`demo-${a.label.toLowerCase().replace(/[^a-z]/g, "-")}`}
                >
                  <div>
                    <div className="font-medium text-ink">{a.label}</div>
                    <div className="text-xs text-ink-muted">{a.email}</div>
                  </div>
                  <span className="text-xs text-ink-muted group-hover:text-primary">use</span>
                </button>
              ))}
            </div>
          </div>
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
