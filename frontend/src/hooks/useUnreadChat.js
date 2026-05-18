import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";

/**
 * Polls /messaging/unread-count every 25s, on window focus, and on the
 * `scms:chat:refresh-unread` custom event so any sender can force a refresh
 * after marking a conversation as read.
 *
 * Returns { count, mentions, refresh }.
 *   - `count` already excludes muted conversations (mentions still counted).
 *   - `mentions` is total @-mentions across all chats.
 */
export function useUnreadChat() {
  const [count, setCount] = useState(0);
  const [mentions, setMentions] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const r = await api.get("/messaging/unread-count");
      setCount(r.data?.count || 0);
      setMentions(r.data?.mentions || 0);
    } catch (_e) {
      // ignore
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 25000);
    const onFocus = () => refresh();
    const onEvt = () => refresh();
    window.addEventListener("focus", onFocus);
    window.addEventListener("scms:chat:refresh-unread", onEvt);
    return () => {
      clearInterval(t);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("scms:chat:refresh-unread", onEvt);
    };
  }, [refresh]);

  return { count, mentions, refresh };
}
