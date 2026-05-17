import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";

const REFRESH_EVENT = "scms:notifications:refresh-unread";

/**
 * Poll the unread in-app notification count for the current user.
 * Powers the sidebar "Notifications" badge. Re-fetches every `intervalMs`,
 * on window focus, and on the `scms:notifications:refresh-unread` window
 * event so any caller (e.g. the NotificationsLog page after marking
 * notifications as read) can clear the badge instantly without waiting
 * for the polling interval.
 */
export function useUnreadNotifications(intervalMs = 30000) {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  const fetchCount = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications/unread-count");
      setCount(data?.count || 0);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!user) {
      setCount(0);
      return;
    }
    let alive = true;
    const tick = async () => {
      if (!alive) return;
      await fetchCount();
    };
    tick();
    const id = setInterval(tick, intervalMs);
    const onFocus = () => tick();
    const onRefresh = () => tick();
    window.addEventListener("focus", onFocus);
    window.addEventListener(REFRESH_EVENT, onRefresh);
    return () => {
      alive = false;
      clearInterval(id);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener(REFRESH_EVENT, onRefresh);
    };
  }, [user, intervalMs, fetchCount]);

  return { count, refresh: fetchCount };
}

/** Tell every active `useUnreadNotifications` instance to re-fetch immediately. */
export function broadcastUnreadRefresh() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(REFRESH_EVENT));
  }
}
