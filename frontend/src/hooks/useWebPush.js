import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

/**
 * Manages the Web Push subscription for this device.
 * Returns: { supported, permission, isSubscribed, subscribe, unsubscribe }
 */
export function useWebPush(enabled = true) {
  const [supported, setSupported] = useState(false);
  const [permission, setPermission] = useState(
    typeof Notification !== "undefined" ? Notification.permission : "default"
  );
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [endpoint, setEndpoint] = useState(null);

  useEffect(() => {
    const ok = typeof window !== "undefined"
      && "serviceWorker" in navigator
      && "PushManager" in window
      && "Notification" in window;
    setSupported(ok);
  }, []);

  // Register service worker + check existing subscription
  useEffect(() => {
    if (!enabled || !supported) return;
    let cancelled = false;
    (async () => {
      try {
        const reg = await navigator.serviceWorker.register("/sw.js");
        await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (!cancelled) {
          setIsSubscribed(!!sub);
          setEndpoint(sub ? sub.endpoint : null);
        }
      } catch (_e) {
        // SW failures are non-fatal
      }
    })();
    return () => { cancelled = true; };
  }, [enabled, supported]);

  const subscribe = useCallback(async () => {
    if (!supported) return { ok: false, reason: "unsupported" };
    let perm = Notification.permission;
    if (perm === "default") {
      perm = await Notification.requestPermission();
      setPermission(perm);
    }
    if (perm !== "granted") return { ok: false, reason: "denied" };
    try {
      const cfg = await api.get("/messaging/push/config");
      if (!cfg.data?.enabled || !cfg.data?.public_key) {
        return { ok: false, reason: "server_disabled" };
      }
      const reg = await navigator.serviceWorker.ready;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(cfg.data.public_key),
        });
      }
      const json = sub.toJSON();
      await api.post("/messaging/push/subscribe", {
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      });
      setIsSubscribed(true);
      setEndpoint(json.endpoint);
      return { ok: true };
    } catch (_e) {
      return { ok: false, reason: "error" };
    }
  }, [supported]);

  const unsubscribe = useCallback(async () => {
    if (!supported) return { ok: false };
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        const ep = sub.endpoint;
        await sub.unsubscribe();
        await api.post("/messaging/push/unsubscribe", { endpoint: ep }).catch(() => {});
      }
      setIsSubscribed(false);
      setEndpoint(null);
      return { ok: true };
    } catch (_e) {
      return { ok: false };
    }
  }, [supported]);

  return { supported, permission, isSubscribed, endpoint, subscribe, unsubscribe };
}
