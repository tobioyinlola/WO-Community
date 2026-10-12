import type { ReactNode } from "react";
import { cx } from "../lib/cx";

export type AlertTone = "info" | "success" | "warning" | "danger";

const GLYPH: Record<AlertTone, string> = {
  info: "i",
  success: "✓",
  warning: "!",
  danger: "×",
};

export interface AlertProps {
  tone?: AlertTone;
  title: string;
  children?: ReactNode;
  /** A link or button that says what to do next. */
  action?: ReactNode;
  className?: string;
}

/**
 * An inline message. Status is carried by the glyph and the title as well as the colour.
 * Errors use `role="alert"`; the others use `role="status"`.
 */
export function Alert({ tone = "info", title, children, action, className }: AlertProps) {
  return (
    <div
      className={cx("wo-alert", `wo-alert--${tone}`, className)}
      role={tone === "danger" ? "alert" : "status"}
    >
      <span className="wo-alert__icon" aria-hidden="true">
        {GLYPH[tone]}
      </span>
      <div>
        <p className="wo-alert__title">{title}</p>
        {children ? <div className="wo-alert__text">{children}</div> : null}
        {action ? <div style={{ marginTop: "var(--space-2)" }}>{action}</div> : null}
      </div>
    </div>
  );
}
