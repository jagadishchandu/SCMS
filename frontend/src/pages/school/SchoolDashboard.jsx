import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { formatDate, currency, CHART_COLORS } from "../../lib/utils";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";
import { PaperPlaneTilt } from "@phosphor-icons/react";
import toast from "react-hot-toast";

export default function SchoolDashboard() {
  const [data, setData] = useState(null);
  const [sendingDigest, setSendingDigest] = useState(false);

  const load = () => api.get("/analytics/school").then((r) => setData(r.data));
  useEffect(() => { load(); }, []);

  const runDigests = async () => {
    if (!window.confirm("Send last month's WhatsApp digest to every parent in the school?")) return;
    setSendingDigest(true);
    try {
      const { data: res } = await api.post("/digests/run-monthly");
      const t = res.totals;
      toast.success(`Digest run · sent ${t.sent}, queued ${t.queued}, failed ${t.failed} (${res.period})`);
      load();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSendingDigest(false); }
  };

  if (!data) return <div className="skeleton h-40 w-full" />;
  const k = data.kpis;

  const feeData = [
    { name: "Collected", value: k.fees_collected },
    { name: "Outstanding", value: k.fees_outstanding },
  ];

  return (
    <div data-testid="school-dashboard">
      <PageHeader eyebrow="Overview" title="Your school at a glance"
        subtitle="Live attendance, fees, and upcoming exams across all classes."
        actions={
          <button className="btn-primary" onClick={runDigests} disabled={sendingDigest} data-testid="send-monthly-digest-btn">
            <PaperPlaneTilt size={16}/> {sendingDigest ? "Sending…" : "Send monthly digest"}
          </button>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KPI label="Active students" value={k.total_students} accent="primary" testId="kpi-students" />
        <KPI label="Teachers" value={k.total_teachers} accent="info" testId="kpi-teachers" />
        <KPI label="Classes" value={k.total_classes} accent="secondary" testId="kpi-classes" />
        <KPI label="Today's attendance" value={`${k.attendance_today_pct}%`}
          accent={k.attendance_today_pct >= 85 ? "success" : k.attendance_today_pct >= 70 ? "warning" : "danger"}
          testId="kpi-attendance-today" />
        <KPI label="Fees billed" value={currency(k.fees_billed)} accent="secondary" testId="kpi-fees-billed" />
        <KPI label="Fees collected" value={currency(k.fees_collected)} accent="success" testId="kpi-fees-collected" />
        <KPI label="Fees outstanding" value={currency(k.fees_outstanding)} accent={k.fees_outstanding > 0 ? "danger" : "success"} testId="kpi-fees-outstanding" />
        <KPI label="Notifications sent" value={k.notifications_sent} accent="info" testId="kpi-notifications-sent" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2">
          <Section title="Upcoming exams">
            {data.upcoming_exams.length === 0 ? <Empty title="No upcoming exams" /> :
              <table className="table">
                <thead><tr><th className="th">Name</th><th className="th">Term</th><th className="th">From</th><th className="th">To</th><th className="th">Published</th></tr></thead>
                <tbody>
                  {data.upcoming_exams.map((e) => (
                    <tr key={e.id} className="table-row">
                      <td className="td font-medium">{e.name}</td>
                      <td className="td">{e.term}</td>
                      <td className="td">{formatDate(e.start_date)}</td>
                      <td className="td">{formatDate(e.end_date)}</td>
                      <td className="td">{e.is_published ? <span className="badge-success">Published</span> : <span className="badge-warning">Draft</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>}
          </Section>
        </div>
        <Section title="Fee collection">
          <div className="h-56">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={feeData} dataKey="value" innerRadius={50} outerRadius={80} paddingAngle={3}>
                  {feeData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i]} />)}
                </Pie>
                <Tooltip formatter={(v) => currency(v)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-around text-sm mt-2">
            <div className="text-center"><div className="text-ink-muted text-xs">Collected</div><div className="font-display font-semibold">{currency(k.fees_collected)}</div></div>
            <div className="text-center"><div className="text-ink-muted text-xs">Outstanding</div><div className="font-display font-semibold">{currency(k.fees_outstanding)}</div></div>
          </div>
        </Section>
      </div>

      <Section title="Upcoming holidays">
        {data.upcoming_holidays.length === 0 ? <Empty title="No upcoming holidays" /> :
          <ul className="divide-y divide-line">
            {data.upcoming_holidays.map((h) => (
              <li key={h.id} className="py-3 flex items-center justify-between" data-testid={`holiday-${h.id}`}>
                <div>
                  <div className="font-medium">{h.title}</div>
                  <div className="text-xs text-ink-muted">{h.type} · {h.description || "—"}</div>
                </div>
                <div className="text-sm">{formatDate(h.date)}</div>
              </li>
            ))}
          </ul>}
      </Section>
    </div>
  );
}
