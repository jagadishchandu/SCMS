import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { Link } from "react-router-dom";
import { ATTENDANCE_STATUSES } from "../../lib/utils";

export default function TeacherDashboard() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [timetable, setTimetable] = useState([]);
  const [perf, setPerf] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get("/students").then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
      api.get("/timetable").then((r) => r.data),
      api.get("/analytics/teacher-performance").then((r) => r.data[0]),
    ]).then(([s, c, t, p]) => { setStudents(s); setClasses(c); setTimetable(t); setPerf(p); });
  }, []);

  const today = new Date().toLocaleDateString("en-US", { weekday: "short" }).toLowerCase().slice(0, 3);
  const todays = timetable.filter((t) => t.day === today).sort((a, b) => a.period - b.period);

  return (
    <div data-testid="teacher-dashboard">
      <PageHeader eyebrow="Your day" title="Teacher dashboard"
        subtitle="A focused view of your assigned classes, students and tasks." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPI label="Today's classes" value={todays.length} accent="primary" testId="kpi-today-classes" />
        <KPI label="My students" value={students.length} accent="info" testId="kpi-my-students" />
        <KPI label="Performance score" value={perf?.score ?? "—"} accent={
          perf?.status === "Excellent" ? "success" :
          perf?.status === "Good" ? "info" :
          perf?.status === "Needs Attention" ? "warning" : "danger"
        } hint={perf?.status} testId="kpi-my-perf" />
        <KPI label="Assigned classes" value={perf?.assigned_classes ?? "—"} accent="secondary" testId="kpi-assigned-classes" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Section title="Today's schedule">
          {todays.length === 0 ? <Empty title="No classes today" message="Enjoy a calm day." /> :
            <ul className="divide-y divide-line">
              {todays.map((s) => (
                <li key={s.id} className="py-3 flex items-center justify-between">
                  <div>
                    <div className="font-medium">Period {s.period}</div>
                    <div className="text-xs text-ink-muted">{classes.find(c => c.id === s.class_id)?.name} · Section {s.section}</div>
                  </div>
                  <div className="text-sm text-ink-soft">{s.start_time}–{s.end_time}</div>
                </li>
              ))}
            </ul>}
        </Section>
        <Section title="Quick actions">
          <div className="space-y-2">
            <Link className="btn-primary w-full" to="/teacher/attendance" data-testid="ta-go-attendance">Mark attendance</Link>
            <Link className="btn-secondary w-full" to="/teacher/marks" data-testid="ta-go-marks">Enter marks</Link>
            <Link className="btn-secondary w-full" to="/teacher/students" data-testid="ta-go-students">View my students</Link>
          </div>
        </Section>
      </div>

      <Section title="My students">
        {students.length === 0 ? <Empty title="No students assigned" /> :
          <table className="table">
            <thead><tr><th className="th">UID</th><th className="th">Name</th><th className="th">Class</th><th className="th">Section</th></tr></thead>
            <tbody>
              {students.slice(0, 12).map((s) => (
                <tr key={s.id} className="table-row" data-testid={`teacher-student-${s.student_uid}`}>
                  <td className="td font-mono text-xs"><Link to={`/student/${s.student_uid}`}>{s.student_uid}</Link></td>
                  <td className="td font-medium">{s.name}</td>
                  <td className="td">{classes.find(c => c.id === s.class_id)?.name}</td>
                  <td className="td">{s.section}</td>
                </tr>
              ))}
            </tbody>
          </table>}
      </Section>
    </div>
  );
}
