import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Select } from "../components";
import { formatMoney } from "../lib/format";
import { EmptyState, ErrorState, SkeletonRows } from "../ui/blocks";
import "../styles/mentor.css";

export type Slots = components["schemas"]["Slots"];
export type PickedSlot = { starts_at: string; local_date: string; local_time: string; length: number; timezone: string; price: Slots["price"] };

export const browserZone = (): string => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
};

/** Zones to choose from: the viewer's own and the mentor's first, then every zone the browser knows. */
export function zoneOptions(...first: string[]): Array<{ value: string; label: string }> {
  const all = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  const seen = new Set<string>();
  return [...first, ...all].filter((z) => z && !seen.has(z) && seen.add(z)).map((z) => ({ value: z, label: z.replace(/_/g, " ") }));
}

/** "Mon 12 Oct" for a calendar date that has no time or zone of its own. */
export function dayLabel(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(date);
}

export function priceText(price: Slots["price"]): string {
  return price ? `${formatMoney(price.price_minor, price.currency)} per session` : "Free";
}

/**
 * The booking calendar a mentee sees: pick a session length, then a day, then a time, all in the viewer's
 * own time zone. The mentor's "Preview as mentee" shows this same component for themselves.
 */
export function BookingCalendar({ mentorId, onPick, initialZone }: { mentorId: string | "me"; onPick?: (slot: PickedSlot) => void; initialZone?: string }) {
  const [length, setLength] = useState<number | undefined>(undefined);
  const [zone, setZone] = useState(initialZone ?? browserZone());
  const [day, setDay] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["slots", mentorId, length ?? "default", zone],
    queryFn: () => {
      const q = { ...(length ? { length } : {}), tz: zone };
      return mentorId === "me"
        ? unwrap(api.GET("/api/v1/me/mentor/preview", { params: { query: q } }))
        : unwrap(api.GET("/api/v1/mentors/{user_id}/slots", { params: { path: { user_id: mentorId }, query: q } }));
    },
    retry: false,
  });
  const data = query.data;
  const days = useMemo(() => {
    const groups = new Map<string, Slots["slots"]>();
    for (const s of data?.slots ?? []) groups.set(s.local_date, [...(groups.get(s.local_date) ?? []), s]);
    return [...groups.entries()];
  }, [data]);
  const shown = days.find(([d]) => d === day) ?? days[0];

  if (query.isPending) return <SkeletonRows />;
  if (query.isError || !data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const zones = zoneOptions(zone, browserZone(), data.mentor_timezone);

  return (
    <div className="wo-booking">
      <div className="wo-booking__top">
        <div role="group" aria-label="Session length" className="wo-booking__lengths">
          {data.lengths.map((n) => (
            <button key={n} type="button" className="wo-chip" aria-pressed={n === data.length_minutes} onClick={() => { setLength(n); setDay(null); }}>
              {n} min
            </button>
          ))}
        </div>
        <p className="wo-booking__price">{priceText(data.price)}</p>
      </div>
      {data.price?.payment === "arranged" ? <p className="caption app-muted wo-booking__note">Payment arranged directly with the mentor. Nothing is charged here.</p> : null}
      <Select label="Time zone" options={zones} value={zone} onChange={(e) => { setZone(e.target.value); setDay(null); }} />
      {!data.accepting_new ? (
        <p className="body-sm app-muted" role="status">
          This mentor is not taking new mentees right now.
        </p>
      ) : days.length === 0 ? (
        <EmptyState title="No times in the next weeks">Try another session length, or check back soon.</EmptyState>
      ) : (
        <>
          <div role="group" aria-label="Days with times" className="wo-booking__days">
            {days.map(([d, slots]) => (
              <button key={d} type="button" className="wo-day" aria-pressed={shown?.[0] === d} onClick={() => setDay(d)}>
                <span>{dayLabel(d)}</span>
                <span className="caption">{slots.length} {slots.length === 1 ? "time" : "times"}</span>
              </button>
            ))}
          </div>
          <div role="group" aria-label={`Times on ${shown ? dayLabel(shown[0]) : ""}`} className="wo-booking__slots">
            {(shown?.[1] ?? []).map((s) => (
              <button
                key={s.starts_at}
                type="button"
                className="wo-btn wo-btn--secondary wo-btn--sm"
                disabled={!onPick}
                onClick={() => onPick?.({ starts_at: s.starts_at, local_date: s.local_date, local_time: s.local_time, length: data.length_minutes, timezone: data.timezone, price: data.price })}
              >
                {s.local_time}
              </button>
            ))}
          </div>
          <p className="caption app-muted" style={{ margin: 0 }}>
            Times are shown in {zone.replace(/_/g, " ")}. {data.sessions_left_this_week} {data.sessions_left_this_week === 1 ? "place" : "places"} left this week.
          </p>
        </>
      )}
    </div>
  );
}
