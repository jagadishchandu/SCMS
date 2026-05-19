import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";

/**
 * Poll the pending teacher-leave approval count. Only the school_admin sees a non-zero count.
 */
export function useTeacherLeavePending(intervalMs = 30000) {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!user || user.role !== "school_admin") {
      setCount(0);
      return;
    }
    let alive = true;
    const fetchCount = async () => {
      try {
        const { data } = await api.get("/teacher-leaves/pending-count");
        if (alive) setCount(data?.count || 0);
      } catch {
        /* ignore */
      }
    };
    fetchCount();
    const id = setInterval(fetchCount, intervalMs);
    const onFocus = () => fetchCount();
    window.addEventListener("focus", onFocus);
    return () => { alive = false; clearInterval(id); window.removeEventListener("focus", onFocus); };
  }, [user, intervalMs]);

  return count;
}
