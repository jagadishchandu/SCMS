import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { currency } from "../../lib/utils";

export default function AccountsDashboard() {
  const [fees, setFees] = useState([]);
  const [payments, setPayments] = useState([]);
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get("/fees").then((r) => r.data),
      api.get("/fees/payments").then((r) => r.data),
      api.get("/students").then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
    ]).then(([f, p, s, c]) => { setFees(f); setPayments(p); setStudents(s); setClasses(c); });
  }, []);

  const billed = fees.reduce((a, b) => a + b.total, 0);
  const collected = fees.reduce((a, b) => a + b.paid, 0);
  const outstanding = fees.reduce((a, b) => a + b.due, 0);

  // class-wise collection
  const byClass = {};
  for (const f of fees) {
    const cName = classes.find((c) => c.id === f.class_id)?.name || f.class_id;
    byClass[cName] = byClass[cName] || { billed: 0, paid: 0, due: 0 };
    byClass[cName].billed += f.total;
    byClass[cName].paid += f.paid;
    byClass[cName].due += f.due;
  }

  const unpaid = fees.filter((f) => f.due > 0);
  const sMap = Object.fromEntries(students.map((s) => [s.id, s]));

  return (
    <div data-testid="accounts-dashboard">
      <PageHeader eyebrow="Finance" title="Accounts dashboard" subtitle="Collections, dues and unpaid students across the school." />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPI label="Total billed" value={currency(billed)} accent="secondary" testId="ad-billed" />
        <KPI label="Collected" value={currency(collected)} accent="success" testId="ad-collected" />
        <KPI label="Outstanding" value={currency(outstanding)} accent={outstanding > 0 ? "danger" : "success"} testId="ad-due" />
        <KPI label="Recent payments" value={payments.length} accent="info" testId="ad-payments-count" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Section title="Class-wise collection">
          {Object.keys(byClass).length === 0 ? <Empty title="No data" /> :
            <table className="table">
              <thead><tr><th className="th">Class</th><th className="th">Billed</th><th className="th">Collected</th><th className="th">Due</th></tr></thead>
              <tbody>
                {Object.entries(byClass).map(([k, v]) => (
                  <tr key={k} className="table-row">
                    <td className="td font-medium">{k}</td>
                    <td className="td">{currency(v.billed)}</td>
                    <td className="td">{currency(v.paid)}</td>
                    <td className="td">{currency(v.due)}</td>
                  </tr>
                ))}
              </tbody>
            </table>}
        </Section>

        <Section title="Recent payments">
          {payments.length === 0 ? <Empty title="No payments yet" /> :
            <ul className="divide-y divide-line">
              {payments.slice(0, 10).map((p) => (
                <li key={p.id} className="py-3 flex items-center justify-between" data-testid={`pay-${p.id}`}>
                  <div>
                    <div className="font-medium">{sMap[p.student_id]?.name || "—"}</div>
                    <div className="text-xs text-ink-muted">{p.receipt_no} · {p.mode}</div>
                  </div>
                  <div className="font-display text-base">{currency(p.amount)}</div>
                </li>
              ))}
            </ul>}
        </Section>
      </div>

      <Section title={`Unpaid students (${unpaid.length})`}>
        {unpaid.length === 0 ? <Empty title="All clear" message="Every fee has been collected." /> :
          <table className="table">
            <thead><tr><th className="th">Student</th><th className="th">Class</th><th className="th">Outstanding</th><th className="th">Status</th></tr></thead>
            <tbody>
              {unpaid.map((f) => (
                <tr key={f.id} className="table-row">
                  <td className="td">
                    <div className="font-medium">{sMap[f.student_id]?.name || "—"}</div>
                    <div className="text-xs text-ink-muted">{sMap[f.student_id]?.student_uid}</div>
                  </td>
                  <td className="td">{classes.find(c => c.id === f.class_id)?.name}</td>
                  <td className="td">{currency(f.due)}</td>
                  <td className="td"><span className={f.status === "partial" ? "badge-warning" : "badge-danger"}>{f.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>}
      </Section>
    </div>
  );
}
