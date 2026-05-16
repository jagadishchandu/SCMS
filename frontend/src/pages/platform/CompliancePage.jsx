import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty, KPI } from "../../components/Primitives";
import { formatDate } from "../../lib/utils";
import { ShieldCheck, Warning, Clock, XCircle, MinusCircle } from "@phosphor-icons/react";

const COMPLIANCE_LABELS = {
  compliant: { label: "Within capacity", className: "badge-success", Icon: ShieldCheck },
  over_capacity: { label: "Over capacity", className: "badge-danger", Icon: Warning },
  pending_review: { label: "Awaiting approval", className: "badge-warning", Icon: Clock },
  rejected: { label: "Rejected", className: "badge-danger", Icon: XCircle },
  no_request: { label: "No request", className: "badge-neutral", Icon: MinusCircle },
};

const FILTERS = [
  ["all", "All"],
  ["over_capacity", "Over capacity"],
  ["compliant", "Within capacity"],
  ["pending_review", "Awaiting approval"],
  ["rejected", "Rejected"],
  ["no_request", "No request"],
];

export default function CompliancePage() {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    api.get("/subscriptions/compliance").then((r) => setData(r.data));
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.rows;
    return data.rows.filter((r) => r.compliance === filter);
  }, [data, filter]);

  if (!data) return <div className="p-6 text-ink-muted">Loading…</div>;

  const summary = data.summary || {};
  return (
    <div data-testid="compliance-page">
      <PageHeader
        eyebrow="Platform · Compliance"
        title="Subscription compliance"
        subtitle="Read-only view comparing each school's requested/approved children count against the actual active students in their tenant database."
      />

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 mb-8">
        <KPI label="Total schools" value={data.total} accent="primary" testId="kpi-total-schools" />
        <KPI label="Over capacity" value={summary.over_capacity || 0} accent="danger" testId="kpi-over-capacity" />
        <KPI label="Within capacity" value={summary.compliant || 0} accent="success" testId="kpi-compliant" />
        <KPI label="Awaiting approval" value={summary.pending_review || 0} accent="warning" testId="kpi-pending-review" />
        <KPI label="No request" value={summary.no_request || 0} accent="neutral" testId="kpi-no-request" />
      </div>

      <div className="flex flex-wrap gap-2 mb-4" role="tablist">
        {FILTERS.map(([k, label]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`btn-secondary ${filter === k ? "border-primary text-primary" : ""}`}
            data-testid={`compliance-filter-${k}`}>
            {label}
            {k !== "all" && <span className="ml-1 text-xs text-ink-muted">({summary[k] || 0})</span>}
          </button>
        ))}
      </div>

      <Section title="Compliance report" subtitle="View-only. Submit corrections via the Approval Requests tab if a school exceeds its approved capacity.">
        {filtered.length === 0 ? (
          <Empty title="No schools match this filter" message="Adjust filters or wait for new schools to onboard." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">School</th>
                <th className="th">Status</th>
                <th className="th text-right">Requested</th>
                <th className="th text-right">Approved</th>
                <th className="th text-right">Actual</th>
                <th className="th text-right">Variance</th>
                <th className="th">Compliance</th>
                <th className="th">Last edited</th>
              </tr></thead>
              <tbody>
                {filtered.map((r) => {
                  const meta = COMPLIANCE_LABELS[r.compliance] || COMPLIANCE_LABELS.no_request;
                  const Icon = meta.Icon;
                  const variance = r.variance;
                  const varianceClass = variance == null ? "text-ink-muted"
                    : variance > 0 ? "text-status-danger font-semibold"
                    : variance < 0 ? "text-ink-soft" : "text-ink";
                  return (
                    <tr key={r.school_id} className="table-row" data-testid={`compliance-row-${r.school_id}`}>
                      <td className="td">
                        <div className="font-medium">{r.school_name}</div>
                        <div className="text-xs text-ink-muted font-mono">{r.school_code}</div>
                      </td>
                      <td className="td"><span className="text-xs uppercase tracking-wider text-ink-soft">{r.approval_status}</span></td>
                      <td className="td text-right font-mono">{r.requested_children_count ?? "—"}</td>
                      <td className="td text-right font-mono">{r.approved_children_count ?? "—"}</td>
                      <td className="td text-right font-mono font-semibold">{r.actual_active_students}</td>
                      <td className={`td text-right font-mono ${varianceClass}`}>{variance == null ? "—" : (variance > 0 ? `+${variance}` : variance)}</td>
                      <td className="td">
                        <span className={meta.className}><Icon size={12} /> {meta.label}</span>
                      </td>
                      <td className="td text-xs text-ink-muted">
                        {r.approval_meta?.last_edited_at
                          ? formatDate(r.approval_meta.last_edited_at)
                          : r.approval_meta?.decided_at
                          ? formatDate(r.approval_meta.decided_at)
                          : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
