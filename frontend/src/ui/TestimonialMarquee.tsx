import { Avatar } from "../components";

export interface MarqueeTestimonial {
  id: string;
  quote: string;
  name: string;
  role: string;
}

/** Enough cards in one pass that the row is wider than the screen before it repeats. */
const MIN_IN_ROW = 6;

/**
 * Members' words gliding past. It pauses while pointed at or focused, and without motion it is a
 * still, wrapped set of the quotes, each once. Copies made to fill the loop are hidden from
 * assistive technology, so each quote is read once.
 */
export function TestimonialMarquee({ items }: { items: MarqueeTestimonial[] }) {
  if (items.length === 0) return null;
  const passes = Math.ceil(MIN_IN_ROW / items.length);
  const seconds = Math.max(40, items.length * passes * 9);

  const row = (copy: boolean) => (
    <ul className="site-voices__row" aria-hidden={copy || undefined} data-copy={copy || undefined}>
      {Array.from({ length: passes }, (_, pass) =>
        items.map((t) => (
          <li key={`${pass}-${t.id}`} className="site-voices__item" data-repeat={pass > 0 || undefined} aria-hidden={pass > 0 || undefined}>
            <figure className="site-voice">
              <blockquote>
                <p>&ldquo;{t.quote}&rdquo;</p>
              </blockquote>
              <figcaption>
                <Avatar name={t.name} id={t.id} size="md" />
                <span className="site-voice__who">
                  <strong>{t.name}</strong>
                  {t.role ? <span className="site-voice__role">{t.role}</span> : null}
                </span>
              </figcaption>
            </figure>
          </li>
        )),
      )}
    </ul>
  );

  return (
    <div className="site-voices" style={{ ["--voices-duration" as string]: `${seconds}s` }}>
      <div className="site-voices__track">
        {row(false)}
        {row(true)}
      </div>
    </div>
  );
}
