import React, { useEffect, useMemo, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, Section, Empty, KPI } from "../../components/Primitives";
import { ATTENDANCE_STATUSES } from "../../lib/utils";
import DatePicker from "../../components/DatePicker";
import toast from "react-hot-toast";

const TODAY = () => new Date().toISOString().slice(0, 10);

const TABS = [
  { id: "mark", label: "Mark students" },
  { id: "absentees", label: "Absentees" },
  { id: "teachers", label: "Teacher attendance" },
];

export default function AttendancePage() {
  const { user } = useAuth();
  const isAdminLike = user?.role === "school_admin" || user?.role === "accounts";
  const [tab, setTab] = useState("mark");

  // The Teacher-attendance tab is admin-only; if a teacher lands here,
  // hide it from the tab strip.
  const visibleTabs = isAdminLike ? TABS : TABS.filter((t) => t.id === "mark");

  return (
    <div data-testid="attendance-page">
      <PageHeader
        eyebrow="Operations"
        title="Attendance"
        subtitle="Mark students, review absentees by day / week / month, and track teacher attendance."
      />

      <div className="flex gap-2 mb-4 border-b border-line" role="tablist">
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={
              "px-4 py-2 text-sm border-b-2 -mb-px transition " +
              (tab === t.id
                ? "border-primary text-primary font-medium"
                : "border-transparent text-ink-muted hover:text-ink")
            }
            data-testid={`attendance-tab-${t.id}`}
            role="tab"
            aria-selected={tab === t.id}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "mark" && <MarkStudentsTab />}
      {tab === "absentees" && isAdminLike && <AbsenteesTab />}
      {tab === "teachers" && isAdminLike && <TeacherAttendanceTab />}
    </div>
  );
}

