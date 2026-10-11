import type { InputHTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/cx";

interface ChoiceProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  /** Text shown next to the control. The whole row is the tap target. */
  label: ReactNode;
}

/** Picks any number of options. */
export function Checkbox({ label, className, ...rest }: ChoiceProps) {
  return (
    <label className={cx("wo-check", className)}>
      <input {...rest} type="checkbox" />
      {label}
    </label>
  );
}

/** Picks one option of a group; give every radio of a group the same `name`. */
export function Radio({ label, className, ...rest }: ChoiceProps) {
  return (
    <label className={cx("wo-check", className)}>
      <input {...rest} type="radio" />
      {label}
    </label>
  );
}

/** A switch applies immediately, so use it only where there is no Save button. */
export function Switch({ label, className, ...rest }: ChoiceProps) {
  return (
    <label className={cx("wo-check", className)}>
      <input {...rest} type="checkbox" role="switch" className="wo-switch" />
      {label}
    </label>
  );
}

/** A labelled group of related choices. */
export function ChoiceGroup({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset style={{ border: 0, margin: 0, padding: 0 }}>
      <legend className="wo-label" style={{ marginBottom: "var(--space-2)", padding: 0 }}>
        {legend}
      </legend>
      <div className="wo-stack" style={{ gap: "var(--space-2)" }}>
        {children}
      </div>
    </fieldset>
  );
}
