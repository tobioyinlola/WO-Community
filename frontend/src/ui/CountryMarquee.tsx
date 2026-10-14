import "flag-icons/css/flag-icons.min.css";

export interface MarqueeCountry {
  /** Two letter country code, such as NG. */
  code: string;
  founders: number;
}

const MAX = 10;
/** Enough entries in a row that it is wider than any screen, so the loop never shows a gap. */
const MIN_IN_ROW = 8;

function nameOf(code: string): string {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/**
 * A strip of countries, each with its flag, that drifts sideways. The row is repeated once so the
 * loop has no gap; everything but the first pass through the list is hidden from assistive
 * technology, which reads each country once. It stops under the pointer and when motion is
 * reduced, where it becomes a wrapped, still row of the countries once each.
 */
export function CountryMarquee({ countries }: { countries: MarqueeCountry[] }) {
  const items = countries
    .filter((c) => /^[A-Za-z]{2}$/.test(c.code))
    .slice(0, MAX)
    .map((c) => ({ code: c.code.toLowerCase(), name: nameOf(c.code.toUpperCase()) }));
  if (items.length === 0) return null;

  const passes = Math.ceil(MIN_IN_ROW / items.length);

  const row = (copy: boolean) => (
    <ul className="site-marquee__row" aria-hidden={copy || undefined} aria-label={copy ? undefined : "Countries our founders are in"}>
      {Array.from({ length: passes }, (_, pass) =>
        items.map((c) => (
          <li key={`${pass}-${c.code}`} className="site-marquee__item" data-repeat={pass > 0 || undefined} aria-hidden={pass > 0 || undefined}>
            <span className={`fi fi-${c.code} site-marquee__flag`} aria-hidden="true" />
            <span>{c.name}</span>
          </li>
        )),
      )}
    </ul>
  );

  return (
    <div className="site-marquee">
      <div className="site-marquee__track">
        {row(false)}
        {row(true)}
      </div>
    </div>
  );
}
