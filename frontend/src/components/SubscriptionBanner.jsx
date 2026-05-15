import React from "react";
import { Link } from "react-router-dom";
import { Warning, Clock } from "@phosphor-icons/react";

/**
 * Renders a top banner when the user's school subscription is expiring or expired.
 * Reads `user.subscription_state` provided by /auth/me.
 *
 * States:
 *  - is_expiring_soon (days_left <= 7) → amber, "Subscription expires in N days"
 *  - is_in_grace                       → red,   "Subscription expired N days ago — grace period"
 *  - is_expired                        → red,   "Write actions blocked. Please renew now."
 */
export default function SubscriptionBanner({ user }) {
  const s = user?.subscription_state;
  if (!s || s.status !== "active") return null;
  if (!(s.is_expiring_soon || s.is_in_grace || s.is_expired)) return null;

  const isParent = user.role === "parent";
  const isSchoolAdmin = user.role === "school_admin";

  let bg = "bg-amber-100 border-amber-300 text-amber-900";
  let Icon = Clock;
  let label = "";
  if (s.is_expired) {
    bg = "bg-status-danger/10 border-status-danger/40 text-status-danger";
    Icon = Warning;
    label = `Subscription expired on ${(s.valid_until || "").slice(0, 10)}. New entries are blocked until you renew.`;
  } else if (s.is_in_grace) {
    bg = "bg-status-danger/10 border-status-danger/40 text-status-danger";
    Icon = Warning;
    const overdue = Math.abs(s.days_left || 0);
    label = `Subscription expired ${overdue} day${overdue === 1 ? "" : "s"} ago. You're in the grace period — renew to avoid feature lockout.`;
  } else {
    label = `Subscription expires in ${s.days_left} day${s.days_left === 1 ? "" : "s"} (${(s.valid_until || "").slice(0, 10)}). Renew to keep all features active.`;
  }

  return (
    <div
      className={`flex items-center gap-3 px-4 lg:px-8 py-2.5 border-b ${bg}`}
      data-testid="subscription-banner"
      role="alert"
    >
      <Icon size={18} weight="duotone" className="shrink-0" />
      <div className="text-sm leading-snug flex-1">{label}</div>
      {isSchoolAdmin && (
        <Link
          to="/school/subscription"
          className="btn-secondary text-xs px-3 py-1.5 whitespace-nowrap"
          data-testid="banner-renew-btn"
        >
          Renew now
        </Link>
      )}
      {isParent && (
        <span className="text-xs opacity-70">Please ask your school admin to renew.</span>
      )}
    </div>
  );
}
