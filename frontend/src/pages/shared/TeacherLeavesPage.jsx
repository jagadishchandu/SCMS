import React, { useEffect, useMemo, useState, useCallback } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import DatePicker from "../../components/DatePicker";
import { useAuth } from "../../contexts/AuthContext";
import toast from "react-hot-toast";

const LEAVE_TYPES = [
  { value: "casual", label: "Casual" },
  { value: "sick", label: "Sick" },
  { value: "earned", label: "Earned" },
  { value: "maternity", label: "Maternity" },
  { value: "other", label: "Other" },
];

const STATUS_TINT = {
  pending: "bg-status-warning-bg text-status-warning border-status-warning/40",
  approved: "bg-status-success-bg text-status-success border-status-success/40",
  rejected: "bg-status-danger-bg text-status-danger border-status-danger/40",
  cancelled: "bg-bg-subtle text-ink-muted border-line",
};

function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md border text-xs font-medium uppercase tracking-wider ${STATUS_TINT[status] || "border-line"}`}
      data-testid={`leave-status-${status}`}
    >
      {status}
    </span>
  );
}

function CreateLeaveForm({ onCreated }) {
  const [form, setForm] = useState({
    leave_type: "casual",
    start_date: "",
    end_date: "",
    reason: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.start_date || !form.end_date) {
      toast.error("Pick start & end dates");
      return;
    }
    if (form.end_date < form.start_date) {
      toast.error("End date cannot be before start date");
      return;
    }
    setSubmitting(true);
    try {
      await api.post("/teacher-leaves", form);
      toast.success("Leave request submitted — school admin will review it.");
      setForm({ leave_type: "casual", start_date: "", end_date: "", reason: "" });
      onCreated?.();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} data-testid="leave-create-form" className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="label">Leave type</label>
          <select
            className="input"
            value={form.leave_type}
            onChange={(e) => setForm({ ...form, leave_type: e.target.value })}
            data-testid="leave-type-select"
          >
            {LEAVE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Start date</label>
          <DatePicker
            value={form.start_date}
            onChange={(v) => setForm({ ...form, start_date: v })}
            testId="leave-start-date"
          />
        </div>
        <div>
          <label className="label">End date</label>
          <DatePicker
            value={form.end_date}
            onChange={(v) => setForm({ ...form, end_date: v })}
            testId="leave-end-date"
            minDate={form.start_date || undefined}
          />
        </div>
      </div>
      <div>
        <label className="label">Reason (optional)</label>
        <textarea
          className="input min-h-[80px]"
          placeholder="Short note for school admin…"
          value={form.reason}
          onChange={(e) => setForm({ ...form, reason: e.target.value })}
          data-testid="leave-reason-input"
        />
      </div>
      <div className="flex justify-end">
        <button
          type="submit"
          disabled={submitting}
          className="btn-primary"
          data-testid="leave-submit-btn"
        >
          {submitting ? "Submitting…" : "Submit leave request"}
        </button>
      </div>
    </form>
  );
}

function LeaveRow({ leave, isAdmin, onChanged, teacherNameMap }) {
  const [busy, setBusy] = useState(false);
  const teacherName = leave.teacher_name || teacherNameMap?.[leave.teacher_id] || leave.teacher_id;

  const decide = async (decision) => {
    setBusy(true);
    try {
      await api.post(`/teacher-leaves/${leave.id}/${decision}`, { note: "" });
      toast.success(`Leave ${decision === "approve" ? "approved" : "rejected"}`);
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!window.confirm("Cancel this leave request?")) return;
    setBusy(true);
    try {
      await api.delete(`/teacher-leaves/${leave.id}`);
      toast.success("Leave cancelled");
      onChanged?.();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <tr className="table-row" data-testid={`leave-row-${leave.id}`}>
      {isAdmin && (
        <td className="td font-medium">{teacherName}</td>
      )}
      <td className="td capitalize">{leave.leave_type}</td>
      <td className="td">
        <div className="text-sm">{leave.start_date} → {leave.end_date}</div>
        <div className="text-xs text-ink-muted">{leave.working_days} day(s)</div>
      </td>
      <td className="td max-w-xs">
        <div className="text-sm text-ink-soft truncate" title={leave.reason || ""}>
          {leave.reason || <span className="text-ink-muted">—</span>}
        </div>
        {leave.decision_note && (
          <div className="text-[11px] text-ink-muted italic mt-1">
            Admin note: {leave.decision_note}
          </div>
        )}
      </td>
      <td className="td">
        <StatusBadge status={leave.status} />
        {leave.decided_by_name && leave.status !== "pending" && (
          <div className="text-[10px] text-ink-muted mt-1">
            by {leave.decided_by_name}
          </div>
        )}
      </td>
      <td className="td">
        <div className="flex gap-2 justify-end flex-wrap">
          {isAdmin && leave.status === "pending" && (
            <>
              <button
                className="btn-primary text-xs px-3 py-1"
                disabled={busy}
                onClick={() => decide("approve")}
                data-testid={`leave-approve-${leave.id}`}
              >
                Approve
              </button>
              <button
                className="btn-ghost text-xs px-3 py-1 text-status-danger"
                disabled={busy}
                onClick={() => decide("reject")}
                data-testid={`leave-reject-${leave.id}`}
              >
                Reject
              </button>
            </>
          )}
          {!isAdmin && leave.status === "pending" && (
            <button
              className="btn-ghost text-xs px-3 py-1 text-status-danger"
              disabled={busy}
              onClick={cancel}
              data-testid={`leave-cancel-${leave.id}`}
            >
              Cancel
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

export default function TeacherLeavesPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "school_admin";
  const [leaves, setLeaves] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState(isAdmin ? "pending" : "all");
  const [teachers, setTeachers] = useState([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter !== "all" ? { status: filter } : {};
      const { data } = await api.get("/teacher-leaves", { params });
      setLeaves(data);
    } catch {
      setLeaves([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    if (isAdmin) {
      api.get("/users", { params: { role: "teacher" } })
        .then((r) => setTeachers(r.data || []))
        .catch(() => setTeachers([]));
    }
  }, [isAdmin]);

  const teacherNameMap = useMemo(
    () => Object.fromEntries(teachers.map((t) => [t.id, t.name])),
    [teachers],
  );

  const grouped = useMemo(() => {
    const out = { pending: [], approved: [], rejected: [], cancelled: [] };
    for (const l of leaves) (out[l.status] ||= []).push(l);
    return out;
  }, [leaves]);

  return (
    <div data-testid="teacher-leaves-page">
      <PageHeader
        eyebrow={isAdmin ? "Approvals" : "Time off"}
        title={isAdmin ? "Teacher leave approvals" : "My leave requests"}
        subtitle={
          isAdmin
            ? "Review and decide on leave requests from teachers. Approved leaves automatically reflect in the timetable so you can find substitutes."
            : "Raise a leave request for the school admin to approve. Approved days show ‘ON LEAVE — find substitute’ in the class timetable."
        }
      />

      {!isAdmin && (
        <Section title="New leave request">
          <CreateLeaveForm onCreated={refresh} />
        </Section>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <span className="text-xs text-ink-muted mr-1">Filter:</span>
        {["all", "pending", "approved", "rejected", "cancelled"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            data-testid={`leave-filter-${s}`}
            className={
              "px-3 py-1 rounded-md text-xs uppercase tracking-wider border transition-colors " +
              (filter === s
                ? "bg-primary text-primary-foreground border-primary"
                : "border-line text-ink-soft hover:bg-bg-subtle")
            }
          >
            {s}
            {s !== "all" && grouped[s]?.length ? ` (${grouped[s].length})` : ""}
          </button>
        ))}
      </div>

      <div className="mt-4">
        <Section
          title={
            isAdmin
              ? (filter === "pending" ? "Awaiting your decision" : "Leave history")
              : "My requests"
          }
        >
          {loading ? (
            <div className="text-sm text-ink-muted py-6 text-center">Loading…</div>
          ) : leaves.length === 0 ? (
            <Empty title="No leave requests" message={isAdmin ? "Nothing to review right now." : "Submit your first request above."} />
          ) : (
            <div className="overflow-x-auto">
              <table className="table" data-testid="leaves-table">
                <thead>
                  <tr>
                    {isAdmin && <th className="th">Teacher</th>}
                    <th className="th">Type</th>
                    <th className="th">Dates</th>
                    <th className="th">Reason</th>
                    <th className="th">Status</th>
                    <th className="th text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {leaves.map((l) => (
                    <LeaveRow
                      key={l.id}
                      leave={l}
                      isAdmin={isAdmin}
                      onChanged={refresh}
                      teacherNameMap={teacherNameMap}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
