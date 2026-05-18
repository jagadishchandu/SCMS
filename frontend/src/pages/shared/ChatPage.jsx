import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { useMessagingSocket } from "../../hooks/useMessagingSocket";
import { useWebPush } from "../../hooks/useWebPush";
import { PageHeader, Empty } from "../../components/Primitives";
import {
  ChatCircleDots, PaperPlaneTilt, MagnifyingGlass, CaretLeft,
  CheckCircle, Check, Circle, BellSimpleSlash, BellSimple, Paperclip,
  FilePdf, X as XIcon, At, Megaphone, Newspaper, WhatsappLogo, TelegramLogo,
  EnvelopeSimple, DeviceMobile, UsersThree, PushPin, PushPinSlash, Buildings,
  ClipboardText, Receipt, GraduationCap, Heartbeat, CalendarBlank, AirplaneTilt,
  Lightning,
} from "@phosphor-icons/react";
import toast from "react-hot-toast";

const ROLE_BADGE = {
  teacher: { label: "Teacher", cls: "bg-status-info-bg text-status-info" },
  parent: { label: "Parent", cls: "bg-status-warning-bg text-status-warning" },
  school_admin: { label: "Admin", cls: "bg-primary-light text-primary" },
  system: { label: "School", cls: "bg-primary text-white" },
};

const MAX_ATT_BYTES = 1_800_000; // ~1.8MB raw → ~2.4MB base64
const ALLOWED_MIMES = ["image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"];

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = () => reject(r.error);
    r.onload = () => resolve(String(r.result || ""));
    r.readAsDataURL(file);
  });
}

function renderTextWithMentions(text, peerName) {
  if (!text || !peerName) return text;
  const parts = [];
  let last = 0;
  const re = /@([A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*){0,2})/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const candidate = m[1].trim();
    const firstToken = candidate.split(/\s+/)[0].toLowerCase();
    const matches = candidate.toLowerCase() === peerName.toLowerCase()
      || firstToken === peerName.split(/\s+/)[0].toLowerCase();
    if (matches) {
      if (m.index > last) parts.push(text.slice(last, m.index));
      parts.push(
        <span key={`m-${m.index}`} className="chat-mention">@{candidate}</span>
      );
      last = m.index + m[0].length;
    }
  }
  if (last === 0) return text;
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function timeShort(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch (_e) { return ""; }
}

function fullTime(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString(); } catch (_e) { return ""; }
}

function initials(name = "?") {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0].toUpperCase())
    .join("") || "?";
}

function Avatar({ name, online, size = 40, isSystem = false }) {
  if (isSystem) {
    return (
      <div
        className="relative rounded-full grid place-items-center font-display select-none chat-avatar chat-avatar-system"
        style={{ width: size, height: size }}
        data-testid="chat-avatar-system"
      >
        <Buildings size={size * 0.5} weight="duotone" />
      </div>
    );
  }
  return (
    <div
      className="relative rounded-full grid place-items-center font-display font-medium select-none chat-avatar"
      style={{
        width: size, height: size,
        background: "linear-gradient(135deg, var(--primary-light), var(--sand))",
        color: "var(--primary)",
        fontSize: size * 0.36,
      }}
      data-testid="chat-avatar"
    >
      {initials(name)}
      {online ? (
        <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-status-success ring-2 ring-bg-surface chat-pulse" />
      ) : null}
    </div>
  );
}

function ContactRow({ contact, active, onClick }) {
  const badge = ROLE_BADGE[contact.role] || { label: contact.role, cls: "badge-neutral" };
  const isMention = (contact.mentions || 0) > 0;
  const isSystem = !!contact.is_system;
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`chat-contact-${contact.id}`}
      className={`w-full text-left px-3 py-3 flex items-center gap-3 rounded-lg transition-all duration-200 chat-contact-row ${
        active ? "bg-primary-light/60 ring-1 ring-primary/30" : "hover:bg-bg-subtle"
      } ${isSystem ? "chat-contact-system" : ""}`}
    >
      <Avatar name={contact.name} online={contact.online} isSystem={isSystem} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <div className="font-medium text-sm truncate text-ink flex items-center gap-1.5">
            {contact.name}
            {!isSystem && contact.muted ? (
              <BellSimpleSlash size={12} className="text-ink-muted shrink-0" data-testid={`chat-muted-icon-${contact.id}`} />
            ) : null}
          </div>
          {contact.last_message_at ? (
            <div className="ml-auto text-[10px] text-ink-muted shrink-0">{timeShort(contact.last_message_at)}</div>
          ) : null}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className={`badge ${badge.cls} !text-[10px] !py-0`}>{badge.label}</span>
          <div className="text-xs text-ink-muted truncate flex-1">
            {contact.last_message_text || contact.context || (contact.online ? "Online now" : "Tap to chat")}
          </div>
        </div>
      </div>
      {isMention ? (
        <span
          className="ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-semibold bg-status-warning text-white chat-unread-badge"
          data-testid={`chat-mention-badge-${contact.id}`}
          title={`${contact.mentions} mention${contact.mentions > 1 ? "s" : ""}`}
        >
          @
        </span>
      ) : null}
      {contact.unread > 0 && !isMention ? (
        <span
          className={`ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-semibold chat-unread-badge ${
            contact.muted ? "bg-ink-muted text-white" : "bg-status-danger text-white"
          }`}
          data-testid={`chat-unread-${contact.id}`}
        >
          {contact.unread > 99 ? "99+" : contact.unread}
        </span>
      ) : null}
    </button>
  );
}

