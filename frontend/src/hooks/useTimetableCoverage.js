import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";

/** Polls /api/timetable/coverage and returns the unfilled-slot count for the school admin sidebar badge. */
export function useTimetableCoverage(intervalMs = 60000) {
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
        const { data } = await api.get("/timetable/coverage");
        if (alive) setCount(data?.total_unfilled || 0);
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
