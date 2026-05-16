import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Modal } from "../../components/Modal";
import { Plus, MagnifyingGlass, Key, Copy, PencilSimple, ArrowsLeftRight, Trash, FilePdf, PaperPlaneTilt, DownloadSimple, TelegramLogo, CheckCircle, XCircle } from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";
import PhoneInput from "../../components/PhoneInput";

const API_BASE = (process.env.REACT_APP_BACKEND_URL || "") + "/api";

export default function StudentsPage() {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [filter, setFilter] = useState({ class_id: "", section: "", q: "" });
  const [open, setOpen] = useState(false);
  const [credsFor, setCredsFor] = useState(null);
  const [editFor, setEditFor] = useState(null);
  const [sendFor, setSendFor] = useState(null);
  const navigate = useNavigate();

  const load = async () => {
    const params = {};
    if (filter.class_id) params.class_id = filter.class_id;
    if (filter.section) params.section = filter.section;
    if (filter.q) params.q = filter.q;
    const [s, c] = await Promise.all([
      api.get("/students", { params }).then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
    ]);
    setStudents(s); setClasses(c);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter.class_id, filter.section]);

  const sections = useMemo(() => {
    const c = classes.find((x) => x.id === filter.class_id);
    return c ? c.sections : [];
  }, [classes, filter.class_id]);

  const deactivate = async (s) => {
    if (!window.confirm(`Mark ${s.name} (${s.student_uid}) as inactive?`)) return;
    try {
      await api.delete(`/students/${s.id}`);
      toast.success("Student marked inactive");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const downloadSlip = async (s) => {
    try {
      const res = await api.get(`/students/${s.id}/credential-slip`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `credentials-${s.student_uid}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const exportClassCreds = async () => {
    if (!filter.class_id) { toast.error("Pick a class first"); return; }
    try {
      const res = await api.get("/uploads/parent-credentials", {
        params: { class_id: filter.class_id, section: filter.section || undefined },
        responseType: "blob",
      });
      const url = URL.createObjectURL(res.data);
      const cls = classes.find((c) => c.id === filter.class_id);
      const a = document.createElement("a");
      a.href = url; a.download = `parent-credentials-${(cls?.name || "class").replace(/\s+/g, "_")}${filter.section ? "-" + filter.section : ""}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <div data-testid="students-page">
      <PageHeader
        eyebrow="Students"
        title="Manage students & parents"
        subtitle="Add students manually or via Excel. Click any student to view their analytics."
        actions={
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={exportClassCreds} disabled={!filter.class_id} data-testid="bulk-export-creds-btn" title={filter.class_id ? "Download parent-creds Excel for this class" : "Pick a class first"}>
              <DownloadSimple size={14}/> Export creds
            </button>
            <button className="btn-primary" onClick={() => setOpen(true)} data-testid="add-student-btn"><Plus size={16}/> New student</button>
          </div>
        }
      />
      <div className="flex flex-wrap gap-3 mb-4">
        <div className="relative">
          <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
          <input
            className="input pl-8 w-64" placeholder="Search name or UID"
            value={filter.q}
            onChange={(e) => setFilter({ ...filter, q: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && load()}
            data-testid="students-search-input"
          />
        </div>
        <select className="input w-44" value={filter.class_id} onChange={(e) => setFilter({ ...filter, class_id: e.target.value, section: "" })} data-testid="students-class-filter">
          <option value="">All classes</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-32" value={filter.section} onChange={(e) => setFilter({ ...filter, section: e.target.value })} disabled={!filter.class_id} data-testid="students-section-filter">
          <option value="">All sections</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button className="btn-secondary" onClick={load} data-testid="students-apply-btn">Apply</button>
      </div>

      <Section title={`${students.length} students`}>
        {students.length > 0 && (() => {
          const linked = students.filter((s) => s.parent_telegram_linked).length;
          const unlinked = students.length - linked;
          const pct = students.length ? Math.round((linked / students.length) * 100) : 0;
          return (
            <div
              className="mb-3 flex flex-wrap items-center gap-3 p-3 rounded-md border border-line/60 bg-bg-subtle"
              data-testid="tg-reachability-summary"
            >
              <TelegramLogo size={20} weight="fill" className="text-sky-600" />
              <div className="text-sm">
                <span className="font-semibold">{linked}</span>
                <span className="text-ink-soft"> / {students.length} parents reachable on Telegram</span>
                <span className="ml-1 text-xs text-ink-muted">({pct}%)</span>
              </div>
              {unlinked > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                  {unlinked} not linked — cannot receive notifications
                </span>
              )}
            </div>
          );
        })()}
        {students.length === 0 ? <Empty title="No students yet" message="Add your first student to get started." /> :
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">UID</th><th className="th">Name</th><th className="th">Class</th>
                <th className="th">Section</th><th className="th">Roll</th><th className="th">Parent</th>
                <th className="th">Parent login</th>
                <th className="th" title="Whether the parent has linked their Telegram account (so they can receive notifications)">Telegram</th>
                <th className="th">Status</th>
                <th className="th">Actions</th>
              </tr></thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id} className="table-row" data-testid={`student-row-${s.student_uid}`}>
                    <td className="td font-mono text-xs cursor-pointer" onClick={() => navigate(`/student/${s.student_uid}`)}>{s.student_uid}</td>
                    <td className="td font-medium cursor-pointer" onClick={() => navigate(`/student/${s.student_uid}`)}>{s.name}</td>
                    <td className="td">{classes.find((c) => c.id === s.class_id)?.name || s.class_id}</td>
                    <td className="td">{s.section}</td>
                    <td className="td">{s.roll_number || "—"}</td>
                    <td className="td">{s.parent?.name} <div className="text-xs text-ink-muted">{s.parent?.phone}</div></td>
                    <td className="td">
                      <button
                        className="btn-secondary text-xs"
                        onClick={(e) => { e.stopPropagation(); setCredsFor(s); }}
                        title="View / reset parent login"
                        data-testid={`parent-login-btn-${s.student_uid}`}
                      ><Key size={12}/> Show login</button>
                    </td>
                    <td className="td" data-testid={`tg-status-cell-${s.student_uid}`}>
                      {s.parent_telegram_linked ? (
                        <span
                          className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800 border border-green-200"
                          title="Parent has linked their Telegram — they will receive school notifications."
                          data-testid={`tg-linked-${s.student_uid}`}
                        >
                          <TelegramLogo size={12} weight="fill" /> Linked
                        </span>
                      ) : (
                        <span
                          className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200"
                          title="Parent has NOT linked their Telegram — they cannot receive notifications until they scan/start the bot."
                          data-testid={`tg-unlinked-${s.student_uid}`}
                        >
                          <TelegramLogo size={12} /> Not linked
                        </span>
                      )}
                    </td>
                    <td className="td"><span className={s.status === "active" ? "badge-success" : "badge-neutral"}>{s.status}</span></td>
                    <td className="td">
                      <div className="flex gap-1 flex-wrap">
                        <button className="btn-secondary text-xs" onClick={() => setEditFor(s)} title="Edit / move section" data-testid={`edit-student-btn-${s.student_uid}`}>
                          <PencilSimple size={12}/>
                        </button>
                        <button className="btn-secondary text-xs" onClick={() => downloadSlip(s)} title="Download credential slip PDF" data-testid={`slip-btn-${s.student_uid}`}>
                          <FilePdf size={12}/>
                        </button>
                        <button className="btn-secondary text-xs" onClick={() => setSendFor(s)} title="Send credentials to parent" data-testid={`send-creds-btn-${s.student_uid}`}>
                          <PaperPlaneTilt size={12}/>
                        </button>
                        {s.status === "active" && (
                          <button className="btn-secondary text-xs text-status-danger" onClick={() => deactivate(s)} title="Mark inactive" data-testid={`deactivate-student-btn-${s.student_uid}`}>
                            <Trash size={12}/>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
      </Section>

      <CreateStudentModal classes={classes} open={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
      {credsFor && <ParentCredsModal student={credsFor} onClose={() => setCredsFor(null)} />}
      {editFor && (
        <EditStudentModal
          target={editFor}
          classes={classes}
          onClose={() => setEditFor(null)}
          onSaved={() => { setEditFor(null); load(); }}
        />
      )}
      {sendFor && (
        <SendCredsModal
          student={sendFor}
          onClose={() => setSendFor(null)}
          onSent={() => { setSendFor(null); load(); }}
        />
      )}
    </div>
  );
}

function EditStudentModal({ target, classes, onClose, onSaved }) {
  const [form, setForm] = useState({
    name: target.name || "",
    class_id: target.class_id,
    section: target.section,
    roll_number: target.roll_number || "",
    gender: target.gender || "M",
    dob: target.dob || "",
    emergency_contact: target.emergency_contact || "",
    medical_notes: target.medical_notes || "",
    status: target.status || "active",
  });
  const [busy, setBusy] = useState(false);
  const sections = classes.find((c) => c.id === form.class_id)?.sections || [];

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.patch(`/students/${target.id}`, form);
      toast.success("Student updated");
      onSaved();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`Edit student — ${target.name} (${target.student_uid})`} size="lg" testId="edit-student-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2"><label className="label">Name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="edit-student-name" /></div>
        <div>
          <label className="label">Class <span className="text-xs text-ink-muted">(teachers can only move within their assigned classes)</span></label>
          <select className="input" value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value, section: classes.find((c) => c.id === e.target.value)?.sections?.[0] || "A" })} data-testid="edit-student-class">
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Section</label>
          <select className="input" value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} data-testid="edit-student-section">
            {sections.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="label">Roll number</label><input className="input" value={form.roll_number} onChange={(e) => setForm({ ...form, roll_number: e.target.value })} /></div>
        <div>
          <label className="label">Gender</label>
          <select className="input" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
            <option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
          </select>
        </div>
        <div><label className="label">Date of birth</label><input className="input" type="date" value={form.dob} onChange={(e) => setForm({ ...form, dob: e.target.value })} /></div>
        <div><label className="label">Emergency contact</label><PhoneInput value={form.emergency_contact} onChange={(v) => setForm({ ...form, emergency_contact: v })} testId="edit-emergency" /></div>
        <div className="md:col-span-2"><label className="label">Medical notes</label><textarea className="input" rows={2} value={form.medical_notes} onChange={(e) => setForm({ ...form, medical_notes: e.target.value })} /></div>
        <div>
          <label className="label">Status</label>
          <select className="input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="edit-student-status">
            <option value="active">Active</option><option value="inactive">Inactive</option>
          </select>
        </div>
        <div className="md:col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="edit-student-submit">{busy ? "Saving…" : <><ArrowsLeftRight size={14}/> Save changes</>}</button>
        </div>
      </form>
    </Modal>
  );
}

function SendCredsModal({ student, onClose, onSent }) {
  const [channel, setChannel] = useState("telegram");
  const [resetFirst, setResetFirst] = useState(true);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post(`/students/${student.id}/send-credentials`, { channel, reset_first: resetFirst });
      if (data.delivery_status === "sent") {
        toast.success(`Credentials sent via ${channel}`);
      } else {
        toast(`Queued via ${channel} (${data.delivery_note || data.delivery_status})`, { icon: "ℹ️" });
      }
      onSent();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={`Send parent credentials — ${student.name}`} size="md" testId="send-creds-modal">
      <form onSubmit={submit} className="space-y-4">
        <div className="text-sm text-ink-soft">
          Send the parent's login credentials directly to their phone — no need to copy/paste manually.
        </div>
        <div>
          <label className="label">Channel</label>
          <div className="flex gap-2" data-testid="send-creds-channel">
            {["telegram", "whatsapp", "sms"].map((c) => (
              <button
                key={c} type="button" onClick={() => setChannel(c)}
                className={channel === c ? "badge bg-primary text-white cursor-pointer capitalize" : "badge-neutral cursor-pointer hover:bg-line capitalize"}
                data-testid={`send-creds-channel-${c}`}
              >{c}</button>
            ))}
          </div>
        </div>
        <label className="flex items-start gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={resetFirst} onChange={(e) => setResetFirst(e.target.checked)} data-testid="send-creds-reset-first" className="mt-0.5" />
          <span>
            <strong>Reset password to default first</strong>
            <span className="block text-xs text-ink-muted">The message will include the new default password (Parent@123). Recommended for first-time hand-off.</span>
          </span>
        </label>
        <div className="text-xs text-ink-muted">
          ⓘ Telegram requires the parent to have linked the bot. WhatsApp/SMS require provider configuration. If delivery isn't possible, the message is queued and you'll see it in the notifications log.
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="send-creds-submit">
            {busy ? "Sending…" : "Send now"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ParentCredsModal({ student, onClose }) {
  const [data, setData] = useState(null);
  const [tempPwd, setTempPwd] = useState(null); // only present right after a reset
  const [busy, setBusy] = useState(false);

  const fetchInfo = async () => {
    try {
      const { data } = await api.get(`/students/${student.id}/parent-login`);
      setData(data);
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };
  useEffect(() => { fetchInfo(); /* eslint-disable-next-line */ }, []);

  const reset = async () => {
    if (!window.confirm("Reset this parent's password to the default (Parent@123)? They'll need to use it on their next login.")) return;
    setBusy(true);
    try {
      const { data: r } = await api.post(`/students/${student.id}/parent-reset-password`);
      setTempPwd(r.default_password);
      toast.success(`Password reset. Share: ${r.email} / ${r.default_password}`);
      fetchInfo();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const copy = (txt) => {
    navigator.clipboard.writeText(txt).then(() => toast.success("Copied to clipboard"));
  };

  return (
    <Modal open onClose={onClose} title={`Parent login — ${student.name} (${student.student_uid})`} size="md" testId="parent-creds-modal">
      {!data ? <div className="py-8 text-center text-ink-muted">Loading…</div> : (
        <div className="space-y-4">
          <div className="p-3 bg-bg-subtle rounded-md border border-line/60">
            <div className="overline mb-1">Login email</div>
            <div className="flex items-center gap-2">
              <code className="text-sm font-mono flex-1 truncate" data-testid="parent-creds-email">{data.email || "—"}</code>
              {data.email && (
                <button type="button" className="btn-ghost p-1" onClick={() => copy(data.email)} title="Copy">
                  <Copy size={14}/>
                </button>
              )}
            </div>
            {data.phone && <div className="text-xs text-ink-muted mt-1">Phone on file: {data.phone}</div>}
          </div>

          <div
            className={
              "p-3 rounded-md border flex items-start gap-3 " +
              (data.telegram_linked
                ? "bg-green-50 border-green-200"
                : "bg-amber-50 border-amber-200")
            }
            data-testid="parent-creds-telegram-status"
          >
            <TelegramLogo size={22} weight={data.telegram_linked ? "fill" : "regular"} className={data.telegram_linked ? "text-green-700 mt-0.5" : "text-amber-700 mt-0.5"} />
            <div className="flex-1 text-sm">
              {data.telegram_linked ? (
                <>
                  <div className="font-semibold text-green-900 flex items-center gap-1">
                    <CheckCircle size={14} weight="fill" /> Telegram linked
                  </div>
                  <div className="text-xs text-green-800 mt-0.5">
                    This parent is reachable on Telegram and will receive all school notifications.
                    {data.telegram_linked_at && (
                      <> Linked on {new Date(data.telegram_linked_at).toLocaleDateString()}.</>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className="font-semibold text-amber-900 flex items-center gap-1">
                    <XCircle size={14} weight="fill" /> Telegram not linked
                  </div>
                  <div className="text-xs text-amber-800 mt-0.5">
                    Notifications cannot be delivered to this parent until they link Telegram. Ask them to open the school login page and tap “Link Telegram”, or scan the QR code on the credential-slip PDF.
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="text-sm text-ink-soft" data-testid="parent-creds-status">
            {data.last_login_at ? (
              <>✅ Parent has logged in (last login: {new Date(data.last_login_at).toLocaleString()}).
              {data.password_changed_at && <> Password was changed on {new Date(data.password_changed_at).toLocaleDateString()}.</>}</>
            ) : (
              <>⚠ Parent has <strong>not logged in yet</strong>. If they don't know the password, reset it to the default below.</>
            )}
          </div>

          {tempPwd && (
            <div className="border border-status-warning bg-status-warning-bg/40 rounded-md p-3" data-testid="parent-creds-temp-pwd">
              <div className="text-xs font-semibold text-status-warning mb-1">Share these credentials with the parent — they'll only be shown once</div>
              <div className="text-sm font-mono">
                <div>Email: <span className="font-bold">{data.email}</span></div>
                <div>Password: <span className="font-bold">{tempPwd}</span></div>
              </div>
              <button type="button" className="btn-secondary text-xs mt-2" onClick={() => copy(`${data.email} / ${tempPwd}`)}>
                <Copy size={12}/> Copy email + password
              </button>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-line">
            <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
            <button
              type="button"
              className="btn-primary"
              onClick={reset}
              disabled={busy}
              data-testid="parent-creds-reset-btn"
            >{busy ? "Resetting…" : "Reset to default password"}</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function CreateStudentModal({ classes, open, onClose, onCreated }) {
  const [form, setForm] = useState({
    name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
    parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" },
  });
  const [busy, setBusy] = useState(false);
  const [createdCreds, setCreatedCreds] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/students", form);
      toast.success("Student added");
      const pl = data.parent_login;
      if (pl && pl.is_new_account && pl.default_password) {
        setCreatedCreds({ email: pl.email, password: pl.default_password, student_name: data.name });
      } else {
        onCreated();
        setForm({ name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
          parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" } });
      }
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };
  const sections = classes.find((c) => c.id === form.class_id)?.sections || ["A"];

  const dismissCreds = () => {
    setCreatedCreds(null);
    onCreated();
    setForm({ name: "", class_id: "", section: "A", roll_number: "", gender: "M", dob: "",
      parent: { name: "", relationship: "father", phone: "", whatsapp: "", email: "" } });
  };

  if (createdCreds) {
    return (
      <Modal open onClose={dismissCreds} title="Parent login created" size="md" testId="parent-creds-just-created">
        <div className="space-y-4">
          <p className="text-sm text-ink-soft">
            Share these credentials with the parent of <strong>{createdCreds.student_name}</strong>. They can log in at this site to view marks, attendance and fees.
          </p>
          <div className="p-3 bg-bg-subtle rounded-md border border-line/60 font-mono text-sm space-y-1">
            <div>Login email: <strong data-testid="created-parent-email">{createdCreds.email}</strong></div>
            <div>Password: <strong data-testid="created-parent-password">{createdCreds.password}</strong></div>
          </div>
          <p className="text-xs text-ink-muted">
            ⓘ The password is the school default — parents can change it after first login from their profile.
          </p>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => {
              navigator.clipboard.writeText(`${createdCreds.email} / ${createdCreds.password}`);
              toast.success("Copied");
            }}><Copy size={14}/> Copy</button>
            <button className="btn-primary" onClick={dismissCreds} data-testid="dismiss-creds-btn">Done</button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal open={open} onClose={onClose} title="Add student" size="lg" testId="create-student-modal">
      <form onSubmit={submit} className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label className="label">Name</label><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="new-student-name" /></div>
        <div><label className="label">Class</label>
          <select className="input" required value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value, section: classes.find(c => c.id === e.target.value)?.sections?.[0] || "A" })} data-testid="new-student-class">
            <option value="">Select class</option>
            {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div><label className="label">Section</label>
          <select className="input" value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} data-testid="new-student-section">
            {sections.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div><label className="label">Roll number</label><input className="input" value={form.roll_number} onChange={(e) => setForm({ ...form, roll_number: e.target.value })} data-testid="new-student-roll" /></div>
        <div><label className="label">Gender</label>
          <select className="input" value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
            <option value="M">Male</option><option value="F">Female</option><option value="O">Other</option>
          </select>
        </div>
        <div><label className="label">Date of birth</label><input className="input" type="date" value={form.dob} onChange={(e) => setForm({ ...form, dob: e.target.value })} /></div>
        <div className="md:col-span-2 pt-2 border-t border-line"><div className="overline">Parent / Guardian</div>
          <div className="text-xs text-ink-muted mt-0.5">A login account will be created automatically. You can copy the credentials right after saving.</div>
        </div>
        <div><label className="label">Parent name</label><input className="input" required value={form.parent.name} onChange={(e) => setForm({ ...form, parent: { ...form.parent, name: e.target.value } })} data-testid="new-parent-name" /></div>
        <div><label className="label">Relationship</label>
          <select className="input" value={form.parent.relationship} onChange={(e) => setForm({ ...form, parent: { ...form.parent, relationship: e.target.value } })}>
            <option>father</option><option>mother</option><option>guardian</option>
          </select>
        </div>
        <div><label className="label">Phone</label><PhoneInput required value={form.parent.phone} onChange={(v) => setForm({ ...form, parent: { ...form.parent, phone: v } })} testId="new-parent-phone" /></div>
        <div><label className="label">WhatsApp</label><PhoneInput value={form.parent.whatsapp} onChange={(v) => setForm({ ...form, parent: { ...form.parent, whatsapp: v } })} testId="new-parent-whatsapp" /></div>
        <div className="md:col-span-2"><label className="label">Email (optional — leave blank to auto-generate a login email)</label><input className="input" type="email" value={form.parent.email} onChange={(e) => setForm({ ...form, parent: { ...form.parent, email: e.target.value } })} data-testid="new-parent-email" /></div>
        <div className="md:col-span-2 flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy} data-testid="submit-student-btn">{busy ? "Adding…" : "Add student"}</button>
        </div>
      </form>
    </Modal>
  );
}
