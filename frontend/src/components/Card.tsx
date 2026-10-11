import type { AnchorHTMLAttributes, HTMLAttributes } from "react";
import { cx } from "../lib/cx";

export type CardVariant = "default" | "brand" | "accent" | "white" | "outline";

const VARIANT_CLASS: Record<CardVariant, string | null> = {
  default: null,
  brand: "wo-card--brand",
  accent: "wo-card--accent",
  white: "wo-card--white",
  outline: "wo-card--outline",
};

interface CardBase {
  variant?: CardVariant;
}

export type CardProps = CardBase & HTMLAttributes<HTMLDivElement>;

/** A unit of content: cream surface, 20px radius, hairline. Do not nest cards in cards. */
export function Card({ variant = "default", className, ...rest }: CardProps) {
  return <div {...rest} className={cx("wo-card", VARIANT_CLASS[variant], className)} />;
}

export type CardLinkProps = CardBase & AnchorHTMLAttributes<HTMLAnchorElement>;

/** A card that is one link. It lifts 2px on hover. */
export function CardLink({ variant = "default", className, ...rest }: CardLinkProps) {
  return (
    // The caller supplies the text content, so the link has an accessible name.
    // eslint-disable-next-line jsx-a11y/anchor-has-content
    <a {...rest} className={cx("wo-card", VARIANT_CLASS[variant], className)} />
  );
}

export function CardTitle({ className, ...rest }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 {...rest} className={cx("wo-card__title", className)} />;
}

export function CardText({ className, ...rest }: HTMLAttributes<HTMLParagraphElement>) {
  return <p {...rest} className={cx("wo-card__text", className)} />;
}
