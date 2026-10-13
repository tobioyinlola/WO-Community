/** The weekly schedule as the editor holds it: for each weekday, whether it is on and its time ranges. */
export interface Range {
  start: string;
  end: string;
}

export interface Day {
  on: boolean;
  ranges: Range[];
}

export type Week = Day[]; // index 0 is Monday

export const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const PRESETS: Record<"mornings" | "afternoons" | "evenings", Range> = {
  mornings: { start: "08:00", end: "12:00" },
  afternoons: { start: "13:00", end: "17:00" },
  evenings: { start: "18:00", end: "21:00" },
};

export const emptyWeek = (): Week => DAY_NAMES.map(() => ({ on: false, ranges: [] }));

export const toMinutes = (clock: string): number => {
  const [h, m] = clock.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

export const fromMinutes = (total: number): string => `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;

/** The API's flat list of windows as a week. */
export function weekFrom(windows: Array<{ weekday: number; start: string; end: string }>): Week {
  const week = emptyWeek();
  for (const w of windows) {
    const day = week[w.weekday];
    if (day) {
      day.on = true;
      day.ranges.push({ start: w.start, end: w.end });
    }
  }
  for (const day of week) day.ranges.sort((a, b) => toMinutes(a.start) - toMinutes(b.start));
  return week;
}

/** A week as the flat list the API takes: only days that are on, only complete ranges. */
export function windowsFrom(week: Week): Array<{ weekday: number; start: string; end: string }> {
  return week.flatMap((day, weekday) => (day.on ? day.ranges.map((r) => ({ weekday, start: r.start, end: r.end })) : []));
}

/** What is wrong with one day, in words, or an empty string. Ranges must end after they start and not overlap. */
export function dayProblem(day: Day, minimum = 30): string {
  if (!day.on) return "";
  if (day.ranges.length === 0) return "Add a time range, or switch the day off.";
  const sorted = [...day.ranges].sort((a, b) => toMinutes(a.start) - toMinutes(b.start));
  for (const r of sorted) {
    if (!r.start || !r.end) return "Fill in both times.";
    if (toMinutes(r.end) <= toMinutes(r.start)) return "Each range must end after it starts.";
    if (toMinutes(r.end) - toMinutes(r.start) < minimum) return `Each range must be at least ${minimum} minutes.`;
  }
  for (let i = 1; i < sorted.length; i += 1) {
    if (toMinutes(sorted[i]!.start) < toMinutes(sorted[i - 1]!.end)) return "Ranges must not overlap.";
  }
  return "";
}

export const weekProblems = (week: Week, minimum = 30): string[] => week.map((d) => dayProblem(d, minimum));

export const hasRanges = (week: Week): boolean => week.some((d) => d.on && d.ranges.length > 0);

/** Copy one day's ranges onto other days, switching them on. */
export function copyDay(week: Week, from: number, to: number[]): Week {
  const source = week[from];
  if (!source) return week;
  return week.map((day, i) => (to.includes(i) && i !== from ? { on: source.on, ranges: source.ranges.map((r) => ({ ...r })) } : day));
}

export const WEEKDAYS = [0, 1, 2, 3, 4];
export const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];

/** Add a preset range to each day that is on (or to weekdays if nothing is on yet), skipping overlaps. */
export function applyPreset(week: Week, preset: Range): Week {
  const anyOn = week.some((d) => d.on);
  return week.map((day, i) => {
    if (anyOn ? !day.on : !WEEKDAYS.includes(i)) return day;
    const clash = day.ranges.some((r) => toMinutes(preset.start) < toMinutes(r.end) && toMinutes(r.start) < toMinutes(preset.end));
    return { on: true, ranges: clash ? day.ranges : [...day.ranges, { ...preset }].sort((a, b) => toMinutes(a.start) - toMinutes(b.start)) };
  });
}

const rangeText = (r: Range) => `${r.start} to ${r.end}`;

/** "Mon to Fri, 10:00 to 12:00 and 15:00 to 17:00 WAT; Sat, 09:00 to 11:00 WAT". */
export function summarise(week: Week, zoneLabel = ""): string {
  const groups = new Map<string, number[]>();
  week.forEach((day, i) => {
    if (!day.on || day.ranges.length === 0) return;
    const key = [...day.ranges].sort((a, b) => toMinutes(a.start) - toMinutes(b.start)).map(rangeText).join(" and ");
    groups.set(key, [...(groups.get(key) ?? []), i]);
  });
  if (groups.size === 0) return "No times set yet.";
  const suffix = zoneLabel ? ` ${zoneLabel}` : "";
  return [...groups.entries()]
    .sort((a, b) => Math.min(...a[1]) - Math.min(...b[1]))
    .map(([text, days]) => {
      const consecutive = days.every((d, k) => k === 0 || d === days[k - 1]! + 1);
      const label = consecutive && days.length > 2 ? `${DAY_SHORT[days[0]!]} to ${DAY_SHORT[days[days.length - 1]!]}` : days.map((d) => DAY_SHORT[d]).join(", ");
      return `${label}, ${text}${suffix}`;
    })
    .join("; ");
}

/** The short zone name (WAT, GMT+1) for a zone, as people write it. */
export function zoneLabel(zone: string, at = new Date()): string {
  try {
    return new Intl.DateTimeFormat("en-GB", { timeZone: zone, timeZoneName: "short" }).formatToParts(at).find((p) => p.type === "timeZoneName")?.value ?? zone;
  } catch {
    return zone;
  }
}

/** Money typed as 20000 (or 20,000.50) in whole units to the smallest unit, or null if it is not a price. */
export function toMinor(text: string): number | null {
  const value = Number(text.replace(/,/g, "").trim());
  if (!Number.isFinite(value) || value <= 0) return null;
  return Math.round(value * 100);
}

export const fromMinor = (minor: number | null | undefined): string => (minor ? String(minor / 100) : "");
