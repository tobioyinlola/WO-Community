import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { useAuth } from "../auth/AuthProvider";
import { Alert, Button, Input } from "../components";
import { formatDate, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, Skeleton, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";
import { StatusChip, type Tone } from "./kit/TableBits";
import { permissionsFor } from "./permissions";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Suppression = components["schemas"]["Suppression"];

const TONE: Record<string, Tone> = { ok: "success", warning: "warning", missing: "danger", unknown: "neutral" };
const WORD: Record<string, string> = { ok: "Good", warning: "Needs attention", missing: "Missing", unknown: "Could not check" };

function Suppressions() {
  const { me } = useAuth();
  const canRemove = permissionsFor(me?.roles ?? []).has("email.suppression.manage");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [email, setEmail] = useState("");
  const [term, setTerm] = useState("");
  const [removing, setRemoving] = useState<Suppression | null>(null);
  const list = useOffsetList<Suppression>(["admin", "email", "suppressions", term], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/email/suppressions", { params: { query: { limit, offset, ...(term ? { email: term } : {}) } } })),
  );
  const remove = async (row: Suppression) => {
    await guard(() => unwrap(api.DELETE("/api/v1/admin/email/suppressions/{suppression_id}", { params: { path: { suppression_id: row.id } } })));
    toast.show("Removed. Broadcasts can go to this address again.");
    await client.invalidateQueries({ queryKey: ["admin", "email"] });
  };
  return (
    <section aria-labelledby="supp-title" className="app-stack">
      <h2 className="h3" id="supp-title" style={{ margin: 0 }}>Suppression list</h2>
      <p className="body-sm app-muted" style={{ margin: 0 }}>Addresses that bounced, complained or unsubscribed never get a broadcast. They are stored as scrambled hashes, so search with the full address.</p>
      <form className="app-cluster" style={{ alignItems: "end" }} role="search" onSubmit={(e) => { e.preventDefault(); setTerm(email.trim()); }}>
        <Input label="Find an address" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Button type="submit" variant="secondary">Search</Button>
        {term ? <Button variant="ghost" onClick={() => { setEmail(""); setTerm(""); }}>Show all</Button> : null}
      </form>
      {list.query.isPending ? <Skeleton height={80} /> : list.isEmpty ? (
        <EmptyState title={term ? "That address is not suppressed" : "Nobody is suppressed"}>{term ? "It can receive broadcasts." : "Bounces, complaints and unsubscribes will appear here."}</EmptyState>
      ) : (
        <div className="adm-tablewrap">
          <table className="adm-table">
            <caption className="wo-visually-hidden">Suppressed addresses</caption>
            <thead><tr><th scope="col">Reason</th><th scope="col">Reference</th><th scope="col">Added</th>{canRemove ? <th scope="col"><span className="wo-visually-hidden">Actions</span></th> : null}</tr></thead>
            <tbody>
              {list.items.map((s) => (
                <tr key={s.id}>
                  <td>{humanise(s.reason)}</td><td><code>{s.reference}</code></td><td>{formatDate(s.created_at)}</td>
                  {canRemove ? <td><Button size="sm" variant="ghost" onClick={() => setRemoving(s)}>Remove</Button></td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
      {removing ? <ConfirmDialog title="Allow broadcasts to this address again?" body="Only do this if the person asked to hear from us again. It is recorded in the audit log." confirmLabel="Remove" tone="danger" onConfirm={() => remove(removing)} onClose={() => setRemoving(null)} /> : null}
    </section>
  );
}

export default function EmailHealth() {
  useDocumentTitle("Email health");
  const health = useQuery({ queryKey: ["admin", "email", "health"], queryFn: () => unwrap(api.GET("/api/v1/admin/email/health")) });
  const h = health.data;
  return (
    <>
      <PageHeader eyebrow="Email" title="Email health" lead="Whether mail from WO Community is trusted, how sending has gone, and who we no longer write to." actions={<Button variant="secondary" loading={health.isFetching} onClick={() => void health.refetch()}>Check again</Button>} />
      {health.isError ? <ErrorState error={health.error} onRetry={() => void health.refetch()} /> : !h ? <Skeleton height={300} /> : (
        <div className="app-stack app-stack--lg">
          {h.provider === "fake" ? <Alert tone="warning" title="No real email provider is connected">Emails are only kept in memory. Set the provider keys to send for real.</Alert> : null}
          <dl className="adm-statstrip" aria-label="Sending in the last 30 days">
            {([["Sent", h.stats.sent], ["Delivered", h.stats.delivered], ["Bounced", h.stats.bounced], ["Complaints", h.stats.complained], ["Unsubscribed", h.stats.unsubscribed], ["Suppressed", h.stats.suppressed_total]] as const).map(([label, value]) => (
              <div key={label} className="adm-statstrip__cell"><dt>{label}</dt><dd>{value.toLocaleString("en-NG")}</dd></div>
            ))}
          </dl>
          <section aria-labelledby="setup-title" className="app-stack">
            <h2 className="h3" id="setup-title" style={{ margin: 0 }}>Setup</h2>
            <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              <li><StatusChip tone={h.configured.api_key ? "success" : "danger"}>{h.configured.api_key ? "Provider key set" : "Provider key missing"}</StatusChip></li>
              <li><StatusChip tone={h.configured.webhook_secret ? "success" : "danger"}>{h.configured.webhook_secret ? "Delivery reports are verified" : "Webhook secret missing, so bounces are not recorded"}</StatusChip></li>
              <li><StatusChip tone={h.separate_streams ? "success" : "warning"}>{h.separate_streams ? "Account mail and broadcasts use separate sending domains" : "Account mail and broadcasts share one domain"}</StatusChip></li>
              <li><StatusChip tone={h.configured.reply_to ? "success" : "warning"}>{h.configured.reply_to ? "A monitored reply address is set" : "No reply address is set"}</StatusChip></li>
              <li><StatusChip tone={h.configured.logo ? "success" : "warning"}>{h.configured.logo ? "Logo is on an https address" : "Logo address is not https"}</StatusChip></li>
              <li><StatusChip tone="neutral">{h.hourly_cap ? `Broadcasts are limited to ${h.hourly_cap} an hour while the domain warms up` : "No hourly limit on broadcasts"}</StatusChip></li>
            </ul>
          </section>
          {h.domains.map((d) => (
            <section key={d.domain} aria-labelledby={`dom-${d.domain}`} className="app-stack">
              <h2 className="h3" id={`dom-${d.domain}`} style={{ margin: 0 }}>{d.domain} <span className="body-sm app-muted">({d.stream === "broadcast" ? "broadcasts" : "account mail"})</span></h2>
              <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {d.checks.map((c) => (
                  <li key={c.key}>
                    <StatusChip tone={TONE[c.status] ?? "neutral"}>{c.title}: {WORD[c.status] ?? c.status}</StatusChip>
                    <p className="body-sm app-muted" style={{ margin: "2px 0 0" }}>{c.detail}</p>
                    {c.record ? <code className="body-sm" style={{ overflowWrap: "anywhere" }}>{c.record}</code> : null}
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <section aria-labelledby="fail-title" className="app-stack">
            <h2 className="h3" id="fail-title" style={{ margin: 0 }}>Recent failures</h2>
            {h.failures.length === 0 ? <p className="body-sm app-muted" style={{ margin: 0 }}>No bounces or complaints have been recorded.</p> : (
              <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {h.failures.map((f) => <li key={f.id} className="body-sm">{humanise(f.kind)} · message <code>{f.provider_message_id}</code> · {timeAgo(f.created_at)}</li>)}
              </ul>
            )}
          </section>
          <Suppressions />
        </div>
      )}
    </>
  );
}
