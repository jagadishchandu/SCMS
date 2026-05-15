import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, MagnifyingGlass } from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";

export default function StudentsPage() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [filter, setFilter] = useState({ class_id: "", section: "", q: "" });
  const [open, setOpen] = useState(false);
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
                <th className="th">Section</th><th className="th">Roll</th><th className="th">Parent</th><th className="th">Status</th>
              </tr></thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id} className="table-row cursor-pointer" onClick={() => navigate(`/student/${s.student_uid}`)} data-testid={`student-row-${s.student_uid}`}>
                    <td className="td font-mono text-xs">{s.student_uid}</td>
                    <td className="td font-medium">{s.name}</td>
                    <td className="td">{classes.find((c) => c.id === s.class_id)?.name || s.class_id}</td>
                    <td className="td">{s.section}</td>
                    <td className="td">{s.roll_number || "—"}</td>
                    <td className="td">{s.parent?.name} <div className="text-xs text-ink-muted">{s.parent?.phone}</div></td>
                    <td className="td"><span className={s.status === "active" ? "badge-success" : "badge-neutral"}>{s.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
      </Section>

      <CreateStudentModal classes={classes} open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
    </div>
  );
}

function CreateStudentModal({ classes, open, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
    parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" },
  });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/students", form);
      toast.success("Student added");
      onCreated();
      setForm({ name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
        parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" } });
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  const sections = classes.find((c) => c.id === form.class_id)?.sections || ["A"];
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
          <select className="input" value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })}>
            {sections.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="label">Roll number</label><input className="input" value={form.roll_number} onChange={(e) => setForm({ ...form, roll_number: e.target.value })} /></div>
        <div><label className="label">Gender</label>
          <select className="input" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
            <option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
          </select>
        </div>
        <div><label className="label">Date of birth</label><input className="input" type="date" value={form.dob} onChange={(e) => setForm({ ...form, dob: e.target.value })} /></div>
        <div className="md:col-span-2 pt-2 border-t border-line"><div className="overline">Parent / Guardian</div></div>
        <div><label className="label">Parent name</label><input className="input" required value={form.parent.name} onChange={(e) => setForm({ ...form, parent: { ...form.parent, name: e.target.value } })} data-testid="new-parent-name" /></div>
        <div><label className="label">Relationship</label>
          <select className="input" value={form.parent.relationship} onChange={(e) => setForm({ ...form, parent: { ...form.parent, relationship: e.target.value } })}>
            <option>father</option><option>mother</option><option>guardian</option>
          </select>
        </div>
        <div><label className="label">Phone</label><input className="input" required value={form.parent.phone} onChange={(e) => setForm({ ...form, parent: { ...form.parent, phone: e.target.value } })} data-testid="new-parent-phone" /></div>
        <div><label className="label">WhatsApp</label><input className="input" value={form.parent.whatsapp} onChange={(e) => setForm({ ...form, parent: { ...form.parent, whatsapp: e.target.value } })} /></div>
        <div className="md:col-span-2"><label className="label">Email (optional)</label><input className="input" type="email" value={form.parent.email} onChange={(e) => setForm({ ...form, parent: { ...form.parent, email: e.target.value } })} /></div>
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-student-btn">{busy ? "Adding…" : "Add student"}</button>
        </div>
      </form>
    </Modal>
  );
}
