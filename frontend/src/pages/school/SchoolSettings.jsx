import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, Section } from "../../components/Primitives";
import { GraduationCap, FloppyDisk } from "@phosphor-icons/react";
import toast from "react-hot-toast";

const PRESET_COLORS = [
  "#4E5B3A", "#2F6F4F", "#4A6CC2", "#7E4FB2",
  "#B25F4F", "#C49A2C", "#1F2937", "#D4A373",
];

export default function SchoolSettings() {
  const { user } = useAuth();
  const [school, setSchool] = useState(null);
  const [logo, setLogo] = useState("");
  const [color, setColor] = useState("#4E5B3A");
  const [tagline, setTagline] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    if (!user?.school_id) return;
    const { data } = await api.get(`/schools/${user.school_id}`);
    setSchool(data);
    setLogo(data?.branding?.logo || "");
    setColor(data?.branding?.primary_color || "#4E5B3A");
    setTagline(data?.branding?.tagline || "");
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [user?.school_id]);

  const onLogoFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 1024 * 1024) { toast.error("Logo must be under 1 MB"); return; }
    const reader = new FileReader();
    reader.onload = () => setLogo(reader.result);
    reader.readAsDataURL(f);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/schools/${user.school_id}/branding`, {
        logo: logo || null,
        primary_color: color || null,
        tagline: tagline || null,
      });
      toast.success("Branding saved — refresh to see updated top bar");
      load();
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSaving(false); }
  };

  return (
    <div data-testid="school-settings-page">
      <PageHeader eyebrow="Settings" title="School branding"
        subtitle="Upload your school logo, pick a primary color, and set a short tagline. Changes apply to your school's dashboard, the parent portal and PDFs." />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Section title="Logo">
            <div className="flex items-center gap-4">
              <div className="w-20 h-20 rounded-lg overflow-hidden bg-bg-subtle border border-line grid place-items-center shrink-0">
                {logo ? <img src={logo} alt="logo preview" className="w-full h-full object-cover" /> :
                  <GraduationCap size={36} className="text-ink-muted" />}
              </div>
              <div className="flex-1">
                <label className="btn-secondary cursor-pointer w-fit">
                  Upload PNG/JPG/SVG (≤ 1 MB)
                  <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" className="hidden" onChange={onLogoFile} data-testid="branding-logo-input" />
                </label>
                {logo && <button className="btn-ghost text-xs ml-2 text-status-danger" onClick={() => setLogo("")} data-testid="branding-logo-clear">Remove</button>}
              </div>
            </div>
          </Section>

          <Section title="Primary color">
            <div className="flex flex-wrap items-center gap-3">
              <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="w-12 h-12 rounded-lg border border-line cursor-pointer" data-testid="branding-color-picker" />
              <input type="text" value={color} onChange={(e) => setColor(e.target.value)} className="input w-32" />
              <div className="flex flex-wrap gap-2">
                {PRESET_COLORS.map((c) => (
                  <button
                    key={c}
                    onClick={() => setColor(c)}
                    title={c}
                    aria-label={`Pick ${c}`}
                    className={`w-8 h-8 rounded-full border-2 transition ${color.toLowerCase() === c.toLowerCase() ? "border-ink" : "border-transparent"}`}
                    style={{ background: c }}
                    data-testid={`branding-preset-${c.replace("#","")}`}
                  />
                ))}
              </div>
            </div>
          </Section>

          <Section title="Tagline">
            <input className="input" maxLength={64} placeholder="e.g. Learning that lifts every child"
              value={tagline} onChange={(e) => setTagline(e.target.value)} data-testid="branding-tagline-input" />
            <div className="text-[11px] text-ink-muted mt-1">{tagline.length}/64</div>
          </Section>

          <button className="btn-primary" onClick={save} disabled={saving} data-testid="branding-save-btn">
            <FloppyDisk size={16}/> {saving ? "Saving…" : "Save branding"}
          </button>
        </div>

        <div>
          <Section title="Live preview">
            <div className="border border-line rounded-lg p-4 bg-bg-surface">
              <div className="flex items-center gap-3 pb-3 border-b border-line">
                {logo ? (
                  <img src={logo} alt="" className="w-10 h-10 rounded-lg object-cover" />
                ) : (
                  <div className="w-10 h-10 rounded-lg grid place-items-center text-white" style={{ background: color }}>
                    <GraduationCap size={20} weight="duotone" />
                  </div>
                )}
                <div>
                  <div className="font-display font-medium leading-tight">{school?.name || "Your School"}</div>
                  <div className="text-[11px] uppercase tracking-widest text-ink-muted">{tagline || "Your tagline here"}</div>
                </div>
              </div>
              <div className="mt-3">
                <button className="btn rounded-lg text-white text-xs px-3 py-1.5" style={{ background: color }}>Sample button</button>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
