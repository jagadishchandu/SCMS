import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import toast from "react-hot-toast";
import { Plus, Trash } from "@phosphor-icons/react";
import { formatDate } from "../../lib/utils";

export default function HolidaysPage() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ title: "", date: "", end_date: "", type: "school", description: "" });
  const load = async () => setItems((await api.get("/holidays")).data);
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/holidays", form);
      toast.success("Holiday added and parents notified");
      setForm({ title: "", date: "", end_date: "", type: "school", description: "" });
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const remove = async (id) => { await api.delete(`/holidays/${id}`); load(); };

  return (
    <div data-testid="holidays-page">
      <PageHeader eyebrow="Calendar" title="School holidays" subtitle="Manage holiday calendar — parents are auto-notified on add." />

      <Section title="Add holiday">
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <input className="input" placeholder="Title" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="holiday-title" />
          <input className="input" type="date" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="holiday-date" />
          <input className="input" type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} placeholder="End (optional)" />
          <select className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="school">School</option><option value="public">Public</option><option value="closure">Closure</option>
          </select>
          <button className="btn-primary" data-testid="add-holiday-btn"><Plus size={16}/> Add</button>
          <div className="md:col-span-5"><input className="input" placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
        </form>
      </Section>

      <div className="mt-6">
        <Section title={`${items.length} holidays`}>
          {items.length === 0 ? <Empty title="No holidays set" /> :
            <ul className="divide-y divide-line">
              {items.map((h) => (
                <li key={h.id} className="py-3 flex items-center justify-between" data-testid={`holiday-row-${h.id}`}>
                  <div>
                    <div className="font-medium">{h.title}</div>
                    <div className="text-xs text-ink-muted">{h.type} · {h.description || "—"}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-sm">{formatDate(h.date)}{h.end_date ? ` → ${formatDate(h.end_date)}` : ""}</div>
                    <button className="btn-ghost p-1.5 text-status-danger" onClick={() => remove(h.id)}><Trash size={14}/></button>
                  </div>
                </li>
              ))}
            </ul>}
        </Section>
      </div>
    </div>
  );
}
