import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, BellRinging, Buildings } from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { formatDate } from "../../lib/utils";

export default function PlatformOverview() {
  const [schools, setSchools] = useState([]);
  const [notifStats, setNotifStats] = useState({ total: 0, queued: 0, sent: 0, failed: 0 });
  const [open, setOpen] = useState(false);

  const load = async () => {
    const [s, n] = await Promise.all([
      api.get("/schools").then((r) => r.data),
      api.get("/notifications/stats").then((r) => r.data),
    ]);
    setSchools(s);
    setNotifStats(n);
  };
  useEffect(() => { load(); }, []);

  return (
    <div data-testid="platform-overview">
      <PageHeader
        eyebrow="Platform Console"
        title="Schools across your platform"
        subtitle="Create new schools, manage school super admins, and monitor system-wide health."
        actions={<button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-school-btn"><Plus size={16}/> New school</button>}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <KPI label="Total schools" value={schools.length} accent="primary" testId="kpi-schools" />
        <KPI label="Active schools" value={schools.filter(s => s.is_active).length} accent="success" testId="kpi-active-schools" />
        <KPI label="Notifications sent" value={notifStats.total} accent="info" hint={`${notifStats.queued} queued`} testId="kpi-notifications" />
        <KPI label="Failed deliveries" value={notifStats.failed} accent={notifStats.failed ? "danger" : "success"} testId="kpi-failed" />
      </div>

      <Section title="Schools">
        {schools.length === 0 ? <Empty title="No schools yet" message="Add your first school to begin." /> : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {schools.map((s) => (
              <div key={s.id} className="border border-line rounded-lg p-5 hover:border-line-strong transition" data-testid={`school-card-${s.id}`}>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="w-10 h-10 rounded-lg bg-primary-light text-primary grid place-items-center"><Buildings size={20} /></div>
                  {s.is_active ? <span className="badge-success">Active</span> : <span className="badge-neutral">Inactive</span>}
                </div>
                <div className="font-display text-lg font-medium">{s.name}</div>
                <div className="text-sm text-ink-muted">{s.code} · {s.academic_year}</div>
                <div className="text-xs text-ink-muted mt-3">{s.address || "—"}</div>
                <div className="text-xs text-ink-muted mt-1">Created {formatDate(s.created_at)}</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <CreateSchoolModal open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
    </div>
  );
}

function CreateSchoolModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "", code: "", address: "", phone: "", email: "", academic_year: "2025-2026",
    admin_name: "", admin_email: "", admin_password: "",
  });
  const [busy, setBusy] = useState(false);
  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/schools", form);
      toast.success(`School ${form.name} created`);
      onCreated();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add a new school" size="lg" testId="create-school-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label className="label">School name</label><input className="input" required value={form.name} onChange={update("name")} data-testid="school-name-input" /></div>
        <div><label className="label">School code</label><input className="input" required value={form.code} onChange={update("code")} data-testid="school-code-input" /></div>
        <div className="md:col-span-2"><label className="label">Address</label><input className="input" value={form.address} onChange={update("address")} /></div>
        <div><label className="label">Phone</label><input className="input" value={form.phone} onChange={update("phone")} /></div>
        <div><label className="label">Email</label><input className="input" type="email" value={form.email} onChange={update("email")} /></div>
        <div><label className="label">Academic year</label><input className="input" value={form.academic_year} onChange={update("academic_year")} /></div>
        <div className="md:col-span-2 pt-2 border-t border-line"><div className="overline">School Super Admin (login account)</div></div>
        <div><label className="label">Admin name</label><input className="input" required value={form.admin_name} onChange={update("admin_name")} data-testid="admin-name-input" /></div>
        <div><label className="label">Admin email</label><input className="input" type="email" required value={form.admin_email} onChange={update("admin_email")} data-testid="admin-email-input" /></div>
        <div className="md:col-span-2"><label className="label">Temporary password</label><input className="input" type="text" required minLength={6} value={form.admin_password} onChange={update("admin_password")} data-testid="admin-password-input" /></div>
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-school-btn">{busy ? "Creating…" : "Create school"}</button>
        </div>
      </form>
    </Modal>
  );
}
