import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import {
  Plus, BellRinging, Buildings, GraduationCap, ChalkboardTeacher,
  Users, BookOpen, CurrencyInr, CaretRight, X,
} from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { formatDate } from "../../lib/utils";

export default function PlatformOverview() {
  const [schools, setSchools] = useState([]);
  const [notifStats, setNotifStats] = useState({ total: 0, queued: 0, sent: 0, failed: 0 });
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null); // { school, teachers, students, counts }
  const [loadingDetail, setLoadingDetail] = useState(false);

  const load = async () => {
    const [s, n] = await Promise.all([
      api.get("/schools/with-stats").then((r) => r.data),
      api.get("/notifications/stats").then((r) => r.data),
    ]);
    setSchools(s);
    setNotifStats(n);
  };
  useEffect(() => { load(); }, []);

  const openDetail = async (school) => {
    setLoadingDetail(true);
    setDetail({ school, teachers: [], students: [], counts: {} });
    try {
      const { data } = await api.get(`/schools/${school.id}/people`);
      setDetail(data);
    } catch (err) {
      toast.error(formatApiError(err));
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  const totalStudents = schools.reduce((a, s) => a + (s.stats?.students || 0), 0);
  const totalTeachers = schools.reduce((a, s) => a + (s.stats?.teachers || 0), 0);

  return (
    <div data-testid="platform-overview">
      <PageHeader
        eyebrow="Platform Console"
        title="Schools across your platform"
        subtitle="Create new schools, manage school super admins, and inspect any school's roster in one click."
        actions={<button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-school-btn"><Plus size={16}/> New school</button>}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <KPI label="Schools" value={schools.length} accent="primary" testId="kpi-schools" />
        <KPI label="Total students" value={totalStudents} accent="info" testId="kpi-total-students" />
        <KPI label="Total teachers" value={totalTeachers} accent="success" testId="kpi-total-teachers" />
        <KPI label="Notifications" value={notifStats.total} accent="info" hint={`${notifStats.queued} queued`} testId="kpi-notifications" />
        <KPI label="Failed deliveries" value={notifStats.failed} accent={notifStats.failed ? "danger" : "success"} testId="kpi-failed" />
      </div>

      <Section title="Schools" subtitle="Click any school card to view its teachers and students.">
        {schools.length === 0 ? <Empty title="No schools yet" message="Add your first school to begin." /> : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {schools.map((s) => {
              const st = s.stats || {};
              return (
                <button
                  type="button"
                  key={s.id}
                  onClick={() => openDetail(s)}
                  className="text-left border border-line rounded-lg p-5 hover:border-primary hover:shadow-sm transition group bg-bg-surface"
                  data-testid={`school-card-${s.id}`}
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="w-10 h-10 rounded-lg bg-primary-light text-primary grid place-items-center">
                      <Buildings size={20} />
                    </div>
                    <div className="flex items-center gap-2">
                      {s.is_active ? <span className="badge-success">Active</span> : <span className="badge-neutral">Inactive</span>}
                      <CaretRight size={14} className="text-ink-muted group-hover:text-primary transition" />
                    </div>
                  </div>
                  <div className="font-display text-lg font-medium">{s.name}</div>
                  <div className="text-sm text-ink-muted">{s.code} · {s.academic_year || "—"}</div>

                  <div className="grid grid-cols-3 gap-2 mt-4">
                    <StatTile icon={GraduationCap} label="Students" value={st.students || 0} testId={`stat-students-${s.id}`} />
                    <StatTile icon={ChalkboardTeacher} label="Teachers" value={st.teachers || 0} testId={`stat-teachers-${s.id}`} />
                    <StatTile icon={Users} label="Parents" value={st.parents || 0} testId={`stat-parents-${s.id}`} />
                    <StatTile icon={BookOpen} label="Classes" value={st.classes || 0} testId={`stat-classes-${s.id}`} />
                    <StatTile icon={BookOpen} label="Sections" value={st.sections || 0} testId={`stat-sections-${s.id}`} />
                    <StatTile icon={CurrencyInr} label="Fee due" value={fmtMoney(st.fee_due || 0)} testId={`stat-feedue-${s.id}`} />
                  </div>

                  <div className="text-xs text-ink-muted mt-4 pt-3 border-t border-line/60 flex items-center justify-between">
                    <span>Created {formatDate(s.created_at)}</span>
                    {s.valid_until && <span>Valid until {formatDate(s.valid_until)}</span>}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Section>

      <CreateSchoolModal open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
      <SchoolDetailDrawer
        open={!!detail}
        detail={detail}
        loading={loadingDetail}
        onClose={() => setDetail(null)}
      />
    </div>
  );
}

function StatTile({ icon: Icon, label, value, testId }) {
  return (
    <div className="bg-bg-subtle rounded-md p-2.5 flex flex-col gap-0.5" data-testid={testId}>
      <Icon size={14} className="text-ink-muted" />
      <div className="text-base font-display font-medium leading-tight">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</div>
    </div>
  );
}

function fmtMoney(v) {
  if (!v) return "₹0";
  const num = Number(v);
  if (num >= 1e7) return `₹${(num / 1e7).toFixed(1)}Cr`;
  if (num >= 1e5) return `₹${(num / 1e5).toFixed(1)}L`;
  if (num >= 1e3) return `₹${(num / 1e3).toFixed(0)}k`;
  return `₹${num.toFixed(0)}`;
}

function SchoolDetailDrawer({ open, detail, loading, onClose }) {
  if (!open) return null;
  const school = detail?.school;
  const teachers = detail?.teachers || [];
  const students = detail?.students || [];
  return (
    <div className="fixed inset-0 z-40" data-testid="school-detail-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="absolute top-0 right-0 bottom-0 w-full max-w-2xl bg-bg-surface border-l border-line shadow-xl overflow-y-auto">
        <div className="sticky top-0 bg-bg-surface border-b border-line p-5 flex items-start justify-between gap-3 z-10">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 rounded-lg bg-primary-light text-primary grid place-items-center shrink-0">
              <Buildings size={20} />
            </div>
            <div className="min-w-0">
              <div className="font-display text-xl font-medium truncate" data-testid="drawer-school-name">{school?.name}</div>
              <div className="text-xs text-ink-muted">{school?.code} · {school?.academic_year || "—"}</div>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost p-2" data-testid="drawer-close-btn"><X size={18}/></button>
        </div>

        <div className="p-5 space-y-6">
          {loading ? (
            <div className="text-ink-muted text-sm">Loading roster…</div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                <KPI label="Students" value={students.length} accent="info" testId="drawer-kpi-students" />
                <KPI label="Teachers" value={teachers.length} accent="success" testId="drawer-kpi-teachers" />
                <KPI label="Classes" value={detail?.counts?.classes || 0} accent="primary" testId="drawer-kpi-classes" />
              </div>

              {school?.id && <MandatoryChannelsPanel schoolId={school.id} schoolName={school.name} />}

              <Section title={`Teachers (${teachers.length})`}>
                {teachers.length === 0 ? (
                  <Empty title="No teachers" message="This school hasn't added any teachers yet." />
                ) : (
                  <div className="border border-line rounded-md overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                        <tr>
                          <th className="text-left p-2.5">Name</th>
                          <th className="text-left p-2.5">Email</th>
                          <th className="text-left p-2.5">Phone</th>
                        </tr>
                      </thead>
                      <tbody>
                        {teachers.map((t) => (
                          <tr key={t.id} className="border-t border-line/60" data-testid={`drawer-teacher-${t.id}`}>
                            <td className="p-2.5 font-medium">{t.name}</td>
                            <td className="p-2.5 text-ink-soft">{t.email}</td>
                            <td className="p-2.5 text-ink-soft">{t.phone || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <Section title={`Students (${students.length})`}>
                {students.length === 0 ? (
                  <Empty title="No students" message="This school hasn't enrolled any students yet." />
                ) : (
                  <div className="border border-line rounded-md overflow-hidden max-h-96 overflow-y-auto">
                    <table className="w-full text-sm">
                      <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider sticky top-0">
                        <tr>
                          <th className="text-left p-2.5">UID</th>
                          <th className="text-left p-2.5">Name</th>
                          <th className="text-left p-2.5">Class</th>
                          <th className="text-left p-2.5">Parent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {students.map((s) => (
                          <tr key={s.id} className="border-t border-line/60" data-testid={`drawer-student-${s.id}`}>
                            <td className="p-2.5 font-mono text-xs text-ink-soft">{s.student_uid}</td>
                            <td className="p-2.5 font-medium">{s.name}</td>
                            <td className="p-2.5 text-ink-soft">{s.class_name || s.class_id} · {s.section}</td>
                            <td className="p-2.5 text-ink-soft text-xs">{s.parent?.name || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>
            </>
          )}
        </div>
      </div>
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


function MandatoryChannelsPanel({ schoolId, schoolName }) {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/schools/${schoolId}/mandatory-channels`)
      .then((r) => { setData(r.data); setDraft(r.data.channels || []); })
      .catch((err) => toast.error(formatApiError(err)));
  }, [schoolId]);

  if (!data) return null;
  const toggle = (ch) => {
    setDraft((d) => d.includes(ch) ? d.filter((x) => x !== ch) : [...d, ch]);
  };
  const dirty = JSON.stringify([...draft].sort()) !== JSON.stringify([...(data.channels || [])].sort());

  const save = async () => {
    if (draft.length === 0) { toast.error("Pick at least one channel"); return; }
    setBusy(true);
    try {
      const { data: r } = await api.patch(`/schools/${schoolId}/mandatory-channels`, { channels: draft });
      setData({ ...data, channels: r.channels });
      toast.success(`Mandatory channels updated for ${schoolName}`);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const meta = {
    email: { label: "Email", hint: "Required for digest summaries & password reset" },
    whatsapp: { label: "WhatsApp / SMS", hint: "Requires user phone number on file" },
    telegram: { label: "Telegram", hint: "Free, fastest. Users link via /start bot" },
  };

  return (
    <Section title="Mandatory communication channels">
      <div className="text-xs text-ink-muted mb-3">
        Pick one or more channels every user in this school must link. Banners appear inside the user's account until they comply.
      </div>
      <div className="space-y-2" data-testid="mandatory-channels-config">
        {(data.allowed || ["email", "whatsapp", "telegram"]).map((ch) => {
          const checked = draft.includes(ch);
          return (
            <label
              key={ch}
              className={"flex items-center gap-3 p-3 rounded-md border cursor-pointer transition " + (checked ? "bg-primary-light/40 border-primary" : "border-line/60 hover:bg-bg-subtle")}
              data-testid={`mc-row-${ch}`}
            >
              <input
                type="checkbox" className="w-4 h-4"
                checked={checked} onChange={() => toggle(ch)}
                data-testid={`mc-check-${ch}`}
              />
              <div className="flex-1">
                <div className="text-sm font-medium capitalize">{meta[ch]?.label || ch}</div>
                <div className="text-xs text-ink-muted">{meta[ch]?.hint}</div>
              </div>
            </label>
          );
        })}
      </div>
      <div className="flex items-center justify-between mt-3">
        <div className="text-xs text-ink-muted" data-testid="mc-current">
          Currently mandatory: {(data.channels || []).map((c) => (
            <span key={c} className="badge bg-primary-light text-primary mr-1 capitalize">{c}</span>
          ))}
        </div>
        <button
          type="button" className="btn-primary text-xs"
          disabled={!dirty || busy || draft.length === 0}
          onClick={save}
          data-testid="mc-save-btn"
        >{busy ? "Saving…" : "Save"}</button>
      </div>
    </Section>
  );
}
