import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { formatDate } from "../../lib/utils";
import { Plus, Trash, Pencil, Calendar, Users } from "@phosphor-icons/react";
import { useAuth } from "../../contexts/AuthContext";
import toast from "react-hot-toast";

const TYPES = [
  ["meeting", "Meeting"],
  ["duty", "Duty"],
  ["parent_teacher", "Parent-teacher"],
  ["training", "Training"],
  ["exam_supervision", "Exam supervision"],
  ["event", "Event"],
  ["other", "Other"],
];

const TYPE_BADGE = {
  meeting: "badge-primary",
  duty: "badge-warning",
  parent_teacher: "badge-success",
  training: "badge-primary",
  exam_supervision: "badge-danger",
  event: "badge-success",
  other: "badge-neutral",
};

function formatDateTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

export default function TeacherDutiesPage({ readOnly = false }) {
  const { user } = useAuth();
  const isTeacherView = readOnly || user?.role === "teacher";
  const [duties, setDuties] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [filterTeacher, setFilterTeacher] = useState("");
  const [modalOpen, setModalOpen] = useState(false);

  const load = async () => {
    const params = new URLSearchParams();
    if (filterTeacher && !isTeacherView) params.append("teacher_id", filterTeacher);
    const r = await api.get(`/teacher-duties?${params.toString()}`);
    setDuties(r.data || []);
  };

  useEffect(() => {
    if (!isTeacherView) {
      api.get("/users?role=teacher").then((r) => setTeachers(r.data || []));
    }
    load();
    // eslint-disable-next-line
  }, [filterTeacher]);

  const remove = async (d) => {
    if (!window.confirm(`Delete "${d.title}"?`)) return;
    try {
      await api.delete(`/teacher-duties/${d.id}`);
      toast.success("Duty deleted");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const now = new Date();
  const upcoming = useMemo(() => duties.filter((d) => new Date(d.start_at) >= new Date(now.getTime() - 60 * 60 * 1000)), [duties]);
  const past = useMemo(() => duties.filter((d) => new Date(d.start_at) < new Date(now.getTime() - 60 * 60 * 1000)), [duties]);

  return (
    <div data-testid="teacher-duties-page">
      <PageHeader
        eyebrow={isTeacherView ? "My schedule" : "HR — Teacher schedule"}
        title={isTeacherView ? "My duties & events" : "Teacher schedule"}
        subtitle={isTeacherView
          ? "Meetings, duties, parent-teacher conferences and other events assigned to you."
          : "Assign meetings, duties, parent-teacher conferences, training, and exam supervision to teachers."}
        actions={!isTeacherView && (
          <button className="btn-primary" onClick={() => setModalOpen(true)} data-testid="add-duty-btn">
            <Plus size={16} /> Assign duty
          </button>
        )}
      />

      {!isTeacherView && (
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <select className="input max-w-[260px]" value={filterTeacher} onChange={(e) => setFilterTeacher(e.target.value)} data-testid="duty-teacher-filter">
            <option value="">All teachers</option>
            {teachers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <div className="text-xs text-ink-muted ml-auto">{duties.length} entr{duties.length === 1 ? "y" : "ies"}</div>
        </div>
      )}

      <DutiesTable title="Upcoming" duties={upcoming} isTeacherView={isTeacherView} onDelete={remove} />
      <DutiesTable title="Past" duties={past} isTeacherView={isTeacherView} onDelete={remove} />

      <DutyModal open={modalOpen} onClose={() => setModalOpen(false)} teachers={teachers} onSaved={load} />
    </div>
  );
}

function DutiesTable({ title, duties, isTeacherView, onDelete }) {
  if (duties.length === 0 && title === "Past") return null;
  return (
    <Section title={title}>
      {duties.length === 0 ? (
        <Empty title={`No ${title.toLowerCase()} duties`} message={title === "Upcoming" ? "Nothing scheduled yet." : "Past entries will appear here."} />
      ) : (
        <div className="overflow-x-auto">
          <table className="table">
            <thead><tr>
              <th className="th">Title</th>
              <th className="th">Type</th>
              {!isTeacherView && <th className="th">Teacher</th>}
              <th className="th">Starts</th>
              <th className="th">Ends</th>
              <th className="th">Location</th>
              <th className="th">Notes</th>
              {!isTeacherView && <th className="th">Actions</th>}
            </tr></thead>
            <tbody>
              {duties.map((d) => (
                <tr key={d.id} className="table-row" data-testid={`duty-row-${d.id}`}>
                  <td className="td font-medium">{d.title}</td>
                  <td className="td">
                    <span className={TYPE_BADGE[d.type] || "badge-neutral"}>
                      {(TYPES.find(([k]) => k === d.type)?.[1]) || d.type}
                    </span>
                  </td>
                  {!isTeacherView && <td className="td text-xs">{d.teacher_name}</td>}
                  <td className="td text-xs whitespace-nowrap">{formatDateTime(d.start_at)}</td>
                  <td className="td text-xs whitespace-nowrap">{d.end_at ? formatDateTime(d.end_at) : "—"}</td>
                  <td className="td text-xs">{d.location || "—"}</td>
                  <td className="td text-xs text-ink-muted italic">{d.notes || "—"}</td>
                  {!isTeacherView && (
                    <td className="td">
                      <button className="btn-secondary text-xs text-status-danger" onClick={() => onDelete(d)} data-testid={`delete-duty-${d.id}`}>
                        <Trash size={14} /> Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function DutyModal({ open, onClose, teachers, onSaved }) {
  const empty = { teacher_ids: [], title: "", type: "duty", start_at: "", end_at: "", location: "", notes: "", notify: true };
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) setForm(empty); /* eslint-disable-next-line */ }, [open]);

  const toggleTeacher = (id) => {
    setForm((f) => ({
      ...f,
      teacher_ids: f.teacher_ids.includes(id) ? f.teacher_ids.filter((x) => x !== id) : [...f.teacher_ids, id],
    }));
  };

  const save = async (e) => {
    e.preventDefault();
    if (form.teacher_ids.length === 0) { toast.error("Pick at least one teacher"); return; }
    if (!form.title || !form.start_at) { toast.error("Title and start date/time are required"); return; }
    setBusy(true);
    try {
      await api.post("/teacher-duties", {
        ...form,
        start_at: new Date(form.start_at).toISOString(),
        end_at: form.end_at ? new Date(form.end_at).toISOString() : null,
        location: form.location || null,
        notes: form.notes || null,
      });
      toast.success(`Assigned to ${form.teacher_ids.length} teacher${form.teacher_ids.length === 1 ? "" : "s"}`);
      onSaved();
      onClose();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="Assign teacher duty" icon={Calendar}>
      <form onSubmit={save} className="space-y-3" data-testid="duty-form">
        <div>
          <label className="label">Title *</label>
          <input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required data-testid="duty-title" />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Type</label>
            <select className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} data-testid="duty-type">
              {TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Location</label>
            <input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="e.g. Staff room" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Start *</label>
            <input type="datetime-local" className="input" value={form.start_at} onChange={(e) => setForm({ ...form, start_at: e.target.value })} required data-testid="duty-start" />
          </div>
          <div>
            <label className="label">End</label>
            <input type="datetime-local" className="input" value={form.end_at} onChange={(e) => setForm({ ...form, end_at: e.target.value })} />
          </div>
        </div>
        <div>
          <label className="label">Notes</label>
          <textarea className="input" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div>
          <label className="label flex items-center gap-2"><Users size={14} /> Assign to teacher(s) * <span className="text-xs text-ink-muted">({form.teacher_ids.length} selected)</span></label>
          <div className="max-h-44 overflow-y-auto border border-line rounded-md p-2 grid grid-cols-1 sm:grid-cols-2 gap-1" data-testid="duty-teacher-list">
            {teachers.length === 0 && <div className="text-xs text-ink-muted col-span-full p-2">No teachers found.</div>}
            {teachers.map((t) => (
              <label key={t.id} className="flex items-center gap-2 text-sm py-1 px-2 rounded hover:bg-line/30 cursor-pointer">
                <input type="checkbox" checked={form.teacher_ids.includes(t.id)} onChange={() => toggleTeacher(t.id)} data-testid={`duty-teacher-${t.id}`} />
                <span>{t.name}</span>
                <span className="text-xs text-ink-muted ml-auto">{t.email}</span>
              </label>
            ))}
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.notify} onChange={(e) => setForm({ ...form, notify: e.target.checked })} data-testid="duty-notify" />
          Send Telegram / WhatsApp alert to the teacher(s)
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="save-duty-btn">
            {busy ? "Saving…" : "Assign duty"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
