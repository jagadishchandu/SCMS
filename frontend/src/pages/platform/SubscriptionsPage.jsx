import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { currency } from "../../lib/utils";
import { Package, Check } from "@phosphor-icons/react";
import toast from "react-hot-toast";

export default function SubscriptionsPage() {
  const [plans, setPlans] = useState([]);
  const [schools, setSchools] = useState([]);
  const [busy, setBusy] = useState(null); // schoolId being updated

  const load = async () => {
    const [p, s] = await Promise.all([
      api.get("/subscriptions/plans").then((r) => r.data),
      api.get("/schools").then((r) => r.data),
    ]);
    setPlans(p);
    setSchools(s);
  };
  useEffect(() => { load(); }, []);

  const assign = async (school_id, plan_id) => {
    setBusy(school_id);
    try {
      await api.post("/subscriptions/assign", { school_id, plan_id });
      toast.success("Plan assigned");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(null); }
  };

  return (
    <div data-testid="subscriptions-page">
      <PageHeader eyebrow="Billing" title="Subscriptions & packages"
        subtitle="Assign a plan to each school. Plans define usage caps and feature gates." />

      <Section title="Available plans">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans.map((p) => (
            <div key={p.id} className="border border-line rounded-lg p-5 flex flex-col" data-testid={`plan-${p.name.toLowerCase()}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="font-display text-xl font-medium">{p.name}</div>
                <Package size={20} className="text-secondary" />
              </div>
              <div className="text-3xl font-display font-medium">{p.monthly_price === 0 ? "Free" : currency(p.monthly_price)}<span className="text-xs text-ink-muted ml-1">/mo</span></div>
              <div className="text-xs text-ink-muted mt-1">{p.description}</div>
              <ul className="mt-4 text-sm text-ink-soft space-y-1.5 flex-1">
                <li className="flex gap-2"><Check size={14} className="text-status-success mt-1" /> Up to {p.max_students.toLocaleString()} students</li>
                <li className="flex gap-2"><Check size={14} className="text-status-success mt-1" /> Up to {p.max_teachers.toLocaleString()} teachers</li>
                {(p.features || []).map((f, i) => (
                  <li key={i} className="flex gap-2"><Check size={14} className="text-status-success mt-1" /> {f}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      <div className="mt-6">
        <Section title={`Assign plans · ${schools.length} schools`}>
          {schools.length === 0 ? <Empty title="No schools yet" /> :
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr><th className="th">School</th><th className="th">Code</th><th className="th">Current plan</th><th className="th">Change to</th></tr></thead>
                <tbody>
                  {schools.map((s) => (
                    <tr key={s.id} className="table-row" data-testid={`school-sub-${s.id}`}>
                      <td className="td font-medium">{s.name}</td>
                      <td className="td font-mono text-xs">{s.code}</td>
                      <td className="td">
                        {s.subscription ? (
                          <span className="badge-info">{s.subscription.plan_name} · {currency(s.subscription.monthly_price)}/mo</span>
                        ) : <span className="badge-neutral">Unassigned</span>}
                      </td>
                      <td className="td">
                        <select
                          className="input w-44"
                          defaultValue={s.subscription?.plan_id || ""}
                          onChange={(e) => e.target.value && assign(s.id, e.target.value)}
                          disabled={busy === s.id}
                          data-testid={`assign-plan-${s.id}`}
                        >
                          <option value="">Choose plan…</option>
                          {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      </td>
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
