import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, KPI } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { currency, formatDate } from "../../lib/utils";
import { CheckCircle, Clock, XCircle, Package, Users, CalendarBlank, Receipt, ShieldCheck, Warning } from "@phosphor-icons/react";
import { useAuth } from "../../contexts/AuthContext";
import toast from "react-hot-toast";

export default function SchoolSubscription() {
  const { refresh } = useAuth();
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [open, setOpen] = useState(false);
  const [cycle, setCycle] = useState("monthly");

  const load = async () => {
    const [my, hist] = await Promise.all([
      api.get("/subscriptions/my").then((r) => r.data),
      api.get("/subscriptions/payments").then((r) => r.data).catch(() => []),
    ]);
    setData(my);
    setHistory(hist);
  };
  useEffect(() => { load(); }, []);

  if (!data) return <div className="p-6 text-ink-muted">Loading…</div>;

  const sub = data.subscription || { status: "none" };
  const q = data.quote;
  const pending = data.pending_payment;
  const approval = data.subscription_approval || { status: "not_started" };
  const isApproved = approval.status === "approved";

  return (
    <div data-testid="school-subscription-page">
      <PageHeader
        eyebrow="Billing"
        title="Subscription & payments"
        subtitle="Pay per child — your invoice is calculated live from your current active students."
      />

      {/* Approval request panel — visible until approved */}
      {!isApproved && (
        <ApprovalPanel
          approval={approval}
          onSubmitted={async () => { await load(); await refresh(); }}
        />
      )}

      {isApproved && (
        <ApprovedEditPanel
          approval={approval}
          actualCount={q.students_active}
          onSubmitted={async () => { await load(); await refresh(); }}
        />
      )}
      {/* Current plan summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <KPI label="Active students" value={q.students_active} accent="primary" testId="kpi-students" />
        <KPI
          label="Subscription status"
          value={sub.status === "active" ? "Active" : pending ? "Pending confirmation" : "Not subscribed"}
          accent={sub.status === "active" ? "success" : pending ? "warning" : "danger"}
          hint={sub.status === "active" && sub.valid_until ? `Valid until ${formatDate(sub.valid_until)}` : null}
          testId="kpi-sub-status"
        />
        <KPI
          label="Current cycle"
          value={sub.billing_cycle ? sub.billing_cycle : "—"}
          accent="info"
          hint={sub.amount ? `${currency(sub.amount)} last paid` : null}
          testId="kpi-cycle"
        />
      </div>

      {pending && (
        <div className="border border-amber-300 bg-amber-50 rounded-lg p-4 mb-6 flex items-start gap-3" data-testid="pending-banner">
          <Clock size={20} className="text-amber-700 mt-0.5" />
          <div>
            <div className="font-medium text-amber-900">Payment pending Platform Super Admin confirmation</div>
            <div className="text-xs text-amber-800 mt-1">
              {currency(pending.amount)} · {pending.billing_cycle} cycle for {pending.students_count} children. Submitted {formatDate(pending.created_at)}.
              {pending.payment_reference && <> · Ref: <span className="font-mono">{pending.payment_reference}</span></>}
            </div>
          </div>
        </div>
      )}

      <Section title="Choose your plan">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PlanCard
            title="Monthly"
            badge={null}
            rate={q.pricing.per_child_monthly}
            amount={q.monthly.amount}
            students={q.students_active}
            disabled={!!pending}
            onPay={() => { setCycle("monthly"); setOpen(true); }}
            testId="plan-card-monthly"
          />
          <PlanCard
            title="Yearly"
            badge="Save more"
            rate={q.pricing.per_child_yearly}
            amount={q.yearly.amount}
            students={q.students_active}
            disabled={!!pending}
            savings={q.yearly.savings_vs_monthly}
            onPay={() => { setCycle("yearly"); setOpen(true); }}
            testId="plan-card-yearly"
          />
        </div>
      </Section>

      <div className="mt-8">
        <Section title="Payment history">
          {history.length === 0 ? (
            <div className="text-sm text-ink-muted py-6">No payments submitted yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th className="th">Submitted</th>
                  <th className="th">Cycle</th>
                  <th className="th">Children</th>
                  <th className="th">Amount</th>
                  <th className="th">Reference</th>
                  <th className="th">Status</th>
                </tr></thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id} className="table-row" data-testid={`history-${h.id}`}>
                      <td className="td text-xs">{formatDate(h.created_at)}</td>
                      <td className="td capitalize">{h.billing_cycle}</td>
                      <td className="td">{h.students_count}</td>
                      <td className="td font-medium">{currency(h.amount)}</td>
                      <td className="td font-mono text-xs">{h.payment_reference || "—"}</td>
                      <td className="td">
                        {h.status === "confirmed" && <span className="badge-success"><CheckCircle size={12} /> confirmed</span>}
                        {h.status === "pending_confirmation" && <span className="badge-warning"><Clock size={12} /> pending</span>}
                        {h.status === "rejected" && <span className="badge-danger"><XCircle size={12} /> rejected</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      <PayModal open={open} onClose={() => setOpen(false)} cycle={cycle} quote={q}
        onSubmitted={() => { setOpen(false); load(); }} />
    </div>
  );
}

function ApprovedEditPanel({ approval, actualCount, onSubmitted }) {
  const cap = approval.approved_children_count ?? approval.requested_children_count;
  const [editing, setEditing] = useState(false);
  const [count, setCount] = useState(approval.requested_children_count || cap || "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const overCapacity = cap != null && actualCount > cap;

  const submit = async (e) => {
    e.preventDefault();
    const n = Number(count);
    if (!n || n < 1) { toast.error("Enter a valid children count (>= 1)"); return; }
    setBusy(true);
    try {
      await api.post("/subscriptions/approval-request", {
        requested_children_count: n,
        note: note || null,
      });
      toast.success("Requested children count updated");
      setEditing(false);
      setNote("");
      onSubmitted();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <div
      className={`border rounded-lg p-5 mb-6 ${overCapacity ? "border-status-danger/40 bg-status-danger/5" : "border-status-success/40 bg-status-success/5"}`}
      data-testid="approved-edit-panel"
    >
      <div className="flex items-start gap-3 mb-3">
        <ShieldCheck size={20} className={`mt-0.5 ${overCapacity ? "text-status-danger" : "text-status-success"}`} />
        <div className="flex-1">
          <div className={`font-medium ${overCapacity ? "text-status-danger" : "text-status-success"}`}>
            {overCapacity ? "Over capacity — update your requested count" : "Subscription approved"}
          </div>
          <div className="text-xs text-ink-soft mt-1">
            Approved capacity: <span className="font-semibold">{cap ?? "—"}</span> children · Actual active students: <span className="font-semibold">{actualCount}</span>
            {overCapacity && <> · <span className="font-semibold">{actualCount - cap} over</span></>}
            {approval.approval_note ? <> · Note: <span className="italic">{approval.approval_note}</span></> : null}
          </div>
        </div>
        {!editing && (
          <button className="btn-secondary text-xs" onClick={() => setEditing(true)} data-testid="edit-approval-btn">
            Edit count
          </button>
        )}
      </div>
      {editing && (
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end mt-2 pt-3 border-t border-line">
          <div className="md:col-span-1">
            <label className="label">Requested children count</label>
            <input
              type="number" min="1" max="100000" className="input" required
              value={count} onChange={(e) => setCount(e.target.value)}
              data-testid="edit-approval-count-input"
            />
          </div>
          <div className="md:col-span-2">
            <label className="label">Reason for change <span className="text-xs text-ink-muted">(optional)</span></label>
            <input
              className="input" value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Adding a new section in Grade 5"
              data-testid="edit-approval-note-input"
            />
          </div>
          <div className="md:col-span-3 flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => { setEditing(false); setCount(approval.requested_children_count || cap || ""); }}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={busy} data-testid="save-approval-edit-btn">
              {busy ? "Saving…" : "Save changes"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}


function ApprovalPanel({ approval, onSubmitted }) {
  const [count, setCount] = useState(approval.requested_children_count || "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    const n = Number(count);
    if (!n || n < 1) { toast.error("Enter a valid children count (>= 1)"); return; }
    setBusy(true);
    try {
      await api.post("/subscriptions/approval-request", {
        requested_children_count: n,
        note: note || null,
      });
      toast.success("Approval request submitted — awaiting Platform Super Admin");
      setNote("");
      onSubmitted();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  if (approval.status === "pending") {
    return (
      <div className="border border-amber-300 bg-amber-50 rounded-lg p-5 mb-6" data-testid="approval-pending-card">
        <div className="flex items-start gap-3">
          <Clock size={22} className="text-amber-700 mt-0.5" />
          <div className="flex-1">
            <div className="font-display text-base font-medium text-amber-900">Awaiting Platform Super Admin approval</div>
            <div className="text-sm text-amber-800 mt-1">
              Your request for <span className="font-semibold">{approval.requested_children_count}</span> children was submitted
              {approval.requested_at ? <> on {formatDate(approval.requested_at)}</> : null}.
              All school features are locked until approval — only this page and the dashboard overview remain accessible.
            </div>
            {approval.note && (
              <div className="text-xs text-amber-800 mt-2">Your note: <span className="italic">{approval.note}</span></div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-status-danger/40 bg-status-danger/5 rounded-lg p-5 mb-6" data-testid="approval-request-form">
      <div className="flex items-start gap-3 mb-4">
        <Warning size={22} className="text-status-danger mt-0.5" />
        <div>
          <div className="font-display text-base font-medium">
            {approval.status === "rejected"
              ? "Your previous request was rejected"
              : "Submit your subscription request"}
          </div>
          <div className="text-sm text-ink-soft mt-1">
            Tell us the maximum number of children you intend to onboard. The Platform Super Admin will approve your school
            and unlock all features. Until then, only the Overview and this Subscription page are visible.
          </div>
          {approval.status === "rejected" && approval.approval_note && (
            <div className="text-xs text-status-danger mt-2">Reviewer note: <span className="italic">{approval.approval_note}</span></div>
          )}
        </div>
      </div>
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
        <div className="md:col-span-1">
          <label className="label">Requested children count</label>
          <input
            type="number"
            min="1"
            max="100000"
            className="input"
            placeholder="e.g. 250"
            value={count}
            onChange={(e) => setCount(e.target.value)}
            data-testid="approval-count-input"
            required
          />
        </div>
        <div className="md:col-span-2">
          <label className="label">Note for the Platform Super Admin <span className="text-xs text-ink-muted">(optional)</span></label>
          <input
            className="input"
            placeholder="Anything that will help process your request quickly."
            value={note}
            onChange={(e) => setNote(e.target.value)}
            data-testid="approval-note-input"
          />
        </div>
        <div className="md:col-span-3 flex justify-end">
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-approval-btn">
            {busy ? "Submitting…" : "Submit approval request"}
          </button>
        </div>
      </form>
    </div>
  );
}


function PlanCard({ title, badge, rate, amount, students, savings, disabled, onPay, testId }) {
  return (
    <div className="border border-line rounded-lg p-6 flex flex-col" data-testid={testId}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2"><Package size={18} className="text-primary" /><div className="font-display text-lg font-medium">{title}</div></div>
        {badge && <span className="badge-success">{badge}</span>}
      </div>
      <div className="text-4xl font-display font-medium">{currency(rate)}<span className="text-sm text-ink-muted ml-1">/child{title === "Yearly" ? "/year" : "/month"}</span></div>
      <div className="text-xs text-ink-muted mt-1">For {students} active student{students === 1 ? "" : "s"} in your school today.</div>

      <div className="mt-5 border-t border-line pt-4 space-y-1.5 text-sm">
        <div className="flex justify-between"><span className="text-ink-soft"><Users size={14} className="inline mr-1" /> Children</span><span className="font-medium">{students}</span></div>
        <div className="flex justify-between"><span className="text-ink-soft">Rate</span><span className="font-medium">{currency(rate)}</span></div>
        {savings > 0 && (
          <div className="flex justify-between text-status-success"><span>Yearly savings vs monthly</span><span className="font-medium">{currency(savings)}</span></div>
        )}
        <div className="flex justify-between text-base pt-2 border-t border-line"><span className="font-medium">Total payable</span><span className="font-display text-xl font-semibold">{currency(amount)}</span></div>
      </div>

      <button className="btn-primary mt-5" onClick={onPay} disabled={disabled || students === 0}
        data-testid={`pay-btn-${title.toLowerCase()}`}>
        <Receipt size={16} /> {disabled ? "Payment pending confirmation" : students === 0 ? "Add students first" : `Pay ${currency(amount)}`}
      </button>
    </div>
  );
}

function PayModal({ open, onClose, cycle, quote, onSubmitted }) {
  const [mode, setMode] = useState("upi");
  const [ref, setRef] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const line = cycle === "monthly" ? quote.monthly : quote.yearly;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/subscriptions/payments", {
        billing_cycle: cycle,
        payment_mode: mode,
        payment_reference: ref || null,
        note: note || null,
      });
      toast.success("Payment submitted — awaiting Platform Super Admin confirmation");
      onSubmitted();
      setRef(""); setNote("");
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Submit ${cycle} payment`} size="md" testId="pay-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="border border-line rounded-lg p-4 bg-bg-subtle">
          <div className="flex justify-between text-sm"><span className="text-ink-soft">Plan</span><span className="capitalize font-medium">{cycle}</span></div>
          <div className="flex justify-between text-sm"><span className="text-ink-soft">Children</span><span className="font-medium">{line.students}</span></div>
          <div className="flex justify-between text-sm"><span className="text-ink-soft">Rate</span><span className="font-medium">{currency(line.rate_per_child)} per child</span></div>
          <div className="flex justify-between text-base mt-2 pt-2 border-t border-line"><span className="font-medium">Total</span><span className="font-display text-xl font-semibold">{currency(line.amount)}</span></div>
        </div>

        <div>
          <label className="label">Payment mode</label>
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)} data-testid="pay-mode">
            <option value="upi">UPI</option>
            <option value="bank_transfer">Bank transfer / NEFT</option>
            <option value="card">Card</option>
            <option value="cash">Cash</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div>
          <label className="label">Reference / UTR / Txn ID <span className="text-xs text-ink-muted">(optional)</span></label>
          <input className="input" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="e.g. UPI Txn 4239xxxx" data-testid="pay-reference" />
        </div>
        <div>
          <label className="label">Note for the Platform Super Admin <span className="text-xs text-ink-muted">(optional)</span></label>
          <textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="Anything that will help confirm your payment quickly." data-testid="pay-note" />
        </div>

        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <CalendarBlank size={14} /> After confirmation, your subscription will be active for {cycle === "monthly" ? "30 days" : "365 days"}.
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-payment-btn">{busy ? "Submitting…" : `Submit ${currency(line.amount)}`}</button>
        </div>
      </form>
    </Modal>
  );
}
