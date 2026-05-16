import React, { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { ChatCircleText, ArrowSquareOut, X } from "@phosphor-icons/react";

/**
 * Mandatory "Link Telegram" banner.
 *
 * Telegram is the school's official communication channel — every user is
 * strongly encouraged (and at the school's discretion, mandated) to link
 * their account so they receive timetable, attendance, exam, fee and
 * holiday updates in real time.
 *
 * The banner appears on every protected page when:
 *   - the user is logged in
 *   - user.telegram_chat_id is missing
 *   - user.telegram_bot_username is set (i.e. the platform has Telegram enabled)
 *
 * Users can collapse the banner (per-session via sessionStorage) but it
 * reappears on the next session until they actually link.
 */
export default function TelegramLinkBanner() {
  const { user } = useAuth();
  const [hidden, setHidden] = useState(() => sessionStorage.getItem("tg_banner_dismissed") === "1");

  if (!user) return null;
  if (user.telegram_linked) return null;
  if (!user.telegram_bot_username) return null;
  if (hidden) return null;

  const linkUrl = user.telegram_link_url || `https://t.me/${user.telegram_bot_username}`;

  return (
    <div
      className="w-full bg-status-warning-bg/70 border-b border-status-warning/40 px-4 lg:px-8 py-2.5 flex items-center gap-3 text-sm"
      role="alert"
      data-testid="telegram-link-banner"
    >
      <ChatCircleText size={20} weight="duotone" className="text-status-warning shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="font-medium text-ink">
          📲 Link Telegram to receive school updates
        </div>
        <div className="text-xs text-ink-soft truncate">
          Telegram is this school's official communication channel — once linked you'll receive
          {user.role === "parent"
            ? " attendance, fees, exam dates, syllabus & holiday alerts for your child."
            : user.role === "teacher"
              ? " your timetable, duty assignments, holidays and school calendar updates."
              : " school operational alerts in real time."}
        </div>
      </div>
      <a
        href={linkUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="btn-primary text-xs whitespace-nowrap inline-flex items-center gap-1.5"
        data-testid="telegram-link-cta"
      >
        Link now <ArrowSquareOut size={12} weight="bold" />
      </a>
      <button
        type="button"
        className="btn-ghost p-1 shrink-0"
        title="Hide for this session"
        onClick={() => { sessionStorage.setItem("tg_banner_dismissed", "1"); setHidden(true); }}
        data-testid="telegram-link-banner-close"
      >
        <X size={14} />
      </button>
    </div>
  );
}
