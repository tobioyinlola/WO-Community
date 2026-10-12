import { Star } from "lucide-react";
import { useState } from "react";
import "../styles/learn.css";

/** The average as five stars, partly filled, with the number said in words for a screen reader. */
export function Stars({ value, count, size = 16, showNumber = true }: { value: number | null; count?: number; size?: number; showNumber?: boolean }) {
  const shown = value ?? 0;
  const label =
    value === null || count === 0
      ? "Not rated yet"
      : `Rated ${shown.toFixed(1)} out of 5${count !== undefined ? `, from ${count} ${count === 1 ? "rating" : "ratings"}` : ""}`;
  return (
    <span className="wo-stars" role="img" aria-label={label}>
      <span className="wo-stars__row" aria-hidden="true">
        {[1, 2, 3, 4, 5].map((n) => {
          const fill = Math.max(0, Math.min(1, shown - (n - 1)));
          return (
            <span key={n} className="wo-stars__star" style={{ width: size, height: size }}>
              <Star size={size} strokeWidth={1.5} className="wo-stars__empty" />
              <span className="wo-stars__fill" style={{ width: `${fill * 100}%` }}>
                <Star size={size} strokeWidth={1.5} fill="currentColor" />
              </span>
            </span>
          );
        })}
      </span>
      {showNumber ? (
        <span className="wo-stars__text" aria-hidden="true">
          {value === null ? "New" : shown.toFixed(1)}
          {count !== undefined && value !== null ? ` (${count})` : ""}
        </span>
      ) : null}
    </span>
  );
}

/** Choose 1 to 5 stars. A radio group, so the arrow keys move between them. */
export function RatingInput({ value, onChange, label = "Your rating", disabled = false }: { value: number; onChange: (stars: number) => void; label?: string; disabled?: boolean }) {
  const [hover, setHover] = useState(0);
  const lit = hover || value;
  return (
    <div className="wo-rate" role="radiogroup" aria-label={label}>
      {[1, 2, 3, 4, 5].map((n) => (
        <label key={n} className="wo-rate__star" data-on={n <= lit} onMouseEnter={() => setHover(n)} onMouseLeave={() => setHover(0)}>
          <input type="radio" name="stars" className="wo-visually-hidden" value={n} checked={value === n} disabled={disabled} onChange={() => onChange(n)} aria-label={`${n} ${n === 1 ? "star" : "stars"}`} />
          <Star size={26} strokeWidth={1.5} fill={n <= lit ? "currentColor" : "none"} aria-hidden="true" />
        </label>
      ))}
    </div>
  );
}
