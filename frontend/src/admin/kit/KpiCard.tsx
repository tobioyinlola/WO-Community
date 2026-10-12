import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Skeleton } from "../../ui/blocks";

export interface KpiRow {
  label: string;
  value: string;
}

interface KpiCardProps {
  label: string;
  /** A small tag in the corner, such as "Today". */
  tag?: string;
  value: string;
  delta?: ReactNode;
  rows: KpiRow[];
  to?: string;
  /** The one card that is solid forest with a gold figure. */
  highlight?: boolean;
  loading?: boolean;
}

/** One headline figure with its change and three comparisons. */
export function KpiCard({ label, tag, value, delta, rows, to, highlight = false, loading = false }: KpiCardProps) {
  const body = (
    <>
      <div className="adm-kpi__top">
        <span className="adm-kpi__label">{label}</span>
        {tag ? <span className="adm-kpi__tag">{tag}</span> : null}
      </div>
      {loading ? (
        <div style={{ margin: "var(--space-3) 0 var(--space-5)" }}><Skeleton width="50%" height={44} /></div>
      ) : (
        <div className="adm-kpi__figure">
          <span className="adm-kpi__value">{value}</span>
          {delta}
        </div>
      )}
      <dl className="adm-kpi__rows">
        {rows.map((row) => (
          <div key={row.label} className="adm-kpi__row">
            <dt>{row.label}</dt>
            <dd>{loading ? "…" : row.value}</dd>
          </div>
        ))}
      </dl>
    </>
  );
  return to ? (
    <Link to={to} className="adm-card adm-kpi" data-highlight={highlight} aria-label={`${label}: ${value}. Open the details`}>
      {body}
    </Link>
  ) : (
    <div className="adm-card adm-kpi" data-highlight={highlight}>{body}</div>
  );
}
