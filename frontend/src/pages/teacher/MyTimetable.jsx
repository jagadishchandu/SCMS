import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat"];
const LABEL = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday" };

export default function MyTimetable() {
  const [slots, setSlots] = useState([]);
  const [classes, setClasses] = useState([]);
  const [subjects, setSubjects] = useState([]);
  useEffect(() => {
    Promise.all([
      api.get("/timetable").then((r) => r.data),
      api.get("/academic/classes").then((r) => r.data),
      api.get("/academic/subjects").then((r) => r.data),
    ]).then(([s, c, sb]) => { setSlots(s); setClasses(c); setSubjects(sb); });
  }, []);

  const byDay = {};
  for (const s of slots) { byDay[s.day] = byDay[s.day] || []; byDay[s.day].push(s); }

  return (
    <div data-testid="my-timetable-page">
      <PageHeader eyebrow="My calendar" title="My weekly timetable" subtitle="Your assigned periods across the week." />
      {slots.length === 0 ? <Empty title="No timetable assigned yet" /> :
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {DAYS.filter((d) => byDay[d]).map((d) => (
            <Section key={d} title={LABEL[d]}>
              <ul className="divide-y divide-line">
                {byDay[d].sort((a, b) => a.period - b.period).map((s) => (
                  <li key={s.id} className="py-3" data-testid={`my-slot-${s.id}`}>
                    <div className="flex items-baseline justify-between">
                      <div className="font-medium">{subjects.find((x) => x.id === s.subject_id)?.name || "—"}</div>
                      <div className="text-xs text-ink-muted">Period {s.period}</div>
                    </div>
                    <div className="text-xs text-ink-muted">
                      {classes.find((c) => c.id === s.class_id)?.name} · Section {s.section} · {s.start_time}–{s.end_time}
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          ))}
        </div>}
    </div>
  );
}
