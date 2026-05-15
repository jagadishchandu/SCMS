import React, { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import Topbar from "../components/Topbar";
import { useAuth } from "../contexts/AuthContext";
import { api } from "../lib/api";

export default function AppLayout({ children }) {
  const { user } = useAuth();
  const [schoolName, setSchoolName] = useState("");

  useEffect(() => {
    if (user && user.school_id) {
      api.get(`/schools/${user.school_id}`).then((r) => setSchoolName(r.data?.name)).catch(() => {});
    } else if (user?.role === "platform_admin") {
      setSchoolName("Platform Console");
    }
  }, [user]);

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="flex flex-col min-w-0">
        <Topbar schoolName={schoolName} />
        <main className="flex-1 px-4 lg:px-8 py-6 lg:py-10 fade-up">{children}</main>
      </div>
    </div>
  );
}
