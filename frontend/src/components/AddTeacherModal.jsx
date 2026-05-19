import React, { useState } from "react";
import { api, formatApiError } from "../lib/api";
import toast from "react-hot-toast";

/**
 * Quick "Add Teacher" modal designed for the Timetable Builder.
 * Captures: name, email, password, phone, global subjects, and an optional
 * per-class subject matrix. The class_subjects matrix is OPTIONAL — leaving
 * it blank means the teacher can be assigned to ANY class for the subjects
 * in their global list. Setting it restricts them to only the (class, subject)
 * pairs that are checked.
 *
 * Calls onCreated(newTeacher) after successful create so the parent page can
 * refresh its teachers list.
 */
export default function AddTeacherModal({ open, onClose, onCreated, classes, subjects }) {
  const [form, setForm] = useState({
    name: "", email: "", password: "", phone: "", subjects: [],
  });
  const [classSubjects, setClassSubjects] = useState({}); // {class_id: Set(subject_ids)}
  const [submitting, setSubmitting] = useState(false);
  const [useMatrix, setUseMatrix] = useState(false);

  if (!open) return null;

  const toggleGlobalSubject = (sid) => {
    setForm((f) => ({
      ...f,
      subjects: f.subjects.includes(sid) ? f.subjects.filter((x) => x !== sid) : [...f.subjects, sid],
    }));
  };
  const toggleMatrixCell = (cid, sid) => {
    setClassSubjects((prev) => {
      const next = { ...prev };
      const set = new Set(next[cid] || []);
      if (set.has(sid)) set.delete(sid); else set.add(sid);
      next[cid] = Array.from(set);
      return next;
    });
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.password) {
      toast.error("Name, email and password are required");
      return;
    }
    if (form.subjects.length === 0 && !useMatrix) {
      toast.error("Pick at least one subject this teacher teaches");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name: form.name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        phone: form.phone.trim() || null,
        role: "teacher",
        subjects: form.subjects.length
          ? form.subjects
          // If only matrix is used, derive the union of subjects across classes
          : Array.from(new Set(Object.values(classSubjects).flat())),
      };
      if (useMatrix) {
        // Drop empty entries
        const cleaned = Object.fromEntries(
          Object.entries(classSubjects).filter(([, v]) => (v || []).length > 0),
        );
        if (Object.keys(cleaned).length > 0) payload.class_subjects = cleaned;
      }
      const { data } = await api.post("/users", payload);
      toast.success(`Added ${data.name}`);
      onCreated?.(data);
      onClose?.();
      // reset
      setForm({ name: "", email: "", password: "", phone: "", subjects: [] });
      setClassSubjects({});
      setUseMatrix(false);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      data-testid="add-teacher-modal"
    >
      <div
        className="bg-bg rounded-lg border border-line shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={submit} className="p-5 space-y-4">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-xl">Add a teacher</h2>
            <button type="button" onClick={onClose} className="text-ink-muted hover:text-ink-soft" data-testid="add-teacher-close">×</button>
          </div>
          <p className="text-xs text-ink-muted">
            Once added, the teacher can be used in the Timetable Builder immediately. They'll receive their login credentials via the email field below.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="label">Full name</label>
              <input className="input" value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Priya Verma" data-testid="add-teacher-name" />
            </div>
            <div>
              <label className="label">Email / login ID</label>
              <input className="input" value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="priya@school.edu" data-testid="add-teacher-email" />
              <div className="text-[10px] text-ink-muted mt-1">Used to log in. Lowercased automatically.</div>
            </div>
            <div>
              <label className="label">Temporary password</label>
              <input type="text" className="input" value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="Teacher@123" data-testid="add-teacher-password" />
              <div className="text-[10px] text-ink-muted mt-1">They'll be prompted to change it on first login.</div>
            </div>
            <div>
              <label className="label">Phone (optional)</label>
              <input className="input" value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+91 98765 43210" data-testid="add-teacher-phone" />
            </div>
          </div>

          <div>
            <label className="label">Subjects this teacher can teach</label>
            <div className="flex flex-wrap gap-2">
              {subjects.map((s) => {
                const on = form.subjects.includes(s.id);
                return (
                  <button key={s.id} type="button"
                    onClick={() => toggleGlobalSubject(s.id)}
                    data-testid={`add-teacher-subj-${s.id}`}
                    className={"px-3 py-1 rounded-md border text-xs " +
                      (on ? "bg-primary text-primary-foreground border-primary" : "border-line text-ink-soft hover:bg-bg-subtle")}>
                    {s.name}
                  </button>
                );
              })}
            </div>
            <div className="text-[11px] text-ink-muted mt-1">
              💡 Tick every subject they're qualified to teach. The Timetable Builder will assign them only to these subjects.
            </div>
          </div>

          <div className="border-t border-line pt-3">
            <label className="inline-flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={useMatrix} onChange={(e) => setUseMatrix(e.target.checked)}
                data-testid="add-teacher-matrix-toggle" />
              Restrict to specific grades (advanced)
            </label>
            <div className="text-[11px] text-ink-muted mt-1">
              {useMatrix
                ? "✏️ Tick the (grade × subject) cells this teacher is allowed to handle. If a cell is blank for a subject they teach globally, they'll still NOT be assigned to that grade. Leave a row entirely blank if the teacher doesn't teach that grade at all."
                : "Leave unchecked if this teacher can be assigned to any grade for the subjects above. Switch on to restrict by grade (e.g. ‘Priya teaches Math to Grade 5 only’)."}
            </div>
            {useMatrix && (
              <div className="overflow-x-auto mt-3">
                <table className="table text-xs" data-testid="add-teacher-matrix">
                  <thead>
                    <tr>
                      <th className="th">Grade</th>
                      {subjects.map((s) => <th key={s.id} className="th text-center">{s.name}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {classes.map((c) => (
                      <tr key={c.id} className="table-row" data-testid={`add-teacher-row-${c.id}`}>
                        <td className="td font-medium">{c.name}</td>
                        {subjects.map((s) => {
                          const on = (classSubjects[c.id] || []).includes(s.id);
                          return (
                            <td key={s.id} className="td text-center">
                              <input type="checkbox" checked={on}
                                onChange={() => toggleMatrixCell(c.id, s.id)}
                                data-testid={`add-teacher-cell-${c.id}-${s.id}`} />
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-line">
            <button type="button" onClick={onClose} className="btn-ghost" data-testid="add-teacher-cancel">Cancel</button>
            <button type="submit" disabled={submitting} className="btn-primary" data-testid="add-teacher-submit">
              {submitting ? "Adding…" : "Add teacher"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
