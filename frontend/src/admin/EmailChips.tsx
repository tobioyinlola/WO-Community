import { AlertCircle, X } from "lucide-react";
import { useId, useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { addChips, FLAG_TEXT, MAX_EMAILS, splitList, type Chip } from "./emailTags";

interface Props {
  chips: Chip[];
  onChange: (chips: Chip[]) => void;
  disabled?: boolean;
}

/**
 * A field that turns addresses into chips. Enter, comma, space, semicolon, Tab or leaving the field
 * closes the chip; pasting a list makes one chip each; Backspace on an empty field removes the last.
 */
export function EmailChips({ chips, onChange, disabled }: Props) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");

  const take = (text: string) => {
    const pieces = splitList(text);
    if (pieces.length === 0) return;
    const { chips: next, merged, overflow } = addChips(chips, pieces);
    onChange(next);
    const parts = [];
    if (merged) parts.push(`${merged} repeated ${merged === 1 ? "address was" : "addresses were"} merged`);
    if (overflow) parts.push(`${overflow} over the limit of ${MAX_EMAILS} ${overflow === 1 ? "was" : "were"} left out`);
    setNote(parts.join(". "));
  };
  const remove = (email: string) => {
    onChange(chips.filter((c) => c.email !== email));
    input.current?.focus();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if ([",", ";", " "].includes(e.key) || e.key === "Enter" || (e.key === "Tab" && draft.trim())) {
      if (draft.trim()) {
        e.preventDefault();
        take(draft);
        setDraft("");
      } else if (e.key === "Enter") {
        e.preventDefault();
      }
    } else if (e.key === "Backspace" && !draft && chips.length) {
      onChange(chips.slice(0, -1));
    }
  };
  const onPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData("text");
    if (/[\s,;]/.test(text.trim())) {
      e.preventDefault();
      take(draft + text);
      setDraft("");
    }
  };

  return (
    <div className="wo-field">
      <label className="wo-label" htmlFor={id}>Email addresses</label>
      <div className="adm-chips">
        <ul className="adm-chips__list" aria-label="Addresses to invite">
          {chips.map((c) => (
            <li key={c.email} className="adm-chip" data-flag={c.flag ?? "ok"} title={c.flag ? FLAG_TEXT[c.flag] : undefined}>
              {c.flag ? <AlertCircle size={14} strokeWidth={1.75} aria-hidden="true" /> : null}
              <span>{c.email}</span>
              {c.flag ? <span className="adm-chip__why">{FLAG_TEXT[c.flag]}</span> : null}
              <button type="button" className="adm-chip__x" onClick={() => remove(c.email)} aria-label={`Remove ${c.email}`} disabled={disabled}>
                <X size={14} strokeWidth={2} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <input
          ref={input}
          id={id}
          className="adm-chips__input"
          value={draft}
          disabled={disabled}
          autoComplete="off"
          placeholder={chips.length ? "" : "Type or paste addresses"}
          aria-describedby={`${id}-hint`}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          onBlur={() => {
            if (draft.trim()) {
              take(draft);
              setDraft("");
            }
          }}
        />
      </div>
      <span className="wo-hint" id={`${id}-hint`}>
        Press Enter, comma or space after each address, or paste a list. {chips.length} of {MAX_EMAILS}.
      </span>
      <span role="status" className="wo-hint">{note}</span>
    </div>
  );
}
