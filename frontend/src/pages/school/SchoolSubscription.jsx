import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, KPI } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { currency, formatDate } from "../../lib/utils";
import { CheckCircle, Clock, XCircle, Package, Users, CalendarBlank, Receipt } from "@phosphor-icons/react";
import toast from "react-hot-toast";

export default function SchoolSubscription() {
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

  return (
    <div data-testid="school-subscription-page">
      <PageHeader
        eyebrow="Billing"
        title="Subscription & payments"
        subtitle="Pay per child — your invoice is calculated live from your current active students."
      />

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
