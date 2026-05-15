import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, PaperPlaneTilt } from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { formatDate } from "../../lib/utils";

export default function ExamsPage() {
  const [exams, setExams] = useState([]);
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [open, setOpen] = useState(false);
  const [marksFor, setMarksFor] = useState(null);

  const load = async () => {
    const [e, c, s] = await Promise.all([
      api.get("/exams").then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
      api.get("/academic/subjects").then((r) => r.data),
    ]);
    setExams(e); setClasses(c); setSubjects(s);
  };
  useEffect(() => { load(); }, []);

  const publish = async (id) => {
    try {
      const { data } = await api.post(`/exams/${id}/publish`);
      toast.success(`Published · ${data.notified_students} parents notified`);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <div data-testid="exams-page">
      <PageHeader eyebrow="Exams & Marks" title="Exam schedule and results"
        subtitle="Create exam schedules, publish to parents, and enter marks per subject."
        actions={<button className="btn-primary" onClick={() => setOpen(true)} data-testid="new-exam-btn"><Plus size={16}/> New exam</button>}
      />

      <Section title={`${exams.length} exams`}>
        {exams.length === 0 ? <Empty title="No exams yet" /> :
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {exams.map((e) => (
              <div key={e.id} className="border border-line rounded-lg p-5" data-testid={`exam-card-${e.id}`}>
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <div className="font-display text-lg font-medium">{e.name}</div>
                    <div className="text-xs text-ink-muted">{e.term} · {classes.find(c => c.id === e.class_id)?.name || e.class_id}</div>
                  </div>
                  {e.is_published ? <span className="badge-success">Published</span> : <span className="badge-warning">Draft</span>}
                </div>
                <div className="text-sm text-ink-soft mb-3">{formatDate(e.start_date)} → {formatDate(e.end_date)}</div>
                <div className="flex gap-2">
                  {!e.is_published && <button className="btn-secondary" onClick={() => publish(e.id)} data-testid={`publish-exam-${e.id}`}><PaperPlaneTilt size={14}/> Publish</button>}
                  <button className="btn-primary" onClick={() => setMarksFor(e)} data-testid={`enter-marks-${e.id}`}>Enter marks</button>
                </div>
              </div>
            ))}
          </div>}
      </Section>

      <CreateExamModal classes={classes} subjects={subjects} open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
      {marksFor && (
        <MarksEntryModal exam={marksFor} subjects={subjects} onClose={() => setMarksFor(null)} />
      )}
    </div>
  );
}

function CreateExamModal({ classes, subjects, open, onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", term: "Term 1", class_id: "", section: "", start_date: "", end_date: "", schedule: [] });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/exams", form);
      toast.success("Exam created");
      onCreated();
      setForm({ name: "", term: "Term 1", class_id: "", section: "", start_date: "", end_date: "", schedule: [] });
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="New exam" size="lg" testId="new-exam-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label className="label">Name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="exam-name" /></div>
        <div><label className="label">Term</label><input className="input" value={form.term} onChange={(e) => setForm({ ...form, term: e.target.value })} /></div>
        <div><label className="label">Class</label>
          <select className="input" required value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })} data-testid="exam-class">
            <option value="">Select class</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="label">Section (optional)</label><input className="input" value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} /></div>
        <div><label className="label">Start date</label><input className="input" type="date" required value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></div>
        <div><label className="label">End date</label><input className="input" type="date" required value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></div>
        <div className="md:col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-exam-btn">{busy ? "Creating…" : "Create"}</button>
        </div>
      </form>
    </Modal>
  );
}

function MarksEntryModal({ exam, subjects, onClose }) {
  const [subjectId, setSubjectId] = useState(subjects[0]?.id || "");
  const [students, setStudents] = useState([]);
  const [entries, setEntries] = useState({});
  const [max, setMax] = useState(100);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!exam.class_id) return;
    api.get("/students", { params: { class_id: exam.class_id, ...(exam.section ? { section: exam.section } : {}) } })
      .then((r) => setStudents(r.data));
  }, [exam]);

  useEffect(() => {
    if (!subjectId) return;
    api.get("/marks", { params: { exam_id: exam.id } }).then((r) => {
      const cur = r.data.filter((m) => m.subject_id === subjectId);
      setEntries(Object.fromEntries(cur.map((m) => [m.student_id, m.marks_obtained])));
      if (cur.length) setMax(cur[0].max_marks);
    });
  }, [subjectId, exam.id]);

  const save = async () => {
    setBusy(true);
    try {
      const payload = {
        exam_id: exam.id, subject_id: subjectId,
        entries: Object.entries(entries).filter(([, v]) => v !== "" && v != null)
          .map(([student_id, v]) => ({ student_id, marks_obtained: Number(v), max_marks: Number(max) })),
      };
      const { data } = await api.post("/marks/bulk", payload);
      toast.success(`Saved ${data.saved} marks`);
      onClose();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={!!exam} onClose={onClose} title={`Marks — ${exam.name}`} size="lg" testId="marks-entry-modal">
      <div className="flex flex-wrap gap-3 mb-4">
        <select className="input w-56" value={subjectId} onChange={(e) => setSubjectId(e.target.value)} data-testid="marks-subject">
          {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-widest font-semibold text-ink-soft">Max marks</span>
          <input className="input w-24" type="number" value={max} onChange={(e) => setMax(e.target.value)} />
        </div>
      </div>
      <table className="table">
        <thead><tr><th className="th">Roll</th><th className="th">UID</th><th className="th">Student</th><th className="th">Marks</th></tr></thead>
        <tbody>
          {students.map((s) => (
            <tr key={s.id} className="table-row">
              <td className="td">{s.roll_number}</td>
              <td className="td font-mono text-xs">{s.student_uid}</td>
              <td className="td">{s.name}</td>
              <td className="td">
                <input className="input w-24" type="number" min="0" max={max}
                  value={entries[s.id] ?? ""} onChange={(e) => setEntries({ ...entries, [s.id]: e.target.value })}
                  data-testid={`marks-input-${s.student_uid}`}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex justify-end gap-2 mt-4">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={save} disabled={busy} data-testid="save-marks-btn">{busy ? "Saving…" : "Save marks"}</button>
      </div>
    </Modal>
  );
}
