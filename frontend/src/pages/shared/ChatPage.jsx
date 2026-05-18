import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { useMessagingSocket } from "../../hooks/useMessagingSocket";
import { PageHeader, Empty } from "../../components/Primitives";
import {
  ChatCircleDots, PaperPlaneTilt, MagnifyingGlass, CaretLeft,
  CheckCircle, Check, Circle, UserCircle,
} from "@phosphor-icons/react";
import toast from "react-hot-toast";

const ROLE_BADGE = {
  teacher: { label: "Teacher", cls: "bg-status-info-bg text-status-info" },
  parent: { label: "Parent", cls: "bg-status-warning-bg text-status-warning" },
  school_admin: { label: "Admin", cls: "bg-primary-light text-primary" },
};

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

function Avatar({ name, online, size = 40 }) {
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
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`chat-contact-${contact.id}`}
      className={`w-full text-left px-3 py-3 flex items-center gap-3 rounded-lg transition-all duration-200 chat-contact-row ${
        active ? "bg-primary-light/60 ring-1 ring-primary/30" : "hover:bg-bg-subtle"
      }`}
    >
      <Avatar name={contact.name} online={contact.online} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <div className="font-medium text-sm truncate text-ink">{contact.name}</div>
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
      {contact.unread > 0 ? (
        <span
          className="ml-1 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-semibold bg-status-danger text-white chat-unread-badge"
          data-testid={`chat-unread-${contact.id}`}
        >
          {contact.unread > 99 ? "99+" : contact.unread}
        </span>
      ) : null}
    </button>
  );
}

function MessageBubble({ msg, mine, peerName }) {
  return (
    <div className={`flex w-full ${mine ? "justify-end" : "justify-start"} chat-msg-enter`}>
      <div className={`max-w-[78%] md:max-w-[62%] ${mine ? "items-end" : "items-start"} flex flex-col gap-0.5`}>
        <div
          className={`px-3.5 py-2 rounded-2xl text-sm leading-snug whitespace-pre-wrap break-words shadow-soft ${
            mine
              ? "bg-primary text-primary-foreground rounded-br-md"
              : "bg-bg-surface border border-line text-ink rounded-bl-md"
          }`}
          title={fullTime(msg.created_at)}
          data-testid={`chat-msg-${msg.id}`}
        >
          {msg.text}
        </div>
        <div className={`text-[10px] flex items-center gap-1 px-1 ${mine ? "text-ink-muted" : "text-ink-muted"}`}>
          {!mine ? <span className="font-medium">{peerName}</span> : null}
          <span>{timeShort(msg.created_at)}</span>
          {mine ? (
            msg.read_at ? (
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

export default function ChatPage() {
  const { user } = useAuth();
  const [contacts, setContacts] = useState([]);
  const [loadingContacts, setLoadingContacts] = useState(true);
  const [active, setActive] = useState(null); // peer object
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [peerTyping, setPeerTyping] = useState(false);
  const [sending, setSending] = useState(false);
  const [showListMobile, setShowListMobile] = useState(true);
  const scrollRef = useRef(null);
  const typingDebounceRef = useRef(null);
  const peerTypingTimerRef = useRef(null);
  const inputRef = useRef(null);

  const { status: wsStatus, sendRaw, onEvent } = useMessagingSocket(!!user);

  const loadContacts = useCallback(async () => {
    try {
      setLoadingContacts(true);
      const r = await api.get("/messaging/contacts");
      setContacts(r.data?.contacts || []);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setLoadingContacts(false);
    }
  }, []);

  useEffect(() => { loadContacts(); }, [loadContacts]);

  const loadMessages = useCallback(async (peer) => {
    try {
      const r = await api.get(`/messaging/conversations/${peer.id}/messages`);
      setMessages(r.data?.messages || []);
      // Mark read
      await api.post(`/messaging/conversations/${peer.id}/read`).catch(() => {});
      window.dispatchEvent(new Event("scms:chat:refresh-unread"));
      // Locally clear unread for this contact
      setContacts((cs) => cs.map((c) => c.id === peer.id ? { ...c, unread: 0 } : c));
    } catch (e) {
      toast.error(formatApiError(e));
    }
  }, []);

  const openChat = useCallback((peer) => {
    setActive(peer);
    setMessages([]);
    setPeerTyping(false);
    setShowListMobile(false);
    loadMessages(peer);
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
    if (!text || !active || sending) return;
    setSending(true);
    setDraft("");
    try {
      const r = await api.post(`/messaging/conversations/${active.id}/messages`, { text });
      const m = r.data;
      setMessages((prev) => prev.some((x) => x.id === m.id) ? prev : [...prev, m]);
      setContacts((cs) => {
        const updated = cs.map((c) => c.id === active.id ? {
          ...c, last_message_at: m.created_at, last_message_text: m.text,
        } : c);
        const idx = updated.findIndex((c) => c.id === active.id);
        if (idx > 0) {
          const [row] = updated.splice(idx, 1);
          updated.unshift(row);
        }
        return updated;
      });
    } catch (e) {
      toast.error(formatApiError(e));
      setDraft(text);
    } finally {
      setSending(false);
    }
  };

  const onDraftChange = (v) => {
    setDraft(v);
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
            {loadingContacts ? (
              <>
                {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-14 w-full" />)}
              </>
            ) : filteredContacts.length === 0 ? (
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
                  active={active?.id === c.id}
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
                <Avatar name={active.name} online={active.online} size={36} />
                <div className="min-w-0">
                  <div className="font-medium truncate">{active.name}</div>
                  <div className="text-[11px] text-ink-muted truncate">
                    {(ROLE_BADGE[active.role]?.label) || active.role}
                    {active.context ? ` · ${active.context}` : ""}
                    {active.online ? " · online" : ""}
                  </div>
                </div>
              </header>

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
                        peerName={active.name}
                      />
                    ))}
                    {peerTyping ? <TypingDots /> : null}
                  </div>
                )}
              </div>

              <footer className="chat-composer">
                <textarea
                  ref={inputRef}
                  rows={1}
                  className="input chat-composer-input"
                  placeholder={`Message ${active.name}…`}
                  value={draft}
                  onChange={(e) => onDraftChange(e.target.value)}
                  onKeyDown={(e) => {
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
                  disabled={!draft.trim() || sending}
                  data-testid="chat-send-btn"
                  aria-label="Send message"
                >
                  <PaperPlaneTilt size={16} weight={sending ? "regular" : "fill"} />
                </button>
              </footer>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
