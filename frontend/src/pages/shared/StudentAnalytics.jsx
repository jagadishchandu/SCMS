import React, { useState, useEffect, useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, KPI, Section, Empty } from "../../components/Primitives";
import { MagnifyingGlass, DownloadSimple, Camera, UserCircle, TelegramLogo, X } from "@phosphor-icons/react";
import { currency, CHART_COLORS } from "../../lib/utils";
import { ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, Legend } from "recharts";
import toast from "react-hot-toast";

export default function StudentAnalytics() {
  const params = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isStaff = ["platform_admin", "school_admin", "teacher", "accounts"].includes(user?.role);

  const [uid, setUid] = useState(params.uid || "");
  const [dash, setDash] = useState(null);
  const [loading, setLoading] = useState(false);

  // -- Typeahead state --
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const [hi, setHi] = useState(-1);

  // -- Filter facets (chip groups) --
  const [classes, setClasses] = useState([]);
  const [activities, setActivities] = useState([]);
  const [filters, setFilters] = useState({
    class_id: "", section: "", gender: "", status: "active",
    activity_id: "", telegram: "any",
  });

  React.useEffect(() => {
    if (params.uid) doSearch(params.uid);
    // eslint-disable-next-line
  }, [params.uid]);

  // Load classes + activities once for facet chips
  useEffect(() => {
    if (!isStaff) return;
    api.get("/academic/classes").then((r) => setClasses(r.data || [])).catch(() => {});
    api.get("/activities").then((r) => setActivities(r.data || [])).catch(() => setActivities([]));
  }, [isStaff]);

  // Debounced typeahead fetch
  useEffect(() => {
    if (!isStaff) return;
    if (!query && Object.values(filters).every((v) => !v || v === "any" || v === "active")) {
      setSuggestions([]);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const params = { q: query || undefined };
        if (filters.class_id) params.class_id = filters.class_id;
        if (filters.section) params.section = filters.section;
        const { data } = await api.get("/students", { params });
        let rows = data || [];
        // Client-side facets that aren't supported server-side
        if (filters.gender) rows = rows.filter((r) => (r.gender || "").toUpperCase() === filters.gender);
        if (filters.status === "active") rows = rows.filter((r) => r.status === "active");
        else if (filters.status === "inactive") rows = rows.filter((r) => r.status !== "active");
        if (filters.activity_id) rows = rows.filter((r) => (r.activities || []).some((a) => a.id === filters.activity_id));
        if (filters.telegram === "linked") rows = rows.filter((r) => r.parent_telegram_linked);
        else if (filters.telegram === "unlinked") rows = rows.filter((r) => !r.parent_telegram_linked);
        setSuggestions(rows.slice(0, 50));
        setHi(rows.length ? 0 : -1);
      } catch { setSuggestions([]); }
    }, 250);
    return () => clearTimeout(t);
  }, [query, filters, isStaff]);

  const doSearch = async (id) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/analytics/student/${id}`);
      setDash(data);
    } catch (err) { toast.error(formatApiError(err)); setDash(null); }
    finally { setLoading(false); }
  };

  const submit = (e) => { e.preventDefault(); if (uid) navigate(`/student/${uid}`); };
  const open = (suid) => { setShowSuggest(false); navigate(`/student/${suid}`); };

  const totalSections = useMemo(
    () => Array.from(new Set(classes.flatMap((c) => c.sections || []))).sort(),
    [classes],
  );
  const activeFiltersCount = useMemo(() => {
    let n = 0;
    if (filters.class_id) n++; if (filters.section) n++;
    if (filters.gender) n++; if (filters.status && filters.status !== "active") n++;
    if (filters.activity_id) n++; if (filters.telegram !== "any") n++;
    return n;
  }, [filters]);
  const resetFilters = () => setFilters({ class_id: "", section: "", gender: "", status: "active", activity_id: "", telegram: "any" });

  return (
    <div data-testid="student-analytics-page">
      <PageHeader
        eyebrow="Student search"
        title="Look up any student in seconds"
        subtitle={isStaff
          ? "Type a name, UID, or parent — full child details show below. Use the chip filters to narrow down."
          : "Type a student's unique ID (e.g. STU-00001) to open their full analytics dashboard."}
      />

      {isStaff ? (
        <div className="mb-6" data-testid="sa-search-block">
          <div className="relative max-w-2xl">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input
              className="input pl-10 pr-10"
              placeholder="Search by name, UID, parent name…"
              value={query}
              onFocus={() => setShowSuggest(true)}
              onChange={(e) => { setQuery(e.target.value); setShowSuggest(true); }}
              onKeyDown={(e) => {
                if (!showSuggest) return;
                if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, suggestions.length - 1)); }
                else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
                else if (e.key === "Enter" && hi >= 0 && suggestions[hi]) { e.preventDefault(); open(suggestions[hi].student_uid); }
                else if (e.key === "Escape") setShowSuggest(false);
              }}
              data-testid="sa-typeahead-input"
            />
            {query && (
              <button
                type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted"
                onClick={() => { setQuery(""); setSuggestions([]); }}
                data-testid="sa-typeahead-clear"
              ><X size={14}/></button>
            )}
            {showSuggest && (suggestions.length > 0 || query) && (
              <div
                className="absolute z-30 mt-1 w-full bg-bg border border-line rounded-md shadow-lg max-h-96 overflow-y-auto"
                data-testid="sa-suggest-dropdown"
              >
                {suggestions.length === 0 ? (
                  <div className="p-4 text-sm text-ink-muted">No matching students. Try a different query or relax the filters.</div>
                ) : (
                  suggestions.map((s, i) => {
                    const klass = classes.find((c) => c.id === s.class_id);
                    return (
                      <button
                        type="button" key={s.id}
                        onClick={() => open(s.student_uid)}
                        onMouseEnter={() => setHi(i)}
                        className={`w-full text-left p-3 flex items-center gap-3 border-b border-line/40 last:border-0 ${i === hi ? "bg-bg-subtle" : "hover:bg-bg-subtle"}`}
                        data-testid={`sa-suggest-${s.student_uid}`}
                      >
                        <div className="w-9 h-9 rounded-full bg-secondary/40 grid place-items-center shrink-0 overflow-hidden">
                          {s.photo ? <img src={s.photo} alt="" className="w-full h-full object-cover" /> : <UserCircle size={20} />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline gap-2">
                            <span className="font-medium truncate">{s.name}</span>
                            <span className="text-xs font-mono text-ink-muted">{s.student_uid}</span>
                            {s.parent_telegram_linked && (
                              <TelegramLogo size={12} weight="fill" className="text-sky-600 shrink-0" />
                            )}
                          </div>
                          <div className="text-xs text-ink-muted truncate">
                            {klass?.name || s.class_id} · Sec {s.section} · Roll {s.roll_number || "—"}
                            {s.parent?.name && <> · Parent: {s.parent.name}</>}
                            {s.parent?.phone && <> · {s.parent.phone}</>}
                          </div>
                          {Array.isArray(s.activities) && s.activities.length > 0 && (
                            <div className="text-[10px] text-amber-600 truncate" data-testid={`sa-suggest-acts-${s.student_uid}`}>
                              🏆 {s.activities.map((a) => a.name).join(" · ")}
                            </div>
                          )}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>
          {showSuggest && <div className="fixed inset-0 z-20" onClick={() => setShowSuggest(false)} />}

          {/* Filter chip groups */}
          <div className="mt-4 space-y-2" data-testid="sa-filter-bar">
            <ChipGroup
              label="Class" testIdPrefix="filter-class"
              options={[{ value: "", label: "All" }, ...classes.map((c) => ({ value: c.id, label: c.name }))]}
              value={filters.class_id}
              onChange={(v) => setFilters((f) => ({ ...f, class_id: v, section: "" }))}
            />
            {(filters.class_id ? (classes.find((c) => c.id === filters.class_id)?.sections || []) : totalSections).length > 0 && (
              <ChipGroup
                label="Section" testIdPrefix="filter-section"
                options={[{ value: "", label: "All" }, ...(filters.class_id
                  ? (classes.find((c) => c.id === filters.class_id)?.sections || [])
                  : totalSections).map((s) => ({ value: s, label: s }))]}
                value={filters.section}
                onChange={(v) => setFilters((f) => ({ ...f, section: v }))}
              />
            )}
            <ChipGroup
              label="Gender" testIdPrefix="filter-gender"
              options={[{ value: "", label: "All" }, { value: "M", label: "Male" }, { value: "F", label: "Female" }, { value: "O", label: "Other" }]}
              value={filters.gender}
              onChange={(v) => setFilters((f) => ({ ...f, gender: v }))}
            />
            <ChipGroup
              label="Status" testIdPrefix="filter-status"
              options={[{ value: "active", label: "Active" }, { value: "inactive", label: "Inactive" }, { value: "", label: "All" }]}
              value={filters.status}
              onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
            />
            {activities.length > 0 && (
              <ChipGroup
                label="Activity" testIdPrefix="filter-activity"
                options={[{ value: "", label: "All" }, ...activities.map((a) => ({ value: a.id, label: a.name }))]}
                value={filters.activity_id}
                onChange={(v) => setFilters((f) => ({ ...f, activity_id: v }))}
              />
            )}
            <ChipGroup
              label="Telegram" testIdPrefix="filter-telegram"
              options={[{ value: "any", label: "Any" }, { value: "linked", label: "Linked" }, { value: "unlinked", label: "Not linked" }]}
              value={filters.telegram}
              onChange={(v) => setFilters((f) => ({ ...f, telegram: v }))}
            />
            {activeFiltersCount > 0 && (
              <button
                type="button"
                className="text-xs text-primary underline mt-1"
                onClick={resetFilters}
                data-testid="filter-reset"
              >Clear {activeFiltersCount} filter{activeFiltersCount > 1 ? "s" : ""}</button>
            )}
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="flex gap-2 mb-6 max-w-md">
          <div className="relative flex-1">
            <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input className="input pl-10" placeholder="e.g. STU-00001" value={uid} onChange={(e) => setUid(e.target.value.toUpperCase())} data-testid="sa-uid-input" />
          </div>
          <button className="btn-primary" data-testid="sa-search-btn">Open</button>
        </form>
      )}

      {loading && <div className="skeleton h-40 w-full" />}
      {!loading && dash && <DashView dash={dash} onRefresh={() => doSearch(params.uid || uid)} />}
      {!loading && !dash && uid && !isStaff && <Empty title="No data" message="No matching student found. Try a different UID." />}
    </div>
  );
}

function ChipGroup({ label, options, value, onChange, testIdPrefix }) {
  return (
    <div className="flex items-center gap-2 flex-wrap" data-testid={testIdPrefix}>
      <span className="text-xs uppercase tracking-wider text-ink-muted w-20 shrink-0">{label}</span>
      {options.map((o) => (
        <button
          key={o.value || "_all"}
          type="button"
          onClick={() => onChange(o.value)}
          className={`text-xs px-2.5 py-1 rounded-full border transition ${value === o.value ? "bg-primary text-white border-primary" : "border-line text-ink-soft hover:border-primary"}`}
          data-testid={`${testIdPrefix}-${o.value || "all"}`}
        >{o.label}</button>
      ))}
    </div>
  );
}

function DashView({ dash, onRefresh }) {
  const { student, attendance, academics, fees, insights, activities } = dash;
  const { user } = useAuth();

  const downloadReport = async () => {
    try {
      const res = await api.get(`/receipts/student/${student.student_uid}/report.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = `${student.student_uid}_report.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const onPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const fd = new FormData(); fd.append("file", file);
      await api.post(`/students/${student.id}/photo`, fd);
      toast.success("Photo updated");
      onRefresh && onRefresh();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const canEditPhoto = ["school_admin", "teacher", "parent"].includes(user?.role);

  const attData = [
    { name: "Present", value: attendance.counts.present },
    { name: "Absent", value: attendance.counts.absent },
    { name: "Sick", value: attendance.counts.sick },
    { name: "Late", value: attendance.counts.late },
    { name: "Half day", value: attendance.counts.half_day },
    { name: "Excused", value: attendance.counts.excused },
  ].filter((x) => x.value > 0);

  const subjectVsClass = academics.subject_avg.map((s) => ({
    subject: s.subject, student: s.avg, class: academics.class_subject_avg[s.subject] || 0,
  }));

  return (
    <>
      <div className="card mb-6" data-testid="sa-profile-card">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="relative w-20 h-20 rounded-lg overflow-hidden bg-bg-subtle grid place-items-center border border-line shrink-0" data-testid="sa-photo-wrap">
              {student.photo ? (
                <img src={student.photo} alt={student.name} className="w-full h-full object-cover" />
              ) : (
                <UserCircle size={48} className="text-ink-muted" />
              )}
              {canEditPhoto && (
                <label className="absolute bottom-1 right-1 bg-primary text-white p-1 rounded cursor-pointer hover:bg-primary-hover" title="Upload photo" data-testid="sa-photo-upload-label">
                  <Camera size={12} />
                  <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={onPhoto} data-testid="sa-photo-input" />
                </label>
              )}
            </div>
            <div>
              <div className="overline mb-1">{student.student_uid}</div>
              <h2 className="font-display text-3xl font-medium">{student.name}</h2>
              <div className="text-ink-soft text-sm mt-1">
                Roll #{student.roll_number} · Section {student.section} · DOB {student.dob || "—"}
              </div>
              <div className="text-xs text-ink-muted mt-2">
                Parent: {student.parent?.name} · {student.parent?.phone}
              </div>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <button className="btn-secondary" onClick={downloadReport} data-testid="sa-download-report"><DownloadSimple size={14}/> Download report (PDF)</button>
            <div className="flex gap-2 flex-wrap justify-end">
              {academics.improvement && (
                <span className={
                  academics.improvement.status === "improving" ? "badge-success" :
                  academics.improvement.status === "declining" ? "badge-danger" : "badge-neutral"
                }>{academics.improvement.status} ({academics.improvement.diff > 0 ? "+" : ""}{academics.improvement.diff}%)</span>
              )}
              {academics.strongest && <span className="badge-success">Best: {academics.strongest.subject} {academics.strongest.avg}%</span>}
              {academics.weakest && <span className="badge-warning">Focus: {academics.weakest.subject} {academics.weakest.avg}%</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KPI label="Attendance" value={`${attendance.attendance_percentage}%`}
          accent={attendance.attendance_percentage >= 85 ? "success" : attendance.attendance_percentage >= 70 ? "warning" : "danger"}
          hint={`${attendance.total_days} days tracked`} testId="sa-kpi-att" />
        <KPI label="Overall marks" value={`${academics.overall_percentage}%`} accent="primary" testId="sa-kpi-marks" />
        <KPI label="Fee paid" value={currency(fees.paid)} accent="success" testId="sa-kpi-paid" />
        <KPI label="Fee due" value={currency(fees.due)} accent={fees.due > 0 ? "danger" : "success"} testId="sa-kpi-due" />
      </div>

      {insights.length > 0 && (
        <Section title="Insights & alerts">
          <ul className="space-y-2">
            {insights.map((i, idx) => (
              <li key={idx} className={
                "px-3 py-2 rounded-md text-sm " +
                (i.type === "success" ? "bg-status-success-bg text-status-success"
                  : i.type === "warning" ? "bg-status-warning-bg text-status-warning"
                  : i.type === "danger" ? "bg-status-danger-bg text-status-danger"
                  : "bg-bg-subtle text-ink-soft")
              } data-testid={`sa-insight-${idx}`}>{i.text}</li>
            ))}
          </ul>
        </Section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Section title="Attendance split">
          {attData.length === 0 ? <Empty title="No attendance yet" /> :
            <div className="h-64">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={attData} dataKey="value" innerRadius={55} outerRadius={90} paddingAngle={2}>
                    {attData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>}
        </Section>
        <Section title="Marks trend">
          {academics.exam_trend.length === 0 ? <Empty title="No marks yet" /> :
            <div className="h-64">
              <ResponsiveContainer>
                <LineChart data={academics.exam_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E6E1D6" />
                  <XAxis dataKey="exam" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="avg" stroke={CHART_COLORS[0]} strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>}
        </Section>
      </div>

      <div className="mt-6 mb-6">
        <Section title="Subject-wise · student vs class average">
          {subjectVsClass.length === 0 ? <Empty title="No marks yet" /> :
            <div className="h-72">
              <ResponsiveContainer>
                <BarChart data={subjectVsClass}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E6E1D6" />
                  <XAxis dataKey="subject" tick={{ fontSize: 11 }} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="student" fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="class" fill={CHART_COLORS[1]} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>}
        </Section>
      </div>

      <Section title={`Extra-curricular activities${activities?.total_enrolled ? ` · ${activities.total_enrolled}` : ""}`}>
        {!activities || activities.total_enrolled === 0 ? (
          <Empty title="No activities yet" message="This student isn't enrolled in any extra-curricular activity." />
        ) : (
          <div className="space-y-3" data-testid="student-activities-section">
            <div className="flex flex-wrap gap-2">
              {activities.by_category.map((c) => (
                <span key={c.category} className="badge bg-primary-light text-primary capitalize" data-testid={`activity-cat-${c.category}`}>
                  {c.category}: {c.count}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {activities.enrolled.map((a) => (
                <div
                  key={a.activity_id}
                  className="p-3 rounded-md border border-line/70 bg-bg-subtle"
                  data-testid={`activity-card-${a.activity_id}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-medium text-ink">{a.name}</div>
                    <span className="badge-neutral capitalize text-xs">{a.category}</span>
                  </div>
                  {a.coach && <div className="text-xs text-ink-muted mt-1">Coach: {a.coach}</div>}
                  {a.schedule && <div className="text-xs text-ink-muted">{a.schedule}</div>}
                </div>
              ))}
            </div>
          </div>
        )}
      </Section>

      <Section title="Monthly attendance">
        {attendance.monthly.length === 0 ? <Empty title="No data" /> :
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={attendance.monthly} stackOffset="sign">
                <CartesianGrid strokeDasharray="3 3" stroke="#E6E1D6" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="present" stackId="a" fill={CHART_COLORS[0]} />
                <Bar dataKey="absent" stackId="a" fill={CHART_COLORS[2]} />
                <Bar dataKey="sick" stackId="a" fill={CHART_COLORS[1]} />
                <Bar dataKey="late" stackId="a" fill={CHART_COLORS[3]} />
              </BarChart>
            </ResponsiveContainer>
          </div>}
      </Section>
    </>
  );
}