function AttachmentView({ att, mine }) {
  if (!att) return null;
  const isImage = (att.type || "").startsWith("image/");
  if (isImage) {
    return (
      <a href={att.data_url} target="_blank" rel="noreferrer" className="chat-attachment-img-link" data-testid="chat-att-image">
        <img src={att.data_url} alt={att.name} className="chat-attachment-img" />
      </a>
    );
  }
  // PDF
  return (
    <a
      href={att.data_url}
      download={att.name}
      target="_blank"
      rel="noreferrer"
      className={`chat-attachment-file ${mine ? "is-mine" : ""}`}
      data-testid="chat-att-pdf"
    >
      <FilePdf size={28} weight="duotone" />
      <div className="min-w-0">
        <div className="text-xs font-medium truncate">{att.name}</div>
        <div className="text-[10px] opacity-70">PDF · {Math.round((att.size || 0) / 1024)} KB</div>
      </div>
    </a>
  );
}

const KIND_META = {
  attendance: { label: "Attendance Alert",   color: "warning", icon: ClipboardText },
  fee:        { label: "Fee Reminder",        color: "danger",  icon: Receipt },
  exam:       { label: "Exam Update",         color: "info",    icon: GraduationCap },
  sick:       { label: "Sick-leave Update",   color: "info",    icon: Heartbeat },
  holiday:    { label: "Holiday Notice",      color: "success", icon: CalendarBlank },
  trip:       { label: "Trip Announcement",   color: "info",    icon: AirplaneTilt },
  general:    { label: "School Notice",       color: "neutral", icon: Buildings },
};

