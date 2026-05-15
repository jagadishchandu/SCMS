import React, { useEffect, useState } from "react";
import { api, formatApiError } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";
import { PageHeader, Section } from "../../components/Primitives";
import { GraduationCap, FloppyDisk, Translate } from "@phosphor-icons/react";
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
  const [lang, setLang] = useState("en");
  const [supportedLangs, setSupportedLangs] = useState([]);
  const [savingLang, setSavingLang] = useState(false);

  const load = async () => {
    if (!user?.school_id) return;
    const [{ data }, { data: langData }] = await Promise.all([
      api.get(`/schools/${user.school_id}`),
      api.get(`/schools/${user.school_id}/language`),
    ]);
    setSchool(data);
    setLogo(data?.branding?.logo || "");
    setColor(data?.branding?.primary_color || "#4E5B3A");
    setTagline(data?.branding?.tagline || "");
    setLang(langData?.language || "en");
    setSupportedLangs(langData?.supported || []);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [user?.school_id]);

  const saveLanguage = async (next) => {
    setLang(next);
    setSavingLang(true);
    try {
      await api.patch(`/schools/${user.school_id}/language`, { language: next });
      toast.success("Default notification language updated");
    } catch (e) { toast.error(formatApiError(e)); }
    finally { setSavingLang(false); }
  };

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

          <Section title="Notification language">
            <div className="flex items-start gap-3">
              <Translate size={18} className="text-primary mt-2.5 shrink-0" />
              <div className="flex-1">
                <p className="text-sm text-ink-soft mb-2">
                  Default language used for WhatsApp + Email messages sent to parents who haven't set their own preference.
                </p>
                <select
                  className="input w-full max-w-sm"
                  value={lang}
                  onChange={(e) => saveLanguage(e.target.value)}
                  disabled={savingLang}
                  data-testid="school-language-select"
                >
                  {supportedLangs.map((l) => (
                    <option key={l.code} value={l.code}>{l.label}</option>
                  ))}
                </select>
                {savingLang && <div className="text-xs text-ink-muted mt-1">Saving…</div>}
              </div>
            </div>
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

      <div className="mt-10">
        <IntegrationTests />
      </div>
    </div>
  );
}

// ---------------- Integration tests ----------------

function IntegrationTests() {
  const [status, setStatus] = useState(null);
  const [whatsappTo, setWhatsappTo] = useState("");
  const [telegramId, setTelegramId] = useState("");
  const [emailTo, setEmailTo] = useState("");
  const [busy, setBusy] = useState({});
  const [results, setResults] = useState({});

  useEffect(() => {
    api.get("/integrations/test/status").then((r) => setStatus(r.data)).catch(() => {});
  }, []);

  const run = async (key, url, body) => {
    setBusy((b) => ({ ...b, [key]: true }));
    setResults((r) => ({ ...r, [key]: null }));
    try {
      const { data } = await api.post(url, body);
      setResults((r) => ({ ...r, [key]: data }));
      if (data.ok) toast.success(`${key} sent (${data.provider})`);
      else toast.error(data.error || `${key} failed`);
    } catch (err) {
      const msg = formatApiError(err);
      setResults((r) => ({ ...r, [key]: { ok: false, error: msg } }));
      toast.error(msg);
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
      // refresh status (linked_to_me may flip after a successful telegram test)
      api.get("/integrations/test/status").then((r) => setStatus(r.data)).catch(() => {});
    }
  };

  const Pill = ({ on }) => (
    <span className={on ? "badge-success" : "badge-neutral"} data-testid={`pill-${on ? "on" : "off"}`}>
      {on ? "configured" : "not configured"}
    </span>
  );

  const ResultLine = ({ data, testid }) => {
    if (!data) return null;
    return (
      <div className={`mt-2 text-xs ${data.ok ? "text-status-success" : "text-status-danger"}`} data-testid={testid}>
        {data.ok ? `✅ sent via ${data.provider} · id ${data.message_id || "—"}`
                 : `❌ ${data.error || "failed"}`}
      </div>
    );
  };

  return (
    <Section title="Test integrations">
      <p className="text-sm text-ink-soft mb-4">
        Send a real test message to validate each integration before relying on it for parent alerts.
      </p>

      {/* WhatsApp */}
      <div className="border border-line rounded-lg p-4 mb-3" data-testid="integration-whatsapp">
        <div className="flex items-center justify-between mb-3">
          <div className="font-medium">WhatsApp</div>
          <div className="flex gap-2 text-[11px]">
            <span>Meta: <Pill on={!!status?.meta_whatsapp?.configured} /></span>
            <span>Twilio: <Pill on={!!status?.twilio_whatsapp?.configured} /></span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <input className="input flex-1 min-w-[200px]"
            placeholder="Recipient in E.164 format e.g. +919999999999"
            value={whatsappTo} onChange={(e) => setWhatsappTo(e.target.value)}
            data-testid="test-whatsapp-input" />
          <button className="btn-primary"
            disabled={!whatsappTo || busy.whatsapp}
            onClick={() => run("whatsapp", "/integrations/test/whatsapp", { to: whatsappTo })}
            data-testid="test-whatsapp-btn">
            {busy.whatsapp ? "Sending…" : "Send test"}
          </button>
        </div>
        <ResultLine data={results.whatsapp} testid="test-whatsapp-result" />
      </div>

      {/* Telegram */}
      <div className="border border-line rounded-lg p-4 mb-3" data-testid="integration-telegram">
        <div className="flex items-center justify-between mb-3">
          <div className="font-medium">Telegram</div>
          <div className="flex gap-2 text-[11px]">
            <span>Bot: <Pill on={!!status?.telegram?.configured} /></span>
            {status?.telegram?.linked_to_me && <span className="badge-success">your account linked</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <input className="input flex-1 min-w-[200px]"
            placeholder="chat_id (leave blank to use your own linked account)"
            value={telegramId} onChange={(e) => setTelegramId(e.target.value)}
            data-testid="test-telegram-input" />
          <button className="btn-primary"
            disabled={busy.telegram}
            onClick={() => run("telegram", "/integrations/test/telegram",
                               telegramId ? { chat_id: Number(telegramId) || telegramId } : {})}
            data-testid="test-telegram-btn">
            {busy.telegram ? "Sending…" : "Send test"}
          </button>
        </div>
        <div className="text-[11px] text-ink-muted mt-1">
          To link your own account, open the bot on Telegram and send{" "}
          <code>/start {`<your-email>`}</code>.
        </div>
        <ResultLine data={results.telegram} testid="test-telegram-result" />
      </div>

      {/* Email */}
      <div className="border border-line rounded-lg p-4" data-testid="integration-email">
        <div className="flex items-center justify-between mb-3">
          <div className="font-medium">Email (SMTP)</div>
          <div className="flex gap-2 text-[11px]">
            <span>SMTP: <Pill on={!!status?.smtp?.configured} /></span>
            {status?.smtp?.from && <span className="text-ink-muted truncate">from {status.smtp.from}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <input type="email" className="input flex-1 min-w-[200px]"
            placeholder="recipient@example.com"
            value={emailTo} onChange={(e) => setEmailTo(e.target.value)}
            data-testid="test-email-input" />
          <button className="btn-primary"
            disabled={!emailTo || busy.email}
            onClick={() => run("email", "/integrations/test/email", { to: emailTo })}
            data-testid="test-email-btn">
            {busy.email ? "Sending…" : "Send test"}
          </button>
        </div>
        <ResultLine data={results.email} testid="test-email-result" />
      </div>
    </Section>
  );
}
