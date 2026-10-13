import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Alert, Badge, Button, Card, Select, Textarea } from "../components";
import { formatDate, humanise } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonRows, useDocumentTitle, TableScroll } from "../ui/blocks";
import { FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { ConfirmDialog } from "./dialogs";
import { ROLE_LABELS } from "./permissions";
import { useStepUp } from "./StepUp";
import { EmailChips } from "./EmailChips";
import { sendable, type Chip } from "./emailTags";
import { useOffsetList } from "./useOffsetList";
import { useAuth } from "../auth/AuthProvider";
import { permissionsFor } from "./permissions";

type Invitation = components["schemas"]["Invitation"];
type Report = components["schemas"]["BulkReport"];
type BatchResult = components["schemas"]["InvitationBatchResult"];

const TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = {
  sent: "info",
  opened: "info",
  registered: "success",
  expired: "neutral",
  revoked: "danger",
};

const INVITE_ROLES = ["member", "mentor", "content_editor", "community_admin"];

export default function Invitations() {
  useDocumentTitle("Invitations");
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [status, setStatus] = useState("");
  const { me } = useAuth();
  const canTeam = permissionsFor(me?.roles ?? []).has("roles.manage");
  const [chips, setChips] = useState<Chip[]>([]);
  const [form, setForm] = useState({ role: "member", message: "" });
  const [batchResult, setBatchResult] = useState<BatchResult | null>(null);
  const key = useRef(crypto.randomUUID());
  const checked = useRef(new Set<string>());
  const [csv, setCsv] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [revoking, setRevoking] = useState<Invitation | null>(null);

  const list = useOffsetList<Invitation>(["admin", "invitations", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/invitations", { params: { query: { limit, offset, ...(status ? { status: status as "sent" | "opened" | "registered" | "revoked" | "expired" } : {}) } } })),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "invitations"] });

  // Ask the server who is already here, so those chips are flagged before anything is sent.
  useEffect(() => {
    const fresh = chips.filter((c) => !c.flag && !checked.current.has(c.email.toLowerCase())).map((c) => c.email);
    if (fresh.length === 0) return;
    fresh.forEach((e) => checked.current.add(e.toLowerCase()));
    void unwrap(api.POST("/api/v1/admin/invitations/check", { body: { emails: fresh } })).then((rows) => {
      const flags = new Map(rows.map((r) => [r.email.toLowerCase(), r.state]));
      setChips((now) => now.map((c) => {
        const state = flags.get(c.email.toLowerCase());
        return state && state !== "ok" ? { ...c, flag: state } : c;
      }));
    }).catch(() => undefined);
  }, [chips]);

  const toSend = sendable(chips);
  const invite = useSubmit(async () => {
    const result = await guard(() =>
      unwrap(api.POST("/api/v1/admin/invitations/batch", { body: { emails: toSend, role: form.role, message: form.message.trim(), idempotency_key: key.current } })),
    );
    setBatchResult(result);
    toast.show(`${result.sent} invitation${result.sent === 1 ? "" : "s"} sent`);
    setChips([]);
    checked.current.clear();
    setForm({ ...form, message: "" });
    key.current = crypto.randomUUID();
    await refresh();
  });
  const bulk = useSubmit(async () => {
    const result = await guard(() => unwrap(api.POST("/api/v1/admin/invitations/bulk", { body: { csv } })));
    setReport(result);
    toast.show(`${result.created} invitation${result.created === 1 ? "" : "s"} sent`);
    await refresh();
  });
  const resend = async (i: Invitation) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/invitations/{invitation_id}/resend", { params: { path: { invitation_id: i.id } } })));
    toast.show("Invitation sent again");
    await refresh();
  };
  const revoke = async (i: Invitation) => {
    await guard(() => unwrap(api.POST("/api/v1/admin/invitations/{invitation_id}/revoke", { params: { path: { invitation_id: i.id } } })));
    toast.show("Invitation withdrawn");
    await refresh();
  };

  return (
    <>
      <PageHeader eyebrow="People" title="Invitations" lead="Invite people straight in, without waiting for them to apply." />
      <div className="app-split app-split--even">
        <Card>
          <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Invite people</h2>
          <form className="app-stack" noValidate onSubmit={(e) => { e.preventDefault(); void invite.run(); }}>
            <FormError error={invite.error} />
            <EmailChips chips={chips} onChange={setChips} disabled={invite.busy} />
            <Select label="Role" options={INVITE_ROLES.filter((r) => canTeam || !["content_editor", "community_admin"].includes(r)).map((r) => ({ value: r, label: ROLE_LABELS[r] ?? humanise(r) }))} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} />
            <Textarea label="A personal note (optional)" rows={3} maxLength={500} hint={`${form.message.length} of 500. It is included in the email.`} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} />
            <div><Button type="submit" loading={invite.busy} disabled={toSend.length === 0}>{`Send ${toSend.length} ${toSend.length === 1 ? "invitation" : "invitations"}`}</Button></div>
            {batchResult ? (
              <Alert tone={batchResult.skipped ? "warning" : "success"} title={`${batchResult.sent} sent, ${batchResult.skipped} skipped`}>
                <ul style={{ margin: 0 }}>{batchResult.results.map((r) => <li key={r.email}>{r.email}: {r.result === "sent" ? "sent" : `${r.result}, ${r.reason}`}</li>)}</ul>
              </Alert>
            ) : null}
          </form>
        </Card>
        <Card>
          <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Invite many at once</h2>
          <div className="app-stack">
            <FormError error={bulk.error} />
            <Textarea label="Paste a CSV" rows={5} hint="One person per line: email,role. Roles default to member." value={csv} onChange={(e) => setCsv(e.target.value)} />
            <div><Button variant="secondary" loading={bulk.busy} disabled={!csv.trim()} onClick={() => void bulk.run()}>Send all</Button></div>
            {report ? (
              <Alert tone={report.skipped ? "warning" : "success"} title={`${report.created} sent, ${report.skipped} skipped`}>
                {report.skipped > 0 ? (
                  <ul style={{ margin: 0 }}>{report.rows.filter((r) => r.result === "skipped").map((r) => <li key={r.row}>Row {r.row}{r.email ? ` (${r.email})` : ""}: {r.reason}</li>)}</ul>
                ) : "Everyone on the list was invited."}
              </Alert>
            ) : null}
          </div>
        </Card>
      </div>

      <section aria-label="Sent invitations" style={{ marginTop: "var(--space-8)" }}>
        <div className="app-cluster" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
          <h2 className="h3" style={{ margin: 0 }}>Sent</h2>
          <Select label="Show" options={[{ value: "", label: "All" }, ...["sent", "opened", "registered", "expired", "revoked"].map((s) => ({ value: s, label: humanise(s) }))]} value={status} onChange={(e) => setStatus(e.target.value)} />
        </div>
        {list.query.isPending ? <SkeletonRows /> : list.query.isError ? (
          <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
        ) : list.isEmpty ? (
          <EmptyState title="No invitations yet">Invitations you send will be listed here.</EmptyState>
        ) : (
          <>
            <TableScroll label="Invitations">
              <table className="app-table">
                <caption className="wo-visually-hidden">Invitations</caption>
                <thead><tr><th scope="col">Email</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col">Sent</th><th scope="col"><span className="wo-visually-hidden">Actions</span></th></tr></thead>
                <tbody>
                  {list.items.map((i) => (
                    <tr key={i.id}>
                      <th scope="row">{i.email}</th>
                      <td>{ROLE_LABELS[i.role] ?? humanise(i.role)}</td>
                      <td><Badge variant={TONE[i.status] ?? "neutral"} dot>{humanise(i.status)}</Badge></td>
                      <td>{formatDate(i.last_sent_at || i.created_at)}</td>
                      <td>
                        {i.status === "sent" || i.status === "opened" || i.status === "expired" ? (
                          <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                            <Button size="sm" variant="secondary" onClick={() => void resend(i)} aria-label={`Send ${i.email} the invitation again`}>Resend</Button>
                            {i.status !== "expired" ? <Button size="sm" variant="ghost" onClick={() => setRevoking(i)} aria-label={`Withdraw the invitation to ${i.email}`}>Withdraw</Button> : null}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
            <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
          </>
        )}
      </section>
      {revoking ? (
        <ConfirmDialog title="Withdraw this invitation?" body={`${revoking.email} will no longer be able to use the link.`} confirmLabel="Withdraw" tone="danger" onConfirm={() => revoke(revoking)} onClose={() => setRevoking(null)} />
      ) : null}
    </>
  );
}
