import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, Section, Empty, KPI } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { formatDate } from "../../lib/utils";
import { Plus, Heartbeat, FileText, Trash, UploadSimple, Warning } from "@phosphor-icons/react";
import toast from "react-hot-toast";

export default function SickLeavesPage() {
  const { user } = useAuth();
  const [leaves, setLeaves] = useState([]);
  const [students, setStudents] = useState([]);
  const [recurring, setRecurring] = useState([]);
  const [open, setOpen] = useState(false);
  const [studentFilter, setStudentFilter] = useState("");

  const canManage = user && ["school_admin", "teacher", "parent"].includes(user.role);
  const canViewRecurring = user && ["school_admin", "teacher"].includes(user.role);

  const load = async () => {
    const params = studentFilter ? { student_uid: studentFilter } : {};
    const [l, s, rec] = await Promise.all([
      api.get("/sick-leaves", { params }).then((r) => r.data),
      api.get("/students").then((r) => r.data).catch(() => []),
      canViewRecurring ? api.get("/sick-leaves/recurring", { params: { threshold: 3, days: 90 } }).then((r) => r.data).catch(() => []) : Promise.resolve([]),
    ]);
    setLeaves(l);
    setStudents(s);
    setRecurring(rec);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [studentFilter]);

  const remove = async (id) => {
    if (!window.confirm("Delete this sick-leave record?")) return;
    try {
      await api.delete(`/sick-leaves/${id}`);
      toast.success("Leave removed");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const uploadCert = async (id, file) => {
    if (!file) return;
    try {
      const fd = new FormData(); fd.append("file", file);
      await api.post(`/sick-leaves/${id}/certificate`, fd);
      toast.success("Medical certificate uploaded");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const totalDays = useMemo(() => leaves.reduce((acc, l) => {
    const s = new Date(l.start_date), e = new Date(l.end_date);
    return acc + Math.max(1, Math.round((e - s) / 86400000) + 1);
  }, 0), [leaves]);

  return (
    <div data-testid="sick-leaves-page">
      <PageHeader
        eyebrow="Health"
        title="Sick leave tracker"
        subtitle="Log multi-day sick leaves, attach medical certificates, and surface students with recurring absences."
        actions={canManage ? (
          <button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-leave-btn"><Plus size={16}/> New sick leave</button>
        ) : null}
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <KPI label="Logged leaves" value={leaves.length} accent="primary" testId="kpi-leave-count" />
        <KPI label="Total sick days" value={totalDays} accent="warning" testId="kpi-leave-days" />
        <KPI label="With medical certificate" value={leaves.filter((l) => l.medical_certificate).length} accent="success" testId="kpi-leave-certs" />
      </div>

      {canViewRecurring && recurring.length > 0 && (
        <Section title="Recurring sick leaves (≥ 3 in 90 days)">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recurring.map((r) => (
              <div key={r.student_id} className="border border-amber-300 bg-amber-50 dark:bg-amber-900/10 rounded-lg p-4" data-testid={`recurring-${r.student_uid}`}>
                <div className="flex items-center gap-2 mb-2">
                  <Warning size={18} className="text-amber-700" />
                  <div className="font-medium">{r.name}</div>
                </div>
                <div className="text-xs text-ink-muted font-mono">{r.student_uid}</div>
                <div className="text-sm mt-2">{r.leaves_in_window} sick leaves in last 90 days</div>
                <div className="text-xs text-ink-muted">last on {formatDate(r.last_end)}</div>
                <button className="btn-secondary text-xs px-3 py-1.5 mt-3" onClick={() => setStudentFilter(r.student_uid)}>View leaves</button>
              </div>
            ))}
          </div>
        </Section>
      )}

      <div className="mt-6">
        <Section title={`${leaves.length} leaves`} action={
          <div className="flex items-center gap-2">
            <input className="input w-44" placeholder="Filter by STU-UID" value={studentFilter}
              onChange={(e) => setStudentFilter(e.target.value)} data-testid="leave-uid-filter" />
            {studentFilter && <button className="btn-ghost text-xs" onClick={() => setStudentFilter("")}>Clear</button>}
          </div>
        }>
          {leaves.length === 0 ? <Empty title="No sick leaves recorded" message="Use the New sick leave button to log one." /> :
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th className="th">Student</th><th className="th">From → To</th><th className="th">Days</th>
                  <th className="th">Reason / Diagnosis</th><th className="th">Certificate</th><th className="th">Logged</th><th className="th"></th>
                </tr></thead>
                <tbody>
                  {leaves.map((l) => {
                    const s = students.find((st) => st.id === l.student_id) || { name: "—", student_uid: l.student_uid };
                    const days = Math.max(1, Math.round((new Date(l.end_date) - new Date(l.start_date)) / 86400000) + 1);
                    return (
                      <tr key={l.id} className="table-row" data-testid={`leave-row-${l.id}`}>
                        <td className="td"><div className="font-medium">{s.name}</div><div className="text-xs text-ink-muted font-mono">{l.student_uid}</div></td>
                        <td className="td text-xs">{formatDate(l.start_date)} <span className="text-ink-muted">→</span> {formatDate(l.end_date)}</td>
                        <td className="td">{days}</td>
                        <td className="td text-xs">
                          {l.reason ? <div>{l.reason}</div> : null}
                          {l.diagnosis ? <div className="text-ink-muted">{l.diagnosis}</div> : null}
                          {!l.reason && !l.diagnosis ? <span className="text-ink-muted">—</span> : null}
                        </td>
                        <td className="td">
                          {l.medical_certificate ? (
                            <a href={l.medical_certificate.data_url} target="_blank" rel="noreferrer" className="badge-success" data-testid={`cert-link-${l.id}`}>
                              <FileText size={12} /> view
                            </a>
                          ) : (
                            <label className="btn-secondary text-xs px-2.5 py-1 cursor-pointer" data-testid={`upload-cert-label-${l.id}`}>
                              <UploadSimple size={12} /> Upload
                              <input type="file" accept="image/*,application/pdf" className="hidden"
                                onChange={(e) => uploadCert(l.id, e.target.files?.[0])} data-testid={`upload-cert-${l.id}`} />
                            </label>
                          )}
                        </td>
                        <td className="td text-xs text-ink-muted">{formatDate(l.created_at)}<br/><span>by {l.recorded_by_role}</span></td>
                        <td className="td">
                          {(user?.role === "school_admin" || (user?.role === "parent" && l.recorded_by === user.id)) && (
                            <button className="btn-ghost text-status-danger p-1.5" onClick={() => remove(l.id)} data-testid={`delete-leave-${l.id}`}>
                              <Trash size={14} />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>}
        </Section>
      </div>

      <CreateLeaveModal open={open} onClose={() => setOpen(false)} students={students} user={user}
        onCreated={() => { setOpen(false); load(); }} />
    </div>
  );
}

function CreateLeaveModal({ open, onClose, students, user, onCreated }) {
  const [form, setForm] = useState({ student_id: "", start_date: "", end_date: "", reason: "", diagnosis: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/sick-leaves", form);
      toast.success("Sick leave recorded — attendance updated");
      onCreated();
      setForm({ student_id: "", start_date: "", end_date: "", reason: "", diagnosis: "" });
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const visibleStudents = user?.role === "parent" ? students : students;

  return (
    <Modal open={open} onClose={onClose} title="Record sick leave" size="md" testId="create-leave-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <label className="label">Student</label>
          <select className="input" required value={form.student_id} onChange={set("student_id")} data-testid="leave-student-select">
            <option value="">Select student…</option>
            {visibleStudents.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.student_uid}</option>)}
          </select>
        </div>
        <div><label className="label">Start date</label><input className="input" type="date" required value={form.start_date} onChange={set("start_date")} data-testid="leave-start-date" /></div>
        <div><label className="label">End date</label><input className="input" type="date" required value={form.end_date} onChange={set("end_date")} data-testid="leave-end-date" /></div>
        <div className="md:col-span-2"><label className="label">Reason</label><input className="input" placeholder="e.g. Viral fever" value={form.reason} onChange={set("reason")} data-testid="leave-reason" /></div>
        <div className="md:col-span-2"><label className="label">Diagnosis (optional)</label><input className="input" placeholder="from doctor's note" value={form.diagnosis} onChange={set("diagnosis")} /></div>
        <div className="md:col-span-2 text-xs text-ink-muted flex items-center gap-2">
          <Heartbeat size={14} /> Attendance will be auto-marked 'sick' for working days within the span.
        </div>
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-leave-btn">{busy ? "Saving…" : "Record leave"}</button>
        </div>
      </form>
    </Modal>
  );
}
