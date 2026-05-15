import React, { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { currency, CHART_COLORS, formatDate } from "../../lib/utils";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, Legend } from "recharts";
import toast from "react-hot-toast";

export default function StudentAnalytics() {
  const params = useParams();
  const navigate = useNavigate();
  const [uid, setUid] = useState(params.uid || "");
  const [dash, setDash] = useState(null);
  const [loading, setLoading] = useState(false);

  React.useEffect(() => {
    if (params.uid) doSearch(params.uid);
    // eslint-disable-next-line
  }, [params.uid]);

  const doSearch = async (id) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/analytics/student/${id}`);
      setDash(data);
    } catch (err) { toast.error(formatApiError(err)); setDash(null); }
    finally { setLoading(false); }
  };

  const submit = (e) => { e.preventDefault(); if (uid) navigate(`/student/${uid}`); };

  return (
    <div data-testid="student-analytics-page">
      <PageHeader eyebrow="Student search" title="Look up any student in seconds"
        subtitle="Type a student's unique ID (e.g. STU-00001) to open their full analytics dashboard." />

      <form onSubmit={submit} className="flex gap-2 mb-6 max-w-md">
        <div className="relative flex-1">
          <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input className="input pl-10" placeholder="e.g. STU-00001" value={uid} onChange={(e) => setUid(e.target.value.toUpperCase())} data-testid="sa-uid-input" />
        </div>
        <button className="btn-primary" data-testid="sa-search-btn">Open</button>
      </form>

      {loading && <div className="skeleton h-40 w-full" />}
      {!loading && dash && <DashView dash={dash} />}
      {!loading && !dash && uid && <Empty title="No data" message="No matching student found. Try a different UID." />}
    </div>
  );
}

function DashView({ dash }) {
  const { student, attendance, academics, fees, insights } = dash;

  const attData = [
    { name: "Present", value: attendance.counts.present },
    { name: "Absent", value: attendance.counts.absent },
    { name: "Sick", value: attendance.counts.sick },
    { name: "Late", value: attendance.counts.late },
    { name: "Half day", value: attendance.counts.half_day },
    { name: "Excused", value: attendance.counts.excused },
  ].filter((x) => x.value > 0);

  const subjectVsClass = academics.subject_avg.map((s) => ({
    subject: s.subject, student: s.avg, class: academics.class_subject_avg[s.subject] || 0,
  }));

  return (
    <>
      <div className="card mb-6" data-testid="sa-profile-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="overline mb-1">{student.student_uid}</div>
            <h2 className="font-display text-3xl font-medium">{student.name}</h2>
            <div className="text-ink-soft text-sm mt-1">
              Roll #{student.roll_number} · Section {student.section} · DOB {student.dob || "—"}
            </div>
            <div className="text-xs text-ink-muted mt-2">
              Parent: {student.parent?.name} · {student.parent?.phone}
            </div>
          </div>
          <div className="flex gap-2 flex-wrap">
            {academics.improvement && (
              <span className={
                academics.improvement.status === "improving" ? "badge-success" :
                academics.improvement.status === "declining" ? "badge-danger" : "badge-neutral"
              }>{academics.improvement.status} ({academics.improvement.diff > 0 ? "+" : ""}{academics.improvement.diff}%)</span>
            )}
            {academics.strongest && <span className="badge-success">Best: {academics.strongest.subject} {academics.strongest.avg}%</span>}
            {academics.weakest && <span className="badge-warning">Focus: {academics.weakest.subject} {academics.weakest.avg}%</span>}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPI label="Attendance" value={`${attendance.attendance_percentage}%`}
          accent={attendance.attendance_percentage >= 85 ? "success" : attendance.attendance_percentage >= 70 ? "warning" : "danger"}
          hint={`${attendance.total_days} days tracked`} testId="sa-kpi-att" />
        <KPI label="Overall marks" value={`${academics.overall_percentage}%`} accent="primary" testId="sa-kpi-marks" />
        <KPI label="Fee paid" value={currency(fees.paid)} accent="success" testId="sa-kpi-paid" />
        <KPI label="Fee due" value={currency(fees.due)} accent={fees.due > 0 ? "danger" : "success"} testId="sa-kpi-due" />
      </div>

      {insights.length > 0 && (
        <Section title="Insights & alerts">
          <ul className="space-y-2">
            {insights.map((i, idx) => (
              <li key={idx} className={
                "px-3 py-2 rounded-md text-sm " +
                (i.type === "success" ? "bg-status-success-bg text-status-success"
                  : i.type === "warning" ? "bg-status-warning-bg text-status-warning"
                  : i.type === "danger" ? "bg-status-danger-bg text-status-danger"
                  : "bg-bg-subtle text-ink-soft")
              } data-testid={`sa-insight-${idx}`}>{i.text}</li>
            ))}
          </ul>
        </Section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Section title="Attendance split">
          {attData.length === 0 ? <Empty title="No attendance yet" /> :
            <div className="h-64">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={attData} dataKey="value" innerRadius={55} outerRadius={90} paddingAngle={2}>
                    {attData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>}
        </Section>
        <Section title="Marks trend">
          {academics.exam_trend.length === 0 ? <Empty title="No marks yet" /> :
            <div className="h-64">
              <ResponsiveContainer>
                <LineChart data={academics.exam_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E6E1D6" />
                  <XAxis dataKey="exam" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="avg" stroke={CHART_COLORS[0]} strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>}
        </Section>
      </div>

      <div className="mt-6 mb-6">
        <Section title="Subject-wise · student vs class average">
          {subjectVsClass.length === 0 ? <Empty title="No marks yet" /> :
            <div className="h-72">
              <ResponsiveContainer>
                <BarChart data={subjectVsClass}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E6E1D6" />
                  <XAxis dataKey="subject" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="student" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="class" fill={CHART_COLORS[1]} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>}
        </Section>
      </div>

      <Section title="Monthly attendance">
        {attendance.monthly.length === 0 ? <Empty title="No data" /> :
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={attendance.monthly} stackOffset="sign">
                <CartesianGrid strokeDasharray="3 3" stroke="#E6E1D6" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="present" stackId="a" fill={CHART_COLORS[0]} />
                <Bar dataKey="absent" stackId="a" fill={CHART_COLORS[2]} />
                <Bar dataKey="sick" stackId="a" fill={CHART_COLORS[1]} />
                <Bar dataKey="late" stackId="a" fill={CHART_COLORS[3]} />
              </BarChart>
            </ResponsiveContainer>
          </div>}
      </Section>
    </>
  );
}
