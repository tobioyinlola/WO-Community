/**
 * Event times are typed as the clock shows in the event's own place, then stored as a moment in
 * time. These two functions convert between the `datetime-local` text and an ISO moment for a named
 * time zone, without a date library.
 */

export const ZONES: Array<{ value: string; label: string }> = [
  { value: "Africa/Lagos", label: "Lagos, WAT" },
  { value: "Africa/Accra", label: "Accra, GMT" },
  { value: "Africa/Nairobi", label: "Nairobi, EAT" },
  { value: "Africa/Johannesburg", label: "Johannesburg, SAST" },
  { value: "Africa/Cairo", label: "Cairo, EET" },
  { value: "UTC", label: "UTC" },
];

function parts(at: Date, zone: string): Record<string, string> {
  const formatted = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).formatToParts(at);
  return Object.fromEntries(formatted.map((p) => [p.type, p.value]));
}

/** An ISO moment as `YYYY-MM-DDTHH:mm` on the clock of `zone`, for a `datetime-local` field. */
export function toLocalInput(iso: string, zone: string): string {
  if (!iso) return "";
  const p = parts(new Date(iso), zone);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

/** What a `datetime-local` value means in `zone`, as an ISO moment in UTC. */
export function fromLocalInput(value: string, zone: string): string {
  const [date = "", time = ""] = value.split("T");
  const [y = 0, mo = 1, d = 1] = date.split("-").map(Number);
  const [h = 0, mi = 0] = time.split(":").map(Number);
  const wanted = Date.UTC(y, mo - 1, d, h, mi);
  // Start from the wall clock read as UTC, then correct by how far the zone's clock differs.
  let guess = wanted;
  for (let i = 0; i < 2; i += 1) {
    const p = parts(new Date(guess), zone);
    const shown = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour), Number(p.minute));
    guess += wanted - shown;
  }
  return new Date(guess).toISOString();
}
