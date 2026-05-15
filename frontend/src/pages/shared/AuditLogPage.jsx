import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { formatDate, ROLE_LABELS } from "../../lib/utils";

export default function AuditLogPage() {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/audit").then((r) => setRows(r.data));
  }, []);

  return (
    <div data-testid="audit-log-page">
      <PageHeader eyebrow="Audit" title="Audit log"
        subtitle="Every important action across your school. Visible to School Super Admin and Platform Admin only." />
      <Section title={`${rows.length} events`}>
        {rows.length === 0 ? <Empty title="No audit entries yet" message="Actions will appear here as soon as users start working in the system." /> :
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">When</th><th className="th">Actor</th><th className="th">Role</th>
                <th className="th">Action</th><th className="th">Resource</th><th className="th">Details</th>
              </tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="table-row" data-testid={`audit-row-${r.id}`}>
                    <td className="td whitespace-nowrap text-xs text-ink-soft">{formatDate(r.created_at)}</td>
                    <td className="td font-mono text-xs">{r.actor_id?.slice(0, 8)}…</td>
                    <td className="td">{ROLE_LABELS[r.actor_role] || r.actor_role}</td>
                    <td className="td"><span className="badge-info">{r.action}</span></td>
                    <td className="td">{r.resource}{r.resource_id ? <span className="text-ink-muted text-xs"> · {r.resource_id.slice(0,8)}…</span> : null}</td>
                    <td className="td text-xs text-ink-soft">{Object.keys(r.meta || {}).length > 0 ? JSON.stringify(r.meta) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
      </Section>
    </div>
  );
}
