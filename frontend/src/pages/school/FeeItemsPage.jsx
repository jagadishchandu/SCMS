import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { currency } from "../../lib/utils";
import { Plus, Pencil, Trash, Receipt } from "@phosphor-icons/react";
import { useAuth } from "../../contexts/AuthContext";
import toast from "react-hot-toast";

const CATEGORIES = [
  ["tuition", "Tuition"],
  ["books", "Books"],
  ["transport", "Transport"],
  ["lab", "Lab"],
  ["activities", "Activities"],
  ["uniform", "Uniform"],
  ["exam", "Exam"],
  ["library", "Library"],
  ["sports", "Sports"],
  ["hostel", "Hostel"],
  ["meals", "Meals"],
  ["other", "Other"],
];
const FREQUENCIES = [
  ["one_time", "One-time"],
  ["monthly", "Monthly"],
  ["quarterly", "Quarterly"],
  ["yearly", "Yearly"],
];

export default function FeeItemsPage() {
  const { user } = useAuth();
  const isSchoolAdmin = user?.role === "school_admin";
  const [items, setItems] = useState([]);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    const r = await api.get(`/fee-items?include_inactive=${includeInactive}`);
    setItems(r.data || []);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [includeInactive]);

  const remove = async (it) => {
    if (!window.confirm(`Deactivate "${it.name}"?`)) return;
    try {
      await api.delete(`/fee-items/${it.id}`);
      toast.success("Fee item deactivated");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const grouped = CATEGORIES.map(([k, label]) => ({
    key: k, label, items: items.filter((it) => it.category === k),
  })).filter((g) => g.items.length > 0);

  return (
    <div data-testid="fee-items-page">
      <PageHeader
        eyebrow="Finance — Fee Catalog"
        title="Fee items catalog"
        subtitle="Define reusable fee items (Tuition · Books · Transport · Lab · Activities …). Use these when building per-class fee structures."
        actions={
          <button className="btn-primary" onClick={() => { setEditing(null); setModalOpen(true); }} data-testid="add-fee-item-btn">
            <Plus size={16} /> Add fee item
          </button>
        }
      />

      <div className="flex items-center gap-3 mb-4">
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} data-testid="toggle-inactive-fee-items" />
          Include inactive
        </label>
        <div className="text-xs text-ink-muted ml-auto">{items.length} item{items.length === 1 ? "" : "s"}</div>
      </div>

      {grouped.length === 0 ? (
        <Empty title="No fee items yet" message="Click 'Add fee item' to create your first one." />
      ) : (
        grouped.map((g) => (
          <Section key={g.key} title={g.label} className="mb-4">
            <div className="overflow-x-auto">
              <table className="table">
                <thead><tr>
                  <th className="th">Name</th>
                  <th className="th text-right">Default amount</th>
                  <th className="th">Frequency</th>
                  <th className="th">Description</th>
                  <th className="th">Status</th>
                  <th className="th">Actions</th>
                </tr></thead>
                <tbody>
                  {g.items.map((it) => (
                    <tr key={it.id} className="table-row" data-testid={`fee-item-row-${it.id}`}>
                      <td className="td font-medium">{it.name}</td>
                      <td className="td text-right font-mono">{currency(it.default_amount)}</td>
                      <td className="td capitalize">{(it.frequency || "yearly").replace("_", " ")}</td>
                      <td className="td text-xs text-ink-muted">{it.description || "—"}</td>
                      <td className="td">
                        {it.is_active ? <span className="badge-success">Active</span> : <span className="badge-neutral">Inactive</span>}
                      </td>
                      <td className="td">
                        <div className="flex gap-2">
                          <button className="btn-secondary text-xs" onClick={() => { setEditing(it); setModalOpen(true); }} data-testid={`edit-fee-item-${it.id}`}>
                            <Pencil size={14} /> Edit
                          </button>
                          {isSchoolAdmin && it.is_active && (
                            <button className="btn-secondary text-xs text-status-danger" onClick={() => remove(it)} data-testid={`delete-fee-item-${it.id}`}>
                              <Trash size={14} /> Deactivate
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        ))
      )}

      <FeeItemModal open={modalOpen} onClose={() => setModalOpen(false)} initial={editing} onSaved={load} />
    </div>
  );
}

function FeeItemModal({ open, onClose, initial, onSaved }) {
  const [form, setForm] = useState({ name: "", category: "tuition", default_amount: "", frequency: "yearly", description: "", is_active: true });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (initial) setForm({ ...initial, default_amount: initial.default_amount });
    else setForm({ name: "", category: "tuition", default_amount: "", frequency: "yearly", description: "", is_active: true });
  }, [initial, open]);

  const save = async (e) => {
    e.preventDefault();
    if (!form.name || !form.category || form.default_amount === "" || Number(form.default_amount) < 0) {
      toast.error("Name, category, and a non-negative default amount are required");
      return;
    }
    setBusy(true);
    const payload = {
      name: form.name.trim(),
      category: form.category,
      default_amount: Number(form.default_amount),
      frequency: form.frequency,
      description: form.description || null,
      is_active: form.is_active,
    };
    try {
      if (initial) await api.patch(`/fee-items/${initial.id}`, payload);
      else await api.post("/fee-items", payload);
      toast.success(initial ? "Fee item updated" : "Fee item created");
      onSaved();
      onClose();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={initial ? "Edit fee item" : "Add fee item"} icon={Receipt}>
      <form onSubmit={save} className="space-y-3" data-testid="fee-item-form">
        <div>
          <label className="label">Name *</label>
          <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required data-testid="fee-item-name" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Category *</label>
            <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="fee-item-category">
              {CATEGORIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Frequency *</label>
            <select className="input" value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })} data-testid="fee-item-frequency">
              {FREQUENCIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="label">Default amount (₹) *</label>
          <input type="number" min="0" step="0.01" className="input" value={form.default_amount}
                  onChange={(e) => setForm({ ...form, default_amount: e.target.value })} required data-testid="fee-item-amount" />
        </div>
        <div>
          <label className="label">Description</label>
          <input className="input" value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Optional details" />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
          Active
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="save-fee-item-btn">
            {busy ? "Saving…" : initial ? "Save changes" : "Create item"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
