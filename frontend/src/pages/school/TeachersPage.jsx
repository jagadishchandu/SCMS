import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, UserCircle, PencilSimple, Trash, ToggleRight, ToggleLeft, PaperPlaneTilt, Key, Copy, Check } from "@phosphor-icons/react";
import toast from "react-hot-toast";
import PhoneInput from "../../components/PhoneInput";

const fmtMoney = (v) => v != null && v !== "" ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(v)) : "—";

export default function TeachersPage() {
  const { user } = useAuth();
  const canSeeSalary = user?.role === "school_admin" || user?.role === "accounts";
  const [users, setUsers] = useState([]);
  const [staff, setStaff] = useState([]);
  const [open, setOpen] = useState(false);
  const [editUser, setEditUser] = useState(null);
  const [resetUser, setResetUser] = useState(null);
  const [editStaff, setEditStaff] = useState(null);
  const [role, setRole] = useState("teacher"); // 'teacher' | 'accounts' | 'other_staff'
  const [subjects, setSubjects] = useState([]);

  const isOtherStaffTab = role === "other_staff";

  const load = async () => {
    if (isOtherStaffTab) {
      const { data } = await api.get("/staff");
      setStaff(data);
    } else {
      const { data } = await api.get("/users", { params: { role } });
      setUsers(data);
    }
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

  const sendCreds = async (u) => {
    if (!window.confirm(`Send login credentials to ${u.name} over Telegram?\nThis will reset their password to Staff@123.`)) return;
    try {
      const { data } = await api.post(`/users/${u.id}/send-credentials`, { channel: "telegram", reset_first: true });
      if (data.delivery_status === "sent") {
        toast.success(`✅ Sent to ${u.name} on Telegram`);
      } else {
        toast(`Queued — ${data.delivery_note || "Telegram not yet linked"}. They'll receive when they link.`, { icon: "ℹ️" });
      }
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
        {[
          { id: "teacher", label: "Teachers" },
          { id: "accounts", label: "Accounts" },
          { id: "other_staff", label: "Other Staff" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setRole(t.id)}
            className={`btn-secondary ${role === t.id ? "border-primary text-primary" : ""}`}
            data-testid={`tab-${t.id}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {isOtherStaffTab ? (
        <StaffSection
          staff={staff}
          canSeeSalary={canSeeSalary}
          onAdd={() => setOpen(true)}
          onEdit={setEditStaff}
          onChanged={load}
        />
      ) : (
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
                {canSeeSalary && u.monthly_salary != null && u.monthly_salary !== "" ? (
                  <div className="text-xs text-ink-soft" data-testid={`user-salary-${u.id}`}>
                    <span className="overline mr-1">Salary</span>{fmtMoney(u.monthly_salary)} / mo
                  </div>
                ) : null}
                <div className="flex gap-1.5 mt-3 pt-3 border-t border-line flex-wrap">
                  <button
                    className="btn-secondary text-xs flex-1"
                    onClick={() => setEditUser(u)}
                    data-testid={`edit-user-btn-${u.id}`}
                  ><PencilSimple size={12}/> Edit</button>
                  <button
                    className="btn-secondary text-xs flex-1"
                    onClick={() => setResetUser(u)}
                    title="Reset this user's password"
                    data-testid={`reset-password-btn-${u.id}`}
                  ><Key size={12}/> Reset password</button>
                  <button
                    className="btn-secondary text-xs flex-1"
                    onClick={() => sendCreds(u)}
                    title="Send login over Telegram"
                    data-testid={`send-staff-creds-btn-${u.id}`}
                  ><PaperPlaneTilt size={12}/> Send creds</button>
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
      )}

      <CreateUserModal
        role={role}
        open={open && !isOtherStaffTab}
        subjects={subjects}
        onClose={() => setOpen(false)}
        onCreated={() => { setOpen(false); load(); }}
      />
      <CreateStaffModal
        open={open && isOtherStaffTab}
        onClose={() => setOpen(false)}
        onCreated={() => { setOpen(false); load(); }}
      />
      {editUser && (
        <EditUserModal
          target={editUser}
          subjects={subjects}
          onClose={() => setEditUser(null)}
          onSaved={() => { setEditUser(null); load(); }}
          onReset={() => { setResetUser(editUser); setEditUser(null); }}
        />
      )}
      {resetUser && (
        <ResetPasswordModal
          target={resetUser}
          onClose={() => setResetUser(null)}
        />
      )}
      {editStaff && (
        <EditStaffModal
          target={editStaff}
          onClose={() => setEditStaff(null)}
          onSaved={() => { setEditStaff(null); load(); }}
        />
      )}
    </div>
  );
}

function CreateUserModal({ role, open, subjects, onClose, onCreated }) {
  const emptyForm = { name: "", email: "", password: "", phone: "", employee_id: "", qualifications: "", subjects: [], monthly_salary: "" };
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
      // monthly_salary is optional. Convert blank → null so backend stores null.
      payload.monthly_salary = form.monthly_salary === "" ? null : Number(form.monthly_salary);
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
        <div><label className="label">Phone</label><PhoneInput value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} testId="new-user-phone" /></div>
        <div><label className="label">Employee ID</label><input className="input" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} data-testid="new-user-employee-id" /></div>
        <div>
          <label className="label">Monthly salary <span className="text-ink-muted font-normal">· optional</span></label>
          <input
            className="input" type="number" min="0" step="100" placeholder="e.g. 35000"
            value={form.monthly_salary}
            onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })}
            data-testid="new-user-salary"
          />
          <div className="text-xs text-ink-muted mt-0.5">Counts towards the school's monthly payroll outflow shown on the Expenses dashboard.</div>
        </div>
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

function EditUserModal({ target, subjects, onClose, onSaved, onReset }) {
  const [form, setForm] = useState({
    name: target.name || "",
    phone: target.phone || "",
    employee_id: target.employee_id || "",
    qualifications: target.qualifications || "",
    subjects: target.subjects || [],
    monthly_salary: target.monthly_salary == null ? "" : target.monthly_salary,
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
        monthly_salary: form.monthly_salary === "" ? null : Number(form.monthly_salary),
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
        <div><label className="label">Phone</label><PhoneInput value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} testId="edit-user-phone" /></div>
        <div><label className="label">Employee ID</label><input className="input" value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} /></div>
        <div>
          <label className="label">Monthly salary <span className="text-ink-muted font-normal">· optional</span></label>
          <input
            className="input" type="number" min="0" step="100" placeholder="e.g. 35000"
            value={form.monthly_salary}
            onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })}
            data-testid="edit-user-salary"
          />
        </div>
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
        <div className="md:col-span-2 flex justify-between items-center gap-2 pt-3 border-t border-line">
          {onReset ? (
            <button
              type="button"
              className="btn-secondary text-xs"
              onClick={onReset}
              data-testid="edit-user-reset-password-btn"
            ><Key size={12}/> Reset password</button>
          ) : <span />}
          <div className="flex gap-2">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy} data-testid="edit-user-submit">{busy ? "Saving…" : "Save changes"}</button>
          </div>
        </div>
      </form>
    </Modal>
  );
}


function ResetPasswordModal({ target, onClose }) {
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // { email, name, role, new_password }
  const [copied, setCopied] = useState(false);

  const generateRandom = () => {
    const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789";
    let s = "";
    for (let i = 0; i < 10; i++) s += chars[Math.floor(Math.random() * chars.length)];
    setNewPw(s); setConfirmPw(s);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (newPw.length < 6) { toast.error("Password must be at least 6 characters"); return; }
    if (newPw !== confirmPw) { toast.error("Passwords don't match"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/users/${target.id}/reset-password`, { new_password: newPw });
      setResult(data);
      toast.success("Password reset");
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const copy = async () => {
    if (!result?.new_password) return;
    try {
      await navigator.clipboard.writeText(result.new_password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  return (
    <Modal open onClose={onClose} title={`Reset password — ${target.name}`} size="sm" testId="reset-password-modal">
      {result ? (
        <div className="space-y-4" data-testid="reset-password-result">
          <div className="rounded-md border border-status-success/40 bg-status-success/10 p-3 text-sm">
            <div className="font-medium text-status-success mb-1">Password updated</div>
            <div className="text-ink-soft text-xs">Share the new password with <strong>{result.name}</strong> ({result.email}) — they can use it to log in immediately. This is the only time it will be shown.</div>
          </div>
          <div>
            <label className="label">New password</label>
            <div className="flex items-stretch gap-2">
              <input
                className="input font-mono"
                readOnly
                value={result.new_password}
                data-testid="reset-password-shown"
              />
              <button
                type="button"
                className="btn-secondary"
                onClick={copy}
                data-testid="copy-new-password-btn"
              >{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? "Copied" : "Copy"}</button>
            </div>
          </div>
          <div className="flex justify-end">
            <button type="button" className="btn-primary" onClick={onClose} data-testid="reset-password-done-btn">Done</button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div className="text-sm text-ink-soft">
            Set a new password for <strong>{target.name}</strong> ({target.email}). The user is not notified — share it with them manually.
          </div>
          <div>
            <label className="label">New password</label>
            <div className="flex items-stretch gap-2">
              <input
                className="input"
                type="text"
                required
                minLength={6}
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                placeholder="At least 6 characters"
                data-testid="reset-password-new"
                autoFocus
              />
              <button
                type="button"
                className="btn-secondary"
                onClick={generateRandom}
                data-testid="reset-password-generate"
                title="Generate a random password"
              >Generate</button>
            </div>
          </div>
          <div>
            <label className="label">Confirm new password</label>
            <input
              className="input"
              type="text"
              required
              minLength={6}
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              data-testid="reset-password-confirm"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy} data-testid="reset-password-submit">{busy ? "Resetting…" : "Reset password"}</button>
          </div>
        </form>
      )}
    </Modal>
  );
}


// ----------------- Other Staff (cleaner/driver/coach/etc.) -----------------

const STAFF_ROLES = ["other", "cleaner", "driver", "coach", "security", "nurse"];

function StaffSection({ staff, canSeeSalary, onAdd, onEdit, onChanged }) {
  const [showInactive, setShowInactive] = useState(true);

  const setActive = async (s, is_active) => {
    try {
      if (!is_active) {
        await api.delete(`/staff/${s.id}`);
      } else {
        await api.patch(`/staff/${s.id}`, { is_active: true });
      }
      toast.success(is_active ? "Reactivated" : "Marked inactive");
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const visible = showInactive ? staff : staff.filter((s) => s.is_active);
  const activeCount = staff.filter((s) => s.is_active).length;
  const inactiveCount = staff.length - activeCount;

  return (
    <Section
      title={`${visible.length} non-teaching staff${activeCount !== staff.length ? `  ·  ${activeCount} active / ${inactiveCount} inactive` : ""}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <label className="text-xs text-ink-muted flex items-center gap-1.5">
          <input
            type="checkbox" checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            data-testid="show-inactive-staff"
          /> Show inactive
        </label>
      </div>
      {visible.length === 0 ? (
        <Empty
          title="No non-teaching staff yet"
          message="Add cleaners, drivers, coaches, security, nurses or other support staff and track their monthly salaries here."
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {visible.map((s) => (
            <div key={s.id} className="border border-line rounded-lg p-5" data-testid={`staff-card-${s.id}`}>
              <div className="flex items-start gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-secondary/40 text-ink grid place-items-center"><UserCircle size={22} /></div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium">{s.name}</div>
                  <div className="text-xs text-ink-muted capitalize">{s.role}</div>
                </div>
                {s.is_active ? <span className="badge-success">Active</span> : <span className="badge-neutral">Inactive</span>}
              </div>
              <div className="text-xs text-ink-soft space-y-1">
                {s.phone ? <div><span className="overline mr-1">Phone</span>{s.phone}</div> : null}
                {s.email ? <div><span className="overline mr-1">Email</span>{s.email}</div> : null}
                {s.joining_date ? <div><span className="overline mr-1">Joined</span>{s.joining_date}</div> : null}
                {s.notes ? <div className="text-ink-muted italic">{s.notes}</div> : null}
                {canSeeSalary && s.monthly_salary != null && s.monthly_salary !== "" ? (
                  <div data-testid={`staff-salary-${s.id}`}>
                    <span className="overline mr-1">Salary</span>{fmtMoney(s.monthly_salary)} / mo
                  </div>
                ) : null}
              </div>
              <div className="flex gap-1.5 mt-3 pt-3 border-t border-line flex-wrap">
                <button className="btn-secondary text-xs flex-1" onClick={() => onEdit(s)} data-testid={`edit-staff-btn-${s.id}`}>
                  <PencilSimple size={12}/> Edit
                </button>
                <button
                  className="btn-secondary text-xs flex-1"
                  onClick={() => setActive(s, !s.is_active)}
                  data-testid={`toggle-staff-btn-${s.id}`}
                >
                  {s.is_active ? <><ToggleRight size={12}/> Deactivate</> : <><ToggleLeft size={12}/> Reactivate</>}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function CreateStaffModal({ open, onClose, onCreated }) {
  const empty = { name: "", role: "other", phone: "", email: "", monthly_salary: "", joining_date: "", notes: "" };
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) setForm(empty); /* eslint-disable-next-line */ }, [open]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        ...form,
        monthly_salary: form.monthly_salary === "" ? null : Number(form.monthly_salary),
      };
      await api.post("/staff", payload);
      toast.success("Staff member added");
      onCreated();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add non-teaching staff" size="md" testId="create-staff-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2"><label className="label">Full name</label>
          <input className="input" required value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })}
                 data-testid="new-staff-name" />
        </div>
        <div><label className="label">Role</label>
          <select className="input" value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  data-testid="new-staff-role">
            {STAFF_ROLES.map((r) => <option key={r} value={r} className="capitalize">{r}</option>)}
          </select>
        </div>
        <div><label className="label">Joining date</label>
          <input className="input" type="date" value={form.joining_date}
                 onChange={(e) => setForm({ ...form, joining_date: e.target.value })} />
        </div>
        <div><label className="label">Phone</label>
          <PhoneInput value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} testId="new-staff-phone" />
        </div>
        <div><label className="label">Email <span className="text-ink-muted font-normal">· optional</span></label>
          <input className="input" type="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>
        <div className="md:col-span-2">
          <label className="label">Monthly salary <span className="text-ink-muted font-normal">· optional</span></label>
          <input
            className="input" type="number" min="0" step="100" placeholder="e.g. 18000"
            value={form.monthly_salary}
            onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })}
            data-testid="new-staff-salary"
          />
          <div className="text-xs text-ink-muted mt-0.5">Counts towards the school's monthly payroll outflow shown on the Expenses dashboard.</div>
        </div>
        <div className="md:col-span-2"><label className="label">Notes</label>
          <textarea className="input" rows={2} value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <div className="md:col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-staff-btn">{busy ? "Adding…" : "Add"}</button>
        </div>
      </form>
    </Modal>
  );
}

function EditStaffModal({ target, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: target.name || "",
    role: target.role || "other",
    phone: target.phone || "",
    email: target.email || "",
    monthly_salary: target.monthly_salary == null ? "" : target.monthly_salary,
    joining_date: target.joining_date || "",
    notes: target.notes || "",
    is_active: target.is_active !== false,
  });
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = {
        ...form,
        monthly_salary: form.monthly_salary === "" ? null : Number(form.monthly_salary),
      };
      await api.patch(`/staff/${target.id}`, payload);
      toast.success("Saved");
      onSaved();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`Edit staff — ${target.name}`} size="md" testId="edit-staff-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2"><label className="label">Full name</label>
          <input className="input" required value={form.name}
                 onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div><label className="label">Role</label>
          <select className="input" value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {STAFF_ROLES.map((r) => <option key={r} value={r} className="capitalize">{r}</option>)}
          </select>
        </div>
        <div><label className="label">Joining date</label>
          <input className="input" type="date" value={form.joining_date}
                 onChange={(e) => setForm({ ...form, joining_date: e.target.value })} />
        </div>
        <div><label className="label">Phone</label>
          <PhoneInput value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} />
        </div>
        <div><label className="label">Email</label>
          <input className="input" type="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>
        <div className="md:col-span-2"><label className="label">Monthly salary <span className="text-ink-muted font-normal">· optional</span></label>
          <input className="input" type="number" min="0" step="100"
                 value={form.monthly_salary}
                 onChange={(e) => setForm({ ...form, monthly_salary: e.target.value })}
                 data-testid="edit-staff-salary" />
        </div>
        <div className="md:col-span-2"><label className="label">Notes</label>
          <textarea className="input" rows={2} value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>
        <label className="md:col-span-2 flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={form.is_active}
                 onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
          Account is active
        </label>
        <div className="md:col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Save changes"}</button>
        </div>
      </form>
    </Modal>
  );
}

