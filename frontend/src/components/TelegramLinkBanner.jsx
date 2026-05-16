import React, { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Link } from "react-router-dom";
import { ChatCircleText, ArrowSquareOut, X, Phone, Envelope } from "@phosphor-icons/react";

/**
 * Mandatory-channel link banner.
 *
 * Each school's super admin (or the platform super admin) decides which
 * communication channels are MANDATORY for that school (any of email /
 * whatsapp / telegram). This banner surfaces one strip per unlinked mandatory
 * channel so users can self-serve linking.
 *
 * Read from /auth/me:
 *   - user.school_mandatory_channels: string[]
 *   - user.email_linked / phone_linked / telegram_linked: bool
 *   - user.telegram_bot_username + telegram_link_url for the Telegram CTA
 *
 * Each banner is dismissible per-session (sessionStorage), but reappears on
 * next session until the user actually links.
 */
export default function TelegramLinkBanner() {
  const { user } = useAuth();
  const [dismissed, setDismissed] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("channel_banner_dismissed") || "{}"); }
    catch { return {}; }
  });

  if (!user) return null;
  const mandatory = user.school_mandatory_channels || ["telegram"];

  const dismiss = (key) => {
    const next = { ...dismissed, [key]: 1 };
    setDismissed(next);
    sessionStorage.setItem("channel_banner_dismissed", JSON.stringify(next));
  };

  const banners = [];

  if (mandatory.includes("telegram") && !user.telegram_linked && user.telegram_bot_username && !dismissed.telegram) {
    const linkUrl = user.telegram_link_url || `https://t.me/${user.telegram_bot_username}`;
    banners.push(
      <Banner
        key="telegram"
        testId="telegram-link-banner"
        icon={<ChatCircleText size={20} weight="duotone" className="text-status-warning shrink-0" />}
        title="📲 Link Telegram to receive school updates"
        body={
          user.role === "parent"
            ? "Telegram is required by this school. Once linked, you'll receive attendance, fees, exam dates, syllabus & holiday alerts for your child."
            : user.role === "teacher"
              ? "Telegram is required by this school. Once linked, you'll receive your timetable, duty assignments, holidays and school calendar updates."
              : "Telegram is required by this school — once linked you'll receive school operational alerts in real time."
        }
        cta={{ href: linkUrl, label: "Link now", external: true, testId: "telegram-link-cta" }}
        onClose={() => dismiss("telegram")}
        closeTestId="telegram-link-banner-close"
      />
    );
  }

  if (mandatory.includes("whatsapp") && !user.phone_linked && !dismissed.whatsapp) {
    banners.push(
      <Banner
        key="whatsapp"
        testId="whatsapp-link-banner"
        icon={<Phone size={20} weight="duotone" className="text-emerald-600 shrink-0" />}
        title="📞 Add a phone number for WhatsApp/SMS alerts"
        body="This school requires a phone number on file so urgent alerts can reach you over WhatsApp or SMS. Add it from your profile."
        cta={{ to: "/profile", label: "Update profile", testId: "whatsapp-link-cta" }}
        onClose={() => dismiss("whatsapp")}
        closeTestId="whatsapp-link-banner-close"
      />
    );
  }

  if (mandatory.includes("email") && !user.email_linked && !dismissed.email) {
    banners.push(
      <Banner
        key="email"
        testId="email-link-banner"
        icon={<Envelope size={20} weight="duotone" className="text-sky-600 shrink-0" />}
        title="✉️ Add an email address"
        body="This school requires every user to have an email address on file so digest summaries can be delivered."
        cta={{ to: "/profile", label: "Update profile", testId: "email-link-cta" }}
        onClose={() => dismiss("email")}
        closeTestId="email-link-banner-close"
      />
    );
  }

  if (banners.length === 0) return null;
  return <>{banners}</>;
}

function Banner({ icon, title, body, cta, onClose, testId, closeTestId }) {
  return (
    <div
      className="w-full bg-status-warning-bg/70 border-b border-status-warning/40 px-4 lg:px-8 py-2.5 flex items-center gap-3 text-sm"
      role="alert"
      data-testid={testId}
    >
      {icon}
      <div className="flex-1 min-w-0">
        <div className="font-medium text-ink">{title}</div>
        <div className="text-xs text-ink-soft truncate">{body}</div>
      </div>
      {cta && cta.href && (
        <a
          href={cta.href}
          target={cta.external ? "_blank" : undefined}
          rel={cta.external ? "noopener noreferrer" : undefined}
          className="btn-primary text-xs whitespace-nowrap inline-flex items-center gap-1.5"
          data-testid={cta.testId}
        >
          {cta.label} {cta.external && <ArrowSquareOut size={12} weight="bold" />}
        </a>
      )}
      {cta && cta.to && (
        <Link
          to={cta.to}
          className="btn-primary text-xs whitespace-nowrap inline-flex items-center gap-1.5"
          data-testid={cta.testId}
        >
          {cta.label}
        </Link>
      )}
      <button
        type="button"
        className="btn-ghost p-1 shrink-0"
        title="Hide for this session"
        onClick={onClose}
        data-testid={closeTestId}
      >
        <X size={14} />
      </button>
    </div>
  );
}