/* ---------------- Tab 1: Mark students (existing flow) ---------------- */
function MarkStudentsTab() {
  const [classes, setClasses] = useState([]);
  const [sel, setSel] = useState({ class_id: "", section: "", date: TODAY() });
  const [students, setStudents] = useState([]);
  const [entries, setEntries] = useState({});

  useEffect(() => { api.get("/academic/classes").then((r) => setClasses(r.data)); }, []);
  const sections = classes.find((c) => c.id === sel.class_id)?.sections || [];

  const loadStudents = async () => {
    if (!sel.class_id || !sel.section) return;
    const [s, a] = await Promise.all([
      api.get("/students", { params: { class_id: sel.class_id, section: sel.section } }).then((r) => r.data),
      api.get("/attendance", { params: { class_id: sel.class_id, section: sel.section, date: sel.date } }).then((r) => r.data),
    ]);
    setStudents(s);
    const ex = Object.fromEntries(a.map((r) => [r.student_id, r.status]));
    setEntries(Object.fromEntries(s.map((st) => [st.id, ex[st.id] || "present"])));
  };
  useEffect(() => { loadStudents(); /* eslint-disable-next-line */ }, [sel.class_id, sel.section, sel.date]);

  const save = async () => {
    try {
      const payload = {
        class_id: sel.class_id, section: sel.section, date: sel.date,
        entries: Object.entries(entries).map(([student_id, status]) => ({ student_id, status })),
      };
      const { data } = await api.post("/attendance/bulk", payload);
      toast.success(`Saved ${data.marked} entries · ${data.notifications} parent alerts queued`);
      loadStudents();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const setAll = (status) => setEntries(Object.fromEntries(students.map((s) => [s.id, status])));

  return (
    <>
      <div className="flex flex-wrap gap-3 mb-4">
        <select className="input w-44" value={sel.class_id} onChange={(e) => setSel({ ...sel, class_id: e.target.value, section: "" })} data-testid="att-class">
          <option value="">Class…</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-32" value={sel.section} onChange={(e) => setSel({ ...sel, section: e.target.value })} disabled={!sel.class_id} data-testid="att-section">
          <option value="">Section…</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <DatePicker
          value={sel.date}
          onChange={(v) => setSel({ ...sel, date: v })}
          testId="att-date"
          className="w-52"
        />
        {students.length > 0 && (
          <>
            <button className="btn-secondary" onClick={() => setAll("present")} data-testid="att-all-present">Mark all present</button>
            <button className="btn-secondary" onClick={() => setAll("absent")}>Mark all absent</button>
          </>
        )}
      </div>

      <Section title={students.length ? `${students.length} students for ${sel.date}` : "Select class and section"}>
        {students.length === 0 ? <Empty title="No students" message="Select class and section to load students." /> :
          <>
            <table className="table">
              <thead><tr><th className="th">Roll</th><th className="th">UID</th><th className="th">Name</th><th className="th">Status</th></tr></thead>
              <tbody>
                {students.map((s) => (
                  <tr key={s.id} className="table-row" data-testid={`att-row-${s.student_uid}`}>
                    <td className="td">{s.roll_number}</td>
                    <td className="td font-mono text-xs">{s.student_uid}</td>
                    <td className="td font-medium">{s.name}</td>
                    <td className="td">
                      <select className="input w-40" value={entries[s.id] || "present"} onChange={(e) => setEntries({ ...entries, [s.id]: e.target.value })} data-testid={`att-status-${s.student_uid}`}>
                        {ATTENDANCE_STATUSES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex justify-end mt-4">
              <button className="btn-primary" onClick={save} data-testid="att-save-btn">Save attendance</button>
            </div>
          </>}
      </Section>
    </>
  );
}

/* ---------------- Tab 2: Absentees (day / week / month) ---------------- */
function AbsenteesTab() {
  const [period, setPeriod] = useState("day"); // day | week | month
  const [date, setDate] = useState(TODAY());
  const [classes, setClasses] = useState([]);
  const [classId, setClassId] = useState("");
  const [section, setSection] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => { api.get("/academic/classes").then((r) => setClasses(r.data)); }, []);
  const sections = classes.find((c) => c.id === classId)?.sections || [];

  const load = async () => {
    setLoading(true);
    try {
      const params = { period, date };
      if (classId) params.class_id = classId;
      if (section) params.section = section;
      const { data: d } = await api.get("/attendance/absentees", { params });
      setData(d);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period, date, classId, section]);

  const rangeLabel = useMemo(() => {
    if (!date) return "";
    const d = new Date(date + "T00:00:00");
    if (period === "day") return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short", year: "numeric" });
    if (period === "week") {
      const day = d.getDay() === 0 ? 7 : d.getDay();
      const mon = new Date(d); mon.setDate(d.getDate() - (day - 1));
      const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
      const fmt = (x) => x.toLocaleDateString(undefined, { day: "numeric", month: "short" });
      return `${fmt(mon)} – ${fmt(sun)}, ${sun.getFullYear()}`;
    }
    return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }, [period, date]);

  const summary = data?.summary || {};
  const absentees = data?.absentees || [];

  return (
    <>
      <div className="flex flex-wrap items-end gap-3 mb-4" data-testid="absentees-toolbar">
        <div className="inline-flex rounded-md border border-line overflow-hidden">
          {[
            { id: "day", label: "Day" },
            { id: "week", label: "Week" },
            { id: "month", label: "Month" },
          ].map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setPeriod(p.id)}
              className={
                "px-4 py-2 text-sm transition " +
                (period === p.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-bg-surface hover:bg-bg-subtle text-ink")
              }
              data-testid={`absentees-period-${p.id}`}
            >{p.label}</button>
          ))}
        </div>
        <DatePicker
          mode={period === "month" ? "month" : "day"}
          value={period === "month" ? (date || "").slice(0, 7) : date}
          onChange={(v) => setDate(period === "month" ? `${v}-01` : v)}
          testId="absentees-date"
          className="w-56"
        />
        <select className="input w-44" value={classId} onChange={(e) => { setClassId(e.target.value); setSection(""); }} data-testid="absentees-class">
          <option value="">All classes</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-32" value={section} onChange={(e) => setSection(e.target.value)} disabled={!classId} data-testid="absentees-section">
          <option value="">All sections</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="text-xs text-ink-muted ml-auto" data-testid="absentees-range-label">{rangeLabel}</div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <KPI label="Students with absences" value={summary.students || 0} accent={summary.students ? "warning" : "success"} testId="kpi-absentee-students" />
        <KPI label="Total absent days" value={summary.total_absent_days || 0} accent="danger" testId="kpi-absent-days" />
        <KPI label="Total sick days" value={summary.total_sick_days || 0} accent="info" testId="kpi-sick-days" />
      </div>

      <Section title={`Absentees (${absentees.length})`} subtitle={loading ? "Loading…" : `Sorted by total absences. Period: ${period}.`}>
        {absentees.length === 0 ? (
          <Empty title="Nobody absent" message={`No absences recorded for the selected ${period}.`} />
        ) : (
          <div className="border border-line rounded-md overflow-hidden" data-testid="absentees-table-wrap">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left p-3">UID</th>
                  <th className="text-left p-3">Name</th>
                  <th className="text-left p-3">Class</th>
                  <th className="text-right p-3">Absent</th>
                  <th className="text-right p-3">Sick</th>
                  {period !== "day" && <th className="text-right p-3">Total days</th>}
                  {period === "month" && <th className="text-right p-3">% attendance</th>}
                  <th className="text-left p-3">Last absent</th>
                  <th className="text-left p-3">Parent phone</th>
                </tr>
              </thead>
              <tbody>
                {absentees.map((a) => (
                  <tr key={a.student_id} className="border-t border-line/60" data-testid={`absentee-row-${a.student_uid}`}>
                    <td className="p-3 font-mono text-xs text-ink-soft">{a.student_uid}</td>
                    <td className="p-3 font-medium">{a.name}</td>
                    <td className="p-3 text-ink-soft">{a.class_name} · {a.section}</td>
                    <td className="p-3 text-right font-medium text-status-danger">{a.absent_days}</td>
                    <td className="p-3 text-right text-status-info">{a.sick_days}</td>
                    {period !== "day" && <td className="p-3 text-right">{a.total_days}</td>}
                    {period === "month" && (
                      <td className={"p-3 text-right font-medium " + (a.attendance_percentage < 75 ? "text-status-danger" : "text-status-success")}>
                        {a.attendance_percentage}%
                      </td>
                    )}
                    <td className="p-3 text-ink-soft text-xs">
                      {a.last_absent_date}
                      {a.last_absent_status === "sick" && <span className="ml-1 badge bg-status-info/10 text-status-info">sick</span>}
                    </td>
                    <td className="p-3 text-ink-soft text-xs">{a.parent_phone || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  );
}

/* ---------------- Tab 3: Teacher attendance ---------------- */
const T_STATUSES = [
  { value: "present", label: "Present", tone: "bg-status-success/15 text-status-success border-status-success/30" },
  { value: "absent", label: "Absent", tone: "bg-status-danger/15 text-status-danger border-status-danger/30" },
  { value: "leave", label: "Leave", tone: "bg-status-warning/15 text-status-warning border-status-warning/30" },
  { value: "half_day", label: "Half day", tone: "bg-status-info/15 text-status-info border-status-info/30" },
];

function TeacherAttendanceTab() {
  const [date, setDate] = useState(TODAY());
  const [today, setToday] = useState(null);
  const [draft, setDraft] = useState({}); // teacher_id -> status
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [{ data: tToday }, { data: byDate }] = await Promise.all([
        api.get("/teacher-attendance/today"),
        api.get("/teacher-attendance", { params: { date } }),
      ]);
      setToday(tToday);
      const ex = Object.fromEntries(byDate.map((r) => [r.teacher_id, r.status]));
      // seed draft from existing marks for the picked date, defaulting to 'present'.
      const seeded = {};
      for (const t of tToday.teachers) seeded[t.id] = ex[t.id] || "present";
      setDraft(seeded);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [date]);

  const setAll = (status) => {
    if (!today) return;
    setDraft(Object.fromEntries(today.teachers.map((t) => [t.id, status])));
  };

  const save = async () => {
    setBusy(true);
    try {
      const entries = Object.entries(draft).map(([teacher_id, status]) => ({ teacher_id, status }));
      const { data } = await api.post("/teacher-attendance/bulk", { date, entries });
      toast.success(`Saved ${data.marked} teacher rows for ${data.date}`);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const teachers = today?.teachers || [];
  const isToday = date === TODAY();
  const counts = today?.counts || { present: 0, absent: 0, leave: 0, half_day: 0, unmarked: 0 };
  const absentToday = teachers.filter((t) => t.status === "absent" || t.status === "leave" || t.status === "half_day");

  return (
    <>
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <DatePicker
          value={date}
          onChange={(v) => setDate(v)}
          testId="teacher-att-date"
          className="w-56"
        />
        <button className="btn-secondary" onClick={() => setAll("present")} data-testid="teacher-att-all-present">Mark all present</button>
        <button className="btn-secondary" onClick={() => setAll("absent")} data-testid="teacher-att-all-absent">Mark all absent</button>
        <button className="btn-primary ml-auto" onClick={save} disabled={busy || loading || teachers.length === 0} data-testid="teacher-att-save-btn">
          {busy ? "Saving…" : `Save ${date}`}
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <KPI label="Present" value={counts.present} accent="success" testId="kpi-tatt-present" />
        <KPI label="Absent" value={counts.absent} accent="danger" testId="kpi-tatt-absent" />
        <KPI label="Leave" value={counts.leave} accent="warning" testId="kpi-tatt-leave" />
        <KPI label="Half day" value={counts.half_day} accent="info" testId="kpi-tatt-halfday" />
        <KPI label="Unmarked" value={counts.unmarked} accent={counts.unmarked ? "warning" : "success"} testId="kpi-tatt-unmarked" />
      </div>

      {isToday && (
        <Section title={`Absent today (${absentToday.length})`} subtitle="Teachers marked absent, on leave or half-day for today.">
          {absentToday.length === 0 ? (
            <Empty title="All teachers present today" message="No absences marked yet." />
          ) : (
            <div className="flex flex-wrap gap-2" data-testid="absent-today-strip">
              {absentToday.map((t) => (
                <div
                  key={t.id}
                  className={"rounded-md px-3 py-2 border " + (T_STATUSES.find((x) => x.value === t.status)?.tone || "")}
                  data-testid={`absent-today-${t.id}`}
                >
                  <div className="text-sm font-medium">{t.name}</div>
                  <div className="text-[10px] uppercase tracking-wider">{t.status.replace("_", " ")}</div>
                  {t.remark ? <div className="text-xs text-ink-soft mt-0.5 italic">{t.remark}</div> : null}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      <Section title={`Roster for ${date} (${teachers.length})`}>
        {teachers.length === 0 ? (
          <Empty title="No teachers" message="Add teachers from the Teachers page first." />
        ) : (
          <div className="border border-line rounded-md overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-bg-subtle text-ink-muted text-xs uppercase tracking-wider">
                <tr>
                  <th className="text-left p-3">Name</th>
                  <th className="text-left p-3">Email</th>
                  <th className="text-left p-3">Phone</th>
                  <th className="text-left p-3 w-72">Status</th>
                </tr>
              </thead>
              <tbody>
                {teachers.map((t) => (
                  <tr key={t.id} className="border-t border-line/60" data-testid={`teacher-att-row-${t.id}`}>
                    <td className="p-3 font-medium">{t.name}</td>
                    <td className="p-3 text-ink-soft text-xs">{t.email}</td>
                    <td className="p-3 text-ink-soft text-xs">{t.phone || "—"}</td>
                    <td className="p-3">
                      <div className="inline-flex flex-wrap gap-1">
                        {T_STATUSES.map((s) => {
                          const active = draft[t.id] === s.value;
                          return (
                            <button
                              key={s.value}
                              type="button"
                              onClick={() => setDraft({ ...draft, [t.id]: s.value })}
                              className={
                                "text-xs px-2.5 py-1 rounded-md border transition " +
                                (active ? s.tone + " font-medium" : "border-line text-ink-soft hover:bg-bg-subtle")
                              }
                              data-testid={`teacher-att-${t.id}-${s.value}`}
                            >{s.label}</button>
                          );
                        })}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  );
}
