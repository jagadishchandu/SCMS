import React, { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section } from "../../components/Primitives";
import { CaretLeft, CaretRight } from "@phosphor-icons/react";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function monthMatrix(year, month) {
  // month: 0-11
  const first = new Date(year, month, 1);
  const startDay = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells = [];
  // leading blanks
  for (let i = 0; i < startDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  // pad to 6 weeks (42 cells)
  while (cells.length < 42) cells.push(null);
  return cells;
}

function isoDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function CalendarPage() {
  const today = new Date();
  const [cursor, setCursor] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [events, setEvents] = useState([]);

  const monthStr = useMemo(() => `${cursor.y}-${String(cursor.m + 1).padStart(2, "0")}`, [cursor]);

  useEffect(() => {
    api.get("/calendar/events").then((r) => setEvents(r.data));
  }, []);

  const eventsByDate = useMemo(() => {
    const map = {};
    for (const ev of events) {
      if (!ev.date) continue;
      const start = new Date(ev.date + "T00:00:00");
      const end = ev.end_date ? new Date(ev.end_date + "T00:00:00") : start;
      // iterate days
      const cur = new Date(start);
      while (cur <= end) {
        const key = isoDate(cur);
        map[key] = map[key] || [];
        map[key].push(ev);
        cur.setDate(cur.getDate() + 1);
      }
    }
    return map;
  }, [events]);

  const cells = monthMatrix(cursor.y, cursor.m);
  const monthName = new Date(cursor.y, cursor.m, 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });

  const prev = () => setCursor((c) => {
    const d = new Date(c.y, c.m - 1, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  });
  const next = () => setCursor((c) => {
    const d = new Date(c.y, c.m + 1, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  });

  const todayKey = isoDate(today);

  // upcoming events (next 60 days)
  const upcoming = useMemo(() => {
    const t = todayKey;
    return events.filter((e) => (e.date || "") >= t).sort((a, b) => (a.date || "").localeCompare(b.date || "")).slice(0, 10);
  }, [events, todayKey]);

  return (
    <div data-testid="calendar-page">
      <PageHeader eyebrow="Calendar" title="School calendar"
        subtitle="Monthly view of holidays and exam schedules. Color-coded by event type." />

      <div className="flex items-center gap-2 mb-4">
        <button className="btn-secondary p-2" onClick={prev} data-testid="cal-prev"><CaretLeft size={16} /></button>
        <div className="font-display text-lg font-medium" data-testid="cal-month">{monthName}</div>
        <button className="btn-secondary p-2" onClick={next} data-testid="cal-next"><CaretRight size={16} /></button>
        <button className="btn-ghost text-sm" onClick={() => setCursor({ y: today.getFullYear(), m: today.getMonth() })} data-testid="cal-today">Today</button>
        <div className="ml-auto flex items-center gap-3 text-xs">
          <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-status-danger inline-block"/> Holiday</span>
          <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-primary inline-block"/> Exam</span>
          <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block"/> Duty</span>
        </div>
      </div>

      <div className="panel p-2 mb-6 overflow-x-auto">
        <div className="grid grid-cols-7 text-center text-[11px] uppercase tracking-widest font-semibold text-ink-muted py-2 min-w-[700px]">
          {WEEKDAYS.map((d) => <div key={d}>{d}</div>)}
        </div>
        <div className="grid grid-cols-7 gap-1 min-w-[700px]">
          {cells.map((d, i) => {
            if (!d) return <div key={i} className="aspect-square bg-bg-subtle rounded-md" />;
            const key = isoDate(d);
            const isToday = key === todayKey;
            const dayEvents = eventsByDate[key] || [];
            return (
              <div key={i} className={`aspect-square rounded-md p-1.5 border ${isToday ? "border-primary bg-primary-light" : "border-line bg-bg-surface"} text-left overflow-hidden`} data-testid={`cal-day-${key}`}>
                <div className={`text-xs ${isToday ? "font-semibold text-primary" : "text-ink-soft"}`}>{d.getDate()}</div>
                <div className="mt-1 space-y-0.5">
                  {dayEvents.slice(0, 2).map((e, idx) => {
                    const cls = e.type === "holiday"
                      ? "bg-status-danger-bg text-status-danger"
                      : e.type === "duty"
                      ? "bg-amber-100 text-amber-800"
                      : "bg-primary-light text-primary";
                    return (
                      <div key={idx} className={`text-[10px] px-1.5 py-0.5 rounded truncate ${cls}`} title={e.title}>
                        {e.title}
                      </div>
                    );
                  })}
                  {dayEvents.length > 2 && <div className="text-[10px] text-ink-muted">+{dayEvents.length - 2} more</div>}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <Section title="Upcoming events (next 60 days)">
        {upcoming.length === 0 ? <div className="text-ink-muted text-sm">Nothing scheduled.</div> :
          <ul className="divide-y divide-line">
            {upcoming.map((e, i) => (
              <li key={i} className="py-3 flex items-center justify-between" data-testid={`cal-upcoming-${i}`}>
                <div className="flex items-center gap-3">
                  <span className={`w-2 h-2 rounded-full ${e.type === "holiday" ? "bg-status-danger" : e.type === "duty" ? "bg-amber-500" : "bg-primary"}`} />
                  <div>
                    <div className="font-medium">{e.title}</div>
                    <div className="text-xs text-ink-muted">
                      {e.type}{e.meta?.term ? ` · ${e.meta.term}` : ""}
                      {e.type === "duty" && e.meta?.duty_type ? ` · ${e.meta.duty_type.replace("_", " ")}` : ""}
                      {e.type === "duty" && e.meta?.location ? ` · ${e.meta.location}` : ""}
                    </div>
                  </div>
                </div>
                <div className="text-sm text-ink-soft">{e.date}{e.end_date ? ` → ${e.end_date}` : ""}</div>
              </li>
            ))}
          </ul>}
      </Section>
    </div>
  );
}
