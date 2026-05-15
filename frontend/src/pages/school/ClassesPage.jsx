import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import toast from "react-hot-toast";
import { Plus, Trash } from "@phosphor-icons/react";

export default function ClassesPage() {
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [maps, setMaps] = useState([]);
  const [newClass, setNewClass] = useState({ name: "", sections: "A,B" });
  const [newSub, setNewSub] = useState({ name: "", code: "" });
  const [assign, setAssign] = useState({ teacher_id: "", class_id: "", section: "" });

  const load = async () => {
    const [c, s, t, m] = await Promise.all([
      api.get("/academic/classes").then((r) => r.data),
      api.get("/academic/subjects").then((r) => r.data),
      api.get("/users", { params: { role: "teacher" } }).then((r) => r.data),
      api.get("/academic/class-teacher").then((r) => r.data),
    ]);
    setClasses(c); setSubjects(s); setTeachers(t); setMaps(m);
  };
  useEffect(() => { load(); }, []);

  const addClass = async (e) => {
    e.preventDefault();
    try {
      await api.post("/academic/classes", { name: newClass.name, sections: newClass.sections.split(",").map((s) => s.trim()).filter(Boolean) });
      toast.success("Class added"); setNewClass({ name: "", sections: "A,B" }); load();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const addSubject = async (e) => {
    e.preventDefault();
    try {
      await api.post("/academic/subjects", newSub);
      toast.success("Subject added"); setNewSub({ name: "", code: "" }); load();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const submitAssign = async (e) => {
    e.preventDefault();
    try {
      await api.post("/academic/class-teacher", assign);
      toast.success("Class teacher assigned"); load();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const delClass = async (id) => { await api.delete(`/academic/classes/${id}`); load(); };
  const delSubject = async (id) => { await api.delete(`/academic/subjects/${id}`); load(); };

  const sections = classes.find((c) => c.id === assign.class_id)?.sections || [];

  return (
    <div data-testid="classes-page">
      <PageHeader eyebrow="Academic setup" title="Classes, sections & subjects" subtitle="Configure the academic structure of your school." />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Section title="Classes & sections">
          <form onSubmit={addClass} className="flex gap-2 mb-4">
            <input className="input flex-1" placeholder="e.g. Grade 5" value={newClass.name} onChange={(e) => setNewClass({ ...newClass, name: e.target.value })} required data-testid="new-class-name" />
            <input className="input w-44" placeholder="Sections (A,B,C)" value={newClass.sections} onChange={(e) => setNewClass({ ...newClass, sections: e.target.value })} />
            <button className="btn-primary" data-testid="add-class-btn"><Plus size={16}/> Add</button>
          </form>
          {classes.length === 0 ? <Empty title="No classes yet" /> :
            <ul className="divide-y divide-line">
              {classes.map((c) => (
                <li key={c.id} className="py-3 flex items-center justify-between">
                  <div>
                    <div className="font-medium">{c.name}</div>
                    <div className="text-xs text-ink-muted">Sections: {c.sections.join(", ")}</div>
                  </div>
                  <button className="btn-ghost p-1.5 text-status-danger" onClick={() => delClass(c.id)} data-testid={`del-class-${c.id}`}><Trash size={14}/></button>
                </li>
              ))}
            </ul>}
        </Section>

        <Section title="Subjects">
          <form onSubmit={addSubject} className="flex gap-2 mb-4">
            <input className="input flex-1" placeholder="Subject name" value={newSub.name} onChange={(e) => setNewSub({ ...newSub, name: e.target.value })} required data-testid="new-subject-name" />
            <input className="input w-24" placeholder="Code" value={newSub.code} onChange={(e) => setNewSub({ ...newSub, code: e.target.value })} />
            <button className="btn-primary" data-testid="add-subject-btn"><Plus size={16}/> Add</button>
          </form>
          {subjects.length === 0 ? <Empty title="No subjects" /> :
            <ul className="divide-y divide-line">
              {subjects.map((s) => (
                <li key={s.id} className="py-3 flex items-center justify-between">
                  <div><div className="font-medium">{s.name}</div><div className="text-xs text-ink-muted">{s.code || ""}</div></div>
                  <button className="btn-ghost p-1.5 text-status-danger" onClick={() => delSubject(s.id)} data-testid={`del-subject-${s.id}`}><Trash size={14}/></button>
                </li>
              ))}
            </ul>}
        </Section>
      </div>

      <Section title="Class teacher assignment">
        <form onSubmit={submitAssign} className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
          <select className="input" required value={assign.class_id} onChange={(e) => setAssign({ ...assign, class_id: e.target.value, section: "" })} data-testid="assign-class">
            <option value="">Class…</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="input" required value={assign.section} onChange={(e) => setAssign({ ...assign, section: e.target.value })} disabled={!assign.class_id} data-testid="assign-section">
            <option value="">Section…</option>
            {sections.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="input" required value={assign.teacher_id} onChange={(e) => setAssign({ ...assign, teacher_id: e.target.value })} data-testid="assign-teacher">
            <option value="">Teacher…</option>
            {teachers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <button className="btn-primary" data-testid="submit-assign-btn"><Plus size={16}/> Assign</button>
        </form>
        {maps.length === 0 ? <Empty title="No class teachers assigned" /> :
          <ul className="divide-y divide-line">
            {maps.map((m) => {
              const cls = classes.find((c) => c.id === m.class_id);
              const t = teachers.find((x) => x.id === m.teacher_id);
              return (
                <li key={m.id} className="py-3 flex items-center justify-between">
                  <div className="font-medium">{cls?.name || m.class_id} · Section {m.section}</div>
                  <div className="text-sm text-ink-soft">{t?.name || "(unknown)"}</div>
                </li>
              );
            })}
          </ul>}
      </Section>
    </div>
  );
}
