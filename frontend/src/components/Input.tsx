import { Eye, EyeOff } from "lucide-react";
import {
  useId,
  useState,
  type InputHTMLAttributes,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { cx } from "../lib/cx";

interface FieldChrome {
  /** Always visible; never replaced by the placeholder. */
  label: string;
  hint?: string;
  /** When set, the field is invalid and the message is announced with it. */
  error?: string;
}

/** Wires the label, hint and error to a control, and builds the aria attributes for it. */
function useFieldIds(hint?: string, error?: string) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return { id, hintId, errorId, describedBy };
}

function FieldFooter({
  hint,
  hintId,
  error,
  errorId,
}: {
  hint?: string;
  hintId?: string;
  error?: string;
  errorId?: string;
}) {
  return (
    <>
      {error ? (
        <span className="wo-error" id={errorId}>
          <span aria-hidden="true">!</span>
          {error}
        </span>
      ) : null}
      {hint ? (
        <span className="wo-hint" id={hintId}>
          {hint}
        </span>
      ) : null}
    </>
  );
}

export interface InputProps
  extends FieldChrome,
    Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {}

export function Input({ label, hint, error, className, type, ...rest }: InputProps) {
  const { id, hintId, errorId, describedBy } = useFieldIds(hint, error);
  const [revealed, setRevealed] = useState(false);
  const isPassword = type === "password";
  const control = (
    <input
      {...rest}
      id={id}
      type={isPassword && revealed ? "text" : type}
      className={cx("wo-input", isPassword && "wo-input--has-toggle", className)}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy}
    />
  );
  return (
    <div className="wo-field">
      <label className="wo-label" htmlFor={id}>
        {label}
      </label>
      {isPassword ? (
        <span className="wo-input-wrap">
          {control}
          <button
            type="button"
            className="wo-input-toggle"
            aria-label={revealed ? "Hide what you typed" : "Show what you typed"}
            aria-pressed={revealed}
            onClick={() => setRevealed((v) => !v)}
          >
            {revealed ? <EyeOff size={20} strokeWidth={1.5} /> : <Eye size={20} strokeWidth={1.5} />}
          </button>
        </span>
      ) : (
        control
      )}
      <FieldFooter hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
}

export interface TextareaProps
  extends FieldChrome,
    Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id"> {}

export function Textarea({ label, hint, error, className, ...rest }: TextareaProps) {
  const { id, hintId, errorId, describedBy } = useFieldIds(hint, error);
  return (
    <div className="wo-field">
      <label className="wo-label" htmlFor={id}>
        {label}
      </label>
      <textarea
        {...rest}
        id={id}
        className={cx("wo-textarea", className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
      />
      <FieldFooter hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps
  extends FieldChrome,
    Omit<SelectHTMLAttributes<HTMLSelectElement>, "id" | "children"> {
  options: SelectOption[];
}

/** A native select with a drawn chevron, so keyboards and phone pickers work as expected. */
export function Select({ label, hint, error, options, className, ...rest }: SelectProps) {
  const { id, hintId, errorId, describedBy } = useFieldIds(hint, error);
  return (
    <div className="wo-field">
      <label className="wo-label" htmlFor={id}>
        {label}
      </label>
      <span className="wo-select">
        <select
          {...rest}
          id={id}
          className={className}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </span>
      <FieldFooter hint={hint} hintId={hintId} error={error} errorId={errorId} />
    </div>
  );
}
