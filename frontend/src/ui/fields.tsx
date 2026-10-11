import { Plus, X } from "lucide-react";
import { useState } from "react";
import { Button, Input } from "../components";

/** Pick any number of options shown as pill toggles. */
export function ChipSelect({
  legend,
  options,
  value,
  onChange,
  error,
  hint,
}: {
  legend: string;
  options: Array<{ value: string; label: string }>;
  value: string[];
  onChange: (next: string[]) => void;
  error?: string;
  hint?: string;
}) {
  return (
    <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
      <legend className="wo-label" style={{ marginBottom: "var(--space-2)", padding: 0 }}>{legend}</legend>
      <div className="app-cluster">
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            className="app-react"
            aria-pressed={value.includes(o.value)}
            onClick={() => onChange(value.includes(o.value) ? value.filter((v) => v !== o.value) : [...value, o.value])}
          >
            {o.label}
          </button>
        ))}
      </div>
      {hint ? <p className="wo-hint" style={{ margin: "var(--space-2) 0 0" }}>{hint}</p> : null}
      {error ? <p className="wo-error" style={{ margin: "var(--space-2) 0 0" }}><span aria-hidden="true">!</span>{error}</p> : null}
    </fieldset>
  );
}

/** A short list of text lines the member can add to and remove from. */
export function StringList({
  label,
  value,
  onChange,
  max,
  placeholder,
  error,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  max: number;
  placeholder?: string;
  error?: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const text = draft.trim();
    if (!text || value.length >= max) return;
    onChange([...value, text]);
    setDraft("");
  };
  return (
    <div className="app-stack" style={{ gap: "var(--space-2)" }}>
      <span className="wo-label">{label}</span>
      {value.length > 0 ? (
        <ol className="app-stack" style={{ gap: "var(--space-2)", margin: 0, paddingLeft: "var(--space-6)" }}>
          {value.map((item, index) => (
            <li key={`${item}-${index}`}>
              <span className="app-cluster" style={{ flexWrap: "nowrap" }}>
                <span style={{ flex: 1 }}>{item}</span>
                <button type="button" className="app-iconbtn" aria-label={`Remove ${item}`} onClick={() => onChange(value.filter((_, i) => i !== index))}>
                  <X size={18} strokeWidth={1.5} />
                </button>
              </span>
            </li>
          ))}
        </ol>
      ) : null}
      {value.length < max ? (
        <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <Input
              label={`Add to ${label.toLowerCase()}`}
              placeholder={placeholder}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  add();
                }
              }}
            />
          </div>
          <Button variant="secondary" onClick={add} disabled={!draft.trim()} icon={<Plus size={16} strokeWidth={1.5} aria-hidden="true" />}>
            Add
          </Button>
        </div>
      ) : (
        <p className="wo-hint" style={{ margin: 0 }}>You can add up to {max}.</p>
      )}
      {error ? <p className="wo-error" style={{ margin: 0 }}><span aria-hidden="true">!</span>{error}</p> : null}
    </div>
  );
}

/** Money is typed in whole currency units and stored in minor units (kobo, cents). */
export function toMinor(text: string): number | null {
  const cleaned = text.replace(/[,\s]/g, "");
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? Math.round(n * 100) : null;
}

export function fromMinor(minor: unknown): string {
  return typeof minor === "number" ? String(minor / 100) : "";
}
