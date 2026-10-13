import { useId, useState, type KeyboardEvent } from "react";
import { TableScroll } from "../../ui/blocks";
import { changeBetween, Delta } from "./Delta";

export interface DayPoint {
  /** The day, as a short label such as "5 Oct". */
  label: string;
  /** This period's value, or null for a day that has not happened yet. */
  current: number | null;
  /** The same day in the period before, or null when that period was shorter. */
  previous: number | null;
}

/** The top of the scale: four whole-number steps of a round size, the smallest that covers the largest value. */
export function niceMax(value: number): number {
  for (let magnitude = 1; magnitude <= 1e9; magnitude *= 10) {
    for (const multiple of [1, 2, 2.5, 3, 4, 5]) {
      const step = multiple * magnitude;
      if (Number.isInteger(step) && step * 4 >= value) return step * 4;
    }
  }
  return Math.ceil(value);
}

interface BarChartProps {
  title: string;
  points: DayPoint[];
  currentLabel: string;
  previousLabel: string;
  format?: (value: number) => string;
}

/**
 * Daily bars for this period with a marker for the same day last period. Days still to come are
 * hatched. It is one focus stop: the arrow keys move between days, and the same numbers are
 * offered as a table.
 */
export function BarChart({ title, points, currentLabel, previousLabel, format = (v) => String(v) }: BarChartProps) {
  const id = useId();
  const [hover, setHover] = useState<number | null>(null);
  const [focused, setFocused] = useState<number | null>(null);
  const active = hover ?? focused;
  const max = niceMax(Math.max(1, ...points.flatMap((p) => [p.current ?? 0, p.previous ?? 0])));
  const ticks = [4, 3, 2, 1, 0].map((n) => (max / 4) * n);
  const lastReal = points.reduce((last, p, i) => (p.current !== null ? i : last), 0);
  const pct = (v: number) => `${Math.min(100, (v / max) * 100)}%`;

  const onKey = (event: KeyboardEvent) => {
    const at = focused ?? lastReal;
    const next = event.key === "ArrowRight" ? Math.min(points.length - 1, at + 1) : event.key === "ArrowLeft" ? Math.max(0, at - 1) : event.key === "Home" ? 0 : event.key === "End" ? points.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    setFocused(next);
  };

  const point = active !== null ? points[active] : undefined;
  const labelFor = (p: DayPoint) =>
    p.current === null
      ? `${p.label}: not yet. ${previousLabel}: ${p.previous === null ? "no day" : format(p.previous)}.`
      : `${p.label}: ${format(p.current)} ${currentLabel.toLowerCase()}, ${p.previous === null ? "no day" : format(p.previous)} ${previousLabel.toLowerCase()}.`;

  return (
    <div className="adm-chart">
      <div className="adm-chart__plot">
        <div className="adm-chart__grid" aria-hidden="true">
          {ticks.map((t) => (
            <div key={t} className="adm-chart__tick" style={{ bottom: pct(t) }}>
              <span>{format(Math.round(t))}</span>
            </div>
          ))}
        </div>
        <div
          className="adm-chart__cols"
          role="listbox"
          aria-label={`${title}, one column for each day. Use the left and right arrow keys.`}
          aria-orientation="horizontal"
          aria-activedescendant={focused !== null ? `${id}-${focused}` : undefined}
          tabIndex={0}
          style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}
          onKeyDown={onKey}
          onFocus={() => setFocused((f) => f ?? lastReal)}
          onBlur={() => setFocused(null)}
          onPointerLeave={() => setHover(null)}
        >
          {points.map((p, i) => (
            <div
              key={p.label}
              id={`${id}-${i}`}
              role="option"
              aria-selected={active === i}
              aria-label={labelFor(p)}
              className="adm-chart__col"
              data-future={p.current === null}
              data-active={active === i}
              onPointerEnter={() => setHover(i)}
            >
              {p.current !== null ? <div className="adm-chart__bar" style={{ height: p.current > 0 ? `max(${pct(p.current)}, 3px)` : "0" }} /> : null}
              {p.previous !== null ? <div className="adm-chart__marker" style={{ bottom: pct(p.previous) }} /> : null}
            </div>
          ))}
        </div>
        {point && active !== null ? (
          <div className="adm-chart__tip" aria-hidden="true" style={{ left: `${((active + 0.5) / points.length) * 100}%` }} data-edge={active < 3 ? "start" : active > points.length - 4 ? "end" : "mid"}>
            <p className="adm-chart__tip-date">{point.label}</p>
            <p className="adm-chart__tip-row"><i className="adm-dotkey" data-series="current" />{currentLabel}<strong>{point.current === null ? "Not yet" : format(point.current)}</strong></p>
            <p className="adm-chart__tip-row"><i className="adm-dotkey" data-series="previous" />{previousLabel}<strong>{point.previous === null ? "No day" : format(point.previous)}</strong></p>
            {point.current !== null && point.previous !== null ? (
              <Delta change={changeBetween(point.current, point.previous)} versus={`on ${previousLabel.toLowerCase()}`} />
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="adm-chart__axis" aria-hidden="true" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
        {points.map((p, i) => (
          <span key={p.label} data-show={i === 0 || (i + 1) % 5 === 0}>{p.label.split(" ")[0]}</span>
        ))}
      </div>
      <details className="adm-chart__table">
        <summary>View {title.toLowerCase()} as a table</summary>
        <TableScroll label={`${title} by day`}>
          <table className="app-table">
            <caption className="wo-visually-hidden">{title} by day</caption>
            <thead>
              <tr>
                <th scope="col">Day</th>
                <th scope="col">{currentLabel}</th>
                <th scope="col">{previousLabel}</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.label}>
                  <th scope="row">{p.label}</th>
                  <td>{p.current === null ? "Not yet" : format(p.current)}</td>
                  <td>{p.previous === null ? "No day" : format(p.previous)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      </details>
    </div>
  );
}
