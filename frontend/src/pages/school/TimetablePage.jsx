import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat"];
const DAY_LABEL = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat" };

export default function TimetablePage() {
  const [slots, setSlots] = useState([]);
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [sel, setSel] = useState({ class_id: "", section: "" });

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

  const sections = classes.find((c) => c.id === sel.class_id)?.sections || [];
  const periods = [...new Set(slots.map((s) => s.period))].sort((a, b) => a - b);
  const grid = {};
  for (const s of slots) {
    grid[s.day] = grid[s.day] || {};
    grid[s.day][s.period] = s;
  }

  return (
    <div data-testid="timetable-page">
      <PageHeader eyebrow="Schedule" title="Class timetable" subtitle="Weekly class schedule visible to school admin and assigned teachers." />
      <div className="flex flex-wrap gap-3 mb-4">
        <select className="input w-44" value={sel.class_id} onChange={(e) => setSel({ class_id: e.target.value, section: "" })}>
          <option value="">Class…</option>
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select className="input w-32" value={sel.section} onChange={(e) => setSel({ ...sel, section: e.target.value })} disabled={!sel.class_id}>
          <option value="">Section…</option>
          {sections.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
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
                    <tr key={d} className="table-row">
                      <td className="td font-medium">{DAY_LABEL[d]}</td>
                      {periods.map((p) => {
                        const slot = grid[d][p];
                        return (
                          <td key={p} className="td">
                            {slot ? (
                              <div>
                                <div className="font-medium">{subjects.find(s => s.id === slot.subject_id)?.name || "—"}</div>
                                <div className="text-xs text-ink-muted">{teachers.find(t => t.id === slot.teacher_id)?.name || "—"}</div>
                                <div className="text-[10px] text-ink-muted">{slot.start_time}–{slot.end_time}</div>
                              </div>
                            ) : null}
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
