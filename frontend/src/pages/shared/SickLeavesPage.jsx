import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, Section, Empty, KPI } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { formatDate } from "../../lib/utils";
import {
  Plus, Heartbeat, FileText, Trash, UploadSimple, Warning, CheckCircle,
  XCircle, Clock, Hourglass, User,
} from "@phosphor-icons/react";
import toast from "react-hot-toast";

const isApprover = (role) => role === "school_admin" || role === "teacher";

function statusBadge(leave) {
  const s = leave.status || "approved";
  if (s === "approved") return <span className="badge-success" data-testid={`status-${leave.id}`}><CheckCircle size={12}/> Approved</span>;
  if (s === "rejected") return <span className="badge-danger" data-testid={`status-${leave.id}`}><XCircle size={12}/> Rejected</span>;
  return <span className="badge-warning" data-testid={`status-${leave.id}`}><Hourglass size={12}/> Pending</span>;
}

function approvalStepBadge(stamp, label) {
  if (!stamp) return null;
  const s = stamp.status;
  const cls = s === "approved" ? "badge-success" : s === "rejected" ? "badge-danger" : "badge-warning";
  const Icon = s === "approved" ? CheckCircle : s === "rejected" ? XCircle : Clock;
  return (
    <span className={cls} title={stamp.note || ""}>
      <Icon size={12}/> {label}: {s}
    </span>
  );
}

function workingDaysExclSunday(startIso, endIso) {
  if (!startIso || !endIso) return 0;
  const start = new Date(startIso);
  const end = new Date(endIso);
  if (end < start) return 0;
  let count = 0;
  const d = new Date(start);
  while (d <= end) {
    if (d.getDay() !== 0) count++; // 0 = Sunday
    d.setDate(d.getDate() + 1);
  }
  return count;
}

