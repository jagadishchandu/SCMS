import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { ATTENDANCE_STATUSES } from "../../lib/utils";
import toast from "react-hot-toast";

export default function AttendancePage() {
  const [classes, setClasses] = useState([]);
  const [sel, setSel] = useState({ class_id: "", section: "", date: new Date().toISOString().slice(0, 10) });
  const [students, setStudents] = useState([]);
  const [entries, setEntries] = useState({});
  const [existing, setExisting] = useState({});

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
    setExisting(ex);
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

  const setAll = (status) => {
    setEntries(Object.fromEntries(students.map((s) => [s.id, status])));
  };

  return (
    <div data-testid="attendance-page">
      <PageHeader eyebrow="Operations" title="Daily attendance"
        subtitle="Select class, date and mark each student. Parents get automatic alerts for absent and sick statuses." />

      <div className="flex flex-wrap gap-3 mb-4">
        <select className="input w-44" value={sel.class_id} onChange={(e) => setSel({ ...sel, class_id: e.target.value, section: "" })} data-testid="att-class">
          <option value="">Class…</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-32" value={sel.section} onChange={(e) => setSel({ ...sel, section: e.target.value })} disabled={!sel.class_id} data-testid="att-section">
          <option value="">Section…</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input className="input w-44" type="date" value={sel.date} onChange={(e) => setSel({ ...sel, date: e.target.value })} data-testid="att-date" />
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
    </div>
  );
}
