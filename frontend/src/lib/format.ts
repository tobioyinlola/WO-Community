const locale = "en-GB";

/** "10 Oct 2026". */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric" }).format(
    date,
  );
}

/** "15:00 WAT" in the viewer's own zone, 24 hour clock. */
export function formatTime(value: string | Date | null | undefined): string {
  if (!value) return "";
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return "";
  // The Nigerian English locale names West African time "WAT" rather than "GMT+1".
  const parts = new Intl.DateTimeFormat("en-NG", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZoneName: "short",
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("hour")}:${get("minute")} ${get("timeZoneName")}`.trim();
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "";
  return `${formatDate(value)}, ${formatTime(value)}`;
}

/** "3 minutes ago", falling back to the date after a week. */
export function timeAgo(value: string | Date | null | undefined, now = new Date()): string {
  if (!value) return "";
  const date = typeof value === "string" ? new Date(value) : value;
  const seconds = Math.round((now.getTime() - date.getTime()) / 1000);
  if (Number.isNaN(seconds)) return "";
  if (seconds < 45) return "just now";
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const steps: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
  ];
  if (seconds < 7 * 86400) {
    for (let i = steps.length - 1; i >= 0; i--) {
      const [unit, size] = steps[i] as [Intl.RelativeTimeFormatUnit, number];
      if (seconds >= size) return rtf.format(-Math.floor(seconds / size), unit);
    }
    return rtf.format(-Math.max(1, Math.round(seconds / 60)), "minute");
  }
  return formatDate(date);
}

const SYMBOLS: Record<string, string> = {
  NGN: "₦",
  KES: "KSh ",
  GHS: "GH₵",
  ZAR: "R",
  EGP: "E£",
  USD: "$",
};

/** Currency symbol before the amount, thousands separated: "₦5,000". Amounts are minor units. */
export function formatMoney(minor: number, currency: string): string {
  const major = minor / 100;
  const symbol = SYMBOLS[currency] ?? `${currency} `;
  const whole = Number.isInteger(major);
  return (
    symbol +
    new Intl.NumberFormat(locale, {
      minimumFractionDigits: whole ? 0 : 2,
      maximumFractionDigits: 2,
    }).format(major)
  );
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat(locale).format(value);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatNumber(count)} ${count === 1 ? one : many}`;
}

/** "fintech" or "series-a" to "Fintech" or "Series a" when the API gives no display name. */
export function humanise(slug: string): string {
  const text = slug.replace(/[-_]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A running time in words: "45 min", "1 h 20 min". Nothing for a missing or zero length. */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "";
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** A clock for a position in a video: 1:05 or 1:02:05. */
export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const two = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${two(m)}:${two(s)}` : `${m}:${two(s)}`;
}
