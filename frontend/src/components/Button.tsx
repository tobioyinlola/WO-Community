import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cx } from "../lib/cx";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "accent"
  | "danger"
  | "white"
  | "onBrand";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: "wo-btn--primary",
  secondary: "wo-btn--secondary",
  ghost: "wo-btn--ghost",
  accent: "wo-btn--accent",
  danger: "wo-btn--danger",
  white: "wo-btn--white",
  onBrand: "wo-btn--on-brand",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Keeps the width, shows a spinner and marks the button busy. */
  loading?: boolean;
  /** An icon before the label. Icon-only buttons must pass `aria-label`. */
  icon?: ReactNode;
}

/**
 * The capsule button. Use `primary` once per view; `accent` and `white` belong on forest bands
 * (`bg-brand`, `bg-inverse`) only.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, icon, className, children, disabled, type = "button", ...rest },
  ref,
) {
  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      disabled={disabled}
      aria-busy={loading || undefined}
      className={cx(
        "wo-btn",
        VARIANT_CLASS[variant],
        size === "sm" && "wo-btn--sm",
        size === "lg" && "wo-btn--lg",
        loading && "wo-btn--loading",
        className,
      )}
    >
      {icon}
      {children}
    </button>
  );
});
