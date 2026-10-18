import { ArrowRight, BookOpen, CalendarDays, MessageSquareQuote } from "lucide-react";
import { Link } from "react-router-dom";
import type { components } from "../../api/schema";

export type ShareCard = components["schemas"]["ShareCard"];

const ICONS = { course: BookOpen, event: CalendarDays, post: MessageSquareQuote } as const;

/**
 * A course, event or post as a short card. In the feed it opens the full thing; in the Share
 * dialog it is a preview of what people will see, so it is not a link there.
 */
export function SharedCard({ card, link = true, compact = false }: { card: ShareCard; link?: boolean; compact?: boolean }) {
  const Icon = ICONS[card.kind as keyof typeof ICONS] ?? BookOpen;
  const inner = (
    <>
      <div className="wo-sharecard__media" aria-hidden="true">
        {card.image ? <img src={card.image} alt="" loading="lazy" decoding="async" /> : <Icon size={compact ? 28 : 36} strokeWidth={1.25} />}
      </div>
      <div className="wo-sharecard__body">
        <span className="wo-sharecard__badge">{card.badge}</span>
        <span className="wo-sharecard__title">{card.title}</span>
        {card.facts.length ? <span className="wo-sharecard__facts">{card.facts.join(" · ")}</span> : null}
        {!compact && card.excerpt ? <span className="wo-sharecard__excerpt">{card.excerpt}</span> : null}
        {link ? (
          <span className="wo-sharecard__action">
            {card.action} <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </span>
        ) : null}
      </div>
    </>
  );
  const className = `wo-sharecard${compact ? " wo-sharecard--compact" : ""}`;
  return link ? (
    <Link className={className} to={card.url} aria-label={`${card.action}: ${card.title}`}>
      {inner}
    </Link>
  ) : (
    <div className={className}>{inner}</div>
  );
}
