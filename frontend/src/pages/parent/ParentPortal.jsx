import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { currency, formatDate, CHART_COLORS } from "../../lib/utils";
import { Camera, UserCircle, DownloadSimple, Receipt } from "@phosphor-icons/react";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, Legend } from "recharts";
import toast from "react-hot-toast";

export default function ParentPortal() {
  const [students, setStudents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [dash, setDash] = useState(null);
  const [payments, setPayments] = useState([]);

  const loadStudents = async () => {
    const r = await api.get("/students");
    setStudents(r.data);
    if (r.data.length && !selected) setSelected(r.data[0]);
    if (selected) {
      const updated = r.data.find((s) => s.id === selected.id);
      if (updated) setSelected(updated);
    }
  };

  useEffect(() => { loadStudents(); /* eslint-disable-next-line */ }, []);

  useEffect(() => {
    if (!selected) return;
    Promise.all([
      api.get(`/analytics/student/${selected.student_uid}`).then((r) => r.data),
      api.get(`/fees/payments`, { params: { student_id: selected.id } }).then((r) => r.data),
    ]).then(([d, p]) => { setDash(d); setPayments(p); });
  }, [selected]);

  const onPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selected) return;
    try {
      const fd = new FormData(); fd.append("file", file);
      await api.post(`/students/${selected.id}/photo`, fd);
      toast.success("Photo updated");
      loadStudents();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const downloadReceipt = async (pid) => {
    try {
      const res = await api.get(`/receipts/payment/${pid}.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = `receipt_${pid}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const downloadReport = async () => {
    if (!selected) return;
    try {
      const res = await api.get(`/receipts/student/${selected.student_uid}/report.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = `${selected.student_uid}_report.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  if (!students.length) return <div className="card">No child linked to your account.</div>;

  return (
    <div data-testid="parent-portal">
      <PageHeader eyebrow="Parent portal" title={`Welcome, ${selected ? "tracking " + selected.name : ""}`}
        subtitle="Your child's complete academic and attendance picture, all in one place."
        actions={selected ? <button className="btn-secondary" onClick={downloadReport} data-testid="parent-download-report"><DownloadSimple size={14}/> Report PDF</button> : null}
      />

      {students.length > 1 && (
        <div className="flex gap-2 mb-4 flex-wrap">
          {students.map((s) => (
            <button key={s.id} onClick={() => setSelected(s)} className={`btn-secondary ${selected?.id === s.id ? "border-primary text-primary" : ""}`} data-testid={`child-tab-${s.student_uid}`}>
              {s.name}
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="card mb-4 flex items-center gap-4" data-testid="parent-child-card">
          <div className="relative w-16 h-16 rounded-lg overflow-hidden bg-bg-subtle grid place-items-center border border-line shrink-0">
            {selected.photo ? (
              <img src={selected.photo} alt={selected.name} className="w-full h-full object-cover" />
            ) : (
              <UserCircle size={40} className="text-ink-muted" />
            )}
            <label className="absolute bottom-1 right-1 bg-primary text-white p-1 rounded cursor-pointer" title="Upload photo">
              <Camera size={11} />
              <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={onPhoto} data-testid="parent-photo-input" />
            </label>
          </div>
          <div className="min-w-0">
            <div className="font-display text-lg font-medium truncate">{selected.name}</div>
            <div className="text-xs text-ink-muted">{selected.student_uid} · Section {selected.section} · Roll {selected.roll_number || "—"}</div>
          </div>
        </div>
      )}

      {dash ? <DashboardView dash={dash} payments={payments} onReceipt={downloadReceipt} /> : <div className="skeleton h-40 w-full" />}
    </div>
  );
}

function DashboardView({ dash, payments, onReceipt }) {
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

      <div className="mt-6">
        <Section title="Payment history & receipts">
          {payments.length === 0 ? <Empty title="No payments yet" /> :
            <ul className="divide-y divide-line">
              {payments.map((p) => (
                <li key={p.id} className="py-3 flex items-center justify-between" data-testid={`pp-pay-${p.id}`}>
                  <div>
                    <div className="font-medium">{currency(p.amount)} · {p.mode}</div>
                    <div className="text-xs text-ink-muted">Receipt {p.receipt_no} · {formatDate(p.created_at)}</div>
                  </div>
                  <button className="btn-secondary" onClick={() => onReceipt(p.id)} data-testid={`pp-receipt-${p.id}`}>
                    <Receipt size={14}/> Download
                  </button>
                </li>
              ))}
            </ul>}
        </Section>
      </div>
    </>
  );
}
