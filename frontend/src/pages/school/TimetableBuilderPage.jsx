import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import toast from "react-hot-toast";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat"];
const DAY_LABEL = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat" };
const CATEGORIES = [
  { value: "regular", label: "Regular" },
  { value: "heavy", label: "Heavy (Math, Sci)" },
  { value: "light", label: "Light" },
  { value: "lab", label: "Lab" },
  { value: "sports", label: "Sports" },
  { value: "library", label: "Library" },
];

const CAT_TINT = {
  heavy: "bg-status-danger/10 border-status-danger/40 text-status-danger",
  lab: "bg-status-info/10 border-status-info/40 text-status-info",
  sports: "bg-status-success/10 border-status-success/40 text-status-success",
  library: "bg-status-warning/10 border-status-warning/40 text-status-warning",
  light: "bg-bg-subtle border-line text-ink-soft",
  regular: "bg-bg border-line text-ink-soft",
};

function chunk(arr, n) {
  const out = [];
  for (let i = 0; i < arr.length; i += n) out.push(arr.slice(i, i + n));
  return out;
}

export default function TimetableBuilderPage() {
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);

  // Global defaults
  const [cfg, setCfg] = useState({
    days: ["mon", "tue", "wed", "thu", "fri"],
    periods_per_day: 7,
    start_time: "08:30",
    period_minutes: 45,
    lunch_break_period: 4,
    fixed_breaks: [],
    max_consecutive_heavy: 2,
    max_periods_per_day_per_teacher: "", // empty = unlimited
    no_last_period_subjects: [],
    subject_categories: {},          // {sid: "heavy"|...}
    allowed_periods_per_subject: {}, // {sid: [periods]}
    subject_periods: {},             // {sid: int}
    subject_day_pins: {},            // {sid: [days]}
  });

  // locked_assignments per section: { [`${class_id}|${section}|${day}|${period}`]: {teacher_id, subject_id} }
  const [locks, setLocks] = useState({});
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState(null);

  // Section list (each row: {class_id, section, student_count, class_teacher: {teacher_id, period}})
  const [sections, setSections] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [view, setView] = useState("sections"); // sections | teachers | conflicts

  useEffect(() => {
    Promise.all([
      api.get("/academic/classes").then((r) => r.data),
      api.get("/academic/subjects").then((r) => r.data),
      api.get("/users", { params: { role: "teacher" } }).then((r) => r.data),
    ]).then(([c, s, t]) => {
      setClasses(c); setSubjects(s); setTeachers(t);
      // Default: include every class+section once
      const initial = [];
      for (const cls of c) {
        for (const sec of (cls.sections || [])) {
          initial.push({ class_id: cls.id, section: sec, student_count: "", class_teacher_id: "", class_teacher_period: "" });
        }
      }
      setSections(initial);
    });
  }, []);

  const subjectMap = useMemo(() => Object.fromEntries(subjects.map((s) => [s.id, s])), [subjects]);
  const teacherMap = useMemo(() => Object.fromEntries(teachers.map((t) => [t.id, t])), [teachers]);
  const classMap = useMemo(() => Object.fromEntries(classes.map((c) => [c.id, c])), [classes]);

  const teachingPeriods = useMemo(() => {
    const breaks = new Set([cfg.lunch_break_period, ...cfg.fixed_breaks.map((b) => b.period)].filter(Boolean));
    return Array.from({ length: cfg.periods_per_day }, (_, i) => i + 1).filter((p) => !breaks.has(p));
  }, [cfg.periods_per_day, cfg.lunch_break_period, cfg.fixed_breaks]);

  // Subject row helpers
  const setSubjectCategory = (sid, cat) => {
    setCfg((c) => ({ ...c, subject_categories: { ...c.subject_categories, [sid]: cat } }));
  };
  const togglePeriodForSubject = (sid, period) => {
    setCfg((c) => {
      const current = c.allowed_periods_per_subject[sid] || [];
      const next = current.includes(period) ? current.filter((p) => p !== period) : [...current, period];
      return { ...c, allowed_periods_per_subject: { ...c.allowed_periods_per_subject, [sid]: next } };
    });
  };
  const setSubjectFrequency = (sid, n) => {
    setCfg((c) => {
      const next = { ...c.subject_periods };
      if (n === "" || n == null) delete next[sid];
      else next[sid] = Number(n) || 0;
      return { ...c, subject_periods: next };
    });
  };
  const toggleNoLast = (sid) => {
    setCfg((c) => {
      const arr = c.no_last_period_subjects.includes(sid)
        ? c.no_last_period_subjects.filter((x) => x !== sid)
        : [...c.no_last_period_subjects, sid];
      return { ...c, no_last_period_subjects: arr };
    });
  };

  // Section manipulators
  const toggleSection = (class_id, section) => {
    const idx = sections.findIndex((s) => s.class_id === class_id && s.section === section);
    if (idx >= 0) setSections(sections.filter((_, i) => i !== idx));
    else setSections([...sections, { class_id, section, student_count: "", class_teacher_id: "", class_teacher_period: "" }]);
  };
  const updateSection = (idx, patch) => {
    setSections((arr) => arr.map((s, i) => (i === idx ? { ...s, ...patch } : s)));
  };

  const buildPayload = () => {
    const fixed_breaks = (cfg.fixed_breaks || []).filter((b) => b.period >= 1 && b.period <= cfg.periods_per_day);
    const defaults = {
      class_id: "_",
      section: "_",
      days: cfg.days,
      periods_per_day: cfg.periods_per_day,
      start_time: cfg.start_time,
      period_minutes: cfg.period_minutes,
      lunch_break_period: cfg.lunch_break_period || null,
      fixed_breaks: fixed_breaks.length ? fixed_breaks : undefined,
      max_consecutive_heavy: cfg.max_consecutive_heavy,
      max_periods_per_day_per_teacher:
        cfg.max_periods_per_day_per_teacher !== "" && cfg.max_periods_per_day_per_teacher != null
          ? Number(cfg.max_periods_per_day_per_teacher)
          : undefined,
      no_last_period_subjects: cfg.no_last_period_subjects.length ? cfg.no_last_period_subjects : undefined,
      subject_categories: Object.keys(cfg.subject_categories).length ? cfg.subject_categories : undefined,
      allowed_periods_per_subject:
        Object.keys(cfg.allowed_periods_per_subject).length
          ? Object.fromEntries(Object.entries(cfg.allowed_periods_per_subject).filter(([, v]) => v && v.length))
          : undefined,
      subject_periods: Object.keys(cfg.subject_periods).length ? cfg.subject_periods : undefined,
      subject_day_pins:
        Object.keys(cfg.subject_day_pins).length
          ? Object.fromEntries(Object.entries(cfg.subject_day_pins).filter(([, v]) => v && v.length))
          : undefined,
    };
    const sectionPayload = sections.map((s) => {
      const out = {
        class_id: s.class_id,
        section: s.section,
      };
      if (s.student_count !== "" && s.student_count != null) out.student_count = Number(s.student_count);
      if (s.class_teacher_id && s.class_teacher_period) {
        out.class_teacher = {
          teacher_id: s.class_teacher_id,
          period: Number(s.class_teacher_period),
          label: "Class Teacher",
        };
      }
      // Per-section locks
      const secLocks = Object.entries(locks)
        .filter(([k]) => k.startsWith(`${s.class_id}|${s.section}|`))
        .map(([k, v]) => {
          const [, , day, period] = k.split("|");
          return { day, period: Number(period), teacher_id: v.teacher_id, subject_id: v.subject_id || undefined };
        })
        .filter((l) => l.teacher_id);
      if (secLocks.length) out.locked_assignments = secLocks;
      return out;
    });
    return { defaults, sections: sectionPayload, reset_existing: true };
  };

  const generate = async () => {
    if (sections.length === 0) {
      toast.error("Select at least one section");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post("/timetable/suggest-batch", buildPayload());
      setResult(data);
      toast.success(`Generated ${data.sections.length} section(s)`);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const saveAll = async () => {
    if (!result) return;
    setSaving(true);
    try {
      const payload = {
        sections: result.sections.map((s) => ({
          class_id: s.class_id,
          section: s.section,
          slots: s.slots.filter((sl) => sl.is_break || sl.teacher_id),
        })),
      };
      const { data } = await api.post("/timetable/save-batch", payload);
      toast.success(`Saved ${data.inserted} slots across ${data.sections_saved} sections`);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const publishToTelegram = async () => {
    if (!window.confirm("Publish the saved timetable as a PDF to teachers and parents via Telegram?")) return;
    setPublishing(true);
    setPublishResult(null);
    try {
      const class_ids = Array.from(new Set(sections.map((s) => s.class_id)));
      const { data } = await api.post("/timetable/publish", { class_ids, audiences: ["teachers", "parents"] });
      setPublishResult(data);
      const ts = data.teachers_sent || 0, tt = data.teachers_total || 0;
      const ps = data.parents_sent || 0, pt = data.parents_total || 0;
      toast.success(`Published — teachers ${ts}/${tt}, parents ${ps}/${pt}`);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setPublishing(false);
    }
  };

  const setLockForSlot = (class_id, section, day, period, teacher_id, subject_id) => {
    const key = `${class_id}|${section}|${day}|${period}`;
    setLocks((prev) => {
      const next = { ...prev };
      if (!teacher_id) {
        delete next[key];
      } else {
        next[key] = { teacher_id, subject_id: subject_id || "" };
      }
      return next;
    });
  };
  const clearLock = (class_id, section, day, period) => setLockForSlot(class_id, section, day, period, null);

  return (
    <div data-testid="timetable-builder-page">
      <PageHeader
        eyebrow="Auto-scheduler"
        title="Weekly timetable builder"
        subtitle="Generate conflict-free timetables across multiple grades and sections in one shot. Configure constraints, then save when satisfied."
        actions={
          <>
            <button onClick={generate} disabled={loading} className="btn-primary" data-testid="builder-generate-btn">
              {loading ? "Generating…" : "Generate timetable"}
            </button>
            {result && (
              <button onClick={saveAll} disabled={saving} className="btn-secondary" data-testid="builder-save-btn">
                {saving ? "Saving…" : "Save all sections"}
              </button>
            )}
            {result && (
              <button onClick={publishToTelegram} disabled={publishing} className="btn-ghost"
                data-testid="builder-publish-btn">
                {publishing ? "Publishing…" : "📤 Publish to Telegram"}
              </button>
            )}
          </>
        }
      />

      {/* Configuration */}
      <Section title="Global configuration">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <div>
            <label className="label">Periods / day</label>
            <input type="number" min={1} max={12} className="input" value={cfg.periods_per_day}
              onChange={(e) => setCfg({ ...cfg, periods_per_day: Number(e.target.value) || 1 })} data-testid="cfg-periods" />
          </div>
          <div>
            <label className="label">Start time</label>
            <input type="time" className="input" value={cfg.start_time}
              onChange={(e) => setCfg({ ...cfg, start_time: e.target.value })} data-testid="cfg-start" />
          </div>
          <div>
            <label className="label">Period length (min)</label>
            <input type="number" min={15} max={120} className="input" value={cfg.period_minutes}
              onChange={(e) => setCfg({ ...cfg, period_minutes: Number(e.target.value) || 45 })} data-testid="cfg-duration" />
          </div>
          <div>
            <label className="label">Lunch period</label>
            <select className="input" value={cfg.lunch_break_period || ""}
              onChange={(e) => setCfg({ ...cfg, lunch_break_period: e.target.value ? Number(e.target.value) : null })} data-testid="cfg-lunch">
              <option value="">None</option>
              {Array.from({ length: cfg.periods_per_day }, (_, i) => i + 1).map((p) => (
                <option key={p} value={p}>Period {p}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Max heavy in a row</label>
            <input type="number" min={1} max={8} className="input" value={cfg.max_consecutive_heavy}
              onChange={(e) => setCfg({ ...cfg, max_consecutive_heavy: Number(e.target.value) || 2 })} data-testid="cfg-heavy-cap" />
          </div>
          <div>
            <label className="label">Max periods/day per teacher</label>
            <input type="number" min={1} max={12} className="input" placeholder="No cap"
              value={cfg.max_periods_per_day_per_teacher}
              onChange={(e) => setCfg({ ...cfg, max_periods_per_day_per_teacher: e.target.value })}
              data-testid="cfg-max-ppd-teacher" />
          </div>
          <div className="md:col-span-3">
            <label className="label">Working days</label>
            <div className="flex flex-wrap gap-2">
              {DAYS.map((d) => (
                <button key={d} type="button" data-testid={`cfg-day-${d}`}
                  onClick={() => setCfg({ ...cfg, days: cfg.days.includes(d) ? cfg.days.filter((x) => x !== d) : [...cfg.days, d] })}
                  className={"px-3 py-1 rounded-md border text-xs uppercase tracking-wider " +
                    (cfg.days.includes(d) ? "bg-primary text-primary-foreground border-primary" : "border-line text-ink-soft")}>
                  {DAY_LABEL[d]}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Fixed breaks */}
        <div className="mb-4">
          <label className="label">Additional fixed breaks (assembly, snack, etc.)</label>
          <div className="flex flex-wrap items-center gap-2">
            {cfg.fixed_breaks.map((b, i) => (
              <span key={i} className="inline-flex items-center gap-2 px-2 py-1 rounded-md border border-line text-xs"
                data-testid={`cfg-break-${i}`}>
                P{b.period} · {b.label || "Break"}
                <button onClick={() => setCfg({ ...cfg, fixed_breaks: cfg.fixed_breaks.filter((_, ix) => ix !== i) })} className="text-status-danger">×</button>
              </span>
            ))}
            <FixedBreakAdder onAdd={(b) => setCfg({ ...cfg, fixed_breaks: [...cfg.fixed_breaks, b] })} maxPeriod={cfg.periods_per_day} />
          </div>
        </div>
      </Section>

      {/* Subject constraints matrix */}
      <Section title="Subject constraints">
        <div className="overflow-x-auto">
          <table className="table" data-testid="subject-constraints-table">
            <thead>
              <tr>
                <th className="th">Subject</th>
                <th className="th">Category</th>
                <th className="th">Periods/week</th>
                <th className="th">Allowed periods</th>
                <th className="th">No last period</th>
              </tr>
            </thead>
            <tbody>
              {subjects.map((s) => {
                const cat = cfg.subject_categories[s.id] || "regular";
                const allowed = cfg.allowed_periods_per_subject[s.id] || [];
                const freq = cfg.subject_periods[s.id] ?? "";
                return (
                  <tr key={s.id} className="table-row" data-testid={`subj-row-${s.id}`}>
                    <td className="td font-medium">{s.name}</td>
                    <td className="td">
                      <select className={"input text-xs " + (CAT_TINT[cat] || "")} value={cat}
                        onChange={(e) => setSubjectCategory(s.id, e.target.value)} data-testid={`subj-cat-${s.id}`}>
                        {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                      </select>
                    </td>
                    <td className="td">
                      <input type="number" min={0} className="input w-20" value={freq}
                        onChange={(e) => setSubjectFrequency(s.id, e.target.value)}
                        placeholder="auto" data-testid={`subj-freq-${s.id}`} />
                    </td>
                    <td className="td">
                      <div className="flex flex-wrap gap-1">
                        {Array.from({ length: cfg.periods_per_day }, (_, i) => i + 1).map((p) => {
                          const isBreak = p === cfg.lunch_break_period || cfg.fixed_breaks.some((b) => b.period === p);
                          if (isBreak) return null;
                          const on = allowed.includes(p);
                          const restricted = allowed.length > 0;
                          return (
                            <button key={p} type="button"
                              onClick={() => togglePeriodForSubject(s.id, p)}
                              data-testid={`subj-${s.id}-allow-p${p}`}
                              className={"w-7 h-7 text-[10px] rounded border " +
                                (on ? "bg-primary text-primary-foreground border-primary"
                                    : restricted ? "border-dashed border-line text-ink-muted line-through"
                                    : "border-line text-ink-soft hover:bg-bg-subtle")}>
                              {p}
                            </button>
                          );
                        })}
                        {allowed.length > 0 && (
                          <button onClick={() => setCfg({ ...cfg, allowed_periods_per_subject: { ...cfg.allowed_periods_per_subject, [s.id]: [] } })}
                            className="text-[10px] text-ink-muted underline ml-1" data-testid={`subj-${s.id}-clear`}>
                            clear
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="td">
                      <label className="inline-flex items-center gap-2 text-xs">
                        <input type="checkbox" checked={cfg.no_last_period_subjects.includes(s.id)}
                          onChange={() => toggleNoLast(s.id)} data-testid={`subj-${s.id}-no-last`} />
                        Avoid last
                      </label>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="text-[11px] text-ink-muted mt-2">
          Leave Periods/week blank to auto-distribute. Allowed-periods: click to whitelist (e.g. Sports only in periods 5–6). Heavy subjects respect the “max in a row” cap above.
        </div>
      </Section>

      {/* Sections list */}
      <Section title={`Sections to generate (${sections.length} selected)`}>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {classes.map((c) => (
            <div key={c.id} className="border border-line rounded-md p-3" data-testid={`class-card-${c.id}`}>
              <div className="font-medium mb-2">{c.name}</div>
              <div className="flex flex-wrap gap-2 mb-3">
                {(c.sections || []).map((sec) => {
                  const on = sections.some((s) => s.class_id === c.id && s.section === sec);
                  return (
                    <button key={sec} type="button"
                      onClick={() => toggleSection(c.id, sec)}
                      data-testid={`toggle-${c.id}-${sec}`}
                      className={"px-3 py-1 rounded-md border text-xs " +
                        (on ? "bg-primary text-primary-foreground border-primary" : "border-line text-ink-soft hover:bg-bg-subtle")}>
                      Section {sec}
                    </button>
                  );
                })}
              </div>
              {sections.filter((s) => s.class_id === c.id).map((s) => {
                const idx = sections.indexOf(s);
                return (
                  <div key={s.section} className="text-xs grid grid-cols-3 gap-2 items-center mb-2" data-testid={`section-row-${c.id}-${s.section}`}>
                    <div className="font-medium">Section {s.section}</div>
                    <input type="number" min={0} className="input text-xs" placeholder="# students"
                      value={s.student_count} onChange={(e) => updateSection(idx, { student_count: e.target.value })}
                      data-testid={`students-${c.id}-${s.section}`} />
                    <div className="flex gap-1">
                      <select className="input text-xs" value={s.class_teacher_id}
                        onChange={(e) => updateSection(idx, { class_teacher_id: e.target.value })}
                        data-testid={`ct-teacher-${c.id}-${s.section}`}>
                        <option value="">CT teacher…</option>
                        {teachers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                      </select>
                      <select className="input text-xs w-16" value={s.class_teacher_period}
                        onChange={(e) => updateSection(idx, { class_teacher_period: e.target.value })}
                        disabled={!s.class_teacher_id}
                        data-testid={`ct-period-${c.id}-${s.section}`}>
                        <option value="">P…</option>
                        {teachingPeriods.map((p) => <option key={p} value={p}>P{p}</option>)}
                      </select>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </Section>

      {/* Result */}
      {result && (
        <Section
          title="Generated timetable"
          action={
            <div className="flex gap-2">
              {["sections", "teachers", "conflicts"].map((v) => (
                <button key={v} onClick={() => setView(v)}
                  className={"text-xs px-3 py-1 rounded-md border " +
                    (view === v ? "bg-primary text-primary-foreground border-primary" : "border-line text-ink-soft")}
                  data-testid={`view-${v}`}>
                  {v === "sections" ? "Sections" : v === "teachers" ? "Teacher view" : `Conflicts (${(result.conflict_summary.unfilled_slots.length || 0) + (result.conflict_summary.double_bookings.length || 0)})`}
                </button>
              ))}
            </div>
          }
        >
          {view === "sections" && (
            <div className="space-y-6">
              {result.sections.map((s) => (
                <SectionGrid
                  key={`${s.class_id}-${s.section}`}
                  sec={s}
                  subjectMap={subjectMap}
                  teacherMap={teacherMap}
                  teachers={teachers}
                  subjects={subjects}
                  locks={locks}
                  setLock={setLockForSlot}
                  clearLock={clearLock}
                />
              ))}
            </div>
          )}
          {view === "teachers" && (
            <TeacherView teacher_view={result.teacher_view} subjectMap={subjectMap} classMap={classMap} days={cfg.days} periodsPerDay={cfg.periods_per_day} />
          )}
          {view === "conflicts" && (
            <ConflictPanel summary={result.conflict_summary} suggestions={result.optimization_suggestions} />
          )}
        </Section>
      )}
      {publishResult && (
        <Section title="Publish report">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3" data-testid="publish-report">
            <div className="border border-line rounded-md p-3">
              <div className="overline mb-1">Teachers</div>
              <div className="text-2xl font-display">{publishResult.teachers_sent}/{publishResult.teachers_total}</div>
              <div className="text-xs text-ink-muted">sent · {publishResult.teachers_failed} failed</div>
            </div>
            <div className="border border-line rounded-md p-3">
              <div className="overline mb-1">Parents</div>
              <div className="text-2xl font-display">{publishResult.parents_sent}/{publishResult.parents_total}</div>
              <div className="text-xs text-ink-muted">sent · {publishResult.parents_failed} failed</div>
            </div>
          </div>
          {publishResult.failures?.length > 0 && (
            <div className="text-xs">
              <div className="overline mb-1">Failures (first {publishResult.failures.length}{publishResult.failures_truncated ? ` of ${publishResult.failures.length + publishResult.failures_truncated}` : ""})</div>
              <ul className="space-y-1 text-ink-soft" data-testid="publish-failures">
                {publishResult.failures.slice(0, 20).map((f, i) => (
                  <li key={i}>
                    • {f.name || f.teacher_id || f.parent_id}
                    {f.student_uid ? ` (${f.student_uid})` : ""} — <span className="italic">{f.reason}</span>
                  </li>
                ))}
              </ul>
              {publishResult.failures.some((f) => f.reason === "telegram_not_linked") && (
                <div className="mt-2 text-[11px] text-ink-muted">
                  Tip: ask recipients to link Telegram from their profile page so they receive their PDFs automatically.
                </div>
              )}
            </div>
          )}
        </Section>
      )}
      {!result && !loading && (
        <Empty title="Configure constraints and click Generate" message="The engine will produce a timetable per section, plus a teacher-wise view and a conflict report." />
      )}
    </div>
  );
}

function FixedBreakAdder({ onAdd, maxPeriod }) {
  const [p, setP] = useState("");
  const [lbl, setLbl] = useState("");
  return (
    <div className="inline-flex items-center gap-1 border border-dashed border-line rounded-md px-2 py-1">
      <input type="number" min={1} max={maxPeriod} placeholder="P#" className="input w-14 text-xs"
        value={p} onChange={(e) => setP(e.target.value)} data-testid="cfg-new-break-period" />
      <input placeholder="Label" className="input w-28 text-xs"
        value={lbl} onChange={(e) => setLbl(e.target.value)} data-testid="cfg-new-break-label" />
      <button onClick={() => { if (p) { onAdd({ period: Number(p), label: lbl || "Break" }); setP(""); setLbl(""); } }}
        className="text-xs text-primary px-1" data-testid="cfg-new-break-add">+ Add</button>
    </div>
  );
}

function SectionGrid({ sec, subjectMap, teacherMap, teachers, subjects, locks, setLock, clearLock }) {
  const periods = Array.from(new Set(sec.slots.map((s) => s.period))).sort((a, b) => a - b);
  const grid = {};
  for (const sl of sec.slots) {
    grid[sl.day] = grid[sl.day] || {};
    grid[sl.day][sl.period] = sl;
  }
  const days = Object.keys(grid);
  const dayOrder = ["mon", "tue", "wed", "thu", "fri", "sat"];
  const orderedDays = dayOrder.filter((d) => days.includes(d));

  const [subBusyKey, setSubBusyKey] = useState(null);
  const [subSuggestions, setSubSuggestions] = useState({}); // {`${d}|${p}`: [{teacher_id, teacher_name, …}]}

  const fetchSuggestions = async (d, p, subj_id) => {
    const k = `${d}|${p}`;
    setSubBusyKey(k);
    try {
      const { data } = await api.post("/timetable/substitute-suggest", {
        class_id: sec.class_id, section: sec.section,
        day: d, period: p, prefer_subject_id: subj_id || undefined,
      });
      setSubSuggestions((prev) => ({ ...prev, [k]: data.suggestions || [] }));
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSubBusyKey(null);
    }
  };

  const applySub = async (d, p, subj_id, teacher_id) => {
    try {
      await api.post("/timetable/substitute-apply", {
        class_id: sec.class_id, section: sec.section,
        day: d, period: p, teacher_id, subject_id: subj_id || undefined, notify: true,
      });
      toast.success("Substitute applied & notified");
      // Patch local view so the cell updates without a regenerate
      const sl = grid[d][p];
      if (sl) {
        sl.teacher_id = teacher_id;
        sl.is_substitute = true;
      }
      setSubSuggestions((prev) => ({ ...prev, [`${d}|${p}`]: [] }));
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };

  return (
    <div data-testid={`section-grid-${sec.class_id}-${sec.section}`}>
      <div className="flex items-baseline gap-3 mb-2">
        <div className="font-display text-lg font-medium">{sec.class_name} · Section {sec.section}</div>
        <div className="text-xs text-ink-muted">{sec.total_teaching_slots} teaching slots</div>
        {sec.student_count != null && <div className="text-xs text-ink-muted">{sec.student_count} students</div>}
        {sec.repair_stats && (sec.repair_stats.swap_repairs || sec.repair_stats.substitute_repairs) ? (
          <div className="text-[11px] text-status-info" data-testid={`sec-repair-${sec.class_id}-${sec.section}`}>
            🔧 {sec.repair_stats.swap_repairs} swap{sec.repair_stats.swap_repairs !== 1 ? "s" : ""} · {sec.repair_stats.substitute_repairs} substitute{sec.repair_stats.substitute_repairs !== 1 ? "s" : ""}
          </div>
        ) : null}
        {sec.warnings?.length > 0 && (
          <div className="text-xs text-status-warning" data-testid={`sec-warn-${sec.class_id}-${sec.section}`}>
            ⚠ {sec.warnings.length} warning(s)
          </div>
        )}
        <div className="text-[11px] text-ink-muted ml-auto">💡 Click an unfilled cell → "Find substitute"; click any cell → "Lock…"</div>
      </div>
      <div className="overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th className="th">Day</th>
              {periods.map((p) => <th key={p} className="th text-center">P{p}</th>)}
            </tr>
          </thead>
          <tbody>
            {orderedDays.map((d) => (
              <tr key={d} className="table-row">
                <td className="td font-medium uppercase">{d}</td>
                {periods.map((p) => {
                  const sl = grid[d]?.[p];
                  if (!sl) return <td key={p} className="td"/>;
                  if (sl.is_break) {
                    return <td key={p} className="td bg-bg-subtle text-center text-xs italic text-ink-muted">{sl.break_label}</td>;
                  }
                  const subj = subjectMap[sl.subject_id];
                  const t = teacherMap[sl.teacher_id];
                  const unfilled = !sl.teacher_id;
                  const lockKey = `${sec.class_id}|${sec.section}|${d}|${p}`;
                  const isLocked = sl.is_locked || !!locks[lockKey];
                  const isSubstitute = sl.is_substitute;
                  const cellKey = `${d}|${p}`;
                  const bgClass = sl.is_class_teacher_pin
                    ? "bg-status-info/10 border-l-2 border-status-info"
                    : isLocked
                    ? "bg-primary-light/40 border-l-2 border-primary"
                    : unfilled
                    ? "bg-status-danger/10 border-l-2 border-status-danger"
                    : isSubstitute
                    ? "bg-status-warning/10 border-l-2 border-status-warning"
                    : "";
                  return (
                    <td key={p} className={"td align-top " + bgClass}
                      data-testid={`grid-${sec.class_id}-${sec.section}-${d}-${p}`}>
                      <div className="font-medium text-xs">
                        {subj?.name || (sl.is_class_teacher_pin ? sl.class_teacher_label : "—")}
                        {isLocked && <span className="ml-1 text-[9px] text-primary">🔒</span>}
                        {isSubstitute && <span className="ml-1 text-[9px] text-status-warning" title="Substitute teacher">🔄</span>}
                      </div>
                      <div className={"text-[10px] " + (unfilled ? "text-status-danger uppercase tracking-wider font-semibold" : "text-ink-muted")}>
                        {unfilled ? "Unfilled" : (t?.name || "—")}
                      </div>

                      {/* Substitute auto-fill — only for unfilled cells */}
                      {unfilled && (
                        <details className="mt-1" data-testid={`sub-${sec.class_id}-${sec.section}-${d}-${p}`}>
                          <summary className="text-[10px] text-status-danger cursor-pointer font-semibold">
                            Find substitute
                          </summary>
                          <div className="mt-1 space-y-1">
                            {!subSuggestions[cellKey] ? (
                              <button
                                onClick={() => fetchSuggestions(d, p, sl.subject_id)}
                                disabled={subBusyKey === cellKey}
                                className="text-[10px] text-primary underline"
                                data-testid={`sub-fetch-${sec.class_id}-${sec.section}-${d}-${p}`}
                              >
                                {subBusyKey === cellKey ? "Loading…" : "Show free teachers"}
                              </button>
                            ) : subSuggestions[cellKey].length === 0 ? (
                              <div className="text-[10px] text-ink-muted">No free teachers at this slot.</div>
                            ) : (
                              <div className="space-y-1">
                                {subSuggestions[cellKey].slice(0, 5).map((s) => (
                                  <div key={s.teacher_id} className="flex items-center justify-between gap-1">
                                    <div className="text-[10px]">
                                      {s.teaches_subject && <span title="Teaches this subject">⭐</span>}
                                      {s.on_leave_today && <span title="On leave today">🌴</span>}
                                      <span className={s.on_leave_today ? "line-through" : ""}>{s.teacher_name}</span>
                                      <span className="text-ink-muted ml-1">({s.daily_load})</span>
                                    </div>
                                    <button
                                      onClick={() => applySub(d, p, sl.subject_id, s.teacher_id)}
                                      disabled={s.on_leave_today}
                                      className="text-[10px] text-primary font-medium"
                                      data-testid={`sub-apply-${sec.class_id}-${sec.section}-${d}-${p}-${s.teacher_id}`}
                                    >
                                      Apply
                                    </button>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </details>
                      )}

                      {!sl.is_class_teacher_pin && !unfilled && (
                        <details className="mt-1" data-testid={`lock-${sec.class_id}-${sec.section}-${d}-${p}`}>
                          <summary className="text-[10px] text-ink-muted cursor-pointer hover:text-primary">Lock…</summary>
                          <div className="mt-1 space-y-1">
                            <select
                              className="input text-[10px] w-full"
                              value={locks[lockKey]?.teacher_id || ""}
                              onChange={(e) => setLock(sec.class_id, sec.section, d, p, e.target.value, locks[lockKey]?.subject_id || sl.subject_id)}
                              data-testid={`lock-teacher-${sec.class_id}-${sec.section}-${d}-${p}`}
                            >
                              <option value="">— Pick teacher —</option>
                              {teachers.map((tc) => <option key={tc.id} value={tc.id}>{tc.name}</option>)}
                            </select>
                            {locks[lockKey] && (
                              <select
                                className="input text-[10px] w-full"
                                value={locks[lockKey]?.subject_id || sl.subject_id || ""}
                                onChange={(e) => setLock(sec.class_id, sec.section, d, p, locks[lockKey]?.teacher_id, e.target.value)}
                                data-testid={`lock-subject-${sec.class_id}-${sec.section}-${d}-${p}`}
                              >
                                <option value="">— Any subject —</option>
                                {subjects.map((sj) => <option key={sj.id} value={sj.id}>{sj.name}</option>)}
                              </select>
                            )}
                            {locks[lockKey] && (
                              <button
                                onClick={() => clearLock(sec.class_id, sec.section, d, p)}
                                className="text-[10px] text-status-danger underline"
                                data-testid={`unlock-${sec.class_id}-${sec.section}-${d}-${p}`}
                              >
                                Clear lock
                              </button>
                            )}
                          </div>
                        </details>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TeacherView({ teacher_view, subjectMap, classMap, days, periodsPerDay }) {
  const periods = Array.from({ length: periodsPerDay }, (_, i) => i + 1);
  const dayList = days || ["mon", "tue", "wed", "thu", "fri"];
  const rows = chunk(teacher_view.teachers || [], 1);
  return (
    <div data-testid="teacher-view">
      <div className="text-xs text-ink-muted mb-3">
        Workload range: <strong>{teacher_view.workload_min}</strong> – <strong>{teacher_view.workload_max}</strong> periods/week
      </div>
      <div className="space-y-5">
        {rows.flat().map((t) => (
          <div key={t.teacher_id} data-testid={`tv-row-${t.teacher_id}`}>
            <div className="flex items-baseline justify-between mb-1">
              <div className="font-medium">{t.teacher_name}</div>
              <div className="text-xs text-ink-muted">{t.total_periods} periods/week</div>
            </div>
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th className="th">Day</th>
                    {periods.map((p) => <th key={p} className="th text-center">P{p}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {dayList.map((d) => (
                    <tr key={d} className="table-row">
                      <td className="td font-medium uppercase">{d}</td>
                      {periods.map((p) => {
                        const cell = t.by_day?.[d]?.[p];
                        if (!cell) return <td key={p} className="td text-center text-ink-muted">—</td>;
                        return (
                          <td key={p} className="td align-top bg-primary-light/40">
                            <div className="text-[11px] font-medium">{cell.subject_name || "Class Teacher"}</div>
                            <div className="text-[10px] text-ink-muted">{cell.class_name} · {cell.section}</div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConflictPanel({ summary, suggestions }) {
  return (
    <div className="space-y-5" data-testid="conflict-panel">
      <div>
        <div className="overline mb-2">Optimization suggestions</div>
        <ul className="space-y-2">
          {suggestions.map((s, i) => (
            <li key={i} className="text-sm border border-line rounded-md p-3 bg-bg-subtle" data-testid={`opt-${i}`}>
              {s}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <div className="overline mb-2">Unfilled slots ({summary.unfilled_slots.length})</div>
        {summary.unfilled_slots.length === 0 ? (
          <div className="text-sm text-ink-muted">None — every period has a teacher. 🎉</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">Class · Section</th><th className="th">Day · Period</th><th className="th">Subject</th><th className="th">Reason</th>
              </tr></thead>
              <tbody>
                {summary.unfilled_slots.map((u, i) => (
                  <tr key={i} className="table-row" data-testid={`unfilled-${i}`}>
                    <td className="td">{u.class_name} · {u.section}</td>
                    <td className="td uppercase">{u.day} · P{u.period}</td>
                    <td className="td">{u.subject_name || u.subject_id}</td>
                    <td className="td text-xs text-ink-muted">{u.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {summary.double_bookings.length > 0 && (
        <div>
          <div className="overline mb-2 text-status-danger">Double bookings ({summary.double_bookings.length})</div>
          <ul className="text-sm space-y-1">
            {summary.double_bookings.map((d, i) => (
              <li key={i} data-testid={`dup-${i}`}>
                Teacher {d.teacher_id} clashes on {d.day.toUpperCase()} P{d.period}:
                {" "}{d.first.class_name}/{d.first.section} ↔ {d.second.class_name}/{d.second.section}
              </li>
            ))}
          </ul>
        </div>
      )}
      {summary.warnings.length > 0 && (
        <div>
          <div className="overline mb-2">Constraint warnings</div>
          <ul className="text-xs space-y-1 text-ink-soft">
            {summary.warnings.map((w, i) => <li key={i}>• {w}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}
