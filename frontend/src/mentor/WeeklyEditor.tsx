import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button, Select, Switch } from "../components";
import {
  ALL_DAYS,
  DAY_NAMES,
  DAY_SHORT,
  PRESETS,
  WEEKDAYS,
  applyPreset,
  copyDay,
  dayProblem,
  summarise,
  toMinutes,
  zoneLabel,
  type Day,
  type Week,
} from "./model";
import { browserZone, zoneOptions } from "./BookingCalendar";
import "../styles/mentor.css";

/** Every quarter hour in 24 hour form, so times read the same on every device. */
export const QUARTERS: string[] = Array.from({ length: 96 }, (_, i) => `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`);

export function TimeSelect({ id, value, onChange, invalid = false }: { id: string; value: string; onChange: (value: string) => void; invalid?: boolean }) {
  return (
    <select id={id} className="wo-input wo-timeselect" value={value} aria-invalid={invalid} onChange={(e) => onChange(e.target.value)}>
      {QUARTERS.includes(value) ? null : <option value={value}>{value}</option>}
      {QUARTERS.map((q) => (
        <option key={q} value={q}>
          {q}
        </option>
      ))}
    </select>
  );
}

const GRID_FROM = 6; // hours shown in the live preview
const GRID_TO = 23;

/** The weekly grid: each day's blocks drawn where they fall, so a mistake is visible at a glance. */
export function WeekGrid({ week }: { week: Week }) {
  const total = (GRID_TO - GRID_FROM) * 60;
  return (
    <div className="wo-grid" role="img" aria-label={`Weekly schedule. ${summarise(week)}`}>
      <div className="wo-grid__hours" aria-hidden="true">
        {Array.from({ length: GRID_TO - GRID_FROM + 1 }, (_, i) => GRID_FROM + i)
          .filter((h) => h % 3 === 0)
          .map((h) => (
            <span key={h} style={{ top: `${((h - GRID_FROM) * 60 * 100) / total}%` }}>
              {String(h).padStart(2, "0")}:00
            </span>
          ))}
      </div>
      {week.map((day, i) => (
        <div key={DAY_NAMES[i]} className="wo-grid__col" aria-hidden="true">
          <span className="wo-grid__head">{DAY_SHORT[i]}</span>
          <div className="wo-grid__track">
            {day.on
              ? day.ranges.map((r, k) => {
                  const start = Math.max(toMinutes(r.start), GRID_FROM * 60);
                  const end = Math.min(toMinutes(r.end), GRID_TO * 60);
                  if (end <= start || !r.start || !r.end) return null;
                  return <span key={k} className="wo-grid__block" style={{ top: `${((start - GRID_FROM * 60) * 100) / total}%`, height: `${((end - start) * 100) / total}%` }} />;
                })
              : null}
          </div>
        </div>
      ))}
    </div>
  );
}

interface Props {
  week: Week;
  onChange: (week: Week) => void;
  zone: string;
  onZone: (zone: string) => void;
  /** The shortest session offered; a range must hold at least one. */
  minimum: number;
}

/**
 * A row per day with a switch and one or more time ranges, quick ways to fill the week (copy a day, presets),
 * the time zone, a live grid and a plain sentence that says what has been set.
 */
export function WeeklyEditor({ week, onChange, zone, onZone, minimum }: Props) {
  const [source, setSource] = useState("0");
  const set = (i: number, next: Day) => onChange(week.map((d, k) => (k === i ? next : d)));
  const browser = browserZone();
  const label = zoneLabel(zone);
  return (
    <div className="app-stack">
      <div className="wo-week__tools">
        <div className="wo-week__copy">
          <Select label="Copy from" options={DAY_NAMES.map((n, i) => ({ value: String(i), label: n }))} value={source} onChange={(e) => setSource(e.target.value)} />
          <Button variant="secondary" size="sm" onClick={() => onChange(copyDay(week, Number(source), WEEKDAYS))}>
            Copy to weekdays
          </Button>
          <Button variant="secondary" size="sm" onClick={() => onChange(copyDay(week, Number(source), ALL_DAYS))}>
            Copy to all days
          </Button>
        </div>
        <div className="app-cluster" role="group" aria-label="Quick fill">
          {(Object.keys(PRESETS) as Array<keyof typeof PRESETS>).map((key) => (
            <Button key={key} variant="ghost" size="sm" onClick={() => onChange(applyPreset(week, PRESETS[key]))}>
              {key[0]!.toUpperCase() + key.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      <ul className="wo-week" aria-label="Weekly schedule">
        {week.map((day, i) => {
          const problem = dayProblem(day, minimum);
          return (
            <li key={DAY_NAMES[i]} className="wo-week__day" data-on={day.on}>
              <div className="wo-week__name">
                <Switch
                  label={<span>{DAY_NAMES[i]}</span>}
                  checked={day.on}
                  onChange={(e) => set(i, { on: e.target.checked, ranges: e.target.checked && day.ranges.length === 0 ? [{ start: "09:00", end: "12:00" }] : day.ranges })}
                />
              </div>
              <div className="wo-week__ranges">
                {day.on ? (
                  <>
                    {day.ranges.map((r, k) => (
                      <div key={k} className="wo-week__range">
                        <label className="wo-visually-hidden" htmlFor={`s-${i}-${k}`}>{`${DAY_NAMES[i]} range ${k + 1} starts`}</label>
                        <TimeSelect id={`s-${i}-${k}`} value={r.start} invalid={Boolean(problem)} onChange={(v) => set(i, { ...day, ranges: day.ranges.map((x, j) => (j === k ? { ...x, start: v } : x)) })} />
                        <span aria-hidden="true">to</span>
                        <label className="wo-visually-hidden" htmlFor={`e-${i}-${k}`}>{`${DAY_NAMES[i]} range ${k + 1} ends`}</label>
                        <TimeSelect id={`e-${i}-${k}`} value={r.end} invalid={Boolean(problem)} onChange={(v) => set(i, { ...day, ranges: day.ranges.map((x, j) => (j === k ? { ...x, end: v } : x)) })} />
                        <button type="button" className="wo-iconbtn" aria-label={`Remove ${DAY_NAMES[i]} range ${k + 1}`} onClick={() => set(i, { ...day, ranges: day.ranges.filter((_, j) => j !== k) })}>
                          <Trash2 size={16} strokeWidth={1.5} aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                    <button type="button" className="wo-linkbtn" onClick={() => set(i, { ...day, ranges: [...day.ranges, { start: day.ranges.at(-1)?.end ?? "13:00", end: "17:00" }] })} aria-label={`Add a range on ${DAY_NAMES[i]}`}>
                      <Plus size={14} strokeWidth={1.5} aria-hidden="true" /> Add range
                    </button>
                    {problem ? (
                      <p className="wo-error" role="alert" style={{ margin: 0 }}>
                        {DAY_NAMES[i]}: {problem}
                      </p>
                    ) : null}
                  </>
                ) : (
                  <span className="body-sm app-muted">Not available</span>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className="wo-week__zone">
        <Select label="Time zone" options={zoneOptions(zone, browser)} value={zone} onChange={(e) => onZone(e.target.value)} hint="Your times are read in this zone, and clock changes are followed for you." />
        {zone !== browser ? (
          <Button variant="ghost" size="sm" onClick={() => onZone(browser)}>
            Use my browser's zone ({browser.replace(/_/g, " ")})
          </Button>
        ) : null}
      </div>

      <WeekGrid week={week} />
      <p className="body-sm" role="status" style={{ margin: 0 }}>
        <strong>In summary:</strong> {summarise(week, label)}
      </p>
    </div>
  );
}
