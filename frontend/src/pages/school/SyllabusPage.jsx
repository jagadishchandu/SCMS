import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import toast from "react-hot-toast";
import { Plus } from "@phosphor-icons/react";

export default function SyllabusPage() {
  const [items, setItems] = useState([]);
  const [exams, setExams] = useState([]);
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [form, setForm] = useState({ exam_id: "", class_id: "", subject_id: "", title: "", content: "", version: 1 });

  const load = async () => {
    const [s, e, c, sb] = await Promise.all([
      api.get("/syllabus").then((r) => r.data),
      api.get("/exams").then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
      api.get("/academic/subjects").then((r) => r.data),
    ]);
    setItems(s); setExams(e); setClasses(c); setSubjects(sb);
  };
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    try {
      await api.post("/syllabus", form);
      toast.success("Syllabus published and parents notified");
      setForm({ exam_id: "", class_id: "", subject_id: "", title: "", content: "", version: 1 });
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <div data-testid="syllabus-page">
      <PageHeader eyebrow="Syllabus" title="Exam syllabus" subtitle="Upload and version syllabus per class, subject, and exam." />
      <Section title="Publish new syllabus">
        <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <select className="input" required value={form.exam_id} onChange={(e) => setForm({ ...form, exam_id: e.target.value })} data-testid="syllabus-exam">
            <option value="">Exam…</option>
            {exams.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
          <select className="input" required value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })} data-testid="syllabus-class">
            <option value="">Class…</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <select className="input" required value={form.subject_id} onChange={(e) => setForm({ ...form, subject_id: e.target.value })} data-testid="syllabus-subject">
            <option value="">Subject…</option>
            {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <div className="md:col-span-3"><label className="label">Title</label><input className="input" required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="syllabus-title" /></div>
          <div className="md:col-span-3"><label className="label">Content (text or topic list)</label>
            <textarea className="input min-h-[120px]" required value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} data-testid="syllabus-content" />
          </div>
          <div className="md:col-span-3 flex justify-end">
            <button className="btn-primary" data-testid="syllabus-publish-btn"><Plus size={16}/> Publish & notify parents</button>
          </div>
        </form>
      </Section>

      <div className="mt-6"><Section title={`${items.length} syllabus entries`}>
        {items.length === 0 ? <Empty title="Nothing published yet" /> :
          <ul className="divide-y divide-line">
            {items.map((s) => (
              <li key={s.id} className="py-4" data-testid={`syllabus-item-${s.id}`}>
                <div className="flex items-start justify-between gap-3 mb-1">
                  <div className="font-medium">{s.title}</div>
                  <span className="badge-neutral">v{s.version}</span>
                </div>
                <div className="text-xs text-ink-muted mb-2">
                  {classes.find(c => c.id === s.class_id)?.name} · {subjects.find(x => x.id === s.subject_id)?.name} · {exams.find(e => e.id === s.exam_id)?.name}
                </div>
                <div className="text-sm text-ink-soft whitespace-pre-wrap">{s.content}</div>
              </li>
            ))}
          </ul>}
      </Section></div>
    </div>
  );
}
