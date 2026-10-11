import { cx } from "../lib/cx";

export interface StatTileProps {
  /** Already formatted, with units: "4,200+". */
  value: string;
  /** Two or three words; shown in capitals. */
  label: string;
  /** A change, in words: "+12% this month". Never colour alone. */
  delta?: string;
  /** One branded tile per row. */
  variant?: "default" | "brand";
  className?: string;
}

/** One number with its label. Tabular figures, tight tracking. */
export function StatTile({ value, label, delta, variant = "default", className }: StatTileProps) {
  return (
    <div className={cx("wo-stat", variant === "brand" && "wo-stat--brand", className)}>
      <span className="wo-stat__label">{label}</span>
      <span className="wo-stat__value">{value}</span>
      {delta ? <span className="wo-stat__delta">{delta}</span> : null}
    </div>
  );
}
