import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { formatDate, currency, CHART_COLORS } from "../../lib/utils";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from "recharts";
import { PaperPlaneTilt, Warning, UserCircle, Users, X, Buildings } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";

export default function SchoolDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [risks, setRisks] = useState([]);
  const [sendingDigest, setSendingDigest] = useState(false);
  const [rosterOpen, setRosterOpen] = useState(false);
  const [roster, setRoster] = useState(null);
  const [rosterLoading, setRosterLoading] = useState(false);

  const load = () => Promise.all([
    api.get("/analytics/school").then((r) => setData(r.data)),
    api.get("/analytics/risk-students", { params: { limit: 5 } }).then((r) => setRisks(r.data)).catch(() => setRisks([])),
  ]);
  useEffect(() => { load(); }, []);

  const openRoster = async () => {
    setRosterOpen(true); setRosterLoading(true); setRoster(null);
    try {
      const { data: people } = await api.get(`/schools/${user.school_id}/people`);
      setRoster(people);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setRosterLoading(false); }
  };

  const runDigests = async () => {
    const choice = window.prompt(
      "Send last month's parent digest. Choose channels: 'whatsapp', 'email', or 'whatsapp,email'",
      "whatsapp,email",
    );
    if (!choice) return;
    setSendingDigest(true);
    try {
      const { data: res } = await api.post("/digests/run-monthly", null, { params: { channels: choice } });
      const t = res.totals;
      toast.success(`Digest run (${res.channels.join(" + ")}) · sent ${t.sent}, queued ${t.queued}, failed ${t.failed} (${res.period})`);
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
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={openRoster} data-testid="view-roster-btn">
              <Users size={16}/> View roster
            </button>
            <button className="btn-primary" onClick={runDigests} disabled={sendingDigest} data-testid="send-monthly-digest-btn">
              <PaperPlaneTilt size={16}/> {sendingDigest ? "Sending…" : "Send monthly digest"}
            </button>
          </div>
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

      <div className="mt-6">
        <Section
          title={`Students at risk · top ${risks.length}`}
          action={<Link to="/student-search" className="btn-ghost text-xs">Open analytics →</Link>}
        >
          {risks.length === 0 ? <Empty title="No risk flags right now" message="Attendance and marks look healthy across the board." /> :
            <ul className="divide-y divide-line" data-testid="risk-students-list">
              {risks.map((r) => (
                <li key={r.student.id} className="py-3 flex items-center gap-3" data-testid={`risk-${r.student.student_uid}`}>
                  <div className="w-10 h-10 rounded-full bg-bg-subtle overflow-hidden grid place-items-center border border-line shrink-0">
                    {r.student.photo ? <img src={r.student.photo} alt={r.student.name} className="w-full h-full object-cover" /> : <UserCircle size={22} className="text-ink-muted" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link to={`/student/${r.student.student_uid}`} className="font-medium text-ink hover:text-primary">{r.student.name}</Link>
                      <span className="text-xs text-ink-muted">{r.student.student_uid} · {r.student.class_name} {r.student.section}</span>
                    </div>
                    <div className="text-xs text-ink-soft mt-0.5 flex gap-2 flex-wrap">
                      {r.reasons.map((x, i) => <span key={i} className="badge-warning">{x}</span>)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="flex items-center justify-end gap-1 text-status-danger font-display text-lg leading-none">
                      <Warning size={16} weight="fill" /> {r.score}
                    </div>
                    <div className="text-[10px] text-ink-muted">risk score</div>
                  </div>
                </li>
              ))}
            </ul>}
        </Section>
      </div>

      {rosterOpen && (
        <div className="fixed inset-0 z-40" data-testid="school-roster-drawer">
          <div className="absolute inset-0 bg-black/40" onClick={() => setRosterOpen(false)} />
          <div className="absolute top-0 right-0 bottom-0 w-full max-w-2xl bg-bg-surface border-l border-line shadow-xl overflow-y-auto">
            <div className="sticky top-0 bg-bg-surface border-b border-line p-5 flex items-start justify-between gap-3 z-10">
              <div className="flex items-start gap-3 min-w-0">
                <div className="w-10 h-10 rounded-lg bg-primary-light text-primary grid place-items-center shrink-0">
                  <Buildings size={20} />
                </div>
                <div className="min-w-0">
                  <div className="font-display text-xl font-medium truncate" data-testid="school-roster-name">
                    {roster?.school?.name || "Your school"}
                  </div>
                  <div className="text-xs text-ink-muted">{roster?.school?.code} · {roster?.school?.academic_year || "—"}</div>
                </div>
              </div>
              <button onClick={() => setRosterOpen(false)} className="btn-ghost p-2" data-testid="roster-close-btn"><X size={18}/></button>
            </div>
            <div className="p-5 space-y-6">
              {rosterLoading ? <div className="text-ink-muted text-sm">Loading roster…</div> : roster && (
                <>
                  <div className="grid grid-cols-3 gap-3">
                    <KPI label="Students" value={roster.students.length} accent="info" testId="roster-kpi-students" />
                    <KPI label="Teachers" value={roster.teachers.length} accent="success" testId="roster-kpi-teachers" />
                    <KPI label="Classes" value={roster.counts?.classes || 0} accent="primary" testId="roster-kpi-classes" />
                  </div>
                  <Section title={`Teachers (${roster.teachers.length})`}>
                    {roster.teachers.length === 0 ? <Empty title="No teachers" /> : (
                      <div className="border border-line rounded-md overflow-hidden">
                        <table className="w-full text-sm">
                          <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                            <tr><th className="text-left p-2.5">Name</th><th className="text-left p-2.5">Email</th><th className="text-left p-2.5">Phone</th></tr>
                          </thead>
                          <tbody>
                            {roster.teachers.map((t) => (
                              <tr key={t.id} className="border-t border-line/60" data-testid={`roster-teacher-${t.id}`}>
                                <td className="p-2.5 font-medium">{t.name}</td>
                                <td className="p-2.5 text-ink-soft">{t.email}</td>
                                <td className="p-2.5 text-ink-soft">{t.phone || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </Section>
                  <Section title={`Students (${roster.students.length})`}>
                    {roster.students.length === 0 ? <Empty title="No students" /> : (
                      <div className="border border-line rounded-md overflow-hidden max-h-96 overflow-y-auto">
                        <table className="w-full text-sm">
                          <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider sticky top-0">
                            <tr><th className="text-left p-2.5">UID</th><th className="text-left p-2.5">Name</th><th className="text-left p-2.5">Class</th><th className="text-left p-2.5">Parent</th></tr>
                          </thead>
                          <tbody>
                            {roster.students.map((s) => (
                              <tr key={s.id} className="border-t border-line/60" data-testid={`roster-student-${s.id}`}>
                                <td className="p-2.5 font-mono text-xs text-ink-soft">{s.student_uid}</td>
                                <td className="p-2.5 font-medium">{s.name}</td>
                                <td className="p-2.5 text-ink-soft">{s.class_name || s.class_id} · {s.section}</td>
                                <td className="p-2.5 text-ink-soft text-xs">{s.parent?.name || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </Section>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
