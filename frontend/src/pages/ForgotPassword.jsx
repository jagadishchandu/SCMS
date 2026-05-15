import React, { useState } from "react";
import { Link, useNavigate, Navigate } from "react-router-dom";
import { api, formatApiError } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { GraduationCap, ArrowRight, PaperPlaneTilt, ShieldCheck, ArrowLeft } from "@phosphor-icons/react";
import toast from "react-hot-toast";

export default function ForgotPassword() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1); // 1=enter email, 2=enter code+new pw
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  const requestCode = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/password-reset/request", { email });
      toast.success(data.message || "If your account exists and has Telegram linked, a code was sent.");
      setStep(2);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const verifyCode = async (e) => {
    e.preventDefault();
    if (newPw.length < 6) { toast.error("New password must be at least 6 characters"); return; }
    if (newPw !== confirmPw) { toast.error("Passwords do not match"); return; }
    setBusy(true);
    try {
      await api.post("/auth/password-reset/verify", {
        email, code: code.trim(), new_password: newPw,
      });
      toast.success("Password updated. Please sign in with your new password.");
      navigate("/login", { replace: true });
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setBusy(true);
    try {
      await api.post("/auth/password-reset/request", { email });
      toast.success("If still eligible, a fresh code was sent.");
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-bg" data-testid="forgot-password-page">
      <div className="flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 mb-12">
            <div className="w-9 h-9 rounded-lg bg-primary text-primary-foreground grid place-items-center">
              <GraduationCap size={20} weight="duotone" />
            </div>
            <div>
              <div className="font-display text-lg font-semibold leading-none">SCMS</div>
              <div className="text-[10px] uppercase tracking-widest text-ink-muted mt-0.5">Reset password</div>
            </div>
          </div>

          <div className="overline mb-2">{step === 1 ? "Step 1 of 2" : "Step 2 of 2"}</div>
          <h1 className="font-display text-3xl lg:text-4xl font-medium tracking-tight mb-3">
            {step === 1 ? "Forgot your password?" : "Enter your Telegram code."}
          </h1>
          <p className="text-ink-soft mb-8">
            {step === 1 ? (
              <>We'll send a 6-digit verification code to the <strong>Telegram chat</strong> linked to your SCMS account. If you haven't linked Telegram yet, please contact your school administrator.</>
            ) : (
              <>Check the SCMS bot in Telegram for a 6-digit code we just sent. It expires in 10 minutes.</>
            )}
          </p>

          {step === 1 ? (
            <form onSubmit={requestCode} className="space-y-4" data-testid="forgot-step1-form">
              <div>
                <label className="label">Email</label>
                <input
                  type="email" autoComplete="email" required
                  className="input" placeholder="you@yourschool.edu"
                  value={email} onChange={(e) => setEmail(e.target.value)}
                  data-testid="forgot-email-input"
                />
              </div>
              <button type="submit" disabled={busy || !email} className="btn-primary w-full" data-testid="forgot-send-code-btn">
                {busy ? "Sending…" : (<>Send code to Telegram <PaperPlaneTilt size={16} /></>)}
              </button>
              <Link to="/login" className="flex items-center justify-center gap-1.5 text-sm text-ink-soft hover:text-ink mt-3" data-testid="forgot-back-to-login">
                <ArrowLeft size={14} /> Back to sign in
              </Link>
            </form>
          ) : (
            <form onSubmit={verifyCode} className="space-y-4" data-testid="forgot-step2-form">
              <div>
                <label className="label">Email</label>
                <input type="email" className="input" value={email} disabled data-testid="forgot-email-readonly" />
              </div>
              <div>
                <label className="label">6-digit code from Telegram</label>
                <input
                  type="text" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required
                  className="input tracking-[0.5em] text-center text-xl font-mono"
                  placeholder="000000"
                  value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  data-testid="forgot-code-input"
                />
              </div>
              <div>
                <label className="label">New password</label>
                <input
                  type="password" required minLength={6}
                  className="input" placeholder="At least 6 characters"
                  value={newPw} onChange={(e) => setNewPw(e.target.value)}
                  data-testid="forgot-newpw-input"
                />
              </div>
              <div>
                <label className="label">Confirm new password</label>
                <input
                  type="password" required minLength={6}
                  className="input" placeholder="Re-enter password"
                  value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)}
                  data-testid="forgot-confirmpw-input"
                />
              </div>
              <button type="submit" disabled={busy || code.length !== 6 || !newPw} className="btn-primary w-full" data-testid="forgot-verify-btn">
                {busy ? "Updating…" : (<>Update password <ShieldCheck size={16} /></>)}
              </button>
              <div className="flex items-center justify-between text-sm mt-3">
                <button type="button" className="text-ink-soft hover:text-ink flex items-center gap-1" onClick={() => setStep(1)} data-testid="forgot-step-back">
                  <ArrowLeft size={14} /> Change email
                </button>
                <button type="button" className="text-ink-soft hover:text-ink" onClick={resend} disabled={busy} data-testid="forgot-resend-btn">
                  Didn't get a code? Resend
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      <div className="hidden lg:block relative overflow-hidden bg-bg-subtle hero-grain">
        <img
          src="https://static.prod-images.emergentagent.com/jobs/41728215-3124-4536-9339-78ba88e973ed/images/a7e28c82e63311bdeda4dbc3d20ccb1c4ffcff86be9ad6000b3399e70e73be91.png"
          alt="" className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-tr from-primary/30 via-transparent to-terracotta/20" />
        <div className="relative h-full flex flex-col justify-end p-12 text-white">
          <div className="max-w-md backdrop-blur-sm bg-black/40 rounded-lg p-6 border border-white/10">
            <div className="text-xs uppercase tracking-widest opacity-80 mb-2">Secure recovery</div>
            <h2 className="font-display text-2xl font-medium mb-2">
              Reset your password through Telegram.
            </h2>
            <p className="text-sm opacity-90">
              We never send reset codes over email — they go to the Telegram chat you've already linked to your SCMS account, keeping recovery fast and out of reach of phishing.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
