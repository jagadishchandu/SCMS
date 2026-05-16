import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, MagnifyingGlass, Key, Copy } from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";

export default function StudentsPage() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [filter, setFilter] = useState({ class_id: "", section: "", q: "" });
  const [open, setOpen] = useState(false);
  const [credsFor, setCredsFor] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    const params = {};
    if (filter.class_id) params.class_id = filter.class_id;
    if (filter.section) params.section = filter.section;
    if (filter.q) params.q = filter.q;
    const [s, c] = await Promise.all([
      api.get("/students", { params }).then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
    ]);
    setStudents(s); setClasses(c);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter.class_id, filter.section]);

  const sections = useMemo(() => {
    const c = classes.find((x) => x.id === filter.class_id);
    return c ? c.sections : [];
  }, [classes, filter.class_id]);

  return (
    <div data-testid="students-page">
      <PageHeader
        eyebrow="Students"
        title="Manage students & parents"
        subtitle="Add students manually or via Excel. Click any student to view their analytics."
        actions={<button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-student-btn"><Plus size={16}/> New student</button>}
      />
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            className="input pl-8 w-64" placeholder="Search name or UID"
            value={filter.q}
            onChange={(e) => setFilter({ ...filter, q: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && load()}
            data-testid="students-search-input"
          />
        </div>
        <select className="input w-44" value={filter.class_id} onChange={(e) => setFilter({ ...filter, class_id: e.target.value, section: "" })} data-testid="students-class-filter">
          <option value="">All classes</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-32" value={filter.section} onChange={(e) => setFilter({ ...filter, section: e.target.value })} disabled={!filter.class_id} data-testid="students-section-filter">
          <option value="">All sections</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="btn-secondary" onClick={load} data-testid="students-apply-btn">Apply</button>
      </div>

      <Section title={`${students.length} students`}>
        {students.length === 0 ? <Empty title="No students yet" message="Add your first student to get started." /> :
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">UID</th><th className="th">Name</th><th className="th">Class</th>
                <th className="th">Section</th><th className="th">Roll</th><th className="th">Parent</th>
                <th className="th">Parent login</th>
                <th className="th">Status</th>
              </tr></thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id} className="table-row" data-testid={`student-row-${s.student_uid}`}>
                    <td className="td font-mono text-xs cursor-pointer" onClick={() => navigate(`/student/${s.student_uid}`)}>{s.student_uid}</td>
                    <td className="td font-medium cursor-pointer" onClick={() => navigate(`/student/${s.student_uid}`)}>{s.name}</td>
                    <td className="td">{classes.find((c) => c.id === s.class_id)?.name || s.class_id}</td>
                    <td className="td">{s.section}</td>
                    <td className="td">{s.roll_number || "—"}</td>
                    <td className="td">{s.parent?.name} <div className="text-xs text-ink-muted">{s.parent?.phone}</div></td>
                    <td className="td">
                      <button
                        className="btn-secondary text-xs"
                        onClick={(e) => { e.stopPropagation(); setCredsFor(s); }}
                        title="View / reset parent login"
                        data-testid={`parent-login-btn-${s.student_uid}`}
                      ><Key size={12}/> Show login</button>
                    </td>
                    <td className="td"><span className={s.status === "active" ? "badge-success" : "badge-neutral"}>{s.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
      </Section>

      <CreateStudentModal classes={classes} open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
      {credsFor && <ParentCredsModal student={credsFor} onClose={() => setCredsFor(null)} />}
    </div>
  );
}

function ParentCredsModal({ student, onClose }) {
  const [data, setData] = useState(null);
  const [tempPwd, setTempPwd] = useState(null); // only present right after a reset
  const [busy, setBusy] = useState(false);

  const fetchInfo = async () => {
    try {
      const { data } = await api.get(`/students/${student.id}/parent-login`);
      setData(data);
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };
  useEffect(() => { fetchInfo(); /* eslint-disable-next-line */ }, []);

  const reset = async () => {
    if (!window.confirm("Reset this parent's password to the default (Parent@123)? They'll need to use it on their next login.")) return;
    setBusy(true);
    try {
      const { data: r } = await api.post(`/students/${student.id}/parent-reset-password`);
      setTempPwd(r.default_password);
      toast.success(`Password reset. Share: ${r.email} / ${r.default_password}`);
      fetchInfo();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const copy = (txt) => {
    navigator.clipboard.writeText(txt).then(() => toast.success("Copied to clipboard"));
  };

  return (
    <Modal open onClose={onClose} title={`Parent login — ${student.name} (${student.student_uid})`} size="md" testId="parent-creds-modal">
      {!data ? <div className="py-8 text-center text-ink-muted">Loading…</div> : (
        <div className="space-y-4">
          <div className="p-3 bg-bg-subtle rounded-md border border-line/60">
            <div className="overline mb-1">Login email</div>
            <div className="flex items-center gap-2">
              <code className="text-sm font-mono flex-1 truncate" data-testid="parent-creds-email">{data.email || "—"}</code>
              {data.email && (
                <button type="button" className="btn-ghost p-1" onClick={() => copy(data.email)} title="Copy">
                  <Copy size={14}/>
                </button>
              )}
            </div>
            {data.phone && <div className="text-xs text-ink-muted mt-1">Phone on file: {data.phone}</div>}
          </div>

          <div className="text-sm text-ink-soft" data-testid="parent-creds-status">
            {data.last_login_at ? (
              <>✅ Parent has logged in (last login: {new Date(data.last_login_at).toLocaleString()}).
              {data.password_changed_at && <> Password was changed on {new Date(data.password_changed_at).toLocaleDateString()}.</>}</>
            ) : (
              <>⚠ Parent has <strong>not logged in yet</strong>. If they don't know the password, reset it to the default below.</>
            )}
          </div>

          {tempPwd && (
            <div className="border border-status-warning bg-status-warning-bg/40 rounded-md p-3" data-testid="parent-creds-temp-pwd">
              <div className="text-xs font-semibold text-status-warning mb-1">Share these credentials with the parent — they'll only be shown once</div>
              <div className="text-sm font-mono">
                <div>Email: <span className="font-bold">{data.email}</span></div>
                <div>Password: <span className="font-bold">{tempPwd}</span></div>
              </div>
              <button type="button" className="btn-secondary text-xs mt-2" onClick={() => copy(`${data.email} / ${tempPwd}`)}>
                <Copy size={12}/> Copy email + password
              </button>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-line">
            <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
            <button
              type="button"
              className="btn-primary"
              onClick={reset}
              disabled={busy}
              data-testid="parent-creds-reset-btn"
            >{busy ? "Resetting…" : "Reset to default password"}</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function CreateStudentModal({ classes, open, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
    parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" },
  });
  const [busy, setBusy] = useState(false);
  const [createdCreds, setCreatedCreds] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/students", form);
      toast.success("Student added");
      const pl = data.parent_login;
      if (pl && pl.is_new_account && pl.default_password) {
        setCreatedCreds({ email: pl.email, password: pl.default_password, student_name: data.name });
      } else {
        onCreated();
        setForm({ name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
          parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" } });
      }
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  const sections = classes.find((c) => c.id === form.class_id)?.sections || ["A"];

  const dismissCreds = () => {
    setCreatedCreds(null);
    onCreated();
    setForm({ name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
      parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" } });
  };

  if (createdCreds) {
    return (
      <Modal open onClose={dismissCreds} title="Parent login created" size="md" testId="parent-creds-just-created">
        <div className="space-y-4">
          <p className="text-sm text-ink-soft">
            Share these credentials with the parent of <strong>{createdCreds.student_name}</strong>. They can log in at this site to view marks, attendance and fees.
          </p>
          <div className="p-3 bg-bg-subtle rounded-md border border-line/60 font-mono text-sm space-y-1">
            <div>Login email: <strong data-testid="created-parent-email">{createdCreds.email}</strong></div>
            <div>Password: <strong data-testid="created-parent-password">{createdCreds.password}</strong></div>
          </div>
          <p className="text-xs text-ink-muted">
            ⓘ The password is the school default — parents can change it after first login from their profile.
          </p>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => {
              navigator.clipboard.writeText(`${createdCreds.email} / ${createdCreds.password}`);
              toast.success("Copied");
            }}><Copy size={14}/> Copy</button>
            <button className="btn-primary" onClick={dismissCreds} data-testid="dismiss-creds-btn">Done</button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open={open} onClose={onClose} title="Add student" size="lg" testId="create-student-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label className="label">Name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="new-student-name" /></div>
        <div><label className="label">Class</label>
          <select className="input" required value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value, section: classes.find(c => c.id === e.target.value)?.sections?.[0] || "A" })} data-testid="new-student-class">
            <option value="">Select class</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="label">Section</label>
          <select className="input" value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} data-testid="new-student-section">
            {sections.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="label">Roll number</label><input className="input" value={form.roll_number} onChange={(e) => setForm({ ...form, roll_number: e.target.value })} data-testid="new-student-roll" /></div>
        <div><label className="label">Gender</label>
          <select className="input" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
            <option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
          </select>
        </div>
        <div><label className="label">Date of birth</label><input className="input" type="date" value={form.dob} onChange={(e) => setForm({ ...form, dob: e.target.value })} /></div>
        <div className="md:col-span-2 pt-2 border-t border-line"><div className="overline">Parent / Guardian</div>
          <div className="text-xs text-ink-muted mt-0.5">A login account will be created automatically. You can copy the credentials right after saving.</div>
        </div>
        <div><label className="label">Parent name</label><input className="input" required value={form.parent.name} onChange={(e) => setForm({ ...form, parent: { ...form.parent, name: e.target.value } })} data-testid="new-parent-name" /></div>
        <div><label className="label">Relationship</label>
          <select className="input" value={form.parent.relationship} onChange={(e) => setForm({ ...form, parent: { ...form.parent, relationship: e.target.value } })}>
            <option>father</option><option>mother</option><option>guardian</option>
          </select>
        </div>
        <div><label className="label">Phone</label><input className="input" required value={form.parent.phone} onChange={(e) => setForm({ ...form, parent: { ...form.parent, phone: e.target.value } })} data-testid="new-parent-phone" /></div>
        <div><label className="label">WhatsApp</label><input className="input" value={form.parent.whatsapp} onChange={(e) => setForm({ ...form, parent: { ...form.parent, whatsapp: e.target.value } })} /></div>
        <div className="md:col-span-2"><label className="label">Email (optional — leave blank to auto-generate a login email)</label><input className="input" type="email" value={form.parent.email} onChange={(e) => setForm({ ...form, parent: { ...form.parent, email: e.target.value } })} data-testid="new-parent-email" /></div>
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-student-btn">{busy ? "Adding…" : "Add student"}</button>
        </div>
      </form>
    </Modal>
  );
}
