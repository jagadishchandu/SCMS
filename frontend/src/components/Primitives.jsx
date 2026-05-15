import React from "react";
import { cn } from "../lib/utils";

export function PageHeader({ title, subtitle, actions, eyebrow }) {
  return (
    <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
      <div>
        {eyebrow ? <div className="overline mb-2" data-testid="page-eyebrow">{eyebrow}</div> : null}
        <h1 className="font-display text-3xl lg:text-4xl font-medium tracking-tight" data-testid="page-title">{title}</h1>
        {subtitle ? <p className="text-ink-soft mt-2 max-w-2xl">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function KPI({ label, value, hint, accent = "primary", testId }) {
  const accentMap = {
    primary: "bg-primary-light text-primary",
    secondary: "bg-bg-subtle text-secondary-foreground",
    success: "bg-status-success-bg text-status-success",
    warning: "bg-status-warning-bg text-status-warning",
    danger: "bg-status-danger-bg text-status-danger",
    info: "bg-status-info-bg text-status-info",
  };
  return (
    <div className="card relative" data-testid={testId}>
      <div className="overline mb-3">{label}</div>
      <div className="flex items-baseline gap-2">
        <div className="font-display text-3xl font-medium">{value}</div>
      </div>
      {hint ? <div className={cn("badge mt-3", accentMap[accent])}>{hint}</div> : null}
    </div>
  );
}

export function Section({ title, action, children }) {
  return (
    <section className="panel" data-testid={`section-${(title || "").toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="flex items-center justify-between px-5 py-4 border-b border-line">
        <h3 className="font-display text-base font-medium">{title}</h3>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Empty({ title = "Nothing yet", message }) {
  return (
    <div className="py-12 text-center text-ink-muted">
      <div className="font-display text-lg text-ink-soft mb-1">{title}</div>
      {message ? <div className="text-sm">{message}</div> : null}
    </div>
  );
}
