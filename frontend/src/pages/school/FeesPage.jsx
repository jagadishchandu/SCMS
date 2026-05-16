import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, KPI, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import toast from "react-hot-toast";
import { currency, formatDate } from "../../lib/utils";
import { Plus, Receipt, DownloadSimple, CopySimple } from "@phosphor-icons/react";

export default function FeesPage() {
  const [structures, setStructures] = useState([]);
  const [fees, setFees] = useState([]);
  const [classes, setClasses] = useState([]);
  const [students, setStudents] = useState([]);
  const [payments, setPayments] = useState([]);
  const [openStruct, setOpenStruct] = useState(false);
  const [payFor, setPayFor] = useState(null);

  const downloadReceipt = async (pid) => {
    try {
      const res = await api.get(`/receipts/payment/${pid}.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = `receipt_${pid}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const load = async () => {
    const [str, f, c, s, pay] = await Promise.all([
      api.get("/fees/structures").then((r) => r.data),
      api.get("/fees").then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
      api.get("/students").then((r) => r.data),
      api.get("/fees/payments").then((r) => r.data).catch(() => []),
    ]);
    setStructures(str); setFees(f); setClasses(c); setStudents(s); setPayments(pay);
  };
  useEffect(() => { load(); }, []);

  const assignStructure = async (id) => {
    try {
      const { data } = await api.post(`/fees/structures/${id}/assign`);
      toast.success(`Assigned to ${data.assigned} students`);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const cloneToSections = async (s) => {
    try {
      const { data } = await api.post(`/fees/structures/${s.id}/clone-to-sections`);
      if (data.message) {
        toast(data.message, { icon: "ℹ️" });
      } else if (data.cloned === 0) {
        toast(`Nothing to clone — already exists in sections: ${(data.skipped || []).join(", ") || "—"}`, { icon: "ℹ️" });
      } else {
        const skippedNote = (data.skipped || []).length ? ` (skipped existing: ${data.skipped.join(", ")})` : "";
        toast.success(`Cloned to ${data.cloned} section(s)${skippedNote}`);
      }
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
            {structures.map((s) => {
              const cls = classes.find(c => c.id === s.class_id);
              const sectionLabel = s.section ? `Section ${s.section}` : "All sections";
              return (
              <div key={s.id} className="border border-line rounded-lg p-5" data-testid={`struct-card-${s.id}`}>
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="font-display text-lg font-medium">{s.name}</div>
                    <div className="text-xs text-ink-muted">
                      {cls?.name} · {sectionLabel}
                      {s.term ? <> · <span className="badge-neutral">{s.term}</span></> : null}
                    </div>
                    <div className="text-xs text-ink-muted mt-0.5">Due {formatDate(s.due_date)}</div>
                  </div>
                  <div className="font-display text-xl">{currency(s.total)}</div>
                </div>
                <ul className="text-sm text-ink-soft space-y-1 mb-3">
                  {s.items.map((it, idx) => <li key={idx} className="flex justify-between"><span>{it.type}</span><span>{currency(it.amount)}</span></li>)}
                </ul>
                <div className="flex flex-col sm:flex-row gap-2">
                  <button className="btn-secondary flex-1" onClick={() => assignStructure(s.id)} data-testid={`assign-struct-${s.id}`}>Assign to {s.section ? `Section ${s.section}` : "class"}</button>
                  {s.section && (cls?.sections || []).length > 1 && (
                    <button
                      className="btn-secondary flex-1"
                      title={`Clone this structure to other sections of ${cls?.name}`}
                      onClick={() => cloneToSections(s)}
                      data-testid={`clone-struct-${s.id}`}
                    >
                      <CopySimple size={14}/> Clone to all sections
                    </button>
                  )}
                </div>
              </div>
            );})}
          </div>}
      </Section>

      <div className="mt-6">
        <Section title={`${fees.length} student fee records`}>
          {fees.length === 0 ? <Empty title="No fees assigned" /> :
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th className="th">Student</th><th className="th">Class</th><th className="th">Section</th><th className="th">Term</th><th className="th">Name</th>
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
                        <td className="td">{f.section || st?.section || "—"}</td>
                        <td className="td">{f.term || "—"}</td>
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

      <div className="mt-6">
        <Section title={`Recent payments · ${payments.length}`}>
          {payments.length === 0 ? <Empty title="No payments yet" /> :
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr><th className="th">Date</th><th className="th">Student</th><th className="th">Amount</th><th className="th">Mode</th><th className="th">Receipt #</th><th className="th"></th></tr></thead>
                <tbody>
                  {payments.slice(0, 30).map((p) => {
                    const st = studentMap[p.student_id];
                    return (
                      <tr key={p.id} className="table-row" data-testid={`payment-row-${p.id}`}>
                        <td className="td text-xs">{formatDate(p.created_at)}</td>
                        <td className="td"><div className="font-medium">{st?.name || "—"}</div><div className="text-xs text-ink-muted">{st?.student_uid}</div></td>
                        <td className="td font-display">{currency(p.amount)}</td>
                        <td className="td">{p.mode}</td>
                        <td className="td font-mono text-xs">{p.receipt_no}</td>
                        <td className="td">
                          <button className="btn-secondary" onClick={() => downloadReceipt(p.id)} data-testid={`receipt-${p.id}`}><DownloadSimple size={14}/> Receipt</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>}
        </Section>
      </div>
    </div>
  );
}

function StructureModal({ classes, open, onClose, onCreated }) {
  const TERM_OPTIONS = ["Term 1", "Term 2", "Term 3", "Annual", "Admission", "Monthly", "Custom"];
  const [form, setForm] = useState({
    class_id: "",
    section: "",
    term: "Term 1",
    name: "Term 1 Fees",
    due_date: "",
    items: [{ type: "tuition", amount: 0, fee_item_id: null }],
  });
  const [catalog, setCatalog] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      api.get("/fee-items").then((r) => setCatalog(r.data || [])).catch(() => setCatalog([]));
      setForm({
        class_id: "",
        section: "",
        term: "Term 1",
        name: "Term 1 Fees",
        due_date: "",
        items: [{ type: "tuition", amount: 0, fee_item_id: null }],
      });
    }
  }, [open]);

  // Auto-derive name when term changes & class selected, if user hasn't customized.
  const selectedClass = classes.find((c) => c.id === form.class_id);
  const sectionsForClass = selectedClass?.sections || [];

  const onTermChange = (term) => {
    // If user picked a known term and the name field still looks default, sync the name
    const looksDefault = /Fees?$/i.test(form.name) || form.name === "" || form.name.startsWith("Term ");
    const next = { ...form, term };
    if (term !== "Custom" && looksDefault) {
      const className = selectedClass?.name ? `${selectedClass.name} ` : "";
      next.name = `${className}${term} Fees`.trim();
    }
    setForm(next);
  };

  const onClassChange = (class_id) => {
    const cls = classes.find((c) => c.id === class_id);
    const looksDefault = /Fees?$/i.test(form.name) || form.name === "" || form.name.startsWith("Term ");
    let name = form.name;
    if (looksDefault && cls && form.term && form.term !== "Custom") {
      name = `${cls.name} ${form.term} Fees`;
    }
    setForm({ ...form, class_id, section: "", name });
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.class_id || !form.due_date) { toast.error("Class and due date are required"); return; }
    if (form.items.length === 0 || !form.items.some((i) => Number(i.amount) > 0)) {
      toast.error("Add at least one line item with amount > 0"); return;
    }
    setBusy(true);
    try {
      const payload = {
        class_id: form.class_id,
        name: form.name,
        items: form.items,
        due_date: form.due_date,
        section: form.section || null,
        term: form.term === "Custom" ? null : form.term,
      };
      await api.post("/fees/structures", payload);
      const tip = form.section
        ? " You can now click ‘Clone to all sections’ on the card to replicate it across the grade."
        : "";
      toast.success("Fee structure created." + tip);
      onCreated();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const pickFromCatalog = (idx, itemId) => {
    const it = catalog.find((c) => c.id === itemId);
    if (!it) return;
    const items = [...form.items];
    items[idx] = { ...items[idx], type: it.name, amount: it.default_amount, fee_item_id: it.id };
    setForm({ ...form, items });
  };

  return (
    <Modal open={open} onClose={onClose} title="New fee structure" size="lg" testId="new-structure-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <select className="input" required value={form.class_id} onChange={(e) => onClassChange(e.target.value)} data-testid="struct-class">
            <option value="">Class…</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select
            className="input"
            value={form.section}
            onChange={(e) => setForm({ ...form, section: e.target.value })}
            disabled={!form.class_id}
            data-testid="struct-section"
          >
            <option value="">All sections (class-wide)</option>
            {sectionsForClass.map((sec) => (
              <option key={sec} value={sec}>Section {sec}</option>
            ))}
          </select>
          <select
            className="input"
            value={form.term}
            onChange={(e) => onTermChange(e.target.value)}
            data-testid="struct-term"
          >
            {TERM_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input className="input" type="date" required value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} data-testid="struct-due-date" />
        </div>
        <div>
          <label className="label">Structure name</label>
          <input className="input" placeholder="e.g. Grade 1 Term 1 Fees" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="struct-name" />
          {form.class_id && form.section && (
            <div className="text-xs text-ink-muted mt-1" data-testid="struct-section-hint">
              This structure will apply only to <strong>{selectedClass?.name} – Section {form.section}</strong>. After saving, use “Clone to all sections” to replicate across the grade.
            </div>
          )}
          {form.class_id && !form.section && sectionsForClass.length > 1 && (
            <div className="text-xs text-ink-muted mt-1">
              This structure will apply to <strong>all sections</strong> of {selectedClass?.name} ({sectionsForClass.join(", ")}).
            </div>
          )}
        </div>
        <div className="flex items-center justify-between">
          <div className="overline">Items</div>
          {catalog.length > 0 && (
            <span className="text-xs text-ink-muted">Tip: pick from the catalog ({catalog.length} items) or type a custom name.</span>
          )}
        </div>
        {form.items.map((it, idx) => (
          <div key={idx} className="grid grid-cols-12 gap-2 items-start" data-testid={`struct-item-${idx}`}>
            <select
              className="input col-span-4"
              value={it.fee_item_id || ""}
              onChange={(e) => {
                if (e.target.value === "__custom__") {
                  const items = [...form.items];
                  items[idx] = { ...items[idx], fee_item_id: null, type: "", amount: 0 };
                  setForm({ ...form, items });
                } else if (e.target.value) {
                  pickFromCatalog(idx, e.target.value);
                }
              }}
              data-testid={`struct-item-${idx}-catalog`}
            >
              <option value="">Pick from catalog…</option>
              {catalog.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.category}) · {currency(c.default_amount)}
                </option>
              ))}
              <option value="__custom__">— Custom line item —</option>
            </select>
            <input
              className="input col-span-4"
              placeholder="Line item label"
              value={it.type}
              onChange={(e) => {
                const items = [...form.items]; items[idx] = { ...items[idx], type: e.target.value }; setForm({ ...form, items });
              }}
              data-testid={`struct-item-${idx}-type`}
            />
            <input
              className="input col-span-3"
              type="number" min="0" step="0.01"
              placeholder="Amount"
              value={it.amount}
              onChange={(e) => {
                const items = [...form.items]; items[idx] = { ...items[idx], amount: Number(e.target.value) }; setForm({ ...form, items });
              }}
              data-testid={`struct-item-${idx}-amount`}
            />
            <button
              type="button"
              className="btn-secondary col-span-1 text-status-danger"
              title="Remove line"
              onClick={() => setForm({ ...form, items: form.items.filter((_, i) => i !== idx) })}
              data-testid={`struct-item-${idx}-remove`}
            >×</button>
          </div>
        ))}
        <button type="button" className="btn-secondary" onClick={() => setForm({ ...form, items: [...form.items, { type: "", amount: 0, fee_item_id: null }] })} data-testid="struct-add-line">
          + Add line item
        </button>
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
