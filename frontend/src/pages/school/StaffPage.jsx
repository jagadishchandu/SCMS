import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty, KPI } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, Trash, Pencil, FilePdf } from "@phosphor-icons/react";
import toast from "react-hot-toast";

const ROLE_LABEL = {
  cleaner: "Cleaner", bus_driver: "Bus driver", security: "Security",
  cook: "Cook", sports_coach: "Sports coach", nurse: "Nurse",
  librarian: "Librarian", lab_assistant: "Lab assistant",
  office_assistant: "Office assistant", other: "Other",
};

const fmtMoney = (v) => {
  if (!v) return "—";
  const n = Number(v);
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);
};

export default function StaffPage() {
  const [rows, setRows] = useState([]);
  const [payroll, setPayroll] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    const [s, p] = await Promise.all([
      api.get("/staff").then((r) => r.data),
      api.get("/staff/summary/payroll").then((r) => r.data),
    ]);
    setRows(s); setPayroll(p);
  };
  useEffect(() => { load(); }, []);

  const remove = async (id) => {
    if (!window.confirm("Mark this staff member inactive?")) return;
    try { await api.delete(`/staff/${id}`); toast.success("Deactivated"); load(); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  const activeRows = rows.filter((r) => r.is_active !== false);

  const downloadPayrollPdf = async () => {
    const month = window.prompt(
      "Generate monthly payroll PDF for which month? (YYYY-MM)",
      new Date().toISOString().slice(0, 7),
    );
    if (!month) return;
    try {
      const res = await api.get(`/staff/payroll/monthly-pdf?month=${month}`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `payroll_${month}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Payroll PDF downloaded");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <div data-testid="staff-page">
      <PageHeader
        eyebrow="HR — Non-teaching staff"
        title="Support staff"
        subtitle="Cleaners, drivers, security, cooks, sports coaches, and other non-teaching team members."
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="btn-secondary" onClick={downloadPayrollPdf} data-testid="payroll-pdf-btn">
              <FilePdf size={16} /> Monthly Payroll PDF
            </button>
            <button className="btn-primary" onClick={() => { setEditing(null); setModalOpen(true); }} data-testid="add-staff-btn">
              <Plus size={16} /> Add staff
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <KPI label="Active staff" value={activeRows.length} accent="primary" testId="kpi-active-staff" />
        <KPI label="Monthly payroll" value={fmtMoney(payroll?.monthly_total || 0)} accent="info" testId="kpi-monthly-payroll" hint="Teachers + accounts + staff" />
        <KPI label="Yearly payroll" value={fmtMoney(payroll?.yearly_total || 0)} accent="success" testId="kpi-yearly-payroll" />
      </div>

      <Section title="Roster" subtitle="Only the school super admin can add or remove staff.">
        {activeRows.length === 0 ? (
          <Empty title="No staff yet" message="Add your first non-teaching staff member." />
        ) : (
          <div className="border border-line rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left p-3">Name</th>
                  <th className="text-left p-3">Role</th>
                  <th className="text-left p-3">Phone</th>
                  <th className="text-left p-3">Joined</th>
                  <th className="text-right p-3">Salary</th>
                  <th className="text-right p-3"></th>
                </tr>
              </thead>
              <tbody>
                {activeRows.map((s) => (
                  <tr key={s.id} className="border-t border-line/60" data-testid={`staff-row-${s.id}`}>
                    <td className="p-3 font-medium">{s.name}</td>
                    <td className="p-3"><span className="badge-neutral">{ROLE_LABEL[s.role] || s.role}</span></td>
                    <td className="p-3 text-ink-soft">{s.phone || "—"}</td>
                    <td className="p-3 text-ink-soft">{s.joining_date || "—"}</td>
                    <td className="p-3 text-right font-mono">{fmtMoney(s.monthly_salary)}</td>
                    <td className="p-3 text-right">
                      <button className="btn-ghost p-1.5" onClick={() => { setEditing(s); setModalOpen(true); }} data-testid={`edit-staff-${s.id}`}>
                        <Pencil size={14} />
                      </button>
                      <button className="btn-ghost p-1.5 text-status-danger" onClick={() => remove(s.id)} data-testid={`del-staff-${s.id}`}>
                        <Trash size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <StaffModal
        open={modalOpen}
        editing={editing}
        onClose={() => setModalOpen(false)}
        onSaved={() => { setModalOpen(false); load(); }}
      />
    </div>
  );
}

function StaffModal({ open, editing, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: "", role: "cleaner", phone: "", email: "", monthly_salary: "", joining_date: "", notes: "",
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (editing) {
      setForm({
        name: editing.name || "", role: editing.role || "other",
        phone: editing.phone || "", email: editing.email || "",
        monthly_salary: editing.monthly_salary || "",
        joining_date: editing.joining_date || "", notes: editing.notes || "",
      });
    } else {
      setForm({ name: "", role: "cleaner", phone: "", email: "", monthly_salary: "", joining_date: "", notes: "" });
    }
  }, [editing, open]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        ...form,
        monthly_salary: form.monthly_salary === "" ? null : Number(form.monthly_salary),
      };
      if (editing) await api.patch(`/staff/${editing.id}`, payload);
      else await api.post("/staff", payload);
      toast.success(editing ? "Updated" : "Staff added");
      onSaved();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={editing ? "Edit staff member" : "Add staff member"} size="md" testId="staff-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2"><label className="label">Name</label>
          <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="staff-name-input" />
        </div>
        <div><label className="label">Role</label>
          <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="staff-role-select">
            {Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div><label className="label">Monthly salary (₹)</label>
          <input type="number" min="0" className="input" value={form.monthly_salary} onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })} data-testid="staff-salary-input" />
        </div>
        <div><label className="label">Phone</label>
          <input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="staff-phone-input" />
        </div>
        <div><label className="label">Email</label>
          <input type="email" className="input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>
        <div className="md:col-span-2"><label className="label">Joining date</label>
          <input type="date" className="input" value={form.joining_date} onChange={(e) => setForm({ ...form, joining_date: e.target.value })} />
        </div>
        <div className="md:col-span-2"><label className="label">Notes</label>
          <textarea className="input" rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-staff-btn">
            {busy ? "Saving…" : (editing ? "Update" : "Add staff")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
