import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { PageHeader, Section, Empty } from "../../components/Primitives";
import { UploadSimple, DownloadSimple } from "@phosphor-icons/react";
import toast from "react-hot-toast";
import { formatDate } from "../../lib/utils";

const KINDS = [
  { kind: "students", label: "Students" },
  { kind: "attendance", label: "Attendance", needsClass: true },
  { kind: "holidays", label: "Holidays" },
];

export default function UploadsPage() {
  const [logs, setLogs] = useState([]);
  const [classes, setClasses] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/uploads/logs").then((r) => setLogs(r.data));
    api.get("/academic/classes").then((r) => setClasses(r.data));
  }, []);

  const downloadTemplate = async (kind) => {
    try {
      const res = await api.get(`/uploads/template/${kind}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = `${kind}_template.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const upload = async (kind, file, extras = {}) => {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      for (const k of Object.keys(extras)) fd.append(k, extras[k]);
      const { data } = await api.post(`/uploads/${kind}`, fd);
      toast.success(`Imported ${data.inserted} rows. ${data.errors.length} errors.`);
      const r = await api.get("/uploads/logs"); setLogs(r.data);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <div data-testid="uploads-page">
      <PageHeader eyebrow="Bulk import" title="Excel uploads" subtitle="Download a sample template, fill it, upload and review results." />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {KINDS.map((k) => (
          <div key={k.kind} className="border border-line rounded-lg p-5" data-testid={`upload-card-${k.kind}`}>
            <div className="overline mb-2">{k.kind}</div>
            <div className="font-display text-lg font-medium mb-3">{k.label}</div>
            <button className="btn-secondary mb-2 w-full" onClick={() => downloadTemplate(k.kind)} data-testid={`download-${k.kind}-template`}>
              <DownloadSimple size={14}/> Download template
            </button>
            {k.needsClass ? <ClassSectionUpload classes={classes} kind={k.kind} busy={busy} onUpload={upload} />
              : <SimpleUpload kind={k.kind} busy={busy} onUpload={upload} />}
          </div>
        ))}
      </div>

      <Section title={`${logs.length} recent uploads`}>
        {logs.length === 0 ? <Empty title="No uploads yet" /> :
          <table className="table">
            <thead><tr><th className="th">Date</th><th className="th">Kind</th><th className="th">Rows</th><th className="th">Inserted</th><th className="th">Errors</th></tr></thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id} className="table-row">
                  <td className="td">{formatDate(l.created_at)}</td>
                  <td className="td font-mono text-xs">{l.kind}</td>
                  <td className="td">{l.rows}</td>
                  <td className="td">{l.inserted}</td>
                  <td className="td">{l.errors?.length || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>}
      </Section>
    </div>
  );
}

function SimpleUpload({ kind, busy, onUpload }) {
  return (
    <label className="btn-primary w-full cursor-pointer" data-testid={`upload-${kind}-input-label`}>
      <UploadSimple size={14}/> {busy ? "Uploading…" : "Upload Excel"}
      <input
        type="file" accept=".xlsx" className="hidden"
        onChange={(e) => e.target.files?.[0] && onUpload(kind, e.target.files[0])}
        data-testid={`upload-${kind}-input`}
      />
    </label>
  );
}

function ClassSectionUpload({ kind, busy, onUpload, classes }) {
  const [cid, setCid] = useState(""); const [sec, setSec] = useState("");
  const sections = classes.find((c) => c.id === cid)?.sections || [];
  return (
    <div className="space-y-2">
      <select className="input" value={cid} onChange={(e) => setCid(e.target.value)} data-testid={`upload-${kind}-class`}>
        <option value="">Class…</option>
        {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </select>
      <select className="input" value={sec} onChange={(e) => setSec(e.target.value)} disabled={!cid}>
        <option value="">Section…</option>
        {sections.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
      <label className={`btn-primary w-full cursor-pointer ${(!cid || !sec) ? "opacity-50 pointer-events-none" : ""}`}>
        <UploadSimple size={14}/> {busy ? "Uploading…" : "Upload Excel"}
        <input
          type="file" accept=".xlsx" className="hidden"
          onChange={(e) => e.target.files?.[0] && onUpload(kind, e.target.files[0], { class_id: cid, section: sec })}
          data-testid={`upload-${kind}-input`}
        />
      </label>
    </div>
  );
}
