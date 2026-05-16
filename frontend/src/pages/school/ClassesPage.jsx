import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import toast from "react-hot-toast";
import { Plus, Trash, X, Users, Warning } from "@phosphor-icons/react";

export default function ClassesPage() {
  const { user } = useAuth();
  const canDelete = user?.role === "school_admin"; // only principal can delete
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [maps, setMaps] = useState([]);
  const [coverage, setCoverage] = useState(null);
  const [bulkSubject, setBulkSubject] = useState(null);
  const [newClass, setNewClass] = useState({ name: "", sections: "A,B" });
  const [newSub, setNewSub] = useState({ name: "", code: "" });
  const [assign, setAssign] = useState({ teacher_id: "", class_id: "", section: "" });
  const [addSec, setAddSec] = useState({ class_id: "", section: "" });

  const load = async () => {
    try {
      const [c, s, m] = await Promise.all([
        api.get("/academic/classes").then((r) => r.data),
        api.get("/academic/subjects").then((r) => r.data),
        api.get("/academic/class-teacher").then((r) => r.data),
      ]);
      setClasses(c); setSubjects(s); setMaps(m);
    } catch (err) { /* swallow */ }
    // teachers list + coverage matrix are school_admin-only (require listing all teachers)
    if (user?.role === "school_admin") {
      try {
        const t = await api.get("/users", { params: { role: "teacher" } }).then((r) => r.data);
        setTeachers(t);
      } catch (err) { /* swallow */ }
      try {
        const cov = await api.get("/academic/subjects/coverage").then((r) => r.data);
        setCoverage(cov);
      } catch (err) { /* swallow */ }
    }
  };
  useEffect(() => { load(); }, []);

  const addClass = async (e) => {
    e.preventDefault();
    try {
      await api.post("/academic/classes", {
        name: newClass.name,
        sections: newClass.sections.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean),
      });
      toast.success("Class added");
      setNewClass({ name: "", sections: "A,B" });
      load();
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
  const delClass = async (id) => {
    if (!window.confirm("Delete this class and all its sections?")) return;
    try { await api.delete(`/academic/classes/${id}`); toast.success("Class removed"); load(); }
    catch (err) { toast.error(formatApiError(err)); }
  };
  const delSubject = async (id) => {
    if (!window.confirm("Delete this subject?")) return;
    try { await api.delete(`/academic/subjects/${id}`); toast.success("Subject removed"); load(); }
    catch (err) { toast.error(formatApiError(err)); }
  };
  const addSection = async (e) => {
    e.preventDefault();
    if (!addSec.class_id || !addSec.section) return;
    try {
      await api.post(`/academic/classes/${addSec.class_id}/sections`, { section: addSec.section });
      toast.success(`Section '${addSec.section.toUpperCase()}' added`);
      setAddSec({ class_id: "", section: "" });
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const removeSection = async (classId, section) => {
    if (!window.confirm(`Remove section '${section}'?`)) return;
    try {
      await api.delete(`/academic/classes/${classId}/sections/${section}`);
      toast.success("Section removed");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const subtitle = canDelete
    ? "Configure the academic structure of your school."
    : "Add new classes, sections, and subjects. Removing items requires the school super admin.";

  return (
    <div data-testid="classes-page">
      <PageHeader
        eyebrow="Academic setup"
        title="Classes, sections & subjects"
        subtitle={subtitle}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Section
          title="Classes & sections"
          subtitle="Add classes — anyone (principal or teacher) can add. Only the principal can remove."
        >
          <form onSubmit={addClass} className="flex flex-wrap gap-2 mb-4">
            <input
              className="input flex-1 min-w-[160px]" placeholder="e.g. Grade 5"
              value={newClass.name}
              onChange={(e) => setNewClass({ ...newClass, name: e.target.value })}
              required
              data-testid="new-class-name"
            />
            <input
              className="input w-44" placeholder="Sections (A,B,C)"
              value={newClass.sections}
              onChange={(e) => setNewClass({ ...newClass, sections: e.target.value })}
            />
            <button className="btn-primary" data-testid="add-class-btn">
              <Plus size={16}/> Add class
            </button>
          </form>

          {/* Inline "add section to existing class" — both roles can use */}
          <form onSubmit={addSection} className="flex flex-wrap gap-2 mb-4 p-3 bg-bg-subtle rounded-md border border-line/60">
            <select
              className="input flex-1 min-w-[160px]" value={addSec.class_id}
              onChange={(e) => setAddSec({ ...addSec, class_id: e.target.value })}
              data-testid="add-section-class-select"
            >
              <option value="">Add section to class…</option>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} (current: {(c.sections || []).join(", ") || "—"})
                </option>
              ))}
            </select>
            <input
              className="input w-32 uppercase tracking-widest text-center"
              placeholder="New section"
              value={addSec.section}
              maxLength={6}
              onChange={(e) => setAddSec({ ...addSec, section: e.target.value })}
              data-testid="add-section-input"
            />
            <button
              className="btn-secondary"
              disabled={!addSec.class_id || !addSec.section}
              data-testid="add-section-submit"
            >
              <Plus size={14}/> Add section
            </button>
          </form>

          {classes.length === 0 ? <Empty title="No classes yet" /> :
            <ul className="divide-y divide-line">
              {classes.map((c) => (
                <li key={c.id} className="py-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between" data-testid={`class-row-${c.id}`}>
                  <div className="flex-1">
                    <div className="font-medium">{c.name}</div>
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {(c.sections || []).map((s) => (
                        <span
                          key={s}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-primary-light text-primary"
                          data-testid={`section-tag-${c.id}-${s}`}
                        >
                          {s}
                          {canDelete && (
                            <button
                              type="button"
                              className="text-status-danger hover:bg-status-danger/10 rounded-full p-0.5 -mr-1"
                              onClick={() => removeSection(c.id, s)}
                              aria-label={`Remove section ${s}`}
                              data-testid={`del-section-${c.id}-${s}`}
                            >
                              <X size={10} weight="bold" />
                            </button>
                          )}
                        </span>
                      ))}
                      {(c.sections || []).length === 0 && <span className="text-xs text-ink-muted">No sections</span>}
                    </div>
                  </div>
                  {canDelete && (
                    <button
                      className="btn-ghost p-1.5 text-status-danger self-start"
                      onClick={() => delClass(c.id)}
                      title="Delete class"
                      data-testid={`del-class-${c.id}`}
                    >
                      <Trash size={14}/>
                    </button>
                  )}
                </li>
              ))}
            </ul>}
        </Section>

        <Section title="Subjects" subtitle="Anyone can add subjects. Only the principal can remove.">
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
                  {canDelete && (
                    <button className="btn-ghost p-1.5 text-status-danger" onClick={() => delSubject(s.id)} data-testid={`del-subject-${s.id}`}>
                      <Trash size={14}/>
                    </button>
                  )}
                </li>
              ))}
            </ul>}
        </Section>
      </div>

      {canDelete && (
        <Section title="Class teacher assignment">
          <form onSubmit={submitAssign} className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-4">
            <select className="input" required value={assign.class_id} onChange={(e) => setAssign({ ...assign, class_id: e.target.value, section: "" })} data-testid="assign-class">
              <option value="">Class…</option>
              {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select className="input" required value={assign.section} onChange={(e) => setAssign({ ...assign, section: e.target.value })} disabled={!assign.class_id} data-testid="assign-section">
              <option value="">Section…</option>
              {(classes.find((c) => c.id === assign.class_id)?.sections || []).map((s) => <option key={s} value={s}>{s}</option>)}
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
      )}

      {canDelete && (
        <div className="mt-6">
          <CoverageMatrix
            coverage={coverage}
            onBulkAssign={(subj) => setBulkSubject(subj)}
            onQuickRemove={async (subj, teacher) => {
              if (!window.confirm(`Remove "${subj.subject_name}" from ${teacher.name}?`)) return;
              try {
                await api.post(`/academic/subjects/${subj.subject_id}/unassign-teacher/${teacher.id}`);
                toast.success(`Removed ${subj.subject_name} from ${teacher.name}`);
                load();
              } catch (err) { toast.error(formatApiError(err)); }
            }}
          />
        </div>
      )}

      {bulkSubject && (
        <BulkAssignModal
          subject={bulkSubject}
          teachers={teachers}
          onClose={() => setBulkSubject(null)}
          onDone={() => { setBulkSubject(null); load(); }}
        />
      )}
    </div>
  );
}

