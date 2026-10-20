import DOMPurify from "dompurify";
import { useEffect, type ReactNode, type CSSProperties } from "react";
import { Button, Alert } from "../components";
import { messageOf } from "../api/errors";
import { cx } from "../lib/cx";

/** Sets the browser tab title for a screen. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    const previous = document.title;
    document.title = title ? `${title} | WO Community` : "WO Community";
    return () => {
      document.title = previous;
    };
  }, [title]);
}

interface PageHeaderProps {
  /** The small uppercase word at the right of the header rule: where the member is. */
  eyebrow: string;
  title: string;
  lead?: ReactNode;
  actions?: ReactNode;
}

/** Every page opens with a header rule and a right-aligned eyebrow, then the title. */
export function PageHeader({ eyebrow, title, lead, actions }: PageHeaderProps) {
  useDocumentTitle(title);
  return (
    <header className="app-pagehead">
      <div className="wo-page-rule">
        <hr />
        <span className="wo-eyebrow">{eyebrow}</span>
      </div>
      <div className="app-pagehead__row">
        <div>
          <h1 className="h1 app-pagehead__title">{title}</h1>
          {lead ? <p className="body-lg app-pagehead__lead">{lead}</p> : null}
        </div>
        {actions ? <div className="app-pagehead__actions">{actions}</div> : null}
      </div>
    </header>
  );
}

export function Section({
  title,
  action,
  children,
  id,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section className="app-section" aria-labelledby={id}>
      <div className="app-section__head">
        <h2 className="h3 app-section__title" id={id}>
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Skeleton({ width = "100%", height = 16 }: { width?: string | number; height?: number }) {
  return <span className="app-skeleton" style={{ width, height }} aria-hidden="true" />;
}

/** A card-shaped placeholder shown while a list loads. */
export function SkeletonCards({ count = 6 }: { count?: number }) {
  return (
    <div className="app-grid" role="status" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <div className="wo-card app-stack" key={i}>
          <Skeleton width="40%" height={14} />
          <Skeleton height={22} />
          <Skeleton width="80%" />
          <Skeleton width="60%" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonRows({ count = 4 }: { count?: number }) {
  return (
    <div className="app-list" role="status" aria-label="Loading">
      {Array.from({ length: count }, (_, i) => (
        <div className="app-list__item" key={i}>
          <Skeleton width={44} height={44} />
          <div className="app-list__main app-stack" style={{ gap: "var(--space-2)" }}>
            <Skeleton width="50%" height={18} />
            <Skeleton width="30%" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
  icon,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="app-empty">
      {icon ? <span className="app-tile">{icon}</span> : null}
      <h3 className="h3 app-empty__title">{title}</h3>
      {children ? <div className="app-empty__text">{children}</div> : null}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <Alert
      tone="danger"
      title="We could not load this"
      action={
        onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        ) : undefined
      }
    >
      {messageOf(error)}
    </Alert>
  );
}

interface QueryLike<T> {
  data: T | undefined;
  error: unknown;
  isPending: boolean;
  isError: boolean;
  refetch: () => unknown;
}

/**
 * Renders the right thing for a query: a placeholder while loading, an error with a retry, or the
 * content. `isEmpty` swaps in the empty state when there is nothing to show.
 */
export function Loaded<T>({
  query,
  skeleton,
  empty,
  isEmpty,
  children,
}: {
  query: QueryLike<T>;
  skeleton?: ReactNode;
  empty?: ReactNode;
  isEmpty?: (data: T) => boolean;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <>{skeleton ?? <SkeletonRows />}</>;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const data = query.data as T;
  if (isEmpty?.(data) && empty) return <>{empty}</>;
  return <>{children(data)}</>;
}

function openOutsideLinksInANewTab(node: Element): void {
  if (node.tagName === "A" && /^https?:/i.test(node.getAttribute("href") ?? "")) {
    node.setAttribute("target", "_blank");
    node.setAttribute("rel", "noopener noreferrer nofollow");
  }
}

/** Server HTML is already cleaned; this cleans it again before it reaches the page. */
export function RichText({ html, className }: { html: string; className?: string }) {
  // Links to other websites open in a new tab, so a reader keeps their place in the community.
  DOMPurify.addHook("afterSanitizeAttributes", openOutsideLinksInANewTab);
  let clean: string;
  try {
    clean = DOMPurify.sanitize(html, {
      ALLOWED_TAGS: ["p", "br", "strong", "em", "b", "i", "u", "ul", "ol", "li", "a", "blockquote", "h3", "h4", "code"],
      ALLOWED_ATTR: ["href", "title"],
      ALLOWED_URI_REGEXP: /^(?:https?:|mailto:)/i,
    });
  } finally {
    DOMPurify.removeHook("afterSanitizeAttributes", openOutsideLinksInANewTab);
  }
  return <div className={cx("app-richtext", className)} dangerouslySetInnerHTML={{ __html: clean }} />;
}

/** The "Load more" control for cursor-paged lists. */
export function LoadMore({
  hasNext,
  loading,
  onClick,
}: {
  hasNext: boolean;
  loading: boolean;
  onClick: () => void;
}) {
  if (!hasNext) return null;
  return (
    <div style={{ display: "flex", justifyContent: "center", marginTop: "var(--space-6)" }}>
      <Button variant="secondary" loading={loading} onClick={onClick}>
        Load more
      </Button>
    </div>
  );
}

/** Page controls for lists the server pages by number. */
export function Pagination({
  page,
  pages,
  count,
  noun,
  onPage,
}: {
  page: number;
  pages: number;
  count: number;
  noun: string;
  onPage: (page: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <nav className="app-pager" aria-label="Pages">
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        Previous
      </Button>
      <p className="body-sm app-muted" style={{ margin: 0 }} aria-live="polite">
        Page {page} of {pages} &middot; {count} {noun}
      </p>
      <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next
      </Button>
    </nav>
  );
}

/** A table that scrolls sideways inside its own box on narrow screens, reachable by keyboard. */
export function TableScroll({ label, children, style }: { label: string; children: ReactNode; style?: CSSProperties }) {
  return (
    // A box that scrolls must be focusable so keyboard users can scroll it.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className="app-tablewrap" role="region" aria-label={label} tabIndex={0} style={style}>
      {children}
    </div>
  );
}
