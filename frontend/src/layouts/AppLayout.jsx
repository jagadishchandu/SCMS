import React, { useState, useEffect } from "react";
import Sidebar from "../components/Sidebar";
import Topbar from "../components/Topbar";
import MobileBottomNav from "../components/MobileBottomNav";
import SubscriptionBanner from "../components/SubscriptionBanner";
import TelegramLinkBanner from "../components/TelegramLinkBanner";
import { useAuth } from "../contexts/AuthContext";
import { api } from "../lib/api";
import { useLocation } from "react-router-dom";

export default function AppLayout({ children }) {
  const { user } = useAuth();
  const [schoolName, setSchoolName] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    if (user && user.school_id) {
      api.get(`/schools/${user.school_id}`).then((r) => setSchoolName(r.data?.name)).catch(() => {});
    } else if (user?.role === "platform_admin") {
      setSchoolName("Platform Console");
    }
  }, [user]);

  useEffect(() => { setMobileOpen(false); }, [location.pathname]);

  const isParent = user?.role === "parent";

  return (
    <div className="app-shell">
      <Sidebar mobileOpen={mobileOpen} onCloseMobile={() => setMobileOpen(false)} />
      <div className="flex flex-col min-w-0">
        <Topbar schoolName={schoolName} onToggleMobile={() => setMobileOpen(true)} />
        <SubscriptionBanner user={user} />
        <TelegramLinkBanner />
        <main className={`flex-1 px-4 lg:px-8 py-6 lg:py-10 fade-up ${isParent ? "mobile-bottom-safe" : ""}`}>{children}</main>
      </div>
      <MobileBottomNav />
    </div>
  );
}
