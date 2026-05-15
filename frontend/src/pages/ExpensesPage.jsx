import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { PageHeader, Section, Empty, KPI } from "../components/Primitives";
import { Modal } from "../components/Modal";
import { Plus, CheckCircle, XCircle, MoneyWavy, Receipt } from "@phosphor-icons/react";
import toast from "react-hot-toast";

const CATEGORIES = [
  "salary", "supplies", "maintenance", "utilities", "travel",
  "events", "transport", "food", "stationery", "books", "other",
];

const STATUS_BADGE = {
  pending: "badge-warning",
  approved: "badge-info",
  paid: "badge-success",
  rejected: "badge-danger",
};

const fmtMoney = (v) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(v || 0));
const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "—";

export default function ExpensesPage() {
  const { user } = useAuth();
  const isReviewer = user?.role === "school_admin" || user?.role === "accounts";
  const isTeacher = user?.role === "teacher";
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("all"); // all | pending | approved | paid | rejected

  const load = async () => {
    const flt = filter !== "all" ? { params: { status: filter } } : {};
    const [r, s] = await Promise.all([
      api.get("/expenses", flt).then((res) => res.data),
      isReviewer ? api.get("/expenses/summary").then((res) => res.data) : Promise.resolve(null),
    ]);
    setRows(r); setSummary(s);
  };
  useEffect(() => { load(); }, [filter]);

  const decide = async (id, decision) => {
    try {
      const res = await api.post(`/expenses/${id}/decide`, { decision });
      toast.success(`Marked ${res.data.status}`);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const title = isTeacher ? "My expense submissions" : "School expenses";
  const subtitle = isTeacher
    ? "Submit out-of-pocket spend for school work. The school admin or accounts will review and approve."
    : "All recorded expenses + pending teacher reimbursement requests.";

  return (
    <div data-testid="expenses-page">
      <PageHeader
        eyebrow={isTeacher ? "Finance" : "Finance — Expenses"}
        title={title}
        subtitle={subtitle}
        actions={
          <button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-expense-btn">
            <Plus size={16} /> {isTeacher ? "Submit expense" : "Record expense"}
          </button>
        }
      />

      {isReviewer && summary && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-8">
          <KPI label="Total spent" value={fmtMoney(summary.total_spent)} accent="info" testId="kpi-total-spent" />
          <KPI label="Pending reimbursements" value={summary.pending_teacher_reimbursements?.count || 0}
                accent={summary.pending_teacher_reimbursements?.count ? "warning" : "success"}
                hint={fmtMoney(summary.pending_teacher_reimbursements?.total || 0)} testId="kpi-pending-reimb" />
          <KPI label="Approved" value={summary.by_status?.approved?.count || 0}
                accent="primary" hint={fmtMoney(summary.by_status?.approved?.total || 0)} testId="kpi-approved" />
          <KPI label="Paid" value={summary.by_status?.paid?.count || 0}
                accent="success" hint={fmtMoney(summary.by_status?.paid?.total || 0)} testId="kpi-paid" />
        </div>
      )}

      {isReviewer && (
        <div className="flex flex-wrap gap-2 mb-4">
          {["all", "pending", "approved", "paid", "rejected"].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3 py-1.5 text-xs rounded-full border ${filter === s ? "bg-primary text-primary-foreground border-primary" : "border-line text-ink-soft hover:border-primary"}`}
              data-testid={`filter-${s}`}
            >
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      )}

      <Section title={`Expenses (${rows.length})`}>
        {rows.length === 0 ? <Empty title="No expenses yet" /> : (
          <div className="border border-line rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left p-3">Date</th>
                  <th className="text-left p-3">Category</th>
                  <th className="text-left p-3">Description</th>
                  {isReviewer && <th className="text-left p-3">Submitted by</th>}
                  <th className="text-right p-3">Amount</th>
                  <th className="text-left p-3">Status</th>
                  {isReviewer && <th className="text-right p-3">Action</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id} className="border-t border-line/60" data-testid={`expense-row-${e.id}`}>
                    <td className="p-3 text-ink-soft">{fmtDate(e.incurred_on || e.created_at)}</td>
                    <td className="p-3"><span className="badge-neutral">{e.category}</span></td>
                    <td className="p-3">
                      <div className="font-medium">{e.description}</div>
                      {e.vendor && <div className="text-xs text-ink-muted">{e.vendor}</div>}
                      {e.reimburse_with_salary && <div className="text-xs text-status-info mt-0.5">Reimburse with salary</div>}
                    </td>
                    {isReviewer && (
                      <td className="p-3 text-ink-soft text-xs">
                        <div>{e.submitted_by_name || "—"}</div>
                        <div className="text-ink-muted">{e.submitted_by_role}</div>
                      </td>
                    )}
                    <td className="p-3 text-right font-mono">{fmtMoney(e.amount)}</td>
                    <td className="p-3"><span className={STATUS_BADGE[e.status] || "badge-neutral"} data-testid={`status-${e.id}`}>{e.status}</span></td>
                    {isReviewer && (
                      <td className="p-3 text-right whitespace-nowrap">
                        {e.status === "pending" && (
                          <>
                            <button className="btn-ghost p-1.5 text-status-success" onClick={() => decide(e.id, "approve")} title="Approve" data-testid={`approve-${e.id}`}>
                              <CheckCircle size={16} weight="fill" />
                            </button>
                            <button className="btn-ghost p-1.5 text-status-danger" onClick={() => decide(e.id, "reject")} title="Reject" data-testid={`reject-${e.id}`}>
                              <XCircle size={16} weight="fill" />
                            </button>
                          </>
                        )}
                        {e.status === "approved" && (
                          <button className="btn-ghost p-1.5 text-status-success" onClick={() => decide(e.id, "mark_paid")} title="Mark paid" data-testid={`pay-${e.id}`}>
                            <MoneyWavy size={16} weight="bold" />
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <ExpenseModal open={open} isTeacher={isTeacher} onClose={() => setOpen(false)} onSaved={() => { setOpen(false); load(); }} />
    </div>
  );
}

function ExpenseModal({ open, isTeacher, onClose, onSaved }) {
  const [form, setForm] = useState({
    category: "supplies", description: "", amount: "", vendor: "",
    incurred_on: "", reimburse_with_salary: false,
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setForm({
      category: "supplies", description: "", amount: "", vendor: "",
      incurred_on: "", reimburse_with_salary: false,
    });
  }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.description || !form.amount) return;
    setBusy(true);
    try {
      await api.post("/expenses", { ...form, amount: Number(form.amount) });
      toast.success(isTeacher ? "Submitted for approval" : "Expense recorded");
      onSaved();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={isTeacher ? "Submit a reimbursement" : "Record an expense"} size="md" testId="expense-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label className="label">Category</label>
          <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="expense-category">
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div><label className="label">Amount (₹)</label>
          <input type="number" min="1" required className="input" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} data-testid="expense-amount" />
        </div>
        <div className="md:col-span-2"><label className="label">Description</label>
          <input className="input" required value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="expense-description" />
        </div>
        <div><label className="label">Vendor (optional)</label>
          <input className="input" value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} />
        </div>
        <div><label className="label">Incurred on</label>
          <input type="date" className="input" value={form.incurred_on} onChange={(e) => setForm({ ...form, incurred_on: e.target.value })} />
        </div>
        {isTeacher && (
          <div className="md:col-span-2 pt-2 border-t border-line">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.reimburse_with_salary}
                onChange={(e) => setForm({ ...form, reimburse_with_salary: e.target.checked })}
                data-testid="reimburse-with-salary"
              />
              <span className="text-sm">Reimburse this with my next salary</span>
            </label>
          </div>
        )}
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-expense-btn">
            {busy ? "Saving…" : (isTeacher ? "Submit" : "Record")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
