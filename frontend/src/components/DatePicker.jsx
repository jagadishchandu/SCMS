import React, { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

/**
 * Lightweight calendar date picker — popover style, Tailwind, no extra deps.
 * Replaces <input type="date"> where we need visual consistency with the rest
 * of the app's primitives.
 *
 * Props:
 *   value       — string "YYYY-MM-DD" | "YYYY-MM" (for month mode) | ""
 *   onChange    — (newValue: string) => void
 *   mode        — "day" (default) | "month"
 *   testId      — data-testid root
 *   placeholder — text shown when empty
 *   className   — extra classes on the trigger button
 *   minDate / maxDate — optional bounds ("YYYY-MM-DD"); ignored in month mode
 */
export default function DatePicker({
  value,
  onChange,
  mode = "day",
  testId = "date-picker",
  placeholder,
  className = "",
  minDate,
  maxDate,
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  // Parse current value into a Date for navigation. Empty value -> today's month.
  const parsed = useMemo(() => parseValue(value, mode), [value, mode]);
  const [viewYear, setViewYear] = useState(parsed.year);
  const [viewMonth, setViewMonth] = useState(parsed.month); // 0-indexed
  useEffect(() => {
    setViewYear(parsed.year);
    setViewMonth(parsed.month);
  }, [parsed.year, parsed.month]);

  // Close on outside click / escape
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = formatLabel(value, mode, placeholder);

  return (
    <div ref={wrapRef} className={"relative inline-block " + className} data-testid={testId}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className={
          "input inline-flex items-center justify-between gap-2 w-full text-left disabled:opacity-50 " +
          (value ? "text-ink" : "text-ink-muted")
        }
        data-testid={`${testId}-trigger`}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span className="truncate">{label}</span>
        <CalendarDays size={16} className="text-ink-muted shrink-0" />
      </button>

      {open && (
        <div
          className="absolute z-50 mt-1 w-72 rounded-lg border border-line bg-bg-surface shadow-lg p-3"
          role="dialog"
          data-testid={`${testId}-popover`}
        >
          <div className="flex items-center justify-between mb-2">
            <button
              type="button"
              className="btn-ghost p-1 rounded-md hover:bg-bg-subtle"
              onClick={() => stepView(viewYear, viewMonth, -1, mode, setViewYear, setViewMonth)}
              data-testid={`${testId}-prev`}
              aria-label="Previous"
            ><ChevronLeft size={16} /></button>
            <div className="text-sm font-medium" data-testid={`${testId}-view-label`}>
              {mode === "month"
                ? `${viewYear}`
                : `${MONTHS_LONG[viewMonth]} ${viewYear}`}
            </div>
            <button
              type="button"
              className="btn-ghost p-1 rounded-md hover:bg-bg-subtle"
              onClick={() => stepView(viewYear, viewMonth, +1, mode, setViewYear, setViewMonth)}
              data-testid={`${testId}-next`}
              aria-label="Next"
            ><ChevronRight size={16} /></button>
          </div>

          {mode === "month" ? (
            <MonthGrid
              viewYear={viewYear}
              selectedYear={parsed.year}
              selectedMonth={parsed.month}
              hasValue={!!value}
              onPick={(m) => {
                onChange(`${viewYear}-${String(m + 1).padStart(2, "0")}`);
                setOpen(false);
              }}
              testId={testId}
            />
          ) : (
            <DayGrid
              viewYear={viewYear}
              viewMonth={viewMonth}
              value={value}
              minDate={minDate}
              maxDate={maxDate}
              onPick={(iso) => { onChange(iso); setOpen(false); }}
              testId={testId}
            />
          )}

          <div className="flex items-center justify-between gap-2 mt-3 pt-2 border-t border-line/60">
            <button
              type="button"
              className="text-xs text-primary hover:underline"
              onClick={() => {
                const today = new Date();
                const iso = mode === "month"
                  ? `${today.getFullYear()}-${pad(today.getMonth() + 1)}`
                  : isoOf(today);
                onChange(iso);
                setOpen(false);
              }}
              data-testid={`${testId}-today`}
            >{mode === "month" ? "This month" : "Today"}</button>
            <button
              type="button"
              className="text-xs text-ink-muted hover:underline"
              onClick={() => setOpen(false)}
              data-testid={`${testId}-close`}
            >Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- helpers ---------------- */

const MONTHS_LONG = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DOW = ["S", "M", "T", "W", "T", "F", "S"];

const pad = (n) => String(n).padStart(2, "0");
const isoOf = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function parseValue(value, mode) {
  const today = new Date();
  if (!value) return { year: today.getFullYear(), month: today.getMonth(), day: today.getDate() };
  if (mode === "month") {
    const [y, m] = value.split("-");
    return { year: Number(y) || today.getFullYear(), month: (Number(m) || 1) - 1, day: 1 };
  }
  const [y, m, d] = value.split("-");
  return { year: Number(y) || today.getFullYear(), month: (Number(m) || 1) - 1, day: Number(d) || 1 };
}

function formatLabel(value, mode, placeholder) {
  if (!value) return placeholder || (mode === "month" ? "Pick month…" : "Pick date…");
  if (mode === "month") {
    const [y, m] = value.split("-");
    return `${MONTHS_LONG[(Number(m) || 1) - 1]} ${y}`;
  }
  const d = new Date(value + "T00:00:00");
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}

function stepView(year, month, delta, mode, setYear, setMonth) {
  if (mode === "month") {
    setYear(year + delta);
    return;
  }
  let m = month + delta;
  let y = year;
  if (m < 0) { m = 11; y -= 1; }
  else if (m > 11) { m = 0; y += 1; }
  setYear(y); setMonth(m);
}

function DayGrid({ viewYear, viewMonth, value, minDate, maxDate, onPick, testId }) {
  const firstDayOfMonth = new Date(viewYear, viewMonth, 1);
  const startWeekday = firstDayOfMonth.getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  const todayIso = isoOf(new Date());
  const min = minDate || null;
  const max = maxDate || null;

  return (
    <>
      <div className="grid grid-cols-7 gap-1 text-[10px] uppercase tracking-wider text-ink-muted mb-1">
        {DOW.map((d, i) => <div key={i} className="text-center py-1">{d}</div>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((d, i) => {
          if (d === null) return <div key={i} />;
          const iso = `${viewYear}-${pad(viewMonth + 1)}-${pad(d)}`;
          const isSelected = value === iso;
          const isToday = iso === todayIso;
          const isDisabled = (min && iso < min) || (max && iso > max);
          return (
            <button
              key={i}
              type="button"
              disabled={isDisabled}
              onClick={() => onPick(iso)}
              className={
                "h-8 rounded-md text-sm transition disabled:opacity-30 disabled:cursor-not-allowed " +
                (isSelected
                  ? "bg-primary text-primary-foreground font-medium"
                  : isToday
                    ? "border border-primary/60 text-primary hover:bg-primary/10"
                    : "hover:bg-bg-subtle text-ink")
              }
              data-testid={`${testId}-day-${iso}`}
            >{d}</button>
          );
        })}
      </div>
    </>
  );
}

function MonthGrid({ viewYear, selectedYear, selectedMonth, hasValue, onPick, testId }) {
  const today = new Date();
  return (
    <div className="grid grid-cols-3 gap-1">
      {MONTHS_SHORT.map((label, m) => {
        const isSelected = hasValue && viewYear === selectedYear && m === selectedMonth;
        const isCurrent = today.getFullYear() === viewYear && today.getMonth() === m;
        return (
          <button
            key={m}
            type="button"
            onClick={() => onPick(m)}
            className={
              "py-2 rounded-md text-sm transition " +
              (isSelected
                ? "bg-primary text-primary-foreground font-medium"
                : isCurrent
                  ? "border border-primary/60 text-primary hover:bg-primary/10"
                  : "hover:bg-bg-subtle text-ink")
            }
            data-testid={`${testId}-month-${viewYear}-${pad(m + 1)}`}
          >{label}</button>
        );
      })}
    </div>
  );
}
