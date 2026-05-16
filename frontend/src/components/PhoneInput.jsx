import React, { useMemo } from "react";

// Common country dial-codes — keep the most-used at top, then alphabetical.
// Stored value is always "+<code><digits>" (E.164-ish).
export const COUNTRY_CODES = [
  { code: "91", name: "India", flag: "IN" },
  { code: "1", name: "USA / Canada", flag: "US" },
  { code: "44", name: "United Kingdom", flag: "GB" },
  { code: "61", name: "Australia", flag: "AU" },
  { code: "65", name: "Singapore", flag: "SG" },
  { code: "971", name: "UAE", flag: "AE" },
  { code: "966", name: "Saudi Arabia", flag: "SA" },
  { code: "60", name: "Malaysia", flag: "MY" },
  { code: "94", name: "Sri Lanka", flag: "LK" },
  { code: "977", name: "Nepal", flag: "NP" },
  { code: "880", name: "Bangladesh", flag: "BD" },
  { code: "92", name: "Pakistan", flag: "PK" },
  { code: "49", name: "Germany", flag: "DE" },
  { code: "33", name: "France", flag: "FR" },
  { code: "39", name: "Italy", flag: "IT" },
  { code: "34", name: "Spain", flag: "ES" },
  { code: "81", name: "Japan", flag: "JP" },
  { code: "86", name: "China", flag: "CN" },
  { code: "82", name: "South Korea", flag: "KR" },
  { code: "27", name: "South Africa", flag: "ZA" },
  { code: "234", name: "Nigeria", flag: "NG" },
  { code: "254", name: "Kenya", flag: "KE" },
];

const SORTED_CODES = [...COUNTRY_CODES];

/**
 * Parse a stored phone value (e.g. "+919876543210" or "9876543210") into
 * { code, local } using the longest-prefix match against KNOWN_CODES.
 * If no match, returns the default code + the value as the local part.
 */
function parsePhone(value, defaultCode = "91") {
  const v = String(value || "").trim();
  if (!v) return { code: defaultCode, local: "" };
  const digits = v.replace(/^\+/, "").replace(/[^\d]/g, "");
  // longest-prefix match (1–4 digits)
  const sorted = [...SORTED_CODES].sort((a, b) => b.code.length - a.code.length);
  for (const c of sorted) {
    if (digits.startsWith(c.code) && digits.length > c.code.length) {
      return { code: c.code, local: digits.slice(c.code.length) };
    }
  }
  // value didn't include a recognised dial-code → assume default
  return { code: defaultCode, local: digits };
}

export default function PhoneInput({
  value,
  onChange,
  required = false,
  placeholder = "Phone number",
  defaultCode = "91",
  testId,
  className = "",
  disabled = false,
}) {
  const parsed = useMemo(() => parsePhone(value, defaultCode), [value, defaultCode]);

  const update = (next) => {
    const code = (next.code ?? parsed.code).replace(/[^\d]/g, "");
    const local = (next.local ?? parsed.local).replace(/[^\d]/g, "");
    onChange(local ? `+${code}${local}` : "");
  };

  return (
    <div className={`flex gap-2 ${className}`} data-testid={testId}>
      <select
        className="input w-28 shrink-0"
        value={parsed.code}
        onChange={(e) => update({ code: e.target.value })}
        disabled={disabled}
        data-testid={testId ? `${testId}-code` : undefined}
        aria-label="Country dial code"
      >
        {SORTED_CODES.map((c) => (
          <option key={c.code} value={c.code}>+{c.code} {c.flag}</option>
        ))}
      </select>
      <input
        type="tel"
        className="input flex-1"
        inputMode="tel"
        autoComplete="tel-national"
        required={required}
        placeholder={placeholder}
        value={parsed.local}
        onChange={(e) => update({ local: e.target.value })}
        disabled={disabled}
        data-testid={testId ? `${testId}-local` : undefined}
      />
    </div>
  );
}
