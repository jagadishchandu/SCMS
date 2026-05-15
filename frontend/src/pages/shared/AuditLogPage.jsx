import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { formatDate, ROLE_LABELS } from "../../lib/utils";
import { MagnifyingGlass, FunnelSimple, X } from "@phosphor-icons/react";
import toast from "react-hot-toast";

const ROLES = ["platform_admin", "school_admin", "teacher", "accounts", "parent"];

export default function AuditLogPage() {
  const [rows, setRows] = useState([]);
  const [facets, setFacets] = useState({ actions: [], resources: [], roles: [] });
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    actor_role: "", action: "", resource: "",
    date_from: "", date_to: "", q: "", limit: 200,
  });

  const load = async () => {
    setLoading(true);
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([_, v]) => v));
      const [audit, fac] = await Promise.all([
        api.get("/audit", { params }).then((r) => r.data),
        api.get("/audit/facets").then((r) => r.data).catch(() => facets),
      ]);
      setRows(audit);
      setFacets(fac);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const clear = () => { setFilters({ actor_role: "", action: "", resource: "", date_from: "", date_to: "", q: "", limit: 200 }); setTimeout(load, 50); };
  const set = (k) => (e) => setFilters({ ...filters, [k]: e.target.value });

  const activeFilters = useMemo(() =>
    Object.entries(filters).filter(([k, v]) => v && k !== "limit").length, [filters]);

  return (
    <div data-testid="audit-log-page">
      <PageHeader eyebrow="Audit" title="Audit log"
        subtitle="Every important action across your school. Filter by role, action, resource, date or free text." />

      {/* Filters */}
      <Section title="Filters">
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="lg:col-span-2">
            <label className="label">Search</label>
            <div className="relative">
              <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
              <input
                className="input pl-8"
                placeholder="action, resource id…"
                value={filters.q}
                onChange={set("q")}
                onKeyDown={(e) => e.key === "Enter" && load()}
                data-testid="audit-search"
              />
            </div>
          </div>
          <div>
            <label className="label">Role</label>
            <select className="input" value={filters.actor_role} onChange={set("actor_role")} data-testid="audit-role">
              <option value="">Any role</option>
              {(facets.roles?.length ? facets.roles : ROLES).map((r) => <option key={r} value={r}>{ROLE_LABELS[r] || r}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Action</label>
            <select className="input" value={filters.action} onChange={set("action")} data-testid="audit-action">
              <option value="">Any action</option>
              {facets.actions?.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Resource</label>
            <select className="input" value={filters.resource} onChange={set("resource")} data-testid="audit-resource">
              <option value="">Any resource</option>
              {facets.resources?.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label className="label">From date</label>
            <input className="input" type="date" value={filters.date_from} onChange={set("date_from")} data-testid="audit-date-from" />
          </div>
          <div>
            <label className="label">To date</label>
            <input className="input" type="date" value={filters.date_to} onChange={set("date_to")} data-testid="audit-date-to" />
          </div>
          <div>
            <label className="label">Limit</label>
            <select className="input" value={filters.limit} onChange={set("limit")}>
              {[100, 200, 500, 1000].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-4">
          <button className="btn-primary" onClick={load} disabled={loading} data-testid="audit-apply">
            <FunnelSimple size={14} /> {loading ? "Loading…" : `Apply filters${activeFilters ? ` (${activeFilters})` : ""}`}
          </button>
          <button className="btn-secondary" onClick={clear} disabled={activeFilters === 0} data-testid="audit-clear">
            <X size={14} /> Clear
          </button>
        </div>
      </Section>

      <div className="mt-6">
        <Section title={`${rows.length} events`}>
          {rows.length === 0 ? <Empty title="No audit entries match" message="Try widening the filters or clearing them." /> :
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
                      <td className="td">
                        <div className="text-xs">{r.actor_name || "—"}</div>
                        <div className="text-[10px] text-ink-muted font-mono">{r.actor_email || (r.actor_id || "").slice(0, 8) + "…"}</div>
                      </td>
                      <td className="td"><span className="badge-neutral">{ROLE_LABELS[r.actor_role] || r.actor_role}</span></td>
                      <td className="td"><span className="badge-info">{r.action}</span></td>
                      <td className="td">{r.resource}{r.resource_id ? <span className="text-ink-muted text-xs"> · {r.resource_id.slice(0, 8)}…</span> : null}</td>
                      <td className="td text-xs text-ink-soft max-w-md truncate" title={JSON.stringify(r.meta || {})}>{Object.keys(r.meta || {}).length > 0 ? JSON.stringify(r.meta) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>}
        </Section>
      </div>
    </div>
  );
}
