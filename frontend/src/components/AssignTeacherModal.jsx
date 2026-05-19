import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../lib/api";
import toast from "react-hot-toast";
import { Link } from "react-router-dom";

/**
 * Reassign existing teachers to grades and subjects from inside the Timetable Builder.
 * This modal does NOT create new users — it only updates `class_subjects` (and optionally
 * the global subjects list) for teachers who already exist in the school. Onboarding a
 * brand-new teacher must be done via the Staff/Users page.
 *
 * Calls onSaved(updatedTeacher) so the parent page can refresh its teachers list.
 */
export default function AssignTeacherModal({ open, onClose, onSaved, classes, subjects, teachers }) {
  const [teacherId, setTeacherId] = useState("");
  const [classSubjects, setClassSubjects] = useState({}); // {class_id: [subject_id]}
  const [globalSubjects, setGlobalSubjects] = useState([]);
  const [restrictByGrade, setRestrictByGrade] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const selected = useMemo(() => teachers.find((t) => t.id === teacherId), [teachers, teacherId]);

  // Load the picked teacher's current mapping
  useEffect(() => {
    if (!selected) {
      setClassSubjects({});
      setGlobalSubjects([]);
      setRestrictByGrade(false);
      return;
    }
    setGlobalSubjects(selected.subjects || []);
    const cs = selected.class_subjects || {};
    const normalised = Object.fromEntries(
      Object.entries(cs).map(([k, v]) => [k, Array.isArray(v) ? v : []]),
    );
    setClassSubjects(normalised);
    setRestrictByGrade(Object.keys(normalised).length > 0);
  }, [selected]);

  if (!open) return null;

  const toggleGlobalSubject = (sid) => {
    setGlobalSubjects((arr) => (arr.includes(sid) ? arr.filter((x) => x !== sid) : [...arr, sid]));
  };
  const toggleMatrixCell = (cid, sid) => {
    setClassSubjects((prev) => {
      const set = new Set(prev[cid] || []);
      if (set.has(sid)) set.delete(sid); else set.add(sid);
      return { ...prev, [cid]: Array.from(set) };
    });
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!teacherId) {
      toast.error("Pick a teacher first");
      return;
    }
    if (globalSubjects.length === 0 && !restrictByGrade) {
      toast.error("Pick at least one subject (global) or enable grade restriction");
      return;
    }
    setSubmitting(true);
    try {
      const payload = { subjects: globalSubjects };
      if (restrictByGrade) {
        const cleaned = Object.fromEntries(
          Object.entries(classSubjects).filter(([, v]) => (v || []).length > 0),
        );
        payload.class_subjects = cleaned;
      } else {
        // Clearing the per-grade restriction
        payload.class_subjects = {};
      }
      const { data } = await api.patch(`/users/${teacherId}`, payload);
      toast.success(`Updated ${selected?.name || "teacher"}`);
      onSaved?.(data);
      onClose?.();
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
      data-testid="assign-teacher-modal"
    >
      <div
        className="bg-bg rounded-lg border border-line shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={submit} className="p-5 space-y-4">
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-xl">Assign teacher to grades & subjects</h2>
            <button type="button" onClick={onClose} className="text-ink-muted hover:text-ink-soft" data-testid="assign-teacher-close">×</button>
          </div>
          <div className="bg-status-info/10 border border-status-info/30 rounded-md px-3 py-2 text-xs text-ink-soft">
            ℹ️ This screen <strong>updates existing teachers</strong> (their subjects + which grades they teach).
            To onboard a brand-new teacher, please use the{" "}
            <Link to="/school/staff" className="text-status-info font-medium underline" onClick={onClose} data-testid="assign-teacher-link-staff">
              Staff &amp; Roles
            </Link>{" "}
            module — add them there first, then come back here to assign them to grades/subjects.
          </div>

          <div>
            <label className="label">Pick a teacher</label>
            <select className="input" value={teacherId} onChange={(e) => setTeacherId(e.target.value)}
              data-testid="assign-teacher-select">
              <option value="">— Choose existing teacher —</option>
              {teachers.map((t) => (
                <option key={t.id} value={t.id}>{t.name} — {(t.subjects || []).length} subject(s)</option>
              ))}
            </select>
            <div className="text-[10px] text-ink-muted mt-1">
              Only teachers who already have an account appear here. Want to add someone new?
              <Link to="/school/staff" className="text-status-info underline ml-1" onClick={onClose}>Go to Staff &amp; Roles →</Link>
            </div>
          </div>

          {selected && (
            <>
              <div>
                <label className="label">Subjects this teacher can teach (global)</label>
                <div className="flex flex-wrap gap-2">
                  {subjects.map((s) => {
                    const on = globalSubjects.includes(s.id);
                    return (
                      <button key={s.id} type="button"
                        onClick={() => toggleGlobalSubject(s.id)}
                        data-testid={`assign-teacher-subj-${s.id}`}
                        className={"px-3 py-1 rounded-md border text-xs " +
                          (on ? "bg-primary text-primary-foreground border-primary" : "border-line text-ink-soft hover:bg-bg-subtle")}>
                        {s.name}
                      </button>
                    );
                  })}
                </div>
                <div className="text-[11px] text-ink-muted mt-1">
                  💡 Tick every subject this teacher is qualified for. The auto-scheduler picks from this list when no per-grade restriction is set.
                </div>
              </div>

              <div className="border-t border-line pt-3">
                <label className="inline-flex items-center gap-2 text-sm font-medium">
                  <input type="checkbox" checked={restrictByGrade} onChange={(e) => setRestrictByGrade(e.target.checked)}
                    data-testid="assign-teacher-matrix-toggle" />
                  Restrict to specific grades (advanced)
                </label>
                <div className="text-[11px] text-ink-muted mt-1">
                  {restrictByGrade
                    ? "✏️ Tick the (grade × subject) cells this teacher is allowed to handle. Unticked rows mean the teacher will NOT be assigned to that grade. Useful when a teacher's subjects vary by grade."
                    : "Off = the teacher can teach the subjects above to any grade. Turn on to restrict per-grade (e.g. ‘Priya teaches Math to Grade 5 only, Science to Grade 6 only’)."}
                </div>
                {restrictByGrade && (
                  <div className="overflow-x-auto mt-3">
                    <table className="table text-xs" data-testid="assign-teacher-matrix">
                      <thead>
                        <tr>
                          <th className="th">Grade</th>
                          {subjects.map((s) => <th key={s.id} className="th text-center">{s.name}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {classes.map((c) => (
                          <tr key={c.id} className="table-row" data-testid={`assign-teacher-row-${c.id}`}>
                            <td className="td font-medium">{c.name}</td>
                            {subjects.map((s) => {
                              const on = (classSubjects[c.id] || []).includes(s.id);
                              return (
                                <td key={s.id} className="td text-center">
                                  <input type="checkbox" checked={on}
                                    onChange={() => toggleMatrixCell(c.id, s.id)}
                                    data-testid={`assign-teacher-cell-${c.id}-${s.id}`} />
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
            </>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-line">
            <button type="button" onClick={onClose} className="btn-ghost" data-testid="assign-teacher-cancel">Cancel</button>
            <button type="submit" disabled={submitting || !teacherId} className="btn-primary" data-testid="assign-teacher-submit">
              {submitting ? "Saving…" : "Save assignment"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
