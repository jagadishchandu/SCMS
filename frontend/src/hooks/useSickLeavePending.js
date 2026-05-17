import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";

/**
 * Poll the pending sick-leave approval count for the current user.
 * Returns 0 for roles that cannot approve (parent/accounts/platform_admin).
 */
export function useSickLeavePending(intervalMs = 30000) {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!user || !["school_admin", "teacher"].includes(user.role)) {
      setCount(0);
      return;
    }
    let alive = true;
    const fetchCount = async () => {
      try {
        const { data } = await api.get("/sick-leaves/pending-count");
        if (alive) setCount(data?.count || 0);
      } catch {
        /* ignore */
      }
    };
    fetchCount();
    const id = setInterval(fetchCount, intervalMs);
    // Also refresh when window regains focus
    const onFocus = () => fetchCount();
    window.addEventListener("focus", onFocus);
    return () => { alive = false; clearInterval(id); window.removeEventListener("focus", onFocus); };
  }, [user, intervalMs]);

  return count;
}
