import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";

/** The change from one period to the next as a ratio (0.12 is up 12%), or null when there is nothing to compare. */
export function changeBetween(now: number, before: number): number | null {
  if (before === 0) return now === 0 ? 0 : null;
  return (now - before) / before;
}

/**
 * A change chip. It always carries an arrow and a sign, never colour alone. `inverse` is for figures
 * where lower is better (waiting times), so a fall shows as good news.
 */
export function Delta({ change, versus, inverse = false }: { change: number | null; versus: string; inverse?: boolean }) {
  if (change === null) {
    return (
      <span className="adm-delta" data-tone="flat">
        <span>New</span>
        <span className="wo-visually-hidden">, nothing to compare with {versus}</span>
      </span>
    );
  }
  const pct = Math.round(Math.abs(change) * 100);
  const direction = pct === 0 ? "flat" : change > 0 ? "up" : "down";
  const good = direction === "flat" ? "flat" : (direction === "up") !== inverse ? "good" : "bad";
  const Icon = direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : ArrowRight;
  return (
    <span className="adm-delta" data-tone={good}>
      <Icon size={14} strokeWidth={2} aria-hidden="true" />
      <span>{direction === "flat" ? "0%" : `${direction === "up" ? "+" : "−"}${pct}%`}</span>
      <span className="wo-visually-hidden">{direction === "flat" ? `, no change ${versus}` : `, ${direction} ${pct} percent ${versus}`}</span>
    </span>
  );
}
