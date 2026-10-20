import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Select } from "../components";
import { humanise } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ReasonDialog } from "./dialogs";
import { useOffsetList } from "./useOffsetList";

type Mentor = components["schemas"]["AdminMentor"];

const TONE: Record<string, "success" | "warning" | "danger"> = { active: "success", pending: "warning", revoked: "danger" };
const LABEL: Record<string, string> = { active: "Approved", pending: "Pending", revoked: "Revoked" };

export default function ApprovedMentors() {
  useDocumentTitle("Approved mentors");
  const [status, setStatus] = useState("active");
  const [acting, setActing] = useState<Mentor | null>(null);
  const client = useQueryClient();
  const toast = useToast();
  const list = useOffsetList<Mentor>(["admin", "mentors", status], (offset, limit) =>
    unwrap(api.GET("/api/v1/admin/mentors", { params: { query: { status, limit, offset } } })),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin"] });
  const toPending = async (mentor: Mentor, reason: string) => {
    await unwrap(api.POST("/api/v1/admin/mentors/{user_id}/pending", { params: { path: { user_id: mentor.id } }, body: reason ? { reason } : {} }));
    toast.show(`${mentor.name} is now pending and off the mentor list`);
    await refresh();
  };
  const approve = async (mentor: Mentor) => {
    await unwrap(api.POST("/api/v1/admin/mentors/{user_id}/restore", { params: { path: { user_id: mentor.id } } }));
    toast.show(`${mentor.name} is approved again`);
    await refresh();
  };
  return (
    <>
      <PageHeader eyebrow="People" title="Approved mentors" lead="Move a mentor to pending to take them off the platform's mentor list, then approve them again whenever you are ready." />
      <div style={{ maxWidth: 260, marginBottom: "var(--space-6)" }}>
        <Select label="Show" options={["active", "pending", "revoked"].map((s) => ({ value: s, label: LABEL[s] ?? humanise(s) }))} value={status} onChange={(e) => setStatus(e.target.value)} />
      </div>
      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="Nothing here">No mentors with this status.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((m) => (
              <li key={m.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <h2 className="h4" style={{ margin: 0 }}>{m.name}</h2>
                    <Badge variant={TONE[m.status] ?? "neutral"} dot>{LABEL[m.status] ?? humanise(m.status)}</Badge>
                  </div>
                  <p className="body-sm app-muted" style={{ margin: "var(--space-1) 0 0" }}>
                    {[m.current_role, m.company].filter(Boolean).join(" at ")} · {m.years_experience} years
                  </p>
                  {m.revoke_reason ? <p className="body-sm" style={{ margin: "var(--space-2) 0 0" }}>Note: {m.revoke_reason}</p> : null}
                  <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                    {m.status === "active" ? (
                      <Button size="sm" variant="secondary" onClick={() => setActing(m)}>Move to pending</Button>
                    ) : (
                      <Button size="sm" onClick={() => approve(m)}>Approve again</Button>
                    )}
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}
      {acting ? (
        <ReasonDialog
          title={`Move ${acting.name} to pending?`}
          confirmLabel="Move to pending"
          required={false}
          intro="They are taken off the mentor list and lose the mentor badge. Their open and upcoming sessions are cancelled and the mentees told. You can approve them again at any time."
          onConfirm={(reason) => toPending(acting, reason)}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}
