import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, KPI, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import toast from "react-hot-toast";
import { currency, formatDate } from "../../lib/utils";
import { Plus, Receipt } from "@phosphor-icons/react";

export default function FeesPage() {
  const [structures, setStructures] = useState([]);
  const [fees, setFees] = useState([]);
  const [classes, setClasses] = useState([]);
  const [students, setStudents] = useState([]);
  const [openStruct, setOpenStruct] = useState(false);
  const [payFor, setPayFor] = useState(null);

  const load = async () => {
    const [str, f, c, s] = await Promise.all([
      api.get("/fees/structures").then((r) => r.data),
      api.get("/fees").then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
      api.get("/students").then((r) => r.data),
    ]);
    setStructures(str); setFees(f); setClasses(c); setStudents(s);
  };
  useEffect(() => { load(); }, []);

  const assignStructure = async (id) => {
    try {
      const { data } = await api.post(`/fees/structures/${id}/assign`);
      toast.success(`Assigned to ${data.assigned} students`);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const totals = fees.reduce((acc, f) => ({
    total: acc.total + f.total, paid: acc.paid + f.paid, due: acc.due + f.due,
  }), { total: 0, paid: 0, due: 0 });

  const studentMap = Object.fromEntries(students.map((s) => [s.id, s]));

  return (
    <div data-testid="fees-page">
      <PageHeader
        eyebrow="Finance"
        title="Fees and collections"
        subtitle="Define fee structures, assign them to classes, record payments and track dues."
        actions={<button className="btn-primary" onClick={() => setOpenStruct(true)} data-testid="add-structure-btn"><Plus size={16}/> Fee structure</button>}
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <KPI label="Billed" value={currency(totals.total)} accent="secondary" testId="fees-total" />
        <KPI label="Collected" value={currency(totals.paid)} accent="success" testId="fees-paid" />
        <KPI label="Outstanding" value={currency(totals.due)} accent={totals.due > 0 ? "danger" : "success"} testId="fees-due" />
      </div>

      <Section title="Fee structures">
        {structures.length === 0 ? <Empty title="No fee structures" /> :
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {structures.map((s) => (
              <div key={s.id} className="border border-line rounded-lg p-5">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="font-display text-lg font-medium">{s.name}</div>
                    <div className="text-xs text-ink-muted">{classes.find(c => c.id === s.class_id)?.name} · Due {formatDate(s.due_date)}</div>
                  </div>
                  <div className="font-display text-xl">{currency(s.total)}</div>
                </div>
                <ul className="text-sm text-ink-soft space-y-1 mb-3">
                  {s.items.map((it, idx) => <li key={idx} className="flex justify-between"><span>{it.type}</span><span>{currency(it.amount)}</span></li>)}
                </ul>
                <button className="btn-secondary w-full" onClick={() => assignStructure(s.id)} data-testid={`assign-struct-${s.id}`}>Assign to class</button>
              </div>
            ))}
          </div>}
      </Section>

      <div className="mt-6">
        <Section title={`${fees.length} student fee records`}>
          {fees.length === 0 ? <Empty title="No fees assigned" /> :
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th className="th">Student</th><th className="th">Class</th><th className="th">Name</th>
                  <th className="th">Total</th><th className="th">Paid</th><th className="th">Due</th><th className="th">Status</th><th className="th"></th>
                </tr></thead>
                <tbody>
                  {fees.map((f) => {
                    const st = studentMap[f.student_id];
                    return (
                      <tr key={f.id} className="table-row" data-testid={`fee-row-${f.id}`}>
                        <td className="td">
                          <div className="font-medium">{st?.name || "—"}</div>
                          <div className="text-xs text-ink-muted">{st?.student_uid}</div>
                        </td>
                        <td className="td">{classes.find(c => c.id === f.class_id)?.name}</td>
                        <td className="td">{f.name}</td>
                        <td className="td">{currency(f.total)}</td>
                        <td className="td">{currency(f.paid)}</td>
                        <td className="td">{currency(f.due)}</td>
                        <td className="td">
                          <span className={f.status === "paid" ? "badge-success" : f.status === "partial" ? "badge-warning" : "badge-danger"}>{f.status}</span>
                        </td>
                        <td className="td">
                          {f.due > 0 && <button className="btn-secondary" onClick={() => setPayFor(f)} data-testid={`pay-btn-${f.id}`}><Receipt size={14}/> Pay</button>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>}
        </Section>
      </div>

      <StructureModal classes={classes} open={openStruct} onClose={() => setOpenStruct(false)} onCreated={() => { setOpenStruct(false); load(); }} />
      {payFor && <PaymentModal fee={payFor} onClose={() => setPayFor(null)} onDone={() => { setPayFor(null); load(); }} />}
    </div>
  );
}

function StructureModal({ classes, open, onClose, onCreated }) {
  const [form, setForm] = useState({ class_id: "", name: "Term 1 Fees", due_date: "", items: [{ type: "tuition", amount: 0 }] });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/fees/structures", form);
      toast.success("Fee structure created");
      onCreated();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="New fee structure" size="lg" testId="new-structure-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select className="input md:col-span-1" required value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })} data-testid="struct-class">
            <option value="">Class…</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <input className="input" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="struct-name" />
          <input className="input" type="date" required value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} data-testid="struct-due-date" />
        </div>
        <div className="overline">Items</div>
        {form.items.map((it, idx) => (
          <div key={idx} className="grid grid-cols-3 gap-3">
            <input className="input" value={it.type} onChange={(e) => {
              const items = [...form.items]; items[idx] = { ...items[idx], type: e.target.value }; setForm({ ...form, items });
            }} />
            <input className="input" type="number" value={it.amount} onChange={(e) => {
              const items = [...form.items]; items[idx] = { ...items[idx], amount: Number(e.target.value) }; setForm({ ...form, items });
            }} />
            <button type="button" className="btn-secondary" onClick={() => {
              setForm({ ...form, items: form.items.filter((_, i) => i !== idx) });
            }}>Remove</button>
          </div>
        ))}
        <button type="button" className="btn-secondary" onClick={() => setForm({ ...form, items: [...form.items, { type: "", amount: 0 }] })}>+ Add item</button>
        <div className="text-right font-display text-lg">Total: {currency(form.items.reduce((a, b) => a + Number(b.amount || 0), 0))}</div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-structure-btn">{busy ? "Saving…" : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}

function PaymentModal({ fee, onClose, onDone }) {
  const [amount, setAmount] = useState(fee.due);
  const [mode, setMode] = useState("cash");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/fees/payments", { fee_id: fee.id, student_id: fee.student_id, amount: Number(amount), mode });
      toast.success(`Receipt ${data.receipt_no} generated`);
      onDone();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title="Record payment" size="md" testId="payment-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div><div className="overline mb-1">Total</div><div className="font-display text-xl">{currency(fee.total)}</div></div>
          <div><div className="overline mb-1">Outstanding</div><div className="font-display text-xl text-status-danger">{currency(fee.due)}</div></div>
        </div>
        <div><label className="label">Amount</label><input className="input" type="number" required min="1" max={fee.due} value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="payment-amount" /></div>
        <div><label className="label">Mode</label>
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)} data-testid="payment-mode">
            <option value="cash">Cash</option><option value="bank_transfer">Bank transfer</option>
            <option value="card">Card</option><option value="online">Online</option>
          </select>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-payment-btn">{busy ? "Recording…" : "Record"}</button>
        </div>
      </form>
    </Modal>
  );
}
