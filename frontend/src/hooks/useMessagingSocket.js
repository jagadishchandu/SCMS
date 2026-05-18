import { useEffect, useRef, useState, useCallback } from "react";

/**
 * Open a single WebSocket to /api/messaging/ws. Auth is via the access_token
 * cookie (same-origin); the cookie is also forwarded inside the secure
 * preview/prod hostname so this works out-of-the-box.
 *
 * Caller gets:
 *   - sendRaw(obj)  — emit a JSON event
 *   - onEvent(cb)   — subscribe to incoming events (returns unsubscribe)
 *   - status        — "idle" | "connecting" | "open" | "closed"
 */
export function useMessagingSocket(enabled = true) {
  const wsRef = useRef(null);
  const listenersRef = useRef(new Set());
  const [status, setStatus] = useState("idle");
  const retryRef = useRef(0);

  const dispatch = useCallback((evt) => {
    listenersRef.current.forEach((fn) => {
      try { fn(evt); } catch (_e) { /* ignore */ }
    });
  }, []);

  const connect = useCallback(() => {
    if (!enabled) return;
    const RAW = process.env.REACT_APP_BACKEND_URL || "";
    const base = RAW ? RAW.replace(/^http/i, "ws").replace(/\/$/, "") : (
      window.location.origin.replace(/^http/i, "ws")
    );
    const url = `${base}/api/messaging/ws`;
    setStatus("connecting");
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (_e) {
      setStatus("closed");
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      retryRef.current = 0;
      setStatus("open");
    };
    ws.onmessage = (e) => {
      try { dispatch(JSON.parse(e.data)); } catch (_err) { /* ignore */ }
    };
    ws.onerror = () => { /* silent — onclose will fire next */ };
    ws.onclose = () => {
      setStatus("closed");
      if (!enabled) return;
      const delay = Math.min(15000, 1000 * Math.pow(2, retryRef.current++));
      setTimeout(() => { connect(); }, delay);
    };
  }, [enabled, dispatch]);

  useEffect(() => {
    if (!enabled) return;
    connect();
    return () => {
      try { wsRef.current && wsRef.current.close(); } catch (_e) { /* ignore */ }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  const sendRaw = useCallback((obj) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) {
      try { ws.send(JSON.stringify(obj)); } catch (_e) { /* ignore */ }
    }
  }, []);

  const onEvent = useCallback((fn) => {
    listenersRef.current.add(fn);
    return () => listenersRef.current.delete(fn);
  }, []);

  return { status, sendRaw, onEvent };
}