export default function SickLeavesPage() {
  const { user } = useAuth();
  const [leaves, setLeaves] = useState([]);
  const [students, setStudents] = useState([]);
  const [recurring, setRecurring] = useState([]);
  const [todayList, setTodayList] = useState([]);
  const [pendingList, setPendingList] = useState([]);
  const [open, setOpen] = useState(false);
  const [decideTarget, setDecideTarget] = useState(null); // {leave, action}
  const [studentFilter, setStudentFilter] = useState("");

  const canManage = user && ["school_admin", "teacher", "parent"].includes(user.role);
  const canViewRecurring = user && isApprover(user.role);
  const canApprove = user && isApprover(user.role);

  const load = async () => {
    const params = studentFilter ? { student_uid: studentFilter } : {};
    const [l, s, rec, today, pend] = await Promise.all([
      api.get("/sick-leaves", { params }).then((r) => r.data),
      api.get("/students").then((r) => r.data).catch(() => []),
      canViewRecurring ? api.get("/sick-leaves/recurring", { params: { threshold: 3, days: 90 } }).then((r) => r.data).catch(() => []) : Promise.resolve([]),
      canApprove ? api.get("/sick-leaves/today").then((r) => r.data).catch(() => []) : Promise.resolve([]),
      canApprove ? api.get("/sick-leaves/pending-approvals").then((r) => r.data).catch(() => []) : Promise.resolve([]),
    ]);
    setLeaves(l);
    setStudents(s);
    setRecurring(rec);
    setTodayList(today);
    setPendingList(pend);
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

  const myPendingCount = pendingList.length;

  return (
    <div data-testid="sick-leaves-page">
      <PageHeader
        eyebrow="Health"
        title="Sick leave tracker"
        subtitle="Log multi-day sick leaves, attach medical certificates, and surface students with recurring absences. Leaves longer than 3 working days (excluding Sundays) require teacher AND school-admin approval."
        actions={canManage ? (
          <button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-leave-btn"><Plus size={16}/> New sick leave</button>
        ) : null}
      />

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-8">
        <KPI label="Logged leaves" value={leaves.length} accent="primary" testId="kpi-leave-count" />
        <KPI label="Total sick days" value={totalDays} accent="warning" testId="kpi-leave-days" />
        <KPI label="With medical certificate" value={leaves.filter((l) => l.medical_certificate).length} accent="success" testId="kpi-leave-certs" />
        {canApprove ? (
          <KPI label="Pending your approval" value={myPendingCount} accent={myPendingCount > 0 ? "danger" : "success"} testId="kpi-pending-approvals" />
        ) : (
          <KPI label="Awaiting approval"
               value={leaves.filter((l) => l.status === "pending").length}
               accent="warning" testId="kpi-parent-pending" />
        )}
      </div>

      {canApprove && (
        <Section title={`Sick leave list for today (${todayList.length})`}>
          {todayList.length === 0 ? (
            <Empty title="No students on sick leave today" message="All approved sick leaves covering today will appear here." />
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th className="th">Student</th>
                  <th className="th">From → To</th>
                  <th className="th">Reason</th>
                  <th className="th">Logged by</th>
                  <th className="th">Certificate</th>
                </tr></thead>
                <tbody>
                  {todayList.map((l) => (
                    <tr key={l.id} className="table-row" data-testid={`today-row-${l.id}`}>
                      <td className="td">
                        <div className="font-medium">{l.student_name || "—"}</div>
                        <div className="text-xs text-ink-muted font-mono">{l.student_uid}</div>
                      </td>
                      <td className="td text-xs">{formatDate(l.start_date)} → {formatDate(l.end_date)}</td>
                      <td className="td text-xs">{l.reason || <span className="text-ink-muted">—</span>}</td>
                      <td className="td text-xs">{l.recorded_by_name || l.recorded_by_role}</td>
                      <td className="td">
                        {l.medical_certificate ? (
                          <a href={l.medical_certificate.data_url} target="_blank" rel="noreferrer" className="badge-success">
                            <FileText size={12}/> view
                          </a>
                        ) : <span className="text-ink-muted text-xs">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}

      {canApprove && (
        <div className="mt-6">
          <Section title={`Pending approval requests (${pendingList.length})`}>
            {pendingList.length === 0 ? (
              <Empty title="No requests waiting on you" message="Parent-submitted leaves over 3 working days appear here for approval." />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {pendingList.map((l) => (
                  <div key={l.id} className="border border-amber-300 bg-amber-50 dark:bg-amber-900/10 rounded-lg p-4" data-testid={`pending-card-${l.id}`}>
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <div>
                        <div className="font-medium text-ink">{l.student_name}</div>
                        <div className="text-xs text-ink-muted font-mono">{l.student_uid}</div>
                      </div>
                      <span className="badge-warning"><Hourglass size={12}/> {l.working_days || workingDaysExclSunday(l.start_date, l.end_date)} working days</span>
                    </div>
                    <div className="text-sm mb-2">
                      <span className="text-ink-muted">From</span> <b>{formatDate(l.start_date)}</b>
                      <span className="text-ink-muted"> to </span> <b>{formatDate(l.end_date)}</b>
                    </div>
                    <div className="text-sm mb-2 flex items-start gap-1.5">
                      <User size={14} className="text-ink-muted mt-0.5"/>
                      <div><span className="text-ink-muted">Requested by:</span> {l.parent_name || l.recorded_by_role}</div>
                    </div>
                    <div className="bg-bg-surface dark:bg-bg-subtle rounded-md p-3 my-3 border border-line">
                      <div className="text-xs uppercase tracking-wide text-ink-muted mb-1">Reason given by parent</div>
                      <div className="text-sm whitespace-pre-wrap" data-testid={`pending-reason-${l.id}`}>
                        {l.reason || <span className="text-ink-muted italic">No reason provided</span>}
                      </div>
                      {l.diagnosis ? (
                        <div className="text-xs text-ink-muted mt-2">Diagnosis: {l.diagnosis}</div>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-2 mb-3">
                      {approvalStepBadge(l.teacher_approval, "Teacher")}
                      {approvalStepBadge(l.admin_approval, "Admin")}
                    </div>
                    <div className="flex justify-end gap-2">
                      <button
                        className="btn-secondary text-status-danger border-status-danger/30"
                        onClick={() => setDecideTarget({ leave: l, action: "reject" })}
                        data-testid={`reject-btn-${l.id}`}
                      >
                        <XCircle size={14}/> Reject
                      </button>
                      <button
                        className="btn-primary"
                        onClick={() => setDecideTarget({ leave: l, action: "approve" })}
                        data-testid={`approve-btn-${l.id}`}
                      >
                        <CheckCircle size={14}/> Approve
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>
      )}

      {canViewRecurring && recurring.length > 0 && (
        <div className="mt-6">
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
        </div>
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
                  <th className="th">Status</th>
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
                        <td className="td">
                          {statusBadge(l)}
                          {l.status === "pending" && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {approvalStepBadge(l.teacher_approval, "T")}
                              {approvalStepBadge(l.admin_approval, "A")}
                            </div>
                          )}
                        </td>
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

      <DecisionModal
        target={decideTarget}
        onClose={() => setDecideTarget(null)}
        onDone={() => { setDecideTarget(null); load(); }}
      />
    </div>
  );
}

function CreateLeaveModal({ open, onClose, students, user, onCreated }) {
  const [form, setForm] = useState({ student_id: "", start_date: "", end_date: "", reason: "", diagnosis: "" });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!form.reason || !form.reason.trim()) {
      toast.error("Please provide a reason");
      return;
    }
    setBusy(true);
    try {
      const res = await api.post("/sick-leaves", form);
      if (res.data?.status === "pending") {
        toast.success("Leave request submitted — awaiting teacher and admin approval");
      } else {
        toast.success("Sick leave recorded — attendance updated");
      }
      onCreated();
      setForm({ student_id: "", start_date: "", end_date: "", reason: "", diagnosis: "" });
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const visibleStudents = user?.role === "parent" ? students : students;

  const wDays = workingDaysExclSunday(form.start_date, form.end_date);
  const willNeedApproval = user?.role === "parent" && wDays > 3;

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
        <div className="md:col-span-2"><label className="label">Reason {user?.role === "parent" ? <span className="text-status-danger">*</span> : null}</label>
          <textarea className="input" rows={3} required={user?.role === "parent"} placeholder="e.g. Viral fever, doctor advised rest" value={form.reason} onChange={set("reason")} data-testid="leave-reason" />
        </div>
        <div className="md:col-span-2"><label className="label">Diagnosis (optional)</label><input className="input" placeholder="from doctor's note" value={form.diagnosis} onChange={set("diagnosis")} /></div>
        {form.start_date && form.end_date && (
          <div className="md:col-span-2 text-xs text-ink-soft">
            <b>{wDays}</b> working day{wDays !== 1 ? "s" : ""} (excluding Sundays)
          </div>
        )}
        {willNeedApproval ? (
          <div className="md:col-span-2 bg-amber-50 dark:bg-amber-900/10 border border-amber-300 rounded-md p-3 text-xs flex items-start gap-2" data-testid="approval-needed-banner">
            <Warning size={14} className="text-amber-700 mt-0.5 shrink-0" />
            <div>
              <b>Approval required.</b> Leaves longer than 3 working days need approval from both the class teacher and the school admin before attendance is updated.
            </div>
          </div>
        ) : (
          <div className="md:col-span-2 text-xs text-ink-muted flex items-center gap-2">
            <Heartbeat size={14} /> Attendance will be auto-marked 'sick' for working days within the span.
          </div>
        )}
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-leave-btn">
            {busy ? "Saving…" : willNeedApproval ? "Submit for approval" : "Record leave"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DecisionModal({ target, onClose, onDone }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (target) setNote(""); }, [target]);
  if (!target) return null;
  const { leave, action } = target;
  const isApprove = action === "approve";

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post(`/sick-leaves/${leave.id}/${action}`, { note: note || null });
      toast.success(isApprove ? "Leave approved" : "Leave rejected");
      onDone();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={!!target} onClose={onClose} title={isApprove ? "Approve sick leave" : "Reject sick leave"} size="sm" testId="decision-modal">
      <form onSubmit={submit} className="space-y-3">
        <div className="text-sm">
          <div><b>{leave.student_name}</b> <span className="text-ink-muted font-mono text-xs">{leave.student_uid}</span></div>
          <div className="text-xs text-ink-muted">{formatDate(leave.start_date)} → {formatDate(leave.end_date)} · {leave.working_days || workingDaysExclSunday(leave.start_date, leave.end_date)} working days</div>
        </div>
        <div className="bg-bg-subtle rounded-md p-3 text-sm">
          <div className="text-xs uppercase tracking-wide text-ink-muted mb-1">Reason from parent</div>
          {leave.reason || <span className="text-ink-muted italic">No reason provided</span>}
        </div>
        <div>
          <label className="label">Note (optional)</label>
          <textarea className="input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} data-testid="decision-note" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            type="submit"
            disabled={busy}
            className={isApprove ? "btn-primary" : "btn-primary bg-status-danger hover:bg-status-danger"}
            data-testid="decision-submit"
          >
            {busy ? "Saving…" : isApprove ? "Approve" : "Reject"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
