import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Input, Select } from "../components";
import { formatDate, humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonRows, useDocumentTitle, TableScroll } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ConfirmDialog, ReasonDialog } from "./dialogs";
import { ROLE_LABELS } from "./permissions";
import { useStepUp } from "./StepUp";
import { useOffsetList } from "./useOffsetList";

type Member = components["schemas"]["Member"];
type Status = "pending" | "active" | "suspended" | "removed" | "rejected";

const STATUSES: Status[] = ["pending", "active", "suspended", "removed", "rejected"];
const TONE: Record<string, "success" | "warning" | "danger" | "neutral" | "info"> = {
  active: "success",
  pending: "warning",
  suspended: "danger",
  removed: "neutral",
  rejected: "neutral",
};

type Action =
  | { kind: "approve" | "reinstate" | "reset-mfa"; member: Member }
  | { kind: "reject" | "suspend" | "remove"; member: Member };

export default function Members() {
  useDocumentTitle("Members");
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const status = (params.get("status") ?? "") as Status | "";
  const role = params.get("role") ?? "";
  const client = useQueryClient();
  const toast = useToast();
  const guard = useStepUp();
  const [action, setAction] = useState<Action | null>(null);

  const list = useOffsetList<Member>(["admin", "members", status, role, params.get("q") ?? ""], (offset, limit) =>
    unwrap(
      api.GET("/api/v1/admin/members", {
        params: { query: { limit, offset, ...(status ? { status } : {}), ...(role ? { role } : {}), ...(params.get("q") ? { q: params.get("q") ?? "" } : {}) } },
      }),
    ),
  );

  const set = (next: Record<string, string>) => {
    const merged = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v) merged.set(k, v);
      else merged.delete(k);
    }
    setParams(merged, { replace: true });
  };

  const done = async (text: string) => {
    toast.show(text);
    await client.invalidateQueries({ queryKey: ["admin"] });
  };
  const path = (m: Member) => ({ params: { path: { user_id: m.id } } });

  const run = async (a: Action, reason = "") => {
    const m = a.member;
    await guard(async () => {
      if (a.kind === "approve") await unwrap(api.POST("/api/v1/admin/members/{user_id}/approve", path(m)));
      else if (a.kind === "reinstate") await unwrap(api.POST("/api/v1/admin/members/{user_id}/reinstate", path(m)));
      else if (a.kind === "reset-mfa") await unwrap(api.POST("/api/v1/admin/members/{user_id}/reset-mfa", path(m)));
      else if (a.kind === "reject") await unwrap(api.POST("/api/v1/admin/members/{user_id}/reject", { ...path(m), body: { reason } }));
      else if (a.kind === "suspend") await unwrap(api.POST("/api/v1/admin/members/{user_id}/suspend", { ...path(m), body: { reason } }));
      else await unwrap(api.POST("/api/v1/admin/members/{user_id}/remove", { ...path(m), body: { reason } }));
    });
    await done(
      { approve: "Member approved", reject: "Request rejected", suspend: "Member suspended", reinstate: "Member reinstated", remove: "Member removed", "reset-mfa": "Two step sign in reset" }[a.kind],
    );
  };

  return (
    <>
      <PageHeader eyebrow="People" title="Members" lead="Everyone who has asked to join or is already in." />
      <form
        className="app-formgrid"
        style={{ marginBottom: "var(--space-6)", alignItems: "end" }}
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          set({ q: q.trim() });
        }}
      >
        <Input label="Search by email" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="Status" options={[{ value: "", label: "Any status" }, ...STATUSES.map((s) => ({ value: s, label: humanise(s) }))]} value={status} onChange={(e) => set({ status: e.target.value })} />
        <Select label="Role" options={[{ value: "", label: "Any role" }, ...Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }))]} value={role} onChange={(e) => set({ role: e.target.value })} />
        <div><Button type="submit" variant="secondary">Search</Button></div>
      </form>

      {list.query.isPending ? <SkeletonRows count={6} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No members match">Try a different search or status.</EmptyState>
      ) : (
        <>
          <TableScroll label="Members">
            <table className="app-table">
              <caption className="wo-visually-hidden">Members</caption>
              <thead>
                <tr><th scope="col">Member</th><th scope="col">Status</th><th scope="col">Joined</th><th scope="col">Last seen</th><th scope="col"><span className="wo-visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                {list.items.map((m) => (
                  <tr key={m.id}>
                    <th scope="row">
                      <span style={{ display: "block" }}>{m.email}</span>
                      <span className="caption app-muted">{m.roles.map((r) => ROLE_LABELS[r] ?? humanise(r)).join(", ")}{m.email_verified_at ? "" : " · email not confirmed"}</span>
                    </th>
                    <td>
                      <Badge variant={TONE[m.status] ?? "neutral"} dot>{humanise(m.status)}</Badge>
                      {m.status_reason ? <span className="caption app-muted" style={{ display: "block" }}>{m.status_reason}</span> : null}
                    </td>
                    <td>{formatDate(m.created_at)}</td>
                    <td>{m.last_login ? timeAgo(m.last_login) : "Never"}</td>
                    <td>
                      <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                        {m.status === "pending" ? (
                          <>
                            <Button size="sm" onClick={() => setAction({ kind: "approve", member: m })} aria-label={`Approve ${m.email}`}>Approve</Button>
                            <Button size="sm" variant="ghost" onClick={() => setAction({ kind: "reject", member: m })} aria-label={`Reject ${m.email}`}>Reject</Button>
                          </>
                        ) : null}
                        {m.status === "active" ? (
                          <>
                            <Button size="sm" variant="secondary" onClick={() => setAction({ kind: "suspend", member: m })} aria-label={`Suspend ${m.email}`}>Suspend</Button>
                            <Button size="sm" variant="ghost" onClick={() => setAction({ kind: "reset-mfa", member: m })} aria-label={`Reset two step sign in for ${m.email}`}>Reset 2FA</Button>
                          </>
                        ) : null}
                        {m.status === "suspended" ? <Button size="sm" variant="secondary" onClick={() => setAction({ kind: "reinstate", member: m })} aria-label={`Reinstate ${m.email}`}>Reinstate</Button> : null}
                        {m.status === "active" || m.status === "suspended" ? (
                          <Button size="sm" variant="ghost" onClick={() => setAction({ kind: "remove", member: m })} aria-label={`Remove ${m.email}`}>Remove</Button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}

      {action && (action.kind === "reject" || action.kind === "suspend" || action.kind === "remove") ? (
        <ReasonDialog
          title={{ reject: "Reject this request?", suspend: "Suspend this member?", remove: "Remove this member?" }[action.kind]}
          confirmLabel={{ reject: "Reject", suspend: "Suspend", remove: "Remove" }[action.kind]}
          tone={action.kind === "remove" ? "danger" : "primary"}
          intro={`${action.member.email}. ${action.kind === "reject" ? "They are told their request was not accepted." : action.kind === "suspend" ? "They cannot sign in until reinstated." : "Their access ends and their profile is hidden."}`}
          onConfirm={(reason) => run(action, reason)}
          onClose={() => setAction(null)}
        />
      ) : null}
      {action && (action.kind === "approve" || action.kind === "reinstate" || action.kind === "reset-mfa") ? (
        <ConfirmDialog
          title={{ approve: "Approve this member?", reinstate: "Reinstate this member?", "reset-mfa": "Reset two step sign in?" }[action.kind]}
          body={`${action.member.email}. ${action.kind === "approve" ? "They get full access and an email telling them so." : action.kind === "reinstate" ? "They can sign in again." : "They must set up an authenticator app again next time they sign in."}`}
          confirmLabel={{ approve: "Approve", reinstate: "Reinstate", "reset-mfa": "Reset" }[action.kind]}
          onConfirm={() => run(action)}
          onClose={() => setAction(null)}
        />
      ) : null}
    </>
  );
}
