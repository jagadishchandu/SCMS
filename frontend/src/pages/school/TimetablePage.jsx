import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import DatePicker from "../../components/DatePicker";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat"];
const DAY_LABEL = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat" };
const DAY_INDEX = { mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6, sun: 0 };

const TODAY = () => new Date().toISOString().slice(0, 10);

// Pick a Tailwind tint per teacher attendance status. Used to color the
// timetable cell for the day the user is viewing.
const STATUS_TINT = {
  present: "bg-status-success/10 border-status-success/40",
  absent: "bg-status-danger/15 border-status-danger/40",
  leave: "bg-status-warning/15 border-status-warning/40",
  half_day: "bg-status-info/15 border-status-info/40",
};
const STATUS_LABEL = {
  present: "Present",
  absent: "Absent",
  leave: "On leave",
  half_day: "Half day",
  unmarked: "Not marked",
};

export default function TimetablePage() {
  const [slots, setSlots] = useState([]);
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [sel, setSel] = useState({ class_id: "", section: "" });

  // Day to tint timetable cells for. Defaults to today.
  const [tintDate, setTintDate] = useState(TODAY());
  const [teacherStatus, setTeacherStatus] = useState({}); // teacher_id -> status

  useEffect(() => {
    Promise.all([
      api.get("/academic/classes").then((r) => r.data),
      api.get("/academic/subjects").then((r) => r.data),
      api.get("/users", { params: { role: "teacher" } }).then((r) => r.data),
    ]).then(([c, s, t]) => { setClasses(c); setSubjects(s); setTeachers(t); });
  }, []);

  useEffect(() => {
    if (!sel.class_id || !sel.section) return;
    api.get("/timetable", { params: { class_id: sel.class_id, section: sel.section } })
      .then((r) => setSlots(r.data));
  }, [sel]);

  // Load teacher attendance for the picked tint date and map teacher_id -> status.
  useEffect(() => {
    let cancelled = false;
    api.get("/teacher-attendance", { params: { date: tintDate } })
      .then((r) => {
        if (cancelled) return;
        setTeacherStatus(Object.fromEntries((r.data || []).map((x) => [x.teacher_id, x.status])));
      })
      .catch(() => { if (!cancelled) setTeacherStatus({}); });
    return () => { cancelled = true; };
  }, [tintDate]);

  const sections = classes.find((c) => c.id === sel.class_id)?.sections || [];
  const periods = [...new Set(slots.map((s) => s.period))].sort((a, b) => a - b);
  const grid = {};
  for (const s of slots) {
    grid[s.day] = grid[s.day] || {};
    grid[s.day][s.period] = s;
  }

  // The weekday key that maps to the picked tintDate so we know which row to highlight.
  const tintDayKey = useMemo(() => {
    if (!tintDate) return null;
    const d = new Date(tintDate + "T00:00:00");
    const idx = d.getDay(); // 0=Sun, 1=Mon...
    return Object.keys(DAY_INDEX).find((k) => DAY_INDEX[k] === idx) || null;
  }, [tintDate]);

  const teacherById = useMemo(
    () => Object.fromEntries(teachers.map((t) => [t.id, t])),
    [teachers],
  );

  return (
    <div data-testid="timetable-page">
      <PageHeader
        eyebrow="Schedule"
        title="Class timetable"
        subtitle="Weekly schedule. Cells tint green/red on the picked day based on the teacher's attendance."
      />
      <div className="flex flex-wrap gap-3 mb-4">
        <select className="input w-44" value={sel.class_id} onChange={(e) => setSel({ class_id: e.target.value, section: "" })}>
          <option value="">Class…</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-32" value={sel.section} onChange={(e) => setSel({ ...sel, section: e.target.value })} disabled={!sel.class_id}>
          <option value="">Section…</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs text-ink-muted">Color cells for</label>
          <DatePicker
            value={tintDate}
            onChange={(v) => setTintDate(v)}
            testId="timetable-tint-date"
            className="w-52"
          />
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-2 mb-3 text-xs" data-testid="timetable-legend">
        <span className="text-ink-muted mr-1">Teacher status today:</span>
        {Object.entries(STATUS_LABEL).filter(([k]) => k !== "unmarked").map(([k, label]) => (
          <span key={k} className={"inline-flex items-center gap-1 px-2 py-0.5 rounded-md border " + (STATUS_TINT[k] || "border-line")}>
            <span className="inline-block w-2 h-2 rounded-full bg-current opacity-70"/>{label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-dashed border-line text-ink-muted">
          <span className="inline-block w-2 h-2 rounded-full bg-current opacity-30"/>Not marked yet
        </span>
      </div>

      <Section title={slots.length ? `${slots.length} slots` : "Pick a class and section"}>
        {slots.length === 0 ? <Empty title="No timetable" /> :
          <div className="overflow-x-auto">
            <table className="table">
              <thead><tr>
                <th className="th">Day</th>
                {periods.map((p) => <th key={p} className="th">Period {p}</th>)}
              </tr></thead>
              <tbody>
                {DAYS.map((d) => (
                  grid[d] ? (
                    <tr key={d} className={"table-row " + (d === tintDayKey ? "ring-1 ring-primary/30" : "")}>
                      <td className="td font-medium">
                        {DAY_LABEL[d]}
                        {d === tintDayKey && <div className="text-[10px] text-primary uppercase tracking-wider">picked</div>}
                      </td>
                      {periods.map((p) => {
                        const slot = grid[d][p];
                        if (!slot) return <td key={p} className="td" />;
                        const t = teacherById[slot.teacher_id];
                        const isTintRow = d === tintDayKey;
                        const status = isTintRow ? (teacherStatus[slot.teacher_id] || "unmarked") : null;
                        const tint = status && STATUS_TINT[status]
                          ? STATUS_TINT[status]
                          : (isTintRow ? "border-dashed" : "");
                        return (
                          <td
                            key={p}
                            className={"td align-top border " + tint}
                            data-testid={`tt-cell-${d}-${p}`}
                            data-status={status || ""}
                            title={isTintRow && t ? `${t.name} — ${STATUS_LABEL[status] || "Not marked yet"}` : undefined}
                          >
                            <div className="font-medium">{subjects.find((s) => s.id === slot.subject_id)?.name || "—"}</div>
                            <div className="text-xs text-ink-muted">{t?.name || "—"}</div>
                            <div className="text-[10px] text-ink-muted">{slot.start_time}–{slot.end_time}</div>
                            {isTintRow && status && status !== "unmarked" && (
                              <div className="text-[10px] uppercase tracking-wider mt-1 font-medium">
                                {STATUS_LABEL[status]}
                              </div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ) : null
                ))}
              </tbody>
            </table>
          </div>}
      </Section>
    </div>
  );
}
