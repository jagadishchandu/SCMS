import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty, KPI } from "../../components/Primitives";
import { currency } from "../../lib/utils";
import { CheckCircle, XCircle, Clock, MinusCircle, MagnifyingGlass } from "@phosphor-icons/react";

const STATUS_META = {
  paid:     { label: "Paid",     className: "badge-success", Icon: CheckCircle },
  partial:  { label: "Partial",  className: "badge-warning", Icon: Clock },
  not_paid: { label: "Not paid", className: "badge-danger",  Icon: XCircle },
  no_fees:  { label: "No fees",  className: "badge-neutral", Icon: MinusCircle },
};

const FILTERS = [
  ["all", "All"],
  ["not_paid", "Not paid"],
  ["partial", "Partial"],
  ["paid", "Paid"],
  ["no_fees", "No fees"],
];

function PercentBar({ percent }) {
  const p = Math.max(0, Math.min(100, Number(percent) || 0));
  const color = p >= 100 ? "#4F7A4F" : p >= 50 ? "#C79A3A" : "#B04040";
  return (
    <div className="flex items-center gap-2 min-w-[140px]" data-testid="percent-bar">
      <div className="flex-1 h-2 rounded-full bg-line/60 overflow-hidden">
        <div style={{ width: `${p}%`, background: color }} className="h-full rounded-full transition-all" />
      </div>
      <span className="text-xs font-mono font-medium w-12 text-right">{p.toFixed(p % 1 === 0 ? 0 : 1)}%</span>
    </div>
  );
}

export default function FeeTrackerPage() {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [classes, setClasses] = useState([]);
  const [classId, setClassId] = useState("");

  const load = async () => {
    const params = new URLSearchParams();
    if (filter !== "all") params.append("status", filter);
    if (classId) params.append("class_id", classId);
    if (q) params.append("q", q);
    const r = await api.get(`/fees/per-student-summary?${params.toString()}`);
    setData(r.data);
  };

  useEffect(() => {
    api.get("/academic/classes").then((r) => setClasses(r.data || []));
  }, []);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter, classId]);

  const summary = data?.summary || {};
  const totals = data?.totals || {};
  const classMap = useMemo(() => Object.fromEntries(classes.map((c) => [c.id, c.name])), [classes]);

  return (
    <div data-testid="fee-tracker-page">
      <PageHeader
        eyebrow="Finance — Per-student tracker"
        title="Fee compliance per child"
        subtitle="One row per active student. Total fee, paid amount, balance, % paid. Updated live from the fees collection."
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <KPI label="Total fee" value={currency(totals.total_fee || 0)} accent="primary" testId="kpi-total-fee" />
        <KPI label="Collected" value={currency(totals.paid_amount || 0)} accent="success" testId="kpi-collected" />
        <KPI label="Balance due" value={currency(totals.balance_due || 0)} accent="danger" testId="kpi-balance-due" />
        <KPI label="Students" value={data?.total_students ?? 0} accent="neutral" testId="kpi-students-count" />
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        {FILTERS.map(([k, label]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`btn-secondary ${filter === k ? "border-primary text-primary" : ""}`}
            data-testid={`fee-filter-${k}`}>
            {label}
            {k !== "all" && <span className="ml-1 text-xs text-ink-muted">({summary[k] || 0})</span>}
          </button>
        ))}
        <select className="input max-w-[200px]" value={classId} onChange={(e) => setClassId(e.target.value)} data-testid="fee-class-filter">
          <option value="">All classes</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <div className="flex-1 min-w-[200px] relative">
          <input className="input pl-9" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
                  placeholder="Search by name or UID and press Enter…" data-testid="fee-search-input" />
          <MagnifyingGlass size={16} className="absolute left-3 top-3 text-ink-muted" />
        </div>
      </div>

      <Section title="Per-student fee status" subtitle="Sorted by student name. Click a row to view payment history.">
        {!data ? (
          <div className="p-6 text-ink-muted">Loading…</div>
        ) : data.rows.length === 0 ? (
          <Empty title="No students match the current filters" message="Adjust the status filter, class, or search query." />
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">Student</th>
                <th className="th">Class · Section</th>
                <th className="th">Parent</th>
                <th className="th text-right">Total fee</th>
                <th className="th text-right">Paid</th>
                <th className="th text-right">Paid yet (balance)</th>
                <th className="th">% Paid</th>
                <th className="th">Status</th>
              </tr></thead>
              <tbody>
                {data.rows.map((r) => {
                  const meta = STATUS_META[r.status] || STATUS_META.no_fees;
                  const Icon = meta.Icon;
                  return (
                    <tr key={r.student_id} className="table-row" data-testid={`fee-tracker-row-${r.student_id}`}>
                      <td className="td">
                        <div className="font-medium">{r.student_name}</div>
                        {r.student_uid && <div className="text-xs text-ink-muted font-mono">{r.student_uid}</div>}
                      </td>
                      <td className="td text-xs">
                        {classMap[r.class_id] || r.class_id || "—"}
                        {r.section ? ` · ${r.section}` : ""}
                      </td>
                      <td className="td text-xs">
                        <div>{r.parent_name || "—"}</div>
                        {r.parent_phone && <div className="text-ink-muted font-mono">{r.parent_phone}</div>}
                      </td>
                      <td className="td text-right font-mono">{currency(r.total_fee)}</td>
                      <td className="td text-right font-mono text-status-success">{currency(r.paid_amount)}</td>
                      <td className="td text-right font-mono font-semibold text-status-danger" data-testid={`balance-${r.student_id}`}>
                        {currency(r.balance_due)}
                      </td>
                      <td className="td"><PercentBar percent={r.percent_paid} /></td>
                      <td className="td">
                        <span className={meta.className}><Icon size={12} /> {meta.label}</span>
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
