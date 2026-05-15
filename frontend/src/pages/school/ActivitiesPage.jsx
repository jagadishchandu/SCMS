import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, KPI, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, Trash, Users, MusicNote, Basketball, PaintBrush, Star } from "@phosphor-icons/react";
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, Legend, BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts";
import { CHART_COLORS } from "../../lib/utils";
import toast from "react-hot-toast";

const CATEGORY_META = {
  sport: { label: "Sports", icon: Basketball, color: "text-status-success" },
  music: { label: "Music", icon: MusicNote, color: "text-secondary" },
  art: { label: "Arts", icon: PaintBrush, color: "text-terracotta" },
  club: { label: "Clubs", icon: Users, color: "text-primary" },
  other: { label: "Other", icon: Star, color: "text-ink-soft" },
};

export default function ActivitiesPage() {
  const [stats, setStats] = useState(null);
  const [open, setOpen] = useState(false);
  const [enrollFor, setEnrollFor] = useState(null);
  const [students, setStudents] = useState([]);

  const load = async () => {
    const [st, s] = await Promise.all([
      api.get("/activities/stats/summary").then((r) => r.data),
      api.get("/students").then((r) => r.data),
    ]);
    setStats(st);
    setStudents(s);
  };
  useEffect(() => { load(); }, []);

  const remove = async (id) => {
    if (!window.confirm("Delete this activity and all its enrollments?")) return;
    await api.delete(`/activities/${id}`);
    load();
  };

  if (!stats) return <div className="skeleton h-40 w-full" />;

  const categoryData = stats.by_category.map((c) => ({
    name: CATEGORY_META[c.category]?.label || c.category, value: c.count,
  }));
  const enrollData = stats.per_activity.slice(0, 10).map((a) => ({
    name: a.name, enrolled: a.enrolled,
  }));

  return (
    <div data-testid="activities-page">
      <PageHeader
        eyebrow="Extra-curricular"
        title="Sports, music, arts & clubs"
        subtitle="Track what activities are active and how many children are enrolled in each."
        actions={<button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-activity-btn"><Plus size={16}/> New activity</button>}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KPI label="Total activities" value={stats.total_activities} accent="primary" testId="kpi-activities" />
        <KPI label="Active" value={stats.active_activities} accent="success" testId="kpi-activities-active" />
        <KPI label="Categories" value={stats.by_category.length} accent="info" testId="kpi-activity-categories" />
        <KPI label="Total enrolments" value={stats.per_activity.reduce((a, b) => a + b.enrolled, 0)} accent="secondary" testId="kpi-activity-enrolments" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Section title="Mix by category">
          {categoryData.length === 0 ? <Empty title="No activities yet" /> :
            <div className="h-64">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={categoryData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={90} paddingAngle={3}>
                    {categoryData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip /><Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>}
        </Section>
        <Section title="Top activities by enrolment">
          {enrollData.length === 0 ? <Empty title="No enrolments yet" /> :
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={enrollData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E6E1D6" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={110} />
                  <Tooltip />
                  <Bar dataKey="enrolled" fill={CHART_COLORS[0]} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>}
        </Section>
      </div>

      <Section title={`${stats.per_activity.length} activities`}>
        {stats.per_activity.length === 0 ? <Empty title="No activities" message="Add your first sport, music or club to start tracking participation." /> :
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {stats.per_activity.map((a) => {
              const meta = CATEGORY_META[a.category] || CATEGORY_META.other;
              const Icon = meta.icon;
              return (
                <div key={a.activity_id} className="border border-line rounded-lg p-5" data-testid={`activity-card-${a.activity_id}`}>
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-9 h-9 rounded-lg bg-bg-subtle grid place-items-center"><Icon size={18} className={meta.color} /></div>
                      <div>
                        <div className="font-display text-base font-medium">{a.name}</div>
                        <div className="text-xs text-ink-muted">{meta.label}{a.coach ? ` · ${a.coach}` : ""}</div>
                      </div>
                    </div>
                    {a.is_active ? <span className="badge-success">Active</span> : <span className="badge-neutral">Off</span>}
                  </div>
                  <div className="flex items-baseline gap-2 mt-3">
                    <div className="font-display text-3xl font-medium">{a.enrolled}</div>
                    <div className="text-xs text-ink-muted">students enrolled</div>
                  </div>
                  {a.schedule && <div className="text-xs text-ink-muted mt-2">Schedule: {a.schedule}</div>}
                  <div className="flex gap-2 mt-4">
                    <button className="btn-secondary flex-1" onClick={() => setEnrollFor(a)} data-testid={`enroll-${a.activity_id}`}>Enroll students</button>
                    <button className="btn-ghost p-2 text-status-danger" onClick={() => remove(a.activity_id)} data-testid={`del-activity-${a.activity_id}`}><Trash size={14}/></button>
                  </div>
                </div>
              );
            })}
          </div>}
      </Section>

      <CreateActivityModal open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
      {enrollFor && <EnrollModal activity={enrollFor} students={students} onClose={() => setEnrollFor(null)} onDone={() => { setEnrollFor(null); load(); }} />}
    </div>
  );
}

function CreateActivityModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", category: "sport", coach: "", schedule: "", description: "", is_active: true });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      await api.post("/activities", form);
      toast.success("Activity created");
      onCreated();
      setForm({ name: "", category: "sport", coach: "", schedule: "", description: "", is_active: true });
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="New activity" size="md" testId="new-activity-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="md:col-span-2"><label className="label">Name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="activity-name" /></div>
        <div><label className="label">Category</label>
          <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="activity-category">
            {Object.entries(CATEGORY_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        <div><label className="label">Coach / Mentor</label><input className="input" value={form.coach} onChange={(e) => setForm({ ...form, coach: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="label">Schedule</label><input className="input" placeholder="e.g. Mon, Wed 4-5pm" value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="label">Description</label><textarea className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
        <div className="md:col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-activity-btn">{busy ? "Saving…" : "Create"}</button>
        </div>
      </form>
    </Modal>
  );
}

function EnrollModal({ activity, students, onClose, onDone }) {
  const [picked, setPicked] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [existing, setExisting] = useState(new Set());

  useEffect(() => {
    api.get(`/activities/${activity.activity_id}/roster`).then((r) => {
      setExisting(new Set(r.data.map((s) => s.id)));
    });
  }, [activity.activity_id]);

  const toggle = (id) => {
    setPicked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  };

  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/activities/${activity.activity_id}/enroll`, { student_ids: Array.from(picked) });
      toast.success(`Enrolled ${data.enrolled} students`);
      onDone();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const removeOne = async (sid) => {
    await api.delete(`/activities/${activity.activity_id}/enroll/${sid}`);
    setExisting((s) => { const n = new Set(s); n.delete(sid); return n; });
  };

  return (
    <Modal open onClose={onClose} title={`Enroll students · ${activity.name}`} size="lg" testId="enroll-modal">
      <div className="text-xs text-ink-muted mb-3">Select students to add. Existing enrollees show a Remove button.</div>
      <div className="max-h-96 overflow-y-auto border border-line rounded-lg">
        <ul className="divide-y divide-line">
          {students.map((s) => {
            const isMember = existing.has(s.id);
            return (
              <li key={s.id} className="flex items-center justify-between px-4 py-2 text-sm" data-testid={`enroll-row-${s.student_uid}`}>
                <label className="flex items-center gap-2 cursor-pointer">
                  {!isMember && <input type="checkbox" checked={picked.has(s.id)} onChange={() => toggle(s.id)} />}
                  <span className="font-medium">{s.name}</span>
                  <span className="text-xs text-ink-muted">{s.student_uid}</span>
                </label>
                {isMember && <button className="badge-success text-[10px]" onClick={() => removeOne(s.id)} data-testid={`unenroll-${s.student_uid}`}>Enrolled · Remove</button>}
              </li>
            );
          })}
        </ul>
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <button className="btn-secondary" onClick={onClose}>Close</button>
        <button className="btn-primary" onClick={submit} disabled={busy || picked.size === 0} data-testid="submit-enroll-btn">
          {busy ? "Enrolling…" : `Add ${picked.size} students`}
        </button>
      </div>
    </Modal>
  );
}
