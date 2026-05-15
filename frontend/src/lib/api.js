import axios from "axios";

const baseURL = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