function MessageBubble({ msg, mine, peerName, hideReceipt = false, onPin = null, isPinned = false, onQuickReply = null, onSmartAction = null }) {
  const hasMention = Array.isArray(msg.mentions) && msg.mentions.length > 0;
  const onlyAttachment = !msg.text && msg.attachment;
  const isSystem = msg.sender_id === SYSTEM_PEER_ID || !!msg.kind;
  const kind = msg.kind || "general";
  const meta = KIND_META[kind] || KIND_META.general;
  const Icon = meta.icon;
  const quickReplies = Array.isArray(msg.quick_replies) ? msg.quick_replies : [];
  const alreadyReplied = !!msg.replied_at;
  const smartActions = Array.isArray(msg.smart_actions) ? msg.smart_actions : [];
  const smartDone = !!msg.smart_action_done;
  return (
    <div className={`flex w-full ${mine ? "justify-end" : "justify-start"} chat-msg-enter group-message`}>
      <div className={`max-w-[82%] md:max-w-[66%] ${mine ? "items-end" : "items-start"} flex flex-col gap-1 relative chat-msg-wrap`}>
        {onPin ? (
          <button
            type="button"
            className="chat-msg-pin-btn"
            onClick={() => onPin(msg)}
            title={isPinned ? "Already pinned" : "Pin this broadcast for 24h"}
            disabled={isPinned}
            data-testid={`chat-pin-msg-${msg.id}`}
            aria-label="Pin message"
          >
            <PushPin size={12} weight={isPinned ? "fill" : "regular"} />
          </button>
        ) : null}
        {msg.attachment ? <AttachmentView att={msg.attachment} mine={mine} /> : null}
        {!onlyAttachment ? (
          isSystem ? (
            <div
              className={`chat-system-card chat-system-card-${meta.color}`}
              title={fullTime(msg.created_at)}
              data-testid={`chat-msg-${msg.id}`}
            >
              <div className="chat-system-card-header">
                <span className={`chat-system-card-icon chat-system-card-icon-${meta.color}`}>
                  <Icon size={16} weight="duotone" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="chat-system-card-title">{msg.kind_label || meta.label}</div>
                  {msg.student_name ? (
                    <div className="chat-system-card-subtitle">
                      For <strong>{msg.student_name}</strong>
                      {msg.student_uid ? <span className="opacity-70"> · {msg.student_uid}</span> : null}
                    </div>
                  ) : msg.subject ? (
                    <div className="chat-system-card-subtitle">{msg.subject}</div>
                  ) : null}
                </div>
              </div>
              <div className="chat-system-card-body">
                {msg.text}
              </div>
            </div>
          ) : (
            <div
              className={`px-3.5 py-2 rounded-2xl text-sm leading-snug whitespace-pre-wrap break-words shadow-soft ${
                mine
                  ? "bg-primary text-primary-foreground rounded-br-md"
                  : "bg-bg-surface border border-line text-ink rounded-bl-md"
              } ${hasMention && !mine ? "chat-bubble-mention" : ""}`}
              title={fullTime(msg.created_at)}
              data-testid={`chat-msg-${msg.id}`}
            >
              {renderTextWithMentions(msg.text, peerName)}
            </div>
          )
        ) : null}

        {/* Quick replies (system bubbles only) */}
        {isSystem && onQuickReply && !alreadyReplied && quickReplies.length > 0 ? (
          <div className="chat-quick-replies" data-testid={`chat-quick-replies-${msg.id}`}>
            {quickReplies.map((qr) => (
              <button
                key={qr}
                type="button"
                className="chat-quick-reply"
                onClick={() => onQuickReply(msg, qr)}
                data-testid={`chat-quick-reply-${msg.id}-${qr.replace(/\s+/g, "-").toLowerCase()}`}
              >
                {qr}
              </button>
            ))}
          </div>
        ) : null}
        {isSystem && alreadyReplied ? (
          <div className="chat-quick-reply-done" data-testid={`chat-quick-reply-done-${msg.id}`}>
            <CheckCircle size={11} weight="fill" /> You replied: “{msg.reply_text || "—"}”
          </div>
        ) : null}

        {/* Smart-action suggestions on a parent quick-reply (recipient side) */}
        {!mine && onSmartAction && smartActions.length > 0 && !smartDone ? (
          <div className="chat-smart-actions" data-testid={`chat-smart-actions-${msg.id}`}>
            <div className="chat-smart-actions-label">
              <Lightning size={11} weight="fill" /> Suggested actions
            </div>
            <div className="chat-smart-actions-row">
              {smartActions.map((a) => (
                <button
                  key={a.action}
                  type="button"
                  className="chat-smart-action"
                  onClick={() => onSmartAction(msg, a)}
                  data-testid={`chat-smart-action-${msg.id}-${a.action}`}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {smartDone ? (
          <div className="chat-smart-action-done" data-testid={`chat-smart-done-${msg.id}`}>
            {msg.smart_action_outcome || `✅ Action taken: ${msg.smart_action_done}`}
          </div>
        ) : null}

        <div className={`text-[10px] flex items-center gap-1 px-1 ${mine ? "text-ink-muted" : "text-ink-muted"}`}>
          {!mine && !isSystem ? <span className="font-medium">{peerName}</span> : null}
          <span>{timeShort(msg.created_at)}</span>
          {mine ? (
            hideReceipt ? null : msg.read_at ? (
              <CheckCircle size={12} weight="fill" className="text-status-info" data-testid={`chat-read-${msg.id}`} />
            ) : (
              <Check size={12} className="text-ink-muted" data-testid={`chat-sent-${msg.id}`} />
            )
          ) : null}
        </div>
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1.5 px-3 py-2 rounded-2xl bg-bg-subtle text-ink-soft text-xs w-fit chat-typing" data-testid="chat-typing">
      <span className="chat-typing-dot" />
      <span className="chat-typing-dot" />
      <span className="chat-typing-dot" />
      <span className="ml-1">typing…</span>
    </div>
  );
}

function GroupRow({ group, active, onClick }) {
  const isOwner = group.is_owner;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left px-3 py-3 flex items-center gap-3 rounded-lg transition-all duration-200 chat-contact-row ${
        active ? "bg-primary-light/60 ring-1 ring-primary/30" : "hover:bg-bg-subtle"
      }`}
      data-testid={`chat-group-${group.id}`}
    >
      <div className="chat-group-avatar"><UsersThree size={20} weight="duotone" /></div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <div className="font-medium text-sm truncate text-ink flex items-center gap-1.5">
            {group.name}
            {isOwner ? <Megaphone size={11} className="text-primary" /> : null}
          </div>
          {group.last_message_at ? (
            <div className="ml-auto text-[10px] text-ink-muted shrink-0">{timeShort(group.last_message_at)}</div>
          ) : null}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="badge bg-primary-light text-primary !text-[10px] !py-0">
            {group.scope === "admin_to_teachers" ? "Admin → Teachers" : "Teacher → Parents"}
          </span>
          <div className="text-xs text-ink-muted truncate flex-1">
            {group.last_message_text || `${group.member_count} member${group.member_count === 1 ? "" : "s"}`}
          </div>
        </div>
      </div>
      {group.unread > 0 ? (
        <span
          className="ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-semibold bg-status-danger text-white chat-unread-badge"
          data-testid={`chat-group-unread-${group.id}`}
        >
          {group.unread > 99 ? "99+" : group.unread}
        </span>
      ) : null}
    </button>
  );
}

const SYSTEM_PEER_ID = "system::school-notifications";
const CHANNEL_META = {
  whatsapp: { icon: WhatsappLogo, label: "WhatsApp", cls: "chat-update-whatsapp" },
  telegram: { icon: TelegramLogo, label: "Telegram", cls: "chat-update-telegram" },
  sms: { icon: DeviceMobile, label: "SMS", cls: "chat-update-sms" },
  email: { icon: EnvelopeSimple, label: "Email", cls: "chat-update-email" },
};

function UpdateCard({ upd }) {
  const meta = CHANNEL_META[upd.channel] || { icon: Newspaper, label: upd.channel, cls: "" };
  const Icon = meta.icon;
  return (
    <article
      className={`chat-update-card ${meta.cls} ${upd.read_at ? "" : "is-unread"}`}
      data-testid={`chat-update-${upd.id}`}
    >
      <div className="chat-update-channel">
        <Icon size={16} weight="duotone" />
        <span>{meta.label}</span>
        <span className="ml-auto text-[10px] text-ink-muted">{timeShort(upd.created_at)}</span>
      </div>
      {upd.student_name ? (
        <div className="text-[11px] text-primary font-medium mt-1">
          For {upd.student_name} {upd.student_uid ? <span className="text-ink-muted font-normal">· {upd.student_uid}</span> : null}
        </div>
      ) : null}
      <div className="text-sm text-ink mt-1.5 whitespace-pre-wrap break-words">{upd.body}</div>
    </article>
  );
}

export default function ChatPage() {
  const { user } = useAuth();
  const [contacts, setContacts] = useState([]);
  const [groups, setGroups] = useState([]);
  const [loadingContacts, setLoadingContacts] = useState(true);
  const [active, setActive] = useState(null); // peer object OR group object (has scope)
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [peerTyping, setPeerTyping] = useState(false);
  const [sending, setSending] = useState(false);
  const [showListMobile, setShowListMobile] = useState(true);
  const [attachment, setAttachment] = useState(null); // {name,type,size,data_url}
  const [mentionMenu, setMentionMenu] = useState(false);
  const scrollRef = useRef(null);
  const typingDebounceRef = useRef(null);
  const peerTypingTimerRef = useRef(null);
  const inputRef = useRef(null);
  const fileInputRef = useRef(null);

  const { status: wsStatus, sendRaw, onEvent } = useMessagingSocket(!!user);
  const push = useWebPush(!!user);

  const isGroup = !!(active && active.scope);
  const isSystem = !!(active && (active.is_system || active.id === SYSTEM_PEER_ID));

  const loadContacts = useCallback(async () => {
    try {
      setLoadingContacts(true);
      const [c, g] = await Promise.all([
        api.get("/messaging/contacts").then((r) => r.data?.contacts || []),
        api.get("/messaging/groups").then((r) => r.data?.groups || []).catch(() => []),
      ]);
      setContacts(c);
      setGroups(g);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoadingContacts(false);
    }
  }, []);

  useEffect(() => { loadContacts(); }, [loadContacts]);

  const loadMessages = useCallback(async (target) => {
    try {
      if (target.scope) {
        // Group
        const r = await api.get(`/messaging/groups/${target.id}/messages`);
        setMessages(r.data?.messages || []);
        await api.post(`/messaging/groups/${target.id}/read`).catch(() => {});
        setGroups((gs) => gs.map((g) => g.id === target.id ? { ...g, unread: 0 } : g));
        return;
      }
      const [msgRes, settingsRes] = await Promise.all([
        api.get(`/messaging/conversations/${target.id}/messages`),
        api.get(`/messaging/conversations/${target.id}/settings`).catch(() => ({ data: { muted: false } })),
      ]);
      setMessages(msgRes.data?.messages || []);
      // Sync mute state into the active peer
      setActive((p) => p && p.id === target.id ? { ...p, muted: !!settingsRes.data?.muted } : p);
      setContacts((cs) => cs.map((c) => c.id === target.id ? { ...c, muted: !!settingsRes.data?.muted } : c));
      // Mark read
      await api.post(`/messaging/conversations/${target.id}/read`).catch(() => {});
      window.dispatchEvent(new Event("scms:chat:refresh-unread"));
      // Locally clear unread for this contact
      setContacts((cs) => cs.map((c) => c.id === target.id ? { ...c, unread: 0, mentions: 0 } : c));
    } catch (e) {
      toast.error(formatApiError(e));
    }
  }, []);

  const openChat = useCallback((target) => {
    setActive(target);
    setMessages([]);
    setPeerTyping(false);
    setShowListMobile(false);
    loadMessages(target);
    setTimeout(() => inputRef.current?.focus(), 200);
  }, [loadMessages]);

  // WebSocket events
  useEffect(() => {
    const off = onEvent((evt) => {
      if (!evt) return;
      if (evt.type === "message") {
        const m = evt.message;
        const peerId = m.sender_id === user?.id ? m.recipient_id : m.sender_id;
        // append to open chat
        if (active && peerId === active.id) {
          setMessages((prev) => {
            if (prev.some((x) => x.id === m.id)) return prev;
            return [...prev, m];
          });
          // I am viewing this chat — mark read immediately
          if (m.recipient_id === user?.id) {
            api.post(`/messaging/conversations/${peerId}/read`).catch(() => {});
            window.dispatchEvent(new Event("scms:chat:refresh-unread"));
          }
        }
        // update contact list preview
        setContacts((cs) => {
          const exists = cs.some((c) => c.id === peerId);
          const updated = cs.map((c) => {
            if (c.id !== peerId) return c;
            const incrementUnread = m.sender_id !== user?.id && (!active || active.id !== peerId);
            return {
              ...c,
              last_message_at: m.created_at,
              last_message_text: m.text,
              unread: incrementUnread ? (c.unread || 0) + 1 : c.unread,
            };
          });
          if (!exists) loadContacts();
          // bubble updated row to top
          const idx = updated.findIndex((c) => c.id === peerId);
          if (idx > 0) {
            const [row] = updated.splice(idx, 1);
            updated.unshift(row);
          }
          return updated;
        });
        if (m.sender_id !== user?.id) {
          window.dispatchEvent(new Event("scms:chat:refresh-unread"));
        }
      } else if (evt.type === "group_message") {
        const m = evt.message;
        const gid = evt.group_id;
        if (active && active.scope && active.id === gid) {
          setMessages((prev) => prev.some((x) => x.id === m.id) ? prev : [...prev, m]);
          if (m.sender_id !== user?.id) {
            api.post(`/messaging/groups/${gid}/read`).catch(() => {});
            window.dispatchEvent(new Event("scms:chat:refresh-unread"));
          }
        }
        setGroups((gs) => {
          const updated = gs.map((g) => {
            if (g.id !== gid) return g;
            const incrUnread = m.sender_id !== user?.id && (!active || active.id !== gid);
            return {
              ...g,
              last_message_at: m.created_at,
              last_message_text: m.text || (m.attachment ? `📎 ${m.attachment.name}` : ""),
              last_sender_id: m.sender_id,
              unread: incrUnread ? (g.unread || 0) + 1 : g.unread,
            };
          });
          return updated;
        });
        if (m.sender_id !== user?.id) {
          window.dispatchEvent(new Event("scms:chat:refresh-unread"));
        }
      } else if (evt.type === "smart_action_done") {
        setMessages((prev) => prev.map((m) => m.id === evt.message_id ? {
          ...m,
          smart_action_done: evt.action,
          smart_action_outcome: evt.outcome,
        } : m));
      } else if (evt.type === "group_pin") {
        const gid = evt.group_id;
        setGroups((gs) => gs.map((g) => g.id === gid ? {
          ...g,
          pinned_message_id: evt.pinned_message_id || null,
          pinned_message_text: evt.pinned_message_text || null,
          pinned_until: evt.pinned_until || null,
        } : g));
        if (active && active.scope && active.id === gid) {
          setActive((p) => p ? {
            ...p,
            pinned_message_id: evt.pinned_message_id || null,
            pinned_message_text: evt.pinned_message_text || null,
            pinned_until: evt.pinned_until || null,
          } : p);
        }
      } else if (evt.type === "typing") {
        if (active && evt.from === active.id) {
          setPeerTyping(!!evt.is_typing);
          if (peerTypingTimerRef.current) clearTimeout(peerTypingTimerRef.current);
          if (evt.is_typing) {
            peerTypingTimerRef.current = setTimeout(() => setPeerTyping(false), 3500);
          }
        }
      } else if (evt.type === "read") {
        if (active && evt.by === active.id) {
          setMessages((prev) => prev.map((m) => m.read_at ? m : { ...m, read_at: evt.at }));
        }
      }
    });
    return () => off && off();
  }, [onEvent, active, user, loadContacts]);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, peerTyping, active?.id]);

  const filteredContacts = useMemo(() => {
    if (!search.trim()) return contacts;
    const q = search.toLowerCase();
    return contacts.filter(
      (c) => (c.name || "").toLowerCase().includes(q) || (c.context || "").toLowerCase().includes(q)
    );
  }, [contacts, search]);

  const send = async () => {
    const text = draft.trim();
    if ((!text && !attachment) || !active || sending) return;
    setSending(true);
    const savedText = text;
    const savedAtt = attachment;
    setDraft("");
    setAttachment(null);
    try {
      const body = { text };
      if (savedAtt) body.attachment = savedAtt;
      const url = isGroup
        ? `/messaging/groups/${active.id}/messages`
        : `/messaging/conversations/${active.id}/messages`;
      const r = await api.post(url, body);
      const m = r.data;
      setMessages((prev) => prev.some((x) => x.id === m.id) ? prev : [...prev, m]);
      if (isGroup) {
        setGroups((gs) => {
          const updated = gs.map((g) => g.id === active.id ? {
            ...g,
            last_message_at: m.created_at,
            last_message_text: m.text || (m.attachment ? `📎 ${m.attachment.name}` : ""),
            last_sender_id: m.sender_id,
          } : g);
          return updated;
        });
      } else {
        setContacts((cs) => {
          const updated = cs.map((c) => c.id === active.id ? {
            ...c,
            last_message_at: m.created_at,
            last_message_text: m.text || (m.attachment ? `📎 ${m.attachment.name}` : ""),
          } : c);
          const idx = updated.findIndex((c) => c.id === active.id);
          if (idx > 0) {
            const [row] = updated.splice(idx, 1);
            updated.unshift(row);
          }
          return updated;
        });
      }
    } catch (e) {
      toast.error(formatApiError(e));
      setDraft(savedText);
      setAttachment(savedAtt);
    } finally {
      setSending(false);
    }
  };

  const onPickFile = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!ALLOWED_MIMES.includes(f.type)) {
      toast.error("Only images (jpg/png/webp/gif) and PDF files are allowed.");
      return;
    }
    if (f.size > MAX_ATT_BYTES) {
      toast.error("File too large. Max 1.8 MB.");
      return;
    }
    try {
      const dataUrl = await readFileAsDataURL(f);
      setAttachment({ name: f.name, type: f.type, size: f.size, data_url: dataUrl });
    } catch (_e) {
      toast.error("Could not read that file.");
    }
  };

  const toggleMute = async () => {
    if (!active) return;
    const next = !active.muted;
    try {
      await api.post(`/messaging/conversations/${active.id}/mute`, { muted: next });
      setActive((p) => p ? { ...p, muted: next } : p);
      setContacts((cs) => cs.map((c) => c.id === active.id ? { ...c, muted: next } : c));
      toast.success(next ? "Notifications muted" : "Notifications on");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const toggleGroupMute = async () => {
    if (!active || !isGroup) return;
    const next = !active.muted;
    try {
      await api.post(`/messaging/groups/${active.id}/mute`, { muted: next });
      setActive((p) => p ? { ...p, muted: next } : p);
      setGroups((gs) => gs.map((g) => g.id === active.id ? { ...g, muted: next } : g));
      toast.success(next ? "Group muted" : "Group unmuted");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const pinBroadcast = async (msg) => {
    if (!active || !isGroup || !active.is_owner) return;
    try {
      const r = await api.post(`/messaging/groups/${active.id}/pin`, { message_id: msg.id });
      setActive((p) => p ? {
        ...p,
        pinned_message_id: msg.id,
        pinned_message_text: (msg.text || "").slice(0, 240),
        pinned_until: r.data?.pinned_until,
      } : p);
      setGroups((gs) => gs.map((g) => g.id === active.id ? {
        ...g,
        pinned_message_id: msg.id,
        pinned_message_text: (msg.text || "").slice(0, 240),
        pinned_until: r.data?.pinned_until,
      } : g));
      toast.success("Pinned for 24 hours");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const unpinBroadcast = async () => {
    if (!active || !isGroup || !active.is_owner) return;
    try {
      await api.delete(`/messaging/groups/${active.id}/pin`);
      setActive((p) => p ? { ...p, pinned_message_id: null, pinned_message_text: null, pinned_until: null } : p);
      setGroups((gs) => gs.map((g) => g.id === active.id ? { ...g, pinned_message_id: null, pinned_message_text: null, pinned_until: null } : g));
      toast.success("Unpinned");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const sendQuickReply = async (msg, replyText) => {
    if (!msg || !replyText) return;
    // Optimistic: stamp the bubble as replied so the chips disappear immediately
    setMessages((prev) => prev.map((m) => m.id === msg.id ? { ...m, replied_at: new Date().toISOString(), reply_text: replyText } : m));
    try {
      const r = await api.post("/messaging/system/reply", { update_id: msg.id, text: replyText });
      toast.success(`Sent to ${r.data?.recipient?.name || "school"}`);
    } catch (e) {
      // Rollback on failure
      setMessages((prev) => prev.map((m) => m.id === msg.id ? { ...m, replied_at: null, reply_text: null } : m));
      toast.error(formatApiError(e));
    }
  };

  const runSmartAction = async (msg, action) => {
    if (!msg || !action) return;
    try {
      const r = await api.post(`/messaging/messages/${msg.id}/smart-action`, {
        action: action.action,
        student_id: action.student_id,
        days: action.days,
      });
      setMessages((prev) => prev.map((m) => m.id === msg.id ? {
        ...m,
        smart_action_done: r.data?.action,
        smart_action_outcome: r.data?.outcome,
      } : m));
      toast.success(r.data?.outcome || "Done");
    } catch (e) { toast.error(formatApiError(e)); }
  };

  const insertMention = () => {
    if (!active) return;
    const insertText = `@${active.name} `;
    setDraft((d) => {
      const el = inputRef.current;
      const cursor = el && el.selectionStart != null ? el.selectionStart : d.length;
      // Walk back from cursor to find the most recent unclosed '@' trigger.
      let start = cursor;
      while (start > 0 && d[start - 1] !== "@" && !/\s/.test(d[start - 1])) {
        start--;
      }
      if (start > 0 && d[start - 1] === "@") {
        start--; // include the @ so we replace it
      } else {
        start = cursor; // no trigger found — fall back to plain insert
      }
      return d.slice(0, start) + insertText + d.slice(cursor);
    });
    setMentionMenu(false);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const onDraftChange = (v) => {
    setDraft(v);
    // @-mention autocomplete: show menu when user types @ at the end or with space before
    const el = inputRef.current;
    const cursor = el && el.selectionStart != null ? el.selectionStart : v.length;
    const upto = v.slice(0, cursor);
    const lastAt = upto.lastIndexOf("@");
    const showMenu = lastAt >= 0
      && (lastAt === 0 || /\s/.test(upto[lastAt - 1] || ""))
      && !/\s/.test(upto.slice(lastAt + 1));
    setMentionMenu(!!showMenu);

    if (!active) return;
    if (typingDebounceRef.current) clearTimeout(typingDebounceRef.current);
    if (wsStatus === "open") {
      sendRaw({ type: "typing", to: active.id, is_typing: true });
    }
    typingDebounceRef.current = setTimeout(() => {
      if (wsStatus === "open") {
        sendRaw({ type: "typing", to: active.id, is_typing: false });
      }
    }, 1800);
  };

  return (
    <div data-testid="chat-page" className="chat-page">
      <PageHeader
        eyebrow="Conversations"
        title="Chat"
        subtitle="Send a message to your class teacher, parents in your class or the school admin."
        actions={
          <div className="flex items-center gap-2 text-xs text-ink-muted" data-testid="chat-ws-status">
            <span className={`w-2 h-2 rounded-full ${wsStatus === "open" ? "bg-status-success chat-pulse" : "bg-ink-muted"}`} />
            {wsStatus === "open" ? "Live" : wsStatus === "connecting" ? "Connecting…" : "Reconnecting…"}
          </div>
        }
      />

      <div className="chat-shell">
        {/* Contacts list */}
        <aside
          className={`chat-list panel ${showListMobile ? "is-shown" : ""}`}
          data-testid="chat-contact-list"
        >
          {/* Search */}
          <div className="p-3 border-b border-line">
            <div className="relative">
              <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
              <input
                className="input !pl-9"
                placeholder="Search contacts…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                data-testid="chat-search-input"
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {/* Groups section */}
            {groups.length > 0 ? (
              <>
                <div className="px-2 pt-1 pb-1 text-[10px] uppercase tracking-wider font-semibold text-ink-muted flex items-center gap-1.5">
                  <UsersThree size={11} /> Broadcast Groups
                </div>
                {groups.map((g) => (
                  <GroupRow
                    key={g.id}
                    group={g}
                    active={isGroup && active?.id === g.id}
                    onClick={() => openChat({ ...g, scope: g.scope })}
                  />
                ))}
                <div className="px-2 pt-3 pb-1 text-[10px] uppercase tracking-wider font-semibold text-ink-muted">
                  Direct
                </div>
              </>
            ) : null}

            {loadingContacts ? (
              <>
                {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-14 w-full" />)}
              </>
            ) : filteredContacts.length === 0 && groups.length === 0 ? (
              <div className="p-4">
                <Empty
                  title={search ? "No matches" : "No contacts yet"}
                  message={search ? "Try a different search." : "Once you're assigned to a class, the people you can chat with will appear here."}
                />
              </div>
            ) : (
              filteredContacts.map((c) => (
                <ContactRow
                  key={c.id}
                  contact={c}
                  active={!isGroup && active?.id === c.id}
                  onClick={() => openChat(c)}
                />
              ))
            )}
          </div>
        </aside>

        {/* Chat window */}
        <section
          className={`chat-window panel ${!showListMobile ? "is-shown" : ""}`}
          data-testid="chat-window"
        >
          {!active ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-10 text-ink-muted">
              <div className="chat-empty-illustration mb-4">
                <ChatCircleDots size={56} weight="duotone" />
              </div>
              <div className="font-display text-xl text-ink mb-2">Pick a conversation</div>
              <p className="max-w-sm text-sm">
                Your messages are private to you and the person you're chatting with. Choose a contact on the left to begin.
              </p>
            </div>
          ) : (
            <>
              <header className="chat-header">
                <button
                  type="button"
                  className="btn-ghost lg:hidden p-1.5"
                  onClick={() => setShowListMobile(true)}
                  data-testid="chat-back-btn"
                >
                  <CaretLeft size={16} />
                </button>
                {isGroup ? (
                  <div className="chat-group-avatar"><UsersThree size={20} weight="duotone" /></div>
                ) : isSystem ? (
                  <Avatar name={active.name} size={36} isSystem />
                ) : (
                  <Avatar name={active.name} online={active.online} size={36} />
                )}
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate flex items-center gap-1.5">
                    {active.name}
                    {!isGroup && !isSystem && active.muted ? <BellSimpleSlash size={12} className="text-ink-muted" /> : null}
                    {isGroup && active.muted ? <BellSimpleSlash size={12} className="text-ink-muted" /> : null}
                    {isGroup && active.is_owner ? <Megaphone size={12} className="text-primary" /> : null}
                  </div>
                  <div className="text-[11px] text-ink-muted truncate">
                    {isGroup ? (
                      <>
                        {active.scope === "admin_to_teachers" ? "Broadcast · All teachers" : "Broadcast · Class parents"}
                        {` · ${active.member_count} members`}
                        {active.is_owner ? " · You broadcast" : " · Read-only"}
                      </>
                    ) : isSystem ? (
                      <>School channel · WhatsApp / Telegram mirror · Read-only · Last 7 shown</>
                    ) : (
                      <>
                        {(ROLE_BADGE[active.role]?.label) || active.role}
                        {active.context ? ` · ${active.context}` : ""}
                        {active.online ? " · online" : ""}
                      </>
                    )}
                  </div>
                </div>
                {/* Header action buttons */}
                {!isSystem ? (
                  <div className="flex items-center gap-1 ml-auto">
                    {!isGroup && push.supported && !push.isSubscribed ? (
                      <button
                        type="button"
                        className="btn-ghost p-1.5 chat-icon-btn"
                        onClick={async () => {
                          const r = await push.subscribe();
                          if (r.ok) toast.success("Push notifications enabled");
                          else if (r.reason === "denied") toast.error("Permission denied. Enable in browser settings.");
                          else if (r.reason !== "unsupported") toast.error("Could not enable push notifications.");
                        }}
                        title="Enable push notifications"
                        data-testid="chat-enable-push-btn"
                      >
                        <BellSimple size={16} />
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn-ghost p-1.5 chat-icon-btn"
                      onClick={isGroup ? toggleGroupMute : toggleMute}
                      title={active.muted ? "Unmute" : "Mute notifications"}
                      data-testid="chat-mute-btn"
                    >
                      {active.muted ? <BellSimpleSlash size={16} className="text-status-warning" /> : <BellSimple size={16} />}
                    </button>
                    {isGroup && active.is_owner ? (
                      <button
                        type="button"
                        className="btn-ghost p-1.5 chat-icon-btn"
                        onClick={active.pinned_message_id ? unpinBroadcast : null}
                        disabled={!active.pinned_message_id}
                        title={active.pinned_message_id ? "Unpin current broadcast" : "Long-press a message to pin"}
                        data-testid="chat-unpin-btn"
                      >
                        {active.pinned_message_id ? <PushPinSlash size={16} /> : <PushPin size={16} />}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </header>

              {/* Pinned broadcast banner (groups only) */}
              {isGroup && active.pinned_message_id && active.pinned_message_text ? (
                <div className="chat-pin-banner" data-testid="chat-pin-banner">
                  <PushPin size={14} weight="fill" className="text-status-warning shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div className="text-[10px] uppercase tracking-wider font-semibold text-ink-muted">Pinned broadcast</div>
                    <div className="text-sm text-ink truncate">{active.pinned_message_text}</div>
                  </div>
                  {active.is_owner ? (
                    <button
                      type="button"
                      className="btn-ghost p-1"
                      onClick={unpinBroadcast}
                      data-testid="chat-pin-banner-unpin"
                      aria-label="Unpin"
                    >
                      <XIcon size={14} />
                    </button>
                  ) : null}
                </div>
              ) : null}

              <div className="chat-thread" ref={scrollRef} data-testid="chat-thread">
                {messages.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center text-ink-muted px-6">
                    <Circle size={28} className="mb-2 opacity-50" />
                    <div className="text-sm">No messages yet — say hello!</div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2.5 py-2">
                    {messages.map((m) => (
                      <MessageBubble
                        key={m.id}
                        msg={m}
                        mine={m.sender_id === user?.id}
                        peerName={isGroup ? "" : (isSystem ? "School" : active.name)}
                        hideReceipt={isGroup || isSystem}
                        onPin={isGroup && active.is_owner ? pinBroadcast : null}
                        isPinned={isGroup && active.pinned_message_id === m.id}
                        onQuickReply={isSystem ? sendQuickReply : null}
                        onSmartAction={!isSystem && !isGroup ? runSmartAction : null}
                      />
                    ))}
                    {peerTyping ? <TypingDots /> : null}
                  </div>
                )}
              </div>

              {attachment ? (
                <div className="chat-att-preview" data-testid="chat-att-preview">
                  {attachment.type.startsWith("image/") ? (
                    <img src={attachment.data_url} alt={attachment.name} className="chat-att-preview-img" />
                  ) : (
                    <FilePdf size={22} weight="duotone" className="text-status-danger" />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium truncate">{attachment.name}</div>
                    <div className="text-[10px] text-ink-muted">{Math.round(attachment.size / 1024)} KB</div>
                  </div>
                  <button
                    type="button"
                    className="btn-ghost p-1"
                    onClick={() => setAttachment(null)}
                    data-testid="chat-att-clear"
                    aria-label="Remove attachment"
                  >
                    <XIcon size={14} />
                  </button>
                </div>
              ) : null}

              {mentionMenu && !isGroup ? (
                <div className="chat-mention-menu" data-testid="chat-mention-menu">
                  <button type="button" className="chat-mention-item" onClick={insertMention} data-testid="chat-mention-suggest">
                    <At size={14} className="text-primary" />
                    <span>{active.name}</span>
                    <span className="text-[10px] text-ink-muted ml-auto">{ROLE_BADGE[active.role]?.label || active.role}</span>
                  </button>
                </div>
              ) : null}

              {(isGroup && !active.is_owner) || isSystem ? (
                <footer className="chat-composer chat-composer-locked" data-testid="chat-composer-locked">
                  {isSystem ? (
                    <>
                      <Newspaper size={18} className="text-ink-muted" />
                      <span className="text-xs text-ink-muted">
                        This is a read-only feed of school updates that were also sent via WhatsApp / Telegram.
                      </span>
                    </>
                  ) : (
                    <>
                      <Megaphone size={18} className="text-ink-muted" />
                      <span className="text-xs text-ink-muted">
                        This is a broadcast group. Only {active.scope === "admin_to_teachers" ? "the school admin" : "your class teacher"} can post here.
                      </span>
                    </>
                  )}
                </footer>
              ) : (
                <footer className="chat-composer">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept={ALLOWED_MIMES.join(",")}
                    className="hidden"
                    onChange={onPickFile}
                    data-testid="chat-file-input"
                  />
                  <button
                    type="button"
                    className="btn-ghost chat-composer-icon-btn"
                    onClick={() => fileInputRef.current?.click()}
                    title="Attach image or PDF"
                    data-testid="chat-attach-btn"
                  >
                    <Paperclip size={18} />
                  </button>
                  <textarea
                    ref={inputRef}
                    rows={1}
                    className="input chat-composer-input"
                    placeholder={isGroup
                      ? `Broadcast to ${active.member_count} member${active.member_count === 1 ? "" : "s"}…`
                      : `Message ${active.name}…  (type @ to mention)`}
                    value={draft}
                    onChange={(e) => onDraftChange(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") setMentionMenu(false);
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                    data-testid="chat-input"
                  />
                  <button
                    type="button"
                    className="btn-primary chat-send-btn"
                    onClick={send}
                    disabled={(!draft.trim() && !attachment) || sending}
                    data-testid="chat-send-btn"
                    aria-label="Send message"
                  >
                    <PaperPlaneTilt size={16} weight={sending ? "regular" : "fill"} />
                  </button>
                </footer>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
