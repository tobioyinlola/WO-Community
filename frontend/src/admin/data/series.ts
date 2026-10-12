import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";

/** A date as the `YYYY-MM-DD` text the API takes, on the viewer's calendar. */
export function iso(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export interface MonthWindows {
  today: Date;
  thisStart: Date;
  lastStart: Date;
  lastEnd: Date;
  /** Days in the current month, so a chart can show the days still to come. */
  daysThisMonth: number;
  daysLastMonth: number;
}

export function monthWindows(today = new Date()): MonthWindows {
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const thisStart = new Date(day.getFullYear(), day.getMonth(), 1);
  const lastStart = new Date(day.getFullYear(), day.getMonth() - 1, 1);
  const lastEnd = new Date(day.getFullYear(), day.getMonth(), 0);
  return {
    today: day,
    thisStart,
    lastStart,
    lastEnd,
    daysThisMonth: new Date(day.getFullYear(), day.getMonth() + 1, 0).getDate(),
    daysLastMonth: lastEnd.getDate(),
  };
}

export interface DailySeries {
  /** Value for each `YYYY-MM-DD`; a day the API left out counts as zero. */
  byDay: Map<string, number>;
  description: string;
}

/** One metric, one value per day, from the start of last month to today. */
export function useDailySeries(metric: string, windows: MonthWindows) {
  return useQuery({
    queryKey: ["admin", "series", metric, iso(windows.lastStart), iso(windows.today)],
    queryFn: async (): Promise<DailySeries> => {
      const s = await unwrap(
        api.GET("/api/v1/admin/dashboard/series", {
          params: { query: { metric, date_from: iso(windows.lastStart), date_to: iso(windows.today) } },
        }),
      );
      return { byDay: new Map(s.points.map((p) => [p.date, p.value ?? 0])), description: s.description };
    },
    staleTime: 60_000,
  });
}

/** Today, yesterday and the two months, summed, from a daily series. */
export function summarise(series: DailySeries | undefined, w: MonthWindows) {
  const at = (date: Date) => series?.byDay.get(iso(date)) ?? 0;
  const sum = (from: Date, to: Date) => {
    let total = 0;
    for (const d = new Date(from); d <= to; d.setDate(d.getDate() + 1)) total += at(d);
    return total;
  };
  const yesterday = new Date(w.today);
  yesterday.setDate(yesterday.getDate() - 1);
  return {
    today: at(w.today),
    yesterday: at(yesterday),
    thisMonth: sum(w.thisStart, w.today),
    lastMonth: sum(w.lastStart, w.lastEnd),
  };
}
