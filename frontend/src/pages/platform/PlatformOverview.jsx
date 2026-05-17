import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import {
  Plus, BellRinging, Buildings, GraduationCap, ChalkboardTeacher,
  Users, BookOpen, CurrencyInr, CaretRight, X, Key, Copy, Check, PaperPlaneTilt, Trash,
} from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { formatDate } from "../../lib/utils";
import PhoneInput from "../../components/PhoneInput";

export default function PlatformOverview() {
  const [schools, setSchools] = useState([]);
  const [notifStats, setNotifStats] = useState({ total: 0, queued: 0, sent: 0, failed: 0 });
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null); // { school, teachers, students, counts }
  const [loadingDetail, setLoadingDetail] = useState(false);

  const load = async () => {
    const [s, n] = await Promise.all([
      api.get("/schools/with-stats").then((r) => r.data),
      api.get("/notifications/stats").then((r) => r.data),
    ]);
    setSchools(s);
    setNotifStats(n);
  };
  useEffect(() => { load(); }, []);

  const openDetail = async (school) => {
    setLoadingDetail(true);
    setDetail({ school, teachers: [], students: [], counts: {} });
    try {
      const { data } = await api.get(`/schools/${school.id}/people`);
      setDetail(data);
    } catch (err) {
      toast.error(formatApiError(err));
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  const refreshDetail = async () => {
    if (!detail?.school?.id) return;
    try {
      const { data } = await api.get(`/schools/${detail.school.id}/people`);
      setDetail(data);
    } catch (err) { toast.error(formatApiError(err)); }
    // refresh KPI tiles too so the deletion is reflected in school cards
    try {
      const fresh = await api.get("/schools/with-stats").then((r) => r.data);
      setSchools(fresh);
    } catch { /* ignore */ }
  };

  const totalStudents = schools.reduce((a, s) => a + (s.stats?.students || 0), 0);
  const totalTeachers = schools.reduce((a, s) => a + (s.stats?.teachers || 0), 0);

  return (
    <div data-testid="platform-overview">
      <PageHeader
        eyebrow="Platform Console"
        title="Schools across your platform"
        subtitle="Create new schools, manage school super admins, and inspect any school's roster in one click."
        actions={<button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-school-btn"><Plus size={16}/> New school</button>}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <KPI label="Schools" value={schools.length} accent="primary" testId="kpi-schools" />
        <KPI label="Total students" value={totalStudents} accent="info" testId="kpi-total-students" />
        <KPI label="Total teachers" value={totalTeachers} accent="success" testId="kpi-total-teachers" />
        <KPI label="Notifications" value={notifStats.total} accent="info" hint={`${notifStats.queued} queued`} testId="kpi-notifications" />
        <KPI label="Failed deliveries" value={notifStats.failed} accent={notifStats.failed ? "danger" : "success"} testId="kpi-failed" />
      </div>

      <Section title="Schools" subtitle="Click any school card to view its teachers and students.">
        {schools.length === 0 ? <Empty title="No schools yet" message="Add your first school to begin." /> : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {schools.map((s) => {
              const st = s.stats || {};
              return (
                <button
                  type="button"
                  key={s.id}
                  onClick={() => openDetail(s)}
                  className="text-left border border-line rounded-lg p-5 hover:border-primary hover:shadow-sm transition group bg-bg-surface"
                  data-testid={`school-card-${s.id}`}
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="w-10 h-10 rounded-lg bg-primary-light text-primary grid place-items-center">
                      <Buildings size={20} />
                    </div>
                    <div className="flex items-center gap-2">
                      {s.is_active ? <span className="badge-success">Active</span> : <span className="badge-neutral">Inactive</span>}
                      <CaretRight size={14} className="text-ink-muted group-hover:text-primary transition" />
                    </div>
                  </div>
                  <div className="font-display text-lg font-medium">{s.name}</div>
                  <div className="text-sm text-ink-muted">{s.code} · {s.academic_year || "—"}</div>

                  <div className="grid grid-cols-3 gap-2 mt-4">
                    <StatTile icon={GraduationCap} label="Students" value={st.students || 0} testId={`stat-students-${s.id}`} />
                    <StatTile icon={ChalkboardTeacher} label="Teachers" value={st.teachers || 0} testId={`stat-teachers-${s.id}`} />
                    <StatTile icon={Users} label="Parents" value={st.parents || 0} testId={`stat-parents-${s.id}`} />
                    <StatTile icon={BookOpen} label="Classes" value={st.classes || 0} testId={`stat-classes-${s.id}`} />
                    <StatTile icon={BookOpen} label="Sections" value={st.sections || 0} testId={`stat-sections-${s.id}`} />
                    <StatTile icon={CurrencyInr} label="Fee due" value={fmtMoney(st.fee_due || 0)} testId={`stat-feedue-${s.id}`} />
                  </div>

                  <div className="text-xs text-ink-muted mt-4 pt-3 border-t border-line/60 flex items-center justify-between">
                    <span>Created {formatDate(s.created_at)}</span>
                    {s.valid_until && <span>Valid until {formatDate(s.valid_until)}</span>}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Section>

      <CreateSchoolModal open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
      <SchoolDetailDrawer
        open={!!detail}
        detail={detail}
        loading={loadingDetail}
        onClose={() => setDetail(null)}
        onChanged={refreshDetail}
      />
    </div>
  );
}

function StatTile({ icon: Icon, label, value, testId }) {
  return (
    <div className="bg-bg-subtle rounded-md p-2.5 flex flex-col gap-0.5" data-testid={testId}>
      <Icon size={14} className="text-ink-muted" />
      <div className="text-base font-display font-medium leading-tight">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-ink-muted">{label}</div>
    </div>
  );
}

function fmtMoney(v) {
  if (!v) return "₹0";
  const num = Number(v);
  if (num >= 1e7) return `₹${(num / 1e7).toFixed(1)}Cr`;
  if (num >= 1e5) return `₹${(num / 1e5).toFixed(1)}L`;
  if (num >= 1e3) return `₹${(num / 1e3).toFixed(0)}k`;
  return `₹${num.toFixed(0)}`;
}

function SchoolDetailDrawer({ open, detail, loading, onClose, onChanged }) {
  const [resetAdmin, setResetAdmin] = useState(null);
  const [selectedStudents, setSelectedStudents] = useState(() => new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Reset selection state whenever the drawer opens for a different school
  useEffect(() => {
    setSelectedStudents(new Set());
  }, [detail?.school?.id]);

  if (!open) return null;
  const school = detail?.school;
  const teachers = detail?.teachers || [];
  const students = detail?.students || [];
  const schoolAdmins = detail?.school_admins || [];

  const toggleStudent = (id) => {
    setSelectedStudents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleSelectAll = () => {
    setSelectedStudents((prev) => {
      if (prev.size === students.length) return new Set();
      return new Set(students.map((s) => s.id));
    });
  };
  const allSelected = students.length > 0 && selectedStudents.size === students.length;
  const someSelected = selectedStudents.size > 0 && !allSelected;
  return (
    <div className="fixed inset-0 z-40" data-testid="school-detail-drawer">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="absolute top-0 right-0 bottom-0 w-full max-w-2xl bg-bg-surface border-l border-line shadow-xl overflow-y-auto">
        <div className="sticky top-0 bg-bg-surface border-b border-line p-5 flex items-start justify-between gap-3 z-10">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-10 h-10 rounded-lg bg-primary-light text-primary grid place-items-center shrink-0">
              <Buildings size={20} />
            </div>
            <div className="min-w-0">
              <div className="font-display text-xl font-medium truncate" data-testid="drawer-school-name">{school?.name}</div>
              <div className="text-xs text-ink-muted">{school?.code} · {school?.academic_year || "—"}</div>
            </div>
          </div>
          <button onClick={onClose} className="btn-ghost p-2" data-testid="drawer-close-btn"><X size={18}/></button>
        </div>

        <div className="p-5 space-y-6">
          {loading ? (
            <div className="text-ink-muted text-sm">Loading roster…</div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                <KPI label="Students" value={students.length} accent="info" testId="drawer-kpi-students" />
                <KPI label="Teachers" value={teachers.length} accent="success" testId="drawer-kpi-teachers" />
                <KPI label="Classes" value={detail?.counts?.classes || 0} accent="primary" testId="drawer-kpi-classes" />
              </div>

              {school?.id && <MandatoryChannelsPanel schoolId={school.id} schoolName={school.name} />}

              <Section title={`School Super Admin${schoolAdmins.length === 1 ? "" : "s"} (${schoolAdmins.length})`}>
                {schoolAdmins.length === 0 ? (
                  <Empty title="No school admin" message="This school doesn't have a Super Admin account yet." />
                ) : (
                  <div className="border border-line rounded-md overflow-hidden" data-testid="drawer-school-admins">
                    <table className="w-full text-sm">
                      <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                        <tr>
                          <th className="text-left p-2.5">Name</th>
                          <th className="text-left p-2.5">Email</th>
                          <th className="text-left p-2.5">Status</th>
                          <th className="text-right p-2.5">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {schoolAdmins.map((a) => (
                          <tr key={a.id} className="border-t border-line/60" data-testid={`drawer-school-admin-${a.id}`}>
                            <td className="p-2.5 font-medium">{a.name}</td>
                            <td className="p-2.5 text-ink-soft">{a.email}</td>
                            <td className="p-2.5">
                              {a.is_active !== false
                                ? <span className="badge-success">Active</span>
                                : <span className="badge-neutral">Inactive</span>}
                            </td>
                            <td className="p-2.5 text-right">
                              <button
                                className="btn-secondary text-xs"
                                onClick={() => setResetAdmin(a)}
                                data-testid={`reset-school-admin-btn-${a.id}`}
                              ><Key size={12}/> Reset password</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <Section title={`Teachers (${teachers.length})`}>
                {teachers.length === 0 ? (
                  <Empty title="No teachers" message="This school hasn't added any teachers yet." />
                ) : (
                  <div className="border border-line rounded-md overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                        <tr>
                          <th className="text-left p-2.5">Name</th>
                          <th className="text-left p-2.5">Email</th>
                          <th className="text-left p-2.5">Phone</th>
                        </tr>
                      </thead>
                      <tbody>
                        {teachers.map((t) => (
                          <tr key={t.id} className="border-t border-line/60" data-testid={`drawer-teacher-${t.id}`}>
                            <td className="p-2.5 font-medium">{t.name}</td>
                            <td className="p-2.5 text-ink-soft">{t.email}</td>
                            <td className="p-2.5 text-ink-soft">{t.phone || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <Section title={`Students (${students.length})`}>
                {students.length === 0 ? (
                  <Empty title="No students" message="This school hasn't enrolled any students yet." />
                ) : (
                  <>
                    <div className="flex items-center justify-between flex-wrap gap-2 mb-2" data-testid="drawer-students-toolbar">
                      <label className="flex items-center gap-2 text-xs text-ink-soft cursor-pointer">
                        <input
                          type="checkbox"
                          checked={allSelected}
                          ref={(el) => { if (el) el.indeterminate = someSelected; }}
                          onChange={toggleSelectAll}
                          data-testid="drawer-students-select-all"
                        />
                        {selectedStudents.size > 0
                          ? <span><strong className="text-ink">{selectedStudents.size}</strong> of {students.length} selected</span>
                          : <span>Select all to bulk delete</span>}
                      </label>
                      <button
                        className="btn-secondary text-xs text-status-danger disabled:opacity-50"
                        disabled={selectedStudents.size === 0}
                        onClick={() => setDeleteOpen(true)}
                        data-testid="drawer-bulk-delete-btn"
                        title="Delete selected students from this school"
                      ><Trash size={12}/> Delete selected ({selectedStudents.size})</button>
                    </div>
                    <div className="border border-line rounded-md overflow-hidden max-h-96 overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider sticky top-0">
                          <tr>
                            <th className="text-left p-2.5 w-8"></th>
                            <th className="text-left p-2.5">UID</th>
                            <th className="text-left p-2.5">Name</th>
                            <th className="text-left p-2.5">Class</th>
                            <th className="text-left p-2.5">Parent</th>
                          </tr>
                        </thead>
                        <tbody>
                          {students.map((s) => {
                            const checked = selectedStudents.has(s.id);
                            return (
                              <tr key={s.id} className={`border-t border-line/60 ${checked ? "bg-status-danger/5" : ""}`} data-testid={`drawer-student-${s.id}`}>
                                <td className="p-2.5">
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={() => toggleStudent(s.id)}
                                    data-testid={`drawer-student-select-${s.id}`}
                                  />
                                </td>
                                <td className="p-2.5 font-mono text-xs text-ink-soft">{s.student_uid}</td>
                                <td className="p-2.5 font-medium">{s.name}</td>
                                <td className="p-2.5 text-ink-soft">{s.class_name || s.class_id} · {s.section}</td>
                                <td className="p-2.5 text-ink-soft text-xs">{s.parent?.name || "—"}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </Section>
            </>
          )}
        </div>
      </div>
      {resetAdmin && (
        <AdminResetPasswordModal
          target={resetAdmin}
          onClose={() => setResetAdmin(null)}
        />
      )}
      {deleteOpen && (
        <BulkDeleteStudentsModal
          school={school}
          studentIds={Array.from(selectedStudents)}
          students={students.filter((s) => selectedStudents.has(s.id))}
          onClose={() => setDeleteOpen(false)}
          onDeleted={() => {
            setDeleteOpen(false);
            setSelectedStudents(new Set());
            onChanged && onChanged();
          }}
        />
      )}
    </div>
  );
}

function AdminResetPasswordModal({ target, onClose }) {
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [sendTelegram, setSendTelegram] = useState(Boolean(target?.telegram_chat_id));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);
  const telegramLinked = Boolean(target?.telegram_chat_id);

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
      const { data } = await api.post(`/users/${target.id}/reset-password`, {
        new_password: newPw,
        send_via_telegram: sendTelegram,
      });
      setResult(data);
      if (sendTelegram) {
        if (data?.telegram?.status === "sent") toast.success("Password reset & sent on Telegram");
        else toast(`Password reset · Telegram: ${data?.telegram?.delivery_note || "queued"}`, { icon: "ℹ️" });
      } else {
        toast.success("School admin password reset");
      }
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const copy = async () => {
    if (!result?.new_password) return;
    try {
      await navigator.clipboard.writeText(result.new_password);
      setCopied(true); setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  return (
    <Modal open onClose={onClose} title={`Reset School Admin password — ${target.name}`} size="sm" testId="admin-reset-password-modal">
      {result ? (
        <div className="space-y-4" data-testid="admin-reset-password-result">
          <div className="rounded-md border border-status-success/40 bg-status-success/10 p-3 text-sm">
            <div className="font-medium text-status-success mb-1">Password updated</div>
            <div className="text-ink-soft text-xs">Share the new password with <strong>{result.name}</strong> ({result.email}) — they can log in immediately. This is the only time it will be shown.</div>
          </div>
          {result.telegram ? (
            <div
              className={`rounded-md border p-3 text-xs ${result.telegram.status === "sent" ? "border-status-success/40 bg-status-success/5 text-status-success" : "border-status-warning/40 bg-status-warning/5 text-status-warning"}`}
              data-testid="admin-reset-telegram-status"
            >
              {result.telegram.status === "sent"
                ? <>✅ New password sent to {result.name} on Telegram.</>
                : <>⚠️ Telegram delivery: <code>{result.telegram.delivery_note || result.telegram.status}</code>{result.telegram.linked ? "" : " — admin hasn't linked Telegram yet."}</>}
            </div>
          ) : null}
          <div>
            <label className="label">New password</label>
            <div className="flex items-stretch gap-2">
              <input className="input font-mono" readOnly value={result.new_password} data-testid="admin-reset-password-shown" />
              <button type="button" className="btn-secondary" onClick={copy} data-testid="admin-copy-new-password-btn">
                {copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
          <div className="flex justify-end">
            <button type="button" className="btn-primary" onClick={onClose} data-testid="admin-reset-password-done-btn">Done</button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div className="text-sm text-ink-soft">
            Set a new password for <strong>{target.name}</strong> ({target.email}). Share it manually after submit, or tick the box below to push it directly to their Telegram.
          </div>
          <div>
            <label className="label">New password</label>
            <div className="flex items-stretch gap-2">
              <input
                className="input" type="text" required minLength={6}
                value={newPw} onChange={(e) => setNewPw(e.target.value)}
                placeholder="At least 6 characters"
                data-testid="admin-reset-password-new" autoFocus
              />
              <button type="button" className="btn-secondary" onClick={generateRandom} data-testid="admin-reset-password-generate" title="Generate a random password">Generate</button>
            </div>
          </div>
          <div>
            <label className="label">Confirm new password</label>
            <input
              className="input" type="text" required minLength={6}
              value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)}
              data-testid="admin-reset-password-confirm"
            />
          </div>
          <label className="flex items-start gap-2 text-sm cursor-pointer rounded-md border border-line p-3 hover:bg-bg-subtle">
            <input
              type="checkbox"
              checked={sendTelegram}
              onChange={(e) => setSendTelegram(e.target.checked)}
              data-testid="admin-reset-password-send-telegram"
              className="mt-0.5"
            />
            <div className="flex-1">
              <div className="font-medium flex items-center gap-2">
                <PaperPlaneTilt size={14}/> Also send the new password via Telegram
                {telegramLinked
                  ? <span className="badge-success text-[10px]">Linked</span>
                  : <span className="badge-neutral text-[10px]">Not linked</span>}
              </div>
              <div className="text-xs text-ink-muted mt-0.5">
                {telegramLinked
                  ? "We'll push the credentials straight to the admin's Telegram chat."
                  : "Admin hasn't linked Telegram yet — message will queue and deliver once they connect."}
              </div>
            </div>
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={busy} data-testid="admin-reset-password-submit">
              {busy ? "Resetting…" : (sendTelegram ? "Reset & send" : "Reset password")}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function BulkDeleteStudentsModal({ school, studentIds, students, onClose, onDeleted }) {
  const [confirmCode, setConfirmCode] = useState("");
  const [busy, setBusy] = useState(false);
  const ok = (confirmCode || "").trim() === (school?.code || "");

  const submit = async (e) => {
    e.preventDefault();
    if (!ok || studentIds.length === 0) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/schools/${school.id}/students/bulk-delete`, {
        student_ids: studentIds,
        confirm_code: confirmCode.trim(),
      });
      toast.success(`Deleted ${data.deleted_students} student${data.deleted_students === 1 ? "" : "s"} · ${data.deactivated_parents} parent account${data.deactivated_parents === 1 ? "" : "s"} deactivated`);
      onDeleted();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const preview = students.slice(0, 5);

  return (
    <Modal open onClose={onClose} title={`Delete students from ${school?.name}`} size="md" testId="bulk-delete-students-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="rounded-md border border-status-danger/40 bg-status-danger/10 p-3 text-sm">
          <div className="font-semibold text-status-danger mb-1">⚠ This action cannot be undone.</div>
          <div className="text-ink-soft text-xs">
            You're about to permanently delete <strong>{studentIds.length}</strong> student{studentIds.length === 1 ? "" : "s"} from <strong>{school?.name}</strong>.
            All of their attendance, marks, fees, payments, sick-leaves and activity enrollments will also be removed. Parent accounts with no remaining children will be deactivated.
          </div>
        </div>
        {preview.length > 0 && (
          <div className="text-xs text-ink-soft border border-line rounded-md p-2 max-h-32 overflow-y-auto" data-testid="bulk-delete-preview">
            {preview.map((s) => (
              <div key={s.id} className="flex items-center gap-2 py-0.5">
                <span className="font-mono text-[10px]">{s.student_uid}</span>
                <span>{s.name}</span>
                <span className="text-ink-muted text-[10px]">{s.class_name || ""} {s.section ? `· ${s.section}` : ""}</span>
              </div>
            ))}
            {students.length > preview.length && (
              <div className="text-ink-muted italic pt-1">… and {students.length - preview.length} more</div>
            )}
          </div>
        )}
        <div>
          <label className="label">
            To confirm, type the school code <code className="text-status-danger font-mono ml-1">{school?.code}</code>
          </label>
          <input
            className="input"
            type="text"
            value={confirmCode}
            onChange={(e) => setConfirmCode(e.target.value)}
            placeholder={school?.code}
            autoFocus
            data-testid="bulk-delete-confirm-input"
          />
          {confirmCode && !ok && (
            <div className="text-xs text-status-danger mt-1" data-testid="bulk-delete-confirm-error">Code doesn't match.</div>
          )}
        </div>
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            type="submit"
            className="btn-primary bg-status-danger hover:bg-status-danger/90 border-status-danger"
            disabled={!ok || busy || studentIds.length === 0}
            data-testid="bulk-delete-confirm-btn"
          >{busy ? "Deleting…" : `Delete ${studentIds.length} student${studentIds.length === 1 ? "" : "s"}`}</button>
        </div>
      </form>
    </Modal>
  );
}

function CreateSchoolModal({ open, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "", code: "", address: "", phone: "", email: "", academic_year: "2025-2026",
    admin_name: "", admin_email: "", admin_password: "", admin_phone: "",
  });
  const [busy, setBusy] = useState(false);
  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/schools", form);
      toast.success(`School ${form.name} created`);
      onCreated();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add a new school" size="lg" testId="create-school-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label className="label">School name</label><input className="input" required value={form.name} onChange={update("name")} data-testid="school-name-input" /></div>
        <div><label className="label">School code</label><input className="input" required value={form.code} onChange={update("code")} data-testid="school-code-input" /></div>
        <div className="md:col-span-2"><label className="label">Address</label><input className="input" value={form.address} onChange={update("address")} /></div>
        <div>
          <label className="label">Phone</label>
          <PhoneInput
            value={form.phone}
            onChange={(v) => setForm((f) => ({ ...f, phone: v }))}
            testId="school-phone-input"
            placeholder="School phone"
          />
        </div>
        <div><label className="label">Email</label><input className="input" type="email" value={form.email} onChange={update("email")} /></div>
        <div><label className="label">Academic year</label><input className="input" value={form.academic_year} onChange={update("academic_year")} /></div>
        <div className="md:col-span-2 pt-2 border-t border-line"><div className="overline">School Super Admin (login account)</div></div>
        <div><label className="label">Admin name</label><input className="input" required value={form.admin_name} onChange={update("admin_name")} data-testid="admin-name-input" /></div>
        <div><label className="label">Admin email</label><input className="input" type="email" required value={form.admin_email} onChange={update("admin_email")} data-testid="admin-email-input" /></div>
        <div className="md:col-span-2">
          <label className="label">Admin phone</label>
          <PhoneInput
            value={form.admin_phone}
            onChange={(v) => setForm((f) => ({ ...f, admin_phone: v }))}
            testId="admin-phone-input"
            placeholder="Admin contact number"
          />
          <div className="text-[11px] text-ink-muted mt-1">Pick the country dial code, then enter the local number (no spaces).</div>
        </div>
        <div className="md:col-span-2"><label className="label">Temporary password</label><input className="input" type="text" required minLength={6} value={form.admin_password} onChange={update("admin_password")} data-testid="admin-password-input" /></div>
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-school-btn">{busy ? "Creating…" : "Create school"}</button>
        </div>
      </form>
    </Modal>
  );
}


function MandatoryChannelsPanel({ schoolId, schoolName }) {
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/schools/${schoolId}/mandatory-channels`)
      .then((r) => { setData(r.data); setDraft(r.data.channels || []); })
      .catch((err) => toast.error(formatApiError(err)));
  }, [schoolId]);

  if (!data) return null;
  const toggle = (ch) => {
    setDraft((d) => d.includes(ch) ? d.filter((x) => x !== ch) : [...d, ch]);
  };
  const dirty = JSON.stringify([...draft].sort()) !== JSON.stringify([...(data.channels || [])].sort());

  const save = async () => {
    if (draft.length === 0) { toast.error("Pick at least one channel"); return; }
    setBusy(true);
    try {
      const { data: r } = await api.patch(`/schools/${schoolId}/mandatory-channels`, { channels: draft });
      setData({ ...data, channels: r.channels });
      toast.success(`Mandatory channels updated for ${schoolName}`);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const meta = {
    email: { label: "Email", hint: "Required for digest summaries & password reset" },
    whatsapp: { label: "WhatsApp / SMS", hint: "Requires user phone number on file" },
    telegram: { label: "Telegram", hint: "Free, fastest. Users link via /start bot" },
  };

  return (
    <Section title="Mandatory communication channels">
      <div className="text-xs text-ink-muted mb-3">
        Pick one or more channels every user in this school must link. Banners appear inside the user's account until they comply.
      </div>
      <div className="space-y-2" data-testid="mandatory-channels-config">
        {(data.allowed || ["email", "whatsapp", "telegram"]).map((ch) => {
          const checked = draft.includes(ch);
          return (
            <label
              key={ch}
              className={"flex items-center gap-3 p-3 rounded-md border cursor-pointer transition " + (checked ? "bg-primary-light/40 border-primary" : "border-line/60 hover:bg-bg-subtle")}
              data-testid={`mc-row-${ch}`}
            >
              <input
                type="checkbox" className="w-4 h-4"
                checked={checked} onChange={() => toggle(ch)}
                data-testid={`mc-check-${ch}`}
              />
              <div className="flex-1">
                <div className="text-sm font-medium capitalize">{meta[ch]?.label || ch}</div>
                <div className="text-xs text-ink-muted">{meta[ch]?.hint}</div>
              </div>
            </label>
          );
        })}
      </div>
      <div className="flex items-center justify-between mt-3">
        <div className="text-xs text-ink-muted" data-testid="mc-current">
          Currently mandatory: {(data.channels || []).map((c) => (
            <span key={c} className="badge bg-primary-light text-primary mr-1 capitalize">{c}</span>
          ))}
        </div>
        <button
          type="button" className="btn-primary text-xs"
          disabled={!dirty || busy || draft.length === 0}
          onClick={save}
          data-testid="mc-save-btn"
        >{busy ? "Saving…" : "Save"}</button>
      </div>
    </Section>
  );
}
