import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";

export default function TeacherPerformancePage({ self = false }) {
  const [items, setItems] = useState([]);
  useEffect(() => {
    api.get("/analytics/teacher-performance").then((r) => setItems(r.data));
  }, []);

  return (
    <div data-testid="teacher-performance-page">
      <PageHeader
        eyebrow={self ? "My performance" : "Teacher performance"}
        title={self ? "How am I doing?" : "Teacher performance summary"}
        subtitle={self
          ? "Your own performance summary based on class outcomes & operational compliance."
          : "40% attendance · 30% marks · 15% compliance · 15% admin review. Visible only to School Super Admin."}
      />
      {items.length === 0 ? <Empty title="No performance data yet" /> :
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map((it) => (
            <div key={it.teacher.id} className="border border-line rounded-lg p-5" data-testid={`tp-card-${it.teacher.id}`}>
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <div className="font-display text-lg font-medium">{it.teacher.name}</div>
                  <div className="text-xs text-ink-muted">{it.teacher.email}</div>
                </div>
                <span className={
                  it.status === "Excellent" ? "badge-success" :
                  it.status === "Good" ? "badge-info" :
                  it.status === "Needs Attention" ? "badge-warning" : "badge-danger"
                }>{it.status}</span>
              </div>
              <div className="flex items-baseline gap-2 mb-4">
                <div className="font-display text-4xl font-medium">{it.score}</div>
                <div className="text-xs text-ink-muted">/ 100</div>
              </div>
              <ul className="text-xs text-ink-soft space-y-1">
                <li className="flex justify-between"><span>Attendance trend (40%)</span><span>{it.breakdown.attendance_pct ?? 0}%</span></li>
                <li className="flex justify-between"><span>Marks trend (30%)</span><span>{it.breakdown.marks_avg ?? 0}%</span></li>
                <li className="flex justify-between"><span>Compliance (15%)</span><span>{it.breakdown.compliance_pct ?? 0}%</span></li>
                <li className="flex justify-between"><span>Admin review (15%)</span><span>{it.breakdown.admin_review ?? 0}</span></li>
                <li className="flex justify-between mt-1"><span>Assigned classes</span><span>{it.assigned_classes}</span></li>
              </ul>
            </div>
          ))}
        </div>}
    </div>
  );
}
