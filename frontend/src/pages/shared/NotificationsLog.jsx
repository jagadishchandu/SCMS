import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { formatDate } from "../../lib/utils";
import { broadcastUnreadRefresh } from "../../hooks/useUnreadNotifications";

export default function NotificationsLog() {
  const [items, setItems] = useState([]);
  useEffect(() => {
    let alive = true;
    (async () => {
      const { data } = await api.get("/notifications");
      if (alive) setItems(data);
      // Clear the sidebar badge — all in-app notifications addressed to this
      // user are now considered read because they're rendered on this page.
      try {
        await api.post("/notifications/mark-all-read");
        broadcastUnreadRefresh();
      } catch { /* non-blocking */ }
    })();
    return () => { alive = false; };
  }, []);
  return (
    <div data-testid="notifications-log-page">
      <PageHeader eyebrow="Notifications" title="WhatsApp & parent communication log"
        subtitle="Every queued, sent and failed notification across schools." />
      <Section title={`${items.length} entries`}>
        {items.length === 0 ? <Empty title="No notifications yet" message="Activity will appear here as soon as data is added." /> : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">Date</th><th className="th">Channel</th><th className="th">Template</th>
                <th className="th">Recipient</th><th className="th">Status</th><th className="th">Message</th>
              </tr></thead>
              <tbody>
                {items.map((n) => (
                  <tr key={n.id} className="table-row" data-testid={`notif-row-${n.id}`}>
                    <td className="td whitespace-nowrap">{formatDate(n.created_at)}</td>
                    <td className="td"><span className="badge-info">{n.channel}</span></td>
                    <td className="td font-mono text-xs">{n.template}</td>
                    <td className="td">{n.phone || "—"}</td>
                    <td className="td"><span className={n.status === "sent" ? "badge-success" : n.status === "failed" ? "badge-danger" : "badge-warning"}>{n.status}</span></td>
                    <td className="td text-ink-soft truncate max-w-xl">{n.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
