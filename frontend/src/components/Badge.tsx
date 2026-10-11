import type { HTMLAttributes } from "react";
import { cx } from "../lib/cx";

export type BadgeVariant =
  | "neutral"
  | "founder"
  | "operator"
  | "investor"
  | "mentor"
  | "pro"
  | "solid"
  | "success"
  | "warning"
  | "danger"
  | "info";

const VARIANT_CLASS: Record<BadgeVariant, string | null> = {
  neutral: null,
  founder: "wo-badge--founder",
  operator: "wo-badge--operator",
  investor: "wo-badge--investor",
  mentor: "wo-badge--mentor",
  pro: "wo-badge--pro",
  solid: "wo-badge--solid",
  success: "wo-badge--success",
  warning: "wo-badge--warning",
  danger: "wo-badge--danger",
  info: "wo-badge--info",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  /** A dot before the text, for statuses that should be seen at a glance. */
  dot?: boolean;
}

/** Labels what something is. Short text, one or two words; the CSS makes it uppercase. */
export function Badge({ variant = "neutral", dot = false, className, children, ...rest }: BadgeProps) {
  return (
    <span {...rest} className={cx("wo-badge", VARIANT_CLASS[variant], className)}>
      {dot ? <i className="wo-dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
