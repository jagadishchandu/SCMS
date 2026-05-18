import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { currency, formatDate, CHART_COLORS } from "../../lib/utils";
import { Camera, UserCircle, DownloadSimple, Receipt, GraduationCap, Lightning, BookOpen, CalendarBlank, Warning, ArrowRight } from "@phosphor-icons/react";
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

      {/* Subject focus + upcoming exam countdown — split into two cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <SubjectFocusCard lagging={academics.lagging_subjects || []} />
        <UpcomingExamsCard exams={academics.upcoming_exams || []} />
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


/* ============================================================
   Subject focus + Upcoming exam countdown — Parent dashboard
   ============================================================ */

function statusToTone(status) {
  if (status === "critical") return { wrap: "border-status-danger/40 bg-status-danger-bg", dot: "bg-status-danger" };
  if (status === "needs_work") return { wrap: "border-status-warning/40 bg-status-warning-bg", dot: "bg-status-warning" };
  return { wrap: "border-status-info/30 bg-status-info-bg", dot: "bg-status-info" };
}

function SubjectFocusCard({ lagging }) {
  return (
    <Section title="Where focus is needed" data-testid="parent-subject-focus">
      <div className="flex items-center gap-2 mb-3 text-xs text-ink-muted">
        <Lightning size={12} weight="fill" className="text-status-warning" />
        Based on the most recent exam marks.
      </div>
      {lagging.length === 0 ? (
        <div className="empty-state flex items-center gap-3 px-4 py-6 text-status-success">
          <GraduationCap size={28} weight="duotone" />
          <div>
            <div className="font-display text-sm font-medium">Great work — no weak subjects right now.</div>
            <div className="text-xs text-ink-muted">Keep practising consistently across all subjects.</div>
          </div>
        </div>
      ) : (
        <ul className="space-y-3" data-testid="parent-lagging-list">
          {lagging.map((row) => {
            const tone = statusToTone(row.status);
            return (
              <li
                key={row.subject}
                className={`rounded-lg border ${tone.wrap} p-3 flex items-start gap-3 transition-transform hover:-translate-y-0.5`}
                data-testid={`parent-lagging-${row.subject.toLowerCase()}`}
              >
                <span className={`w-2 h-2 rounded-full mt-2 ${tone.dot}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <div className="font-medium text-sm text-ink">{row.subject}</div>
                    <div className="text-[11px] text-ink-muted">
                      Student <strong>{row.student_avg}%</strong>
                      {row.class_avg != null && <> · Class avg <strong>{row.class_avg}%</strong></>}
                      {row.gap != null && row.gap > 0 ? <> · <span className="text-status-warning font-medium">{row.gap}% behind</span></> : null}
                    </div>
                  </div>
                  <div className="text-xs mt-1 text-ink-soft">{row.suggestion}</div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

function UpcomingExamsCard({ exams }) {
  return (
    <Section title="Next exam countdown" data-testid="parent-upcoming-exams">
      <div className="flex items-center gap-2 mb-3 text-xs text-ink-muted">
        <CalendarBlank size={12} weight="fill" className="text-status-info" />
        Days remaining until each subject's paper.
      </div>
      {exams.length === 0 ? (
        <Empty title="No exams scheduled" message="When the school publishes the next exam, the countdown will appear here." />
      ) : (
        <div className="space-y-4" data-testid="parent-exam-list">
          {exams.map((ex) => (
            <div key={ex.id} className={`rounded-lg border ${ex.is_next ? "border-primary/40 bg-primary-light" : "border-line bg-bg-subtle"} p-3`} data-testid={`parent-exam-${ex.id}`}>
              <div className="flex items-baseline justify-between gap-2 mb-2">
                <div className="font-display font-medium text-sm text-ink">{ex.name}<span className="text-xs text-ink-muted font-normal"> · {ex.term}</span></div>
                <div className={`text-xs font-semibold px-2 py-0.5 rounded-full ${ex.days_until <= 7 ? "bg-status-danger text-white" : ex.days_until <= 14 ? "bg-status-warning text-white" : "bg-primary text-white"}`}>
                  {ex.days_until === 0 ? "TODAY" : ex.days_until === 1 ? "TOMORROW" : `${ex.days_until} days`}
                </div>
              </div>
              {ex.schedule?.length > 0 ? (
                <ul className="space-y-1">
                  {ex.schedule.map((s, idx) => (
                    <li
                      key={idx}
                      className="flex items-center gap-2 text-xs bg-bg-surface rounded-md px-2 py-1.5 border border-line"
                      data-testid={`parent-exam-paper-${ex.id}-${idx}`}
                    >
                      <BookOpen size={12} className="text-ink-muted shrink-0" />
                      <div className="flex-1 truncate">
                        <strong>{s.subject}</strong>
                        {s.time ? <span className="text-ink-muted"> · {s.time}</span> : null}
                      </div>
                      <span className="text-ink-muted">{formatDate(s.date)}</span>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${s.days_until <= 3 ? "bg-status-danger-bg text-status-danger" : s.days_until <= 7 ? "bg-status-warning-bg text-status-warning" : "bg-status-info-bg text-status-info"}`}>
                        {s.days_until}d
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-xs text-ink-muted">Schedule will be published soon.</div>
              )}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
