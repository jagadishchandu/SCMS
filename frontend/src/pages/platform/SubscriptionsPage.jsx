import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty, KPI } from "../../components/Primitives";
import { currency, formatDate } from "../../lib/utils";
import { CheckCircle, XCircle, Receipt, Clock, ShieldCheck } from "@phosphor-icons/react";
import toast from "react-hot-toast";

const STATUS_BADGE = {
  pending_confirmation: "badge-warning",
  confirmed: "badge-success",
  rejected: "badge-danger",
};

export default function SubscriptionsPage() {
  const [payments, setPayments] = useState([]);
  const [approvalReqs, setApprovalReqs] = useState([]);
  const [pricing, setPricing] = useState({ per_child_monthly: 30, per_child_yearly: 300, currency: "INR" });
  const [busy, setBusy] = useState(null);
  const [tab, setTab] = useState("approval_requests");

  const load = async () => {
    const [p, pr, ar] = await Promise.all([
      api.get("/subscriptions/payments").then((r) => r.data),
      api.get("/subscriptions/pricing").then((r) => r.data),
      api.get("/subscriptions/approval-requests").then((r) => r.data).catch(() => []),
    ]);
    setPayments(p);
    setPricing(pr);
    setApprovalReqs(ar);
  };
  useEffect(() => { load(); }, []);

  const act = async (id, kind) => {
    setBusy(id);
    try {
      await api.post(`/subscriptions/payments/${id}/${kind}`);
      toast.success(kind === "confirm" ? "Payment confirmed — subscription active" : "Payment rejected");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(null); }
  };

  const decideApproval = async (schoolId, decision, requestedCount) => {
    const approved = decision === "approve"
      ? Number(window.prompt(`Approved children count? (default: ${requestedCount})`, requestedCount) || requestedCount)
      : null;
    if (decision === "approve" && (!approved || approved < 1)) {
      toast.error("Approved count must be at least 1"); return;
    }
    const note = decision === "reject"
      ? window.prompt("Reason for rejection? (optional)", "") : null;
    setBusy(schoolId);
    try {
      await api.post(`/subscriptions/approval/${schoolId}/decide`, {
        decision,
        approved_children_count: approved,
        note: note || null,
      });
      toast.success(decision === "approve" ? "School approved — features unlocked" : "Request rejected");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(null); }
  };

  const filtered = payments.filter((p) => p.status === tab);
  const counts = {
    pending_confirmation: payments.filter((p) => p.status === "pending_confirmation").length,
    confirmed: payments.filter((p) => p.status === "confirmed").length,
    rejected: payments.filter((p) => p.status === "rejected").length,
  };
  const approvalCount = approvalReqs.length;

  return (
    <div data-testid="subscriptions-page">
      <PageHeader eyebrow="Billing" title="Subscriptions & payments"
        subtitle={`Per-child pricing: ${currency(pricing.per_child_monthly)}/child/month or ${currency(pricing.per_child_yearly)}/child/year. Approve subscription requests and confirm payments raised by schools.`} />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
        <KPI label="Approval requests" value={approvalCount} accent="danger" testId="kpi-approval-requests" />
        <KPI label="Pending payments" value={counts.pending_confirmation} accent="warning" testId="kpi-pending" />
        <KPI label="Confirmed" value={counts.confirmed} accent="success" testId="kpi-confirmed" />
        <KPI label="Rejected" value={counts.rejected} accent="danger" testId="kpi-rejected" />
      </div>

      <div className="flex flex-wrap gap-2 mb-4" role="tablist">
        {[
          ["approval_requests", `Approval requests (${approvalCount})`],
          ["pending_confirmation", `Pending payments (${counts.pending_confirmation})`],
          ["confirmed", `Confirmed (${counts.confirmed})`],
          ["rejected", `Rejected (${counts.rejected})`],
        ].map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`btn-secondary ${tab === k ? "border-primary text-primary" : ""}`}
            data-testid={`sub-tab-${k}`}>
            {label}
          </button>
        ))}
      </div>

      {tab === "approval_requests" ? (
        <Section title="School subscription approval requests"
                  subtitle="Schools cannot use any feature until you approve their requested children count.">
          {approvalReqs.length === 0 ? (
            <Empty title="No pending approval requests"
                   message="When a school admin submits a subscription request, it will appear here." />
          ) : (
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th className="th">School</th>
                  <th className="th">Requested children</th>
                  <th className="th">Submitted</th>
                  <th className="th">Submitted by</th>
                  <th className="th">Note</th>
                  <th className="th">Actions</th>
                </tr></thead>
                <tbody>
                  {approvalReqs.map((r) => (
                    <tr key={r.school_id} className="table-row" data-testid={`approval-row-${r.school_id}`}>
                      <td className="td">
                        <div className="font-medium">{r.school_name}</div>
                        <div className="text-xs text-ink-muted font-mono">{r.school_code}</div>
                      </td>
                      <td className="td font-semibold">{r.approval.requested_children_count}</td>
                      <td className="td text-xs text-ink-muted">{formatDate(r.approval.requested_at)}</td>
                      <td className="td text-xs">{r.approval.requested_by_email}</td>
                      <td className="td text-xs italic">{r.approval.note || "—"}</td>
                      <td className="td">
                        <div className="flex flex-wrap gap-2">
                          <button className="btn-primary text-xs px-3 py-1.5" disabled={busy === r.school_id}
                            onClick={() => decideApproval(r.school_id, "approve", r.approval.requested_children_count)}
                            data-testid={`approve-${r.school_id}`}>
                            <ShieldCheck size={14} /> Approve
                          </button>
                          <button className="btn-secondary text-xs px-3 py-1.5 text-status-danger" disabled={busy === r.school_id}
                            onClick={() => decideApproval(r.school_id, "reject", r.approval.requested_children_count)}
                            data-testid={`reject-approval-${r.school_id}`}>
                            <XCircle size={14} /> Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      ) : (
        <Section title={tab === "pending_confirmation" ? "Awaiting your confirmation" : tab === "confirmed" ? "Confirmed payments" : "Rejected payments"}>
        {filtered.length === 0 ? (
          <Empty title={tab === "pending_confirmation" ? "Nothing to confirm right now" : "No records"}
                 message="When a school submits a subscription payment, it will appear here." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th className="th">School</th>
                  <th className="th">Cycle</th>
                  <th className="th">Children</th>
                  <th className="th">Amount</th>
                  <th className="th">Mode / Ref</th>
                  <th className="th">Submitted</th>
                  <th className="th">Status / Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.id} className="table-row" data-testid={`sub-payment-${p.id}`}>
                    <td className="td">
                      <div className="font-medium">{p.school_name}</div>
                      <div className="text-xs text-ink-muted font-mono">{p.school_code}</div>
                    </td>
                    <td className="td capitalize">{p.billing_cycle}</td>
                    <td className="td">{p.students_count}</td>
                    <td className="td font-medium">{currency(p.amount)}</td>
                    <td className="td">
                      <div className="capitalize">{p.payment_mode || "—"}</div>
                      {p.payment_reference && <div className="text-xs text-ink-muted font-mono break-all">{p.payment_reference}</div>}
                    </td>
                    <td className="td text-xs text-ink-muted">
                      {formatDate(p.created_at)}<br/>
                      <span className="break-all">{p.submitted_by_email}</span>
                    </td>
                    <td className="td">
                      {p.status === "pending_confirmation" ? (
                        <div className="flex flex-wrap gap-2">
                          <button className="btn-primary text-xs px-3 py-1.5" disabled={busy === p.id}
                            onClick={() => act(p.id, "confirm")}
                            data-testid={`confirm-payment-${p.id}`}>
                            <CheckCircle size={14} /> Confirm
                          </button>
                          <button className="btn-secondary text-xs px-3 py-1.5 text-status-danger" disabled={busy === p.id}
                            onClick={() => act(p.id, "reject")}
                            data-testid={`reject-payment-${p.id}`}>
                            <XCircle size={14} /> Reject
                          </button>
                        </div>
                      ) : (
                        <div>
                          <span className={STATUS_BADGE[p.status] || "badge-neutral"}>
                            {p.status === "confirmed" ? <CheckCircle size={12} /> : p.status === "rejected" ? <XCircle size={12} /> : <Clock size={12} />}
                            {" "}{p.status.replace("_", " ")}
                          </span>
                          {p.status === "confirmed" && p.valid_until && (
                            <div className="text-[11px] text-ink-muted mt-1">Valid until {formatDate(p.valid_until)}</div>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      )}

      <div className="mt-8 text-xs text-ink-muted flex items-center gap-2">
        <Receipt size={14} /> Tip: schools see a "Subscription" page in their sidebar where they submit their approval request and pay.
      </div>
    </div>
  );
}
