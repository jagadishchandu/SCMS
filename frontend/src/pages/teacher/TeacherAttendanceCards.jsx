import React, { useEffect, useState, useMemo } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { Check, X, MinusCircle, ArrowLeft, ArrowRight, CheckCircle, UserCircle } from "@phosphor-icons/react";
import toast from "react-hot-toast";

const STATUS_OPTIONS = [
  { value: "present", label: "Present", color: "bg-status-success text-white", icon: Check },
  { value: "absent", label: "Absent", color: "bg-status-danger text-white", icon: X },
  { value: "not_in_class", label: "Not in class", color: "bg-status-warning text-white", icon: MinusCircle },
];

export default function TeacherAttendanceCards() {
  const [classes, setClasses] = useState([]);
  const [sel, setSel] = useState({ class_id: "", section: "", date: new Date().toISOString().slice(0, 10) });
  const [students, setStudents] = useState([]);
  const [entries, setEntries] = useState({});
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState("pick");  // pick | take | done
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.get("/academic/classes").then((r) => setClasses(r.data)); }, []);
  const sections = useMemo(() => classes.find((c) => c.id === sel.class_id)?.sections || [], [classes, sel.class_id]);

  const start = async () => {
    if (!sel.class_id || !sel.section) { toast.error("Pick class and section"); return; }
    try {
      const [s, a] = await Promise.all([
        api.get("/students", { params: { class_id: sel.class_id, section: sel.section } }).then((r) => r.data),
        api.get("/attendance", { params: { class_id: sel.class_id, section: sel.section, date: sel.date } }).then((r) => r.data),
      ]);
      if (!s.length) { toast.error("No students in this class/section"); return; }
      const existing = Object.fromEntries(a.map((r) => [r.student_id, r.status]));
      setStudents(s);
      setEntries(existing);
      setIdx(0);
      setPhase("take");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const setStatus = (status) => {
    setEntries((e) => ({ ...e, [students[idx].id]: status }));
    if (idx + 1 < students.length) setIdx(idx + 1);
    else setPhase("done");
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        class_id: sel.class_id, section: sel.section, date: sel.date,
        entries: students.map((s) => ({ student_id: s.id, status: entries[s.id] || "present" })),
      };
      const { data } = await api.post("/attendance/bulk", payload);
      toast.success(`Saved ${data.marked} entries · ${data.notifications} parent alerts queued`);
      setPhase("pick");
      setStudents([]); setEntries({}); setIdx(0);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  if (phase === "pick") {
    return (
      <div data-testid="teacher-att-cards">
        <PageHeader eyebrow="Attendance · cards" title="Take attendance, one student at a time"
          subtitle="Mobile-friendly card flow. Tap Present, Absent, or Not in class for each student." />
        <div className="card max-w-md">
          <div className="space-y-4">
            <div>
              <label className="label">Class</label>
              <select className="input" value={sel.class_id} onChange={(e) => setSel({ ...sel, class_id: e.target.value, section: "" })} data-testid="tac-class">
                <option value="">Select class…</option>
                {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Section</label>
              <select className="input" value={sel.section} onChange={(e) => setSel({ ...sel, section: e.target.value })} disabled={!sel.class_id} data-testid="tac-section">
                <option value="">Select section…</option>
                {sections.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Date</label>
              <input className="input" type="date" value={sel.date} onChange={(e) => setSel({ ...sel, date: e.target.value })} data-testid="tac-date" />
            </div>
            <button className="btn-primary w-full" onClick={start} data-testid="tac-start-btn">Start taking attendance →</button>
          </div>
        </div>
      </div>
    );
  }

  if (phase === "done") {
    const counts = students.reduce((acc, s) => {
      const st = entries[s.id] || "present"; acc[st] = (acc[st] || 0) + 1; return acc;
    }, {});
    return (
      <div data-testid="teacher-att-cards-done">
        <PageHeader eyebrow="Review" title="Review and submit"
          subtitle="Tap Save to record attendance. Parents will be auto-notified for absent and sick statuses." />
        <div className="grid grid-cols-3 gap-3 mb-4 max-w-md">
          <div className="card text-center"><div className="overline">Present</div><div className="font-display text-2xl">{counts.present || 0}</div></div>
          <div className="card text-center"><div className="overline">Absent</div><div className="font-display text-2xl">{counts.absent || 0}</div></div>
          <div className="card text-center"><div className="overline">Not in class</div><div className="font-display text-2xl">{counts.not_in_class || 0}</div></div>
        </div>
        <div className="panel max-w-md mb-4">
          <ul className="divide-y divide-line max-h-80 overflow-y-auto">
            {students.map((s, i) => (
              <li key={s.id} className="flex items-center justify-between px-4 py-2 text-sm" data-testid={`tac-review-${s.student_uid}`}>
                <div><span className="font-medium">{s.name}</span> <span className="text-ink-muted text-xs">· {s.student_uid}</span></div>
                <button className="badge-neutral" onClick={() => { setIdx(i); setPhase("take"); }}>
                  {entries[s.id] || "present"}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex gap-2 max-w-md">
          <button className="btn-secondary flex-1" onClick={() => { setPhase("take"); setIdx(0); }} data-testid="tac-back-btn">← Back</button>
          <button className="btn-primary flex-1" onClick={save} disabled={saving} data-testid="tac-save-btn">{saving ? "Saving…" : "Save attendance"}</button>
        </div>
      </div>
    );
  }

  // phase === "take"
  const student = students[idx];
  const current = entries[student.id];
  return (
    <div data-testid="teacher-att-cards-take">
      <PageHeader eyebrow="Attendance · cards" title={`Student ${idx + 1} of ${students.length}`}
        subtitle={`${classes.find((c) => c.id === sel.class_id)?.name} · Section ${sel.section} · ${sel.date}`} />

      <div className="max-w-md mx-auto">
        <div className="w-full bg-bg-subtle rounded-full h-1 mb-6">
          <div className="bg-primary h-1 rounded-full transition-all" style={{ width: `${((idx + 1) / students.length) * 100}%` }} />
        </div>

        <div className="card flex flex-col items-center text-center py-10" data-testid="tac-student-card">
          <div className="w-24 h-24 rounded-full overflow-hidden bg-bg-subtle grid place-items-center mb-4 border border-line">
            {student.photo ? <img src={student.photo} alt={student.name} className="w-full h-full object-cover" /> : <UserCircle size={56} className="text-ink-muted" />}
          </div>
          <div className="overline">{student.student_uid}</div>
          <h2 className="font-display text-2xl font-medium mt-1" data-testid="tac-student-name">{student.name}</h2>
          <div className="text-sm text-ink-soft">Roll #{student.roll_number || "—"}</div>
          {current && (
            <div className="mt-3 text-xs">
              Currently: <span className={`badge-${current === "present" ? "success" : current === "absent" ? "danger" : "warning"}`}>{current}</span>
            </div>
          )}
        </div>

        <div className="grid grid-cols-3 gap-2 mt-5">
          {STATUS_OPTIONS.map((o) => {
            const Icon = o.icon;
            return (
              <button
                key={o.value}
                className={`${o.color} rounded-lg py-5 flex flex-col items-center gap-2 font-medium hover:opacity-90 active:scale-95 transition`}
                onClick={() => setStatus(o.value)}
                data-testid={`tac-status-${o.value}`}
              >
                <Icon size={28} weight="bold" />
                <span className="text-xs">{o.label}</span>
              </button>
            );
          })}
        </div>

        <div className="flex justify-between items-center mt-5">
          <button className="btn-ghost" onClick={() => setIdx(Math.max(0, idx - 1))} disabled={idx === 0} data-testid="tac-prev-btn">
            <ArrowLeft size={14}/> Previous
          </button>
          <button className="btn-ghost" onClick={() => idx + 1 < students.length ? setIdx(idx + 1) : setPhase("done")} data-testid="tac-skip-btn">
            Skip / Next <ArrowRight size={14}/>
          </button>
        </div>

        <button className="btn-secondary w-full mt-3" onClick={() => setPhase("done")} data-testid="tac-finish-btn">
          <CheckCircle size={14}/> Finish &amp; review
        </button>
      </div>
    </div>
  );
}
