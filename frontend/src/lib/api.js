import axios from "axios";

// `REACT_APP_BACKEND_URL` may be empty when the React build is served behind the same
// nginx that proxies /api/* to the backend (the default for docker-compose). In that case
// we use a relative baseURL so the browser hits the same origin as the page.
const RAW = process.env.REACT_APP_BACKEND_URL || "";
const baseURL = RAW ? `${RAW.replace(/\/$/, "")}/api` : "/api";

export const api = axios.create({
  baseURL,
  withCredentials: true,
  timeout: 30000,
});

// Global 402 handler: when the subscription guard blocks a write, redirect school admins
// to the renewal page and show a clear message. Other roles see a toast-friendly error.
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const status = err?.response?.status;
    const code = err?.response?.data?.code;
    if (status === 402 && code === "subscription_expired") {
      const renewUrl = err.response.data.renew_url || "/school/subscription";
      if (typeof window !== "undefined" && !window.location.pathname.startsWith(renewUrl)) {
        // Defer so the calling code can still see the rejection if needed.
        setTimeout(() => { window.location.href = renewUrl; }, 1500);
      }
    }
    return Promise.reject(err);
  },
);

export function formatApiError(err) {
  const detail = err?.response?.data?.detail;
  if (detail == null) return err?.message || "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).join(" ");
  }
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
