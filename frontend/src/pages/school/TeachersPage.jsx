import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, UserCircle, PencilSimple, Trash, ToggleRight, ToggleLeft } from "@phosphor-icons/react";
import toast from "react-hot-toast";

export default function TeachersPage() {
  const [users, setUsers] = useState([]);
  const [open, setOpen] = useState(false);
  const [editUser, setEditUser] = useState(null);
  const [role, setRole] = useState("teacher");
  const [subjects, setSubjects] = useState([]);

  const load = async () => {
    const { data } = await api.get("/users", { params: { role } });
    setUsers(data);
  };
  const loadSubjects = async () => {
    try {
      const { data } = await api.get("/academic/subjects");
      setSubjects(data || []);
    } catch {
      setSubjects([]);
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [role]);
  useEffect(() => { loadSubjects(); }, []);

  const toggleActive = async (u) => {
    if (u.is_active && !window.confirm(`Mark ${u.name} as Inactive? They will no longer be able to log in.`)) return;
    try {
      if (u.is_active) {
        await api.delete(`/users/${u.id}`); // soft-deactivate
      } else {
        await api.patch(`/users/${u.id}`, { is_active: true });
      }
      toast.success(u.is_active ? "Marked inactive" : "Reactivated");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const remove = async (u) => {
    if (!window.confirm(`Permanently mark ${u.name} as inactive? (We don't hard-delete user records.)`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      toast.success("Marked inactive");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const subjectMap = Object.fromEntries(subjects.map((s) => [s.id, s]));

  return (
    <div data-testid="teachers-page">
      <PageHeader
        eyebrow="Staff"
        title="Teachers & school staff"
        subtitle="Only the School Super Admin can view full staff details and assign roles."
        actions={<button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-user-btn"><Plus size={16}/> Add staff</button>}
      />

      <div className="flex gap-2 mb-4" role="tablist">
        {["teacher", "accounts"].map((r) => (
          <button key={r} onClick={() => setRole(r)} className={`btn-secondary ${role === r ? "border-primary text-primary" : ""}`} data-testid={`tab-${r}`}>
            {r === "accounts" ? "Accounts" : "Teachers"}
          </button>
        ))}
      </div>

      <Section title={`${users.length} ${role.replace("_", " ")}${users.length === 1 ? "" : "s"}`}>
        {users.length === 0 ? <Empty title={`No ${role}s yet`} /> :
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {users.map((u) => (
              <div key={u.id} className="border border-line rounded-lg p-5" data-testid={`user-card-${u.id}`}>
                <div className="flex items-start gap-3 mb-3">
                  <div className="w-10 h-10 rounded-full bg-secondary/40 text-ink grid place-items-center"><UserCircle size={22} /></div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium">{u.name}</div>
                    <div className="text-xs text-ink-muted truncate">{u.email}</div>
                  </div>
                  {u.is_active ? <span className="badge-success">Active</span> : <span className="badge-neutral">Inactive</span>}
                </div>
                <div className="text-xs text-ink-soft space-y-1">
                  {u.employee_id ? <div><span className="overline mr-1">ID</span>{u.employee_id}</div> : null}
                  {u.phone ? <div><span className="overline mr-1">Phone</span>{u.phone}</div> : null}
                  {u.qualifications ? <div><span className="overline mr-1">Qualifications</span>{u.qualifications}</div> : null}
                  {u.role === "teacher" && (u.subjects?.length ? (
                    <div className="pt-1" data-testid={`user-subjects-${u.id}`}>
                      <span className="overline mr-1">Subjects</span>
                      <span className="inline-flex flex-wrap gap-1 align-middle">
                        {u.subjects.map((sid) => (
                          <span key={sid} className="badge-neutral">{subjectMap[sid]?.name || sid}</span>
                        ))}
                      </span>
                    </div>
                  ) : (
                    <div className="text-status-warning"><span className="overline mr-1">Subjects</span>None assigned</div>
                  ))}
                </div>
                <div className="flex gap-1.5 mt-3 pt-3 border-t border-line">
                  <button
                    className="btn-secondary text-xs flex-1"
                    onClick={() => setEditUser(u)}
                    data-testid={`edit-user-btn-${u.id}`}
                  ><PencilSimple size={12}/> Edit</button>
                  <button
                    className="btn-secondary text-xs flex-1"
                    onClick={() => toggleActive(u)}
                    data-testid={`toggle-user-btn-${u.id}`}
                  >
                    {u.is_active ? <><ToggleRight size={12}/> Deactivate</> : <><ToggleLeft size={12}/> Reactivate</>}
                  </button>
                  <button
                    className="btn-secondary text-xs text-status-danger"
                    onClick={() => remove(u)}
                    data-testid={`delete-user-btn-${u.id}`}
                    title="Mark inactive"
                  ><Trash size={12}/></button>
                </div>
              </div>
            ))}
          </div>}
      </Section>

      <CreateUserModal
        role={role}
        open={open}
        subjects={subjects}
        onClose={() => setOpen(false)}
        onCreated={() => { setOpen(false); load(); }}
      />
      {editUser && (
        <EditUserModal
          target={editUser}
          subjects={subjects}
          onClose={() => setEditUser(null)}
          onSaved={() => { setEditUser(null); load(); }}
        />
      )}
    </div>
  );
}

function CreateUserModal({ role, open, subjects, onClose, onCreated }) {
  const emptyForm = { name: "", email: "", password: "", phone: "", employee_id: "", qualifications: "", subjects: [] };
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) setForm(emptyForm);
    // eslint-disable-next-line
  }, [open, role]);

  const toggleSubject = (id) => {
    setForm((f) => ({
      ...f,
      subjects: f.subjects.includes(id) ? f.subjects.filter((s) => s !== id) : [...f.subjects, id],
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (role === "teacher" && form.subjects.length === 0) {
      toast.error("Please select at least one subject for the teacher.");
      return;
    }
    setBusy(true);
    try {
      const payload = { ...form, role };
      if (role !== "teacher") delete payload.subjects;
      await api.post("/users", payload);
      toast.success("Staff added");
      onCreated();
      setForm(emptyForm);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Add ${role.replace("_", " ")}`} size="md" testId="create-user-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2"><label className="label">Full name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="new-user-name" /></div>
        <div><label className="label">Email</label><input className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="new-user-email" /></div>
        <div><label className="label">Temporary password</label><input className="input" required minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="new-user-password" /></div>
        <div><label className="label">Phone</label><input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="new-user-phone" /></div>
        <div><label className="label">Employee ID</label><input className="input" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="new-user-employee-id" /></div>
        <div className="md:col-span-2"><label className="label">Qualifications</label><input className="input" value={form.qualifications} onChange={(e) => setForm({ ...form, qualifications: e.target.value })} data-testid="new-user-qualifications" /></div>

        {role === "teacher" && (
          <div className="md:col-span-2" data-testid="new-user-subjects-wrap">
            <label className="label">
              Subjects <span className="text-status-danger">*</span>
              <span className="text-xs text-ink-muted ml-2 font-normal">(required — pick one or more)</span>
            </label>
            {subjects.length === 0 ? (
              <div className="text-sm text-ink-muted border border-dashed border-line rounded-md p-3" data-testid="new-user-subjects-empty">
                No subjects defined yet. Add subjects from the <strong>Academic → Subjects</strong> page first, then come back to assign them.
              </div>
            ) : (
              <div className="flex flex-wrap gap-2" data-testid="new-user-subjects">
                {subjects.map((s) => {
                  const selected = form.subjects.includes(s.id);
                  return (
                    <button
                      type="button"
                      key={s.id}
                      onClick={() => toggleSubject(s.id)}
                      className={selected ? "badge bg-primary text-white cursor-pointer" : "badge-neutral cursor-pointer hover:bg-line"}
                      data-testid={`new-user-subject-${s.id}`}
                      aria-pressed={selected}
                    >
                      {selected ? "✓ " : "+ "}{s.name}
                    </button>
                  );
                })}
              </div>
            )}
            <div className="text-xs text-ink-muted mt-1" data-testid="new-user-subjects-count">
              Selected: {form.subjects.length}
            </div>
          </div>
        )}

        <div className="md:col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-user-btn">{busy ? "Adding…" : "Add"}</button>
        </div>
      </form>
    </Modal>
  );
}

function EditUserModal({ target, subjects, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: target.name || "",
    phone: target.phone || "",
    employee_id: target.employee_id || "",
    qualifications: target.qualifications || "",
    subjects: target.subjects || [],
    is_active: target.is_active !== false,
  });
  const [busy, setBusy] = useState(false);
  const isTeacher = target.role === "teacher";

  const toggleSubject = (id) => {
    setForm((f) => ({
      ...f,
      subjects: f.subjects.includes(id) ? f.subjects.filter((s) => s !== id) : [...f.subjects, id],
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (isTeacher && form.subjects.length === 0) {
      toast.error("Teachers must have at least one subject.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        name: form.name,
        phone: form.phone,
        employee_id: form.employee_id,
        qualifications: form.qualifications,
        is_active: form.is_active,
      };
      if (isTeacher) payload.subjects = form.subjects;
      await api.patch(`/users/${target.id}`, payload);
      toast.success("Saved");
      onSaved();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`Edit ${target.role} — ${target.name}`} size="md" testId="edit-user-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2"><label className="label">Full name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="edit-user-name" /></div>
        <div><label className="label">Phone</label><input className="input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="edit-user-phone" /></div>
        <div><label className="label">Employee ID</label><input className="input" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="label">Qualifications</label><input className="input" value={form.qualifications} onChange={(e) => setForm({ ...form, qualifications: e.target.value })} /></div>
        {isTeacher && (
          <div className="md:col-span-2" data-testid="edit-user-subjects-wrap">
            <label className="label">Subjects <span className="text-status-danger">*</span></label>
            <div className="flex flex-wrap gap-2" data-testid="edit-user-subjects">
              {subjects.length === 0 ? (
                <div className="text-sm text-ink-muted">No subjects defined.</div>
              ) : subjects.map((s) => {
                const selected = form.subjects.includes(s.id);
                return (
                  <button
                    type="button"
                    key={s.id}
                    onClick={() => toggleSubject(s.id)}
                    className={selected ? "badge bg-primary text-white cursor-pointer" : "badge-neutral cursor-pointer hover:bg-line"}
                    data-testid={`edit-user-subject-${s.id}`}
                    aria-pressed={selected}
                  >{selected ? "✓ " : "+ "}{s.name}</button>
                );
              })}
            </div>
          </div>
        )}
        <label className="md:col-span-2 flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            data-testid="edit-user-active"
          />
          Account is active (can log in)
        </label>
        <div className="md:col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="edit-user-submit">{busy ? "Saving…" : "Save changes"}</button>
        </div>
      </form>
    </Modal>
  );
}

