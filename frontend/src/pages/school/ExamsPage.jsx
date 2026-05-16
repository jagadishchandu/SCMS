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
  const [students, setStudents] = useState([]);
  // entries[student_id][subject_id] = string (raw input)
  const [entries, setEntries] = useState({});
  // subjectMax[subject_id] = number
  const [subjectMax, setSubjectMax] = useState(() => Object.fromEntries((subjects || []).map((s) => [s.id, 100])));
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!exam.class_id) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api.get("/students", { params: { class_id: exam.class_id, ...(exam.section ? { section: exam.section } : {}) } }).then((r) => r.data),
      api.get("/marks", { params: { exam_id: exam.id } }).then((r) => r.data),
    ]).then(([studentRows, marks]) => {
      if (cancelled) return;
      setStudents(studentRows);
      // Build entries + per-subject max from existing marks
      const ent = {};
      const maxes = { ...Object.fromEntries((subjects || []).map((s) => [s.id, 100])) };
      marks.forEach((m) => {
        ent[m.student_id] = ent[m.student_id] || {};
        ent[m.student_id][m.subject_id] = String(m.marks_obtained);
        if (m.max_marks) maxes[m.subject_id] = m.max_marks;
      });
      setEntries(ent);
      setSubjectMax(maxes);
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exam.id, exam.class_id, exam.section]);

  const setMark = (studentId, subjectId, value) => {
    setEntries((prev) => ({
      ...prev,
      [studentId]: { ...(prev[studentId] || {}), [subjectId]: value },
    }));
  };

  const setMax = (subjectId, value) => {
    const num = value === "" ? "" : Math.max(1, Number(value));
    setSubjectMax((prev) => ({ ...prev, [subjectId]: num }));
  };

  const save = async () => {
    // Validate: every non-empty mark must be <= its subject's max
    for (const s of subjects) {
      const mx = Number(subjectMax[s.id]);
      if (!mx || mx <= 0) { toast.error(`Set a valid 'Out of' for ${s.name}`); return; }
      for (const stu of students) {
        const v = entries[stu.id]?.[s.id];
        if (v === undefined || v === null || v === "") continue;
        const num = Number(v);
        if (Number.isNaN(num) || num < 0 || num > mx) {
          toast.error(`${stu.name} · ${s.name}: marks must be between 0 and ${mx}`);
          return;
        }
      }
    }
    setBusy(true);
    let totalSaved = 0;
    try {
      // One request per subject (reuses existing /marks/bulk endpoint)
      for (const s of subjects) {
        const subjectEntries = students
          .map((stu) => ({ stu, v: entries[stu.id]?.[s.id] }))
          .filter(({ v }) => v !== undefined && v !== null && v !== "")
          .map(({ stu, v }) => ({
            student_id: stu.id,
            marks_obtained: Number(v),
            max_marks: Number(subjectMax[s.id]),
          }));
        if (subjectEntries.length === 0) continue;
        const { data } = await api.post("/marks/bulk", {
          exam_id: exam.id,
          subject_id: s.id,
          entries: subjectEntries,
        });
        totalSaved += data?.saved || 0;
      }
      toast.success(`Saved ${totalSaved} mark${totalSaved === 1 ? "" : "s"} across ${subjects.length} subject${subjects.length === 1 ? "" : "s"}`);
      onClose();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  if (subjects.length === 0) {
    return (
      <Modal open={!!exam} onClose={onClose} title={`Marks — ${exam.name}`} size="xl" testId="marks-entry-modal">
        <Empty title="No subjects defined" message="Add subjects from the Academic → Classes page before entering marks." />
      </Modal>
    );
  }

  return (
    <Modal open={!!exam} onClose={onClose} title={`Marks — ${exam.name}`} size="xl" testId="marks-entry-modal">
      <div className="text-xs text-ink-muted mb-3">
        Enter marks for every subject in one grid. The <strong>Out of</strong> input in each column header is editable — each subject can have its own maximum. Leave a cell blank to skip a student for that subject.
      </div>
      {loading ? (
        <div className="text-ink-muted text-sm py-6 text-center">Loading marks…</div>
      ) : (
        <div className="border border-line rounded-md overflow-x-auto max-h-[60vh] overflow-y-auto" data-testid="marks-grid-wrap">
          <table className="table min-w-max">
            <thead className="sticky top-0 bg-bg-surface z-10">
              <tr>
                <th className="th sticky left-0 bg-bg-surface z-20" style={{ minWidth: 60 }}>Roll</th>
                <th className="th sticky left-[60px] bg-bg-surface z-20" style={{ minWidth: 90 }}>UID</th>
                <th className="th sticky left-[150px] bg-bg-surface z-20" style={{ minWidth: 160 }}>Student</th>
                {subjects.map((s) => (
                  <th key={s.id} className="th align-bottom" style={{ minWidth: 130 }} data-testid={`marks-col-${s.id}`}>
                    <div className="font-semibold text-ink mb-1">{s.name}</div>
                    <div className="flex items-center gap-1.5 normal-case tracking-normal font-normal">
                      <span className="text-[10px] text-ink-muted uppercase tracking-wider">Out of</span>
                      <input
                        className="input h-7 w-16 text-xs px-2"
                        type="number"
                        min="1"
                        value={subjectMax[s.id] ?? ""}
                        onChange={(e) => setMax(s.id, e.target.value)}
                        data-testid={`marks-max-${s.id}`}
                      />
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {students.map((stu) => (
                <tr key={stu.id} className="table-row" data-testid={`marks-row-${stu.student_uid}`}>
                  <td className="td sticky left-0 bg-bg-surface">{stu.roll_number}</td>
                  <td className="td sticky left-[60px] bg-bg-surface font-mono text-xs">{stu.student_uid}</td>
                  <td className="td sticky left-[150px] bg-bg-surface">{stu.name}</td>
                  {subjects.map((s) => {
                    const mx = Number(subjectMax[s.id]) || 100;
                    const val = entries[stu.id]?.[s.id] ?? "";
                    const over = val !== "" && Number(val) > mx;
                    return (
                      <td className="td" key={s.id}>
                        <input
                          className={`input w-24 ${over ? "border-status-danger text-status-danger" : ""}`}
                          type="number"
                          min="0"
                          max={mx}
                          step="0.5"
                          placeholder={`/${mx}`}
                          value={val}
                          onChange={(e) => setMark(stu.id, s.id, e.target.value)}
                          data-testid={`marks-input-${stu.student_uid}-${s.id}`}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
              {students.length === 0 && (
                <tr>
                  <td className="td text-ink-muted" colSpan={3 + subjects.length}>
                    No students in this class/section.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <div className="flex justify-end gap-2 mt-4">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" onClick={save} disabled={busy || loading} data-testid="save-marks-btn">{busy ? "Saving…" : "Save all marks"}</button>
      </div>
    </Modal>
  );
}
