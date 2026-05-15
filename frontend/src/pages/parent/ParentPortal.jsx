import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { currency, formatDate, CHART_COLORS } from "../../lib/utils";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, Legend } from "recharts";

export default function ParentPortal() {
  const [students, setStudents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [dash, setDash] = useState(null);

  useEffect(() => {
    api.get("/students").then((r) => {
      setStudents(r.data);
      if (r.data.length) setSelected(r.data[0]);
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    api.get(`/analytics/student/${selected.student_uid}`).then((r) => setDash(r.data));
  }, [selected]);

  if (!students.length) return <div className="card">No child linked to your account.</div>;

  return (
    <div data-testid="parent-portal">
      <PageHeader eyebrow="Parent portal" title={`Welcome, ${selected ? "tracking " + selected.name : ""}`}
        subtitle="Your child's complete academic and attendance picture, all in one place." />

      {students.length > 1 && (
        <div className="flex gap-2 mb-4">
          {students.map((s) => (
            <button key={s.id} onClick={() => setSelected(s)} className={`btn-secondary ${selected?.id === s.id ? "border-primary text-primary" : ""}`} data-testid={`child-tab-${s.student_uid}`}>
              {s.name}
            </button>
          ))}
        </div>
      )}

      {dash ? <DashboardView dash={dash} /> : <div className="skeleton h-40 w-full" />}
    </div>
  );
}

function DashboardView({ dash }) {
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
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPI label="Attendance" value={`${attendance.attendance_percentage}%`}
          accent={attendance.attendance_percentage >= 85 ? "success" : attendance.attendance_percentage >= 70 ? "warning" : "danger"}
          hint={`${attendance.total_days} days tracked`} testId="parent-att" />
        <KPI label="Overall %" value={`${academics.overall_percentage}%`} accent="primary"
          hint={academics.improvement?.status} testId="parent-overall" />
        <KPI label="Fee outstanding" value={currency(fees.due)} accent={fees.due > 0 ? "danger" : "success"} testId="parent-fee" />
        <KPI label="Class" value={student.section} hint={`Roll ${student.roll_number || "—"}`} accent="info" testId="parent-class" />
      </div>

      {insights.length > 0 && (
        <Section title="Insights">
          <ul className="space-y-2">
            {insights.map((i, idx) => (
              <li key={idx} className={
                "px-3 py-2 rounded-md text-sm " +
                (i.type === "success" ? "bg-status-success-bg text-status-success"
                  : i.type === "warning" ? "bg-status-warning-bg text-status-warning"
                  : i.type === "danger" ? "bg-status-danger-bg text-status-danger"
                  : "bg-bg-subtle text-ink-soft")
              } data-testid={`insight-${idx}`}>{i.text}</li>
            ))}
          </ul>
        </Section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6 mb-6">
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
        <Section title="Marks trend across exams">
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

      <Section title="Subject-wise: student vs class average">
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
    </>
  );
}