function CoverageMatrix({ coverage, onBulkAssign, onQuickRemove }) {
  if (!coverage) return null;
  const rows = coverage.subjects || [];
  return (
    <Section
      title="Subject ⇄ teacher coverage"
      subtitle={`${rows.length} subjects · ${coverage.total_teachers} active teachers · ${coverage.orphan_count} orphan subject(s) with no teacher assigned.`}
    >
      {rows.length === 0 ? <Empty title="No subjects defined yet" /> : (
        <div className="overflow-x-auto" data-testid="coverage-matrix">
          <table className="table">
            <thead>
              <tr>
                <th className="th">Subject</th>
                <th className="th">Code</th>
                <th className="th">Teachers</th>
                <th className="th text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isOrphan = r.teacher_count === 0;
                return (
                  <tr key={r.subject_id} className="table-row" data-testid={`coverage-row-${r.subject_id}`}>
                    <td className="td">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{r.subject_name}</span>
                        {isOrphan && (
                          <span className="badge-warning inline-flex items-center gap-1" data-testid={`orphan-${r.subject_id}`}>
                            <Warning size={12} weight="fill" /> Orphan
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="td text-xs text-ink-muted">{r.code || "—"}</td>
                    <td className="td">
                      {isOrphan ? (
                        <span className="text-xs text-status-warning">No teacher assigned</span>
                      ) : (
                        <div className="flex flex-wrap gap-1.5" data-testid={`coverage-teachers-${r.subject_id}`}>
                          {r.teachers.map((t) => (
                            <span key={t.id} className="badge-neutral inline-flex items-center gap-1" data-testid={`coverage-teacher-${r.subject_id}-${t.id}`}>
                              {t.name}
                              <button
                                type="button"
                                className="text-status-danger hover:bg-status-danger/10 rounded-full -mr-1"
                                onClick={() => onQuickRemove(r, t)}
                                title={`Unassign ${t.name}`}
                                data-testid={`coverage-remove-${r.subject_id}-${t.id}`}
                              >
                                <X size={10} weight="bold" />
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="td text-right">
                      <button
                        className="btn-secondary"
                        onClick={() => onBulkAssign(r)}
                        data-testid={`bulk-assign-btn-${r.subject_id}`}
                      >
                        <Users size={14}/> Bulk-assign teachers
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function BulkAssignModal({ subject, teachers, onClose, onDone }) {
  const initiallySelected = teachers
    .filter((t) => (t.subjects || []).includes(subject.subject_id))
    .map((t) => t.id);
  const [selected, setSelected] = useState(initiallySelected);
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");

  const toggle = (id) => setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  const selectAll = () => setSelected(filteredTeachers.map((t) => t.id));
  const clearAll = () => setSelected([]);

  const filteredTeachers = teachers.filter((t) => {
    if (!q.trim()) return true;
    const needle = q.toLowerCase();
    return t.name.toLowerCase().includes(needle) || (t.email || "").toLowerCase().includes(needle);
  });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post(`/academic/subjects/${subject.subject_id}/bulk-assign-teachers`, {
        teacher_ids: selected,
        replace,
      });
      const parts = [];
      if (data.added) parts.push(`${data.added} added`);
      if (data.removed) parts.push(`${data.removed} removed`);
      const summary = parts.length === 0 ? "no changes" : parts.join(", ");
      toast.success(`${subject.subject_name}: ${summary}`);
      onDone();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`Bulk-assign teachers to ${subject.subject_name}`} size="lg" testId="bulk-assign-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 justify-between">
          <input
            className="input flex-1 min-w-[200px]"
            placeholder="Search teachers by name or email…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="bulk-assign-search"
          />
          <div className="flex gap-2">
            <button type="button" className="btn-secondary" onClick={selectAll} data-testid="bulk-assign-select-all">Select all</button>
            <button type="button" className="btn-secondary" onClick={clearAll} data-testid="bulk-assign-clear-all">Clear</button>
          </div>
        </div>

        {teachers.length === 0 ? (
          <div className="text-sm text-ink-muted border border-dashed border-line rounded-md p-3" data-testid="bulk-assign-empty">
            No teachers in the school yet. Add teachers from the Staff page first.
          </div>
        ) : (
          <div className="max-h-72 overflow-y-auto border border-line rounded-md divide-y divide-line" data-testid="bulk-assign-list">
            {filteredTeachers.map((t) => {
              const isSelected = selected.includes(t.id);
              const wasAssigned = initiallySelected.includes(t.id);
              return (
                <label
                  key={t.id}
                  className="flex items-center gap-3 px-3 py-2 hover:bg-bg-subtle cursor-pointer"
                  data-testid={`bulk-assign-row-${t.id}`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggle(t.id)}
                    data-testid={`bulk-assign-check-${t.id}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{t.name}</div>
                    <div className="text-xs text-ink-muted truncate">{t.email}</div>
                  </div>
                  {wasAssigned && <span className="badge-neutral">Currently assigned</span>}
                </label>
              );
            })}
            {filteredTeachers.length === 0 && (
              <div className="px-3 py-4 text-center text-sm text-ink-muted">No teachers match your search.</div>
            )}
          </div>
        )}

        <label className="flex items-start gap-2 text-sm cursor-pointer" data-testid="bulk-assign-replace-wrap">
          <input
            type="checkbox"
            checked={replace}
            onChange={(e) => setReplace(e.target.checked)}
            data-testid="bulk-assign-replace"
            className="mt-0.5"
          />
          <span>
            <strong>Authoritative mode</strong> — also un-assign this subject from every teacher NOT in the selected list.
            <span className="block text-xs text-ink-muted">Use this when you want the selected teachers to be the only ones teaching {subject.subject_name}.</span>
          </span>
        </label>

        <div className="flex items-center justify-between text-xs text-ink-muted" data-testid="bulk-assign-summary">
          <span>Selected: <strong>{selected.length}</strong> of {teachers.length}</span>
          <span>Previously assigned: <strong>{initiallySelected.length}</strong></span>
        </div>

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="bulk-assign-submit">
            {busy ? "Saving…" : "Apply assignment"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
