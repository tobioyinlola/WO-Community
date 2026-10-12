import { useQuery } from "@tanstack/react-query";
import { UserRound } from "lucide-react";
import { api, unwrap } from "../api/client";
import { Avatar } from "../components";
import { formatNumber } from "../lib/format";
import { EmptyState, SkeletonRows } from "../ui/blocks";
import { changeBetween, Delta } from "./kit/Delta";
import { KpiCard } from "./kit/KpiCard";

/** Referrals on the dashboard: how many sign ups were referred, where people heard of us, and who brings people in. */
export function ReferralSection() {
  const summary = useQuery({ queryKey: ["admin", "referrals", "summary"], queryFn: () => unwrap(api.GET("/api/v1/admin/referrals/summary")) });
  const top = useQuery({ queryKey: ["admin", "referrals", "top"], queryFn: () => unwrap(api.GET("/api/v1/admin/referrals/top", { params: { query: { limit: 5 } } })) });
  const s = summary.data;
  const biggest = Math.max(1, ...(s?.sources ?? []).map((x) => x.count));

  return (
    <>
      <section className="adm-kpis" aria-label="Referrals">
        <KpiCard
          loading={summary.isPending}
          label="Referrals"
          tag="This month"
          value={s ? formatNumber(s.this_month.referred) : "…"}
          delta={s ? <Delta change={changeBetween(s.this_month.referred, s.last_month.referred)} versus="on last month" /> : null}
          rows={[
            { label: "Last month", value: s ? formatNumber(s.last_month.referred) : "…" },
            { label: "Sign ups this month", value: s ? formatNumber(s.this_month.signups) : "…" },
            { label: "Share that were referred", value: s ? `${s.referred_share}%` : "…" },
          ]}
        />
      </section>

      <div className="adm-twocol">
        <section className="adm-card" aria-labelledby="src-title">
          <h2 className="adm-card__title" id="src-title">Where people heard of us</h2>
          <p className="adm-card__sub">Sign ups this month by what they told us</p>
          {summary.isPending ? (
            <SkeletonRows count={3} />
          ) : (s?.sources ?? []).length === 0 ? (
            <EmptyState title="No sign ups yet this month">Sources appear as people ask to join.</EmptyState>
          ) : (
            <ul className="wo-sources">
              {s?.sources.map((x) => (
                <li key={x.kind} className="wo-sources__row">
                  <span className="wo-sources__label">{x.kind_label}</span>
                  <span className="wo-sources__bar" aria-hidden="true">
                    <span style={{ width: `${(x.count / biggest) * 100}%` }} />
                  </span>
                  <strong className="wo-sources__count">{formatNumber(x.count)}</strong>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="adm-card" aria-labelledby="top-title">
          <h2 className="adm-card__title" id="top-title">Top referrers</h2>
          <p className="adm-card__sub">Members with the most approved referrals</p>
          {top.isPending ? (
            <SkeletonRows count={3} />
          ) : (top.data ?? []).length === 0 ? (
            <EmptyState title="No referrals yet" icon={<UserRound size={22} strokeWidth={1.5} />}>
              When people join through a member, they appear here.
            </EmptyState>
          ) : (
            <ol className="wo-top">
              {top.data?.map((m) => (
                <li key={m.id} className="wo-top__row">
                  <Avatar name={m.name} id={m.id} size="sm" />
                  <span className="wo-top__name">{m.name}</span>
                  <strong>{formatNumber(m.approved)}</strong>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </>
  );
}
