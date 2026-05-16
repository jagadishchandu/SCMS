import React, { useEffect, useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { api, formatApiError } from "../lib/api";
import { PageHeader, Section } from "../components/Primitives";
import {
  TelegramLogo, CheckCircle, XCircle, ArrowSquareOut, Copy,
  Envelope, Phone, ShieldCheck, ArrowsClockwise,
} from "@phosphor-icons/react";
import toast from "react-hot-toast";

/**
 * Self-service profile page available to every authenticated user (teacher,
 * school_admin, accounts, parent). Surfaces:
 *   - account details (name, email, role, phone)
 *   - Telegram link status + QR code + one-click deep-link
 *   - which channels the school has marked mandatory
 *   - a refresh button to re-pull /auth/me after linking
 */
export default function Profile() {
  const { user, refresh } = useAuth();
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  const mandatory = user.school_mandatory_channels || ["telegram"];
  const linkUrl = user.telegram_link_url ||
    (user.telegram_bot_username ? `https://t.me/${user.telegram_bot_username}` : null);
  // Use a public QR image API so we don't need to bundle a JS QR lib.
  const qrUrl = linkUrl
    ? `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(linkUrl)}`
    : null;

  const copy = (txt) => navigator.clipboard.writeText(txt).then(() => toast.success("Copied"));

  const recheck = async () => {
    setBusy(true);
    try {
      await refresh();
      toast.success("Profile refreshed");
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid="profile-page">
      <PageHeader
        eyebrow="My Account"
        title={user.name || "My profile"}
        subtitle="Manage how the school can reach you. Linking Telegram is the fastest way to receive timetable, attendance and announcement alerts."
        actions={
          <button className="btn-secondary" onClick={recheck} disabled={busy} data-testid="profile-refresh-btn">
            <ArrowsClockwise size={14}/> {busy ? "Refreshing…" : "Refresh status"}
          </button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Section title="Account details">
          <div className="space-y-3 text-sm">
            <Row label="Name" value={user.name || "—"} />
            <Row label="Role" value={<span className="badge-neutral capitalize">{(user.role || "").replace("_", " ")}</span>} />
            <Row label="Email" value={user.email} icon={<Envelope size={14} />} onCopy={() => copy(user.email)} />
            <Row label="Phone" value={user.phone || "—"} icon={<Phone size={14} />} />
            {user.employee_id && <Row label="Employee ID" value={user.employee_id} />}
            {user.school_name && <Row label="School" value={user.school_name} icon={<ShieldCheck size={14} />} />}
          </div>
        </Section>

        <Section title="Communication channels">
          <div className="text-xs text-ink-muted mb-3" data-testid="profile-mandatory-channels">
            Your school requires:{" "}
            {mandatory.map((c) => (
              <span key={c} className="badge bg-primary-light text-primary mr-1 capitalize" data-testid={`mandatory-chip-${c}`}>{c}</span>
            ))}
          </div>
          <div className="space-y-2">
            <ChannelRow
              channel="email" label="Email" icon={<Envelope size={18} />}
              linked={!!user.email_linked} required={mandatory.includes("email")}
              hint={user.email}
            />
            <ChannelRow
              channel="whatsapp" label="WhatsApp / SMS" icon={<Phone size={18} />}
              linked={!!user.phone_linked} required={mandatory.includes("whatsapp")}
              hint={user.phone || "Add a phone number to receive WhatsApp/SMS alerts"}
            />
            <ChannelRow
              channel="telegram" label="Telegram" icon={<TelegramLogo size={18} weight={user.telegram_linked ? "fill" : "regular"} />}
              linked={!!user.telegram_linked} required={mandatory.includes("telegram")}
              hint={user.telegram_linked
                ? "Bot is linked and ready to deliver notifications."
                : "Tap the link button to open the bot in Telegram, then press Start."}
            />
          </div>
        </Section>
      </div>

      <div className="mt-6">
        <Section title="Link Telegram">
          {!user.telegram_bot_username ? (
            <div className="text-sm text-ink-muted" data-testid="profile-tg-disabled">
              Telegram integration is not enabled on this platform.
            </div>
          ) : user.telegram_linked ? (
            <div
              className="flex items-start gap-3 p-4 rounded-md bg-green-50 border border-green-200"
              data-testid="profile-tg-linked"
            >
              <CheckCircle size={22} weight="fill" className="text-green-700 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold text-green-900 flex items-center gap-1">
                  Telegram linked — you're all set
                </div>
                <div className="text-xs text-green-800 mt-1">
                  School notifications (timetable, attendance, holidays, exam updates) will be delivered to your Telegram chat in real time.
                </div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start" data-testid="profile-tg-unlinked">
              <div className="space-y-3">
                <div className="flex items-start gap-3 p-3 rounded-md bg-amber-50 border border-amber-200">
                  <XCircle size={20} weight="fill" className="text-amber-700 mt-0.5" />
                  <div className="text-sm text-amber-900">
                    <div className="font-semibold">Telegram not linked yet</div>
                    <div className="text-xs mt-1">
                      You'll miss real-time alerts until you link. It takes 10 seconds — no app install needed if Telegram is already on your phone.
                    </div>
                  </div>
                </div>
                <ol className="text-sm text-ink-soft list-decimal pl-5 space-y-1.5">
                  <li>Tap <strong>Open in Telegram</strong> below (or scan the QR code with your phone).</li>
                  <li>Press <strong>Start</strong> inside the chat with @{user.telegram_bot_username}.</li>
                  <li>Come back here and click <strong>Refresh status</strong> — the green badge will appear.</li>
                </ol>
                <div className="flex flex-wrap gap-2 pt-1">
                  <a
                    href={linkUrl} target="_blank" rel="noopener noreferrer"
                    className="btn-primary inline-flex items-center gap-1.5"
                    data-testid="profile-tg-open-btn"
                  >
                    <TelegramLogo size={16} weight="fill" /> Open in Telegram <ArrowSquareOut size={12} weight="bold" />
                  </a>
                  <button
                    type="button" className="btn-secondary inline-flex items-center gap-1.5"
                    onClick={() => copy(linkUrl)}
                    data-testid="profile-tg-copy-btn"
                  >
                    <Copy size={14} /> Copy link
                  </button>
                </div>
                <div className="text-xs text-ink-muted break-all">{linkUrl}</div>
              </div>
              {qrUrl && (
                <div className="flex flex-col items-center gap-2">
                  <img
                    src={qrUrl} alt="Telegram link QR"
                    className="w-56 h-56 rounded-md border border-line bg-white p-2"
                    data-testid="profile-tg-qr"
                  />
                  <div className="text-xs text-ink-muted">Scan from your phone's camera</div>
                </div>
              )}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

function Row({ label, value, icon, onCopy }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 border-b border-line/50 last:border-0">
      <div className="text-ink-muted text-xs uppercase tracking-wider">{label}</div>
      <div className="flex items-center gap-2 min-w-0">
        {icon}
        <div className="font-medium text-ink truncate">{value}</div>
        {onCopy && (
          <button type="button" className="btn-ghost p-1" onClick={onCopy} title="Copy"><Copy size={12} /></button>
        )}
      </div>
    </div>
  );
}

function ChannelRow({ channel, label, icon, linked, required, hint }) {
  return (
    <div
      className="flex items-center gap-3 p-3 rounded-md border border-line/70 bg-bg-subtle"
      data-testid={`channel-row-${channel}`}
    >
      <div className={linked ? "text-green-700" : "text-amber-700"}>{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="font-medium text-ink">{label}</span>
          {required && (
            <span className="badge bg-red-100 text-red-700 text-[10px]" data-testid={`channel-required-${channel}`}>Required</span>
          )}
        </div>
        <div className="text-xs text-ink-muted truncate">{hint}</div>
      </div>
      {linked ? (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-200" data-testid={`channel-status-${channel}-linked`}>
          <CheckCircle size={12} weight="fill" /> Linked
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200" data-testid={`channel-status-${channel}-unlinked`}>
          <XCircle size={12} weight="fill" /> Not linked
        </span>
      )}
    </div>
  );
}
