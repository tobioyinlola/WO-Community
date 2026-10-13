import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { messageOf } from "../api/errors";
import type { components } from "../api/schema";
import { Alert, Avatar, Button, Select, Switch } from "../components";
import { formatDate, formatDateTime } from "../lib/format";
import { Attachments, useAttachments } from "../support/Attachments";
import { ADMIN_STATUS_LABEL, CATEGORIES, PRIORITIES, STATUS_TONE } from "../support/constants";
import { Thread, type ThreadMessage } from "../support/Thread";
import { Drawer } from "../ui/Drawer";
import { ErrorState, Skeleton } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { RichEditor, type RichEditorHandle } from "./kit/RichEditor";
import { StatusChip } from "./kit/TableBits";

type Detail = components["schemas"]["AdminTicketDetail"];
type Person = components["schemas"]["SupportPerson"];

const STATUS_OPTIONS = Object.entries(ADMIN_STATUS_LABEL).map(([value, label]) => ({ value, label }));

export function useAgents() {
  return useQuery({ queryKey: ["admin", "support", "agents"], queryFn: () => unwrap(api.GET("/api/v1/admin/support/agents")), staleTime: 5 * 60_000 });
}

interface Props {
  id: string;
  onClose: () => void;
  position: { index: number; total: number };
  onPrevious: () => void;
  onNext: () => void;
}

/** One request, opened beside the list: who asked, the conversation, and the means to answer it. */
export function TicketDrawer({ id, onClose, position, onPrevious, onNext }: Props) {
  const client = useQueryClient();
  const toast = useToast();
  const editor = useRef<RichEditorHandle>(null);
  const [html, setHtml] = useState("");
  const [empty, setEmpty] = useState(true);
  const [internal, setInternal] = useState(false);
  const files = useAttachments();

  const detail = useQuery({
    queryKey: ["admin", "support", "ticket", id],
    queryFn: () => unwrap(api.GET("/api/v1/admin/support/tickets/{ticket_id}", { params: { path: { ticket_id: id } } })),
    refetchInterval: 30_000,
  });
  const agents = useAgents();
  const t: Detail | undefined = detail.data;
  const canned = useQuery({
    queryKey: ["admin", "support", "canned", t?.category ?? ""],
    enabled: t !== undefined,
    queryFn: () => unwrap(api.GET("/api/v1/admin/support/canned-replies", { params: { query: { category: t?.category ?? "" } as never } })),
  });

  const refresh = () => client.invalidateQueries({ queryKey: ["admin"] });
  const fail = (error: unknown) => toast.show(messageOf(error));

  const change = useMutation({
    mutationFn: (body: components["schemas"]["PatchedAdminTicketUpdateRequest"]) =>
      unwrap(api.PATCH("/api/v1/admin/support/tickets/{ticket_id}", { params: { path: { ticket_id: id } }, body })),
    onSuccess: refresh,
    onError: fail,
  });
  const send = useMutation({
    mutationFn: (status: "awaiting_member" | "resolved" | "in_progress") =>
      unwrap(api.POST("/api/v1/admin/support/tickets/{ticket_id}/messages", { params: { path: { ticket_id: id } }, body: { body: html, internal, status, attachments: files.ids } })),
    onSuccess: async (_data, status) => {
      editor.current?.clear();
      files.reset();
      await refresh();
      toast.show(internal ? "Note added" : status === "resolved" ? "Reply sent and request resolved" : "Reply sent");
    },
    onError: fail,
  });
  const resolve = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/admin/support/tickets/{ticket_id}/resolve", { params: { path: { ticket_id: id } } })),
    onSuccess: async () => {
      await refresh();
      toast.show("Request resolved");
    },
    onError: fail,
  });
  const reopen = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/admin/support/tickets/{ticket_id}/reopen", { params: { path: { ticket_id: id } } })),
    onSuccess: async () => {
      await refresh();
      toast.show("Request reopened");
    },
    onError: fail,
  });

  const busy = send.isPending || change.isPending || resolve.isPending || reopen.isPending || files.busy;
  const messages = (t?.messages ?? []) as unknown as ThreadMessage[];
  const member = t?.member as Person | undefined;
  const assignee = t?.assignee as Person | null | undefined;
  const agentOptions = [{ value: "", label: "Unassigned" }, ...(agents.data ?? []).map((a) => ({ value: a.id as string, label: a.name }))];
  if (assignee?.id && !agentOptions.some((o) => o.value === assignee.id)) agentOptions.push({ value: assignee.id, label: assignee.name });

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      size="lg"
      eyebrow={
        <>
          {t?.reference ?? "Request"}
          <span aria-live="polite"> · {position.index + 1} of {position.total}</span>
        </>
      }
      title={t?.subject ?? "Support request"}
      subtitle={t ? `${t.category_label} · opened ${formatDateTime(t.created_at)}` : undefined}
      dirty={!empty}
      actions={
        <>
          <button type="button" className="wo-drawer__close" onClick={onPrevious} disabled={position.index <= 0} aria-label="Previous request" aria-keyshortcuts="K">
            <ChevronUp size={18} strokeWidth={1.5} aria-hidden="true" />
          </button>
          <button type="button" className="wo-drawer__close" onClick={onNext} disabled={position.index >= position.total - 1} aria-label="Next request" aria-keyshortcuts="J">
            <ChevronDown size={18} strokeWidth={1.5} aria-hidden="true" />
          </button>
        </>
      }
      footer={
        t ? (
          internal ? (
            <Button loading={send.isPending} disabled={empty || busy} onClick={() => send.mutate("awaiting_member")}>
              Add note
            </Button>
          ) : (
            <>
              {t.status === "resolved" ? (
                <Button variant="secondary" loading={reopen.isPending} disabled={busy} onClick={() => reopen.mutate()}>
                  Reopen
                </Button>
              ) : (
                <Button variant="secondary" loading={resolve.isPending} disabled={busy} onClick={() => resolve.mutate()}>
                  Resolve
                </Button>
              )}
              <Button variant="secondary" disabled={empty || busy} onClick={() => send.mutate("resolved")}>
                Send and resolve
              </Button>
              <Button loading={send.isPending} disabled={empty || busy} onClick={() => send.mutate("awaiting_member")}>
                Send reply
              </Button>
            </>
          )
        ) : null
      }
    >
      {detail.isPending ? <Skeleton height={120} /> : null}
      {detail.isError ? <ErrorState error={detail.error} onRetry={() => void detail.refetch()} /> : null}

      {t && member ? (
        <>
          <section className="wo-ticket__who" aria-label="Member">
            <Avatar name={member.name} id={member.id ?? undefined} src={(member.avatar as { thumb?: string } | null)?.thumb} size="sm" />
            <div className="wo-ticket__whotext">
              <strong>{member.name}</strong>
              <span>{member.email}</span>
              <span>
                {t.member_joined_at ? `Member since ${formatDate(t.member_joined_at)}` : "No account (asked without signing in)"} · {t.previous_tickets} earlier{" "}
                {t.previous_tickets === 1 ? "request" : "requests"}
              </span>
            </div>
            {member.id ? (
              <Link className="wo-linkbtn" to={`/admin/members?q=${encodeURIComponent(member.email)}`}>
                View member
              </Link>
            ) : null}
            <StatusChip tone={STATUS_TONE[t.status]}>{ADMIN_STATUS_LABEL[t.status]}</StatusChip>
          </section>

          {t.is_overdue ? (
            <Alert tone="warning" title="Nobody has replied yet">
              This request has waited longer than the service level.
            </Alert>
          ) : null}

          <div className="wo-ticket__controls">
            <Select label="Status" value={t.status} options={STATUS_OPTIONS} disabled={change.isPending} onChange={(e) => change.mutate({ status: e.target.value as never })} />
            <Select
              label="Assign to"
              value={assignee?.id ?? ""}
              options={agentOptions}
              disabled={change.isPending}
              onChange={(e) => change.mutate({ assignee: e.target.value === "" ? null : e.target.value })}
            />
            <Select label="Priority" value={t.priority} options={PRIORITIES} disabled={change.isPending} onChange={(e) => change.mutate({ priority: e.target.value as never })} />
            <Select label="Category" value={t.category} options={CATEGORIES} disabled={change.isPending} onChange={(e) => change.mutate({ category: e.target.value as never })} />
          </div>

          <Thread
            messages={messages}
            fetchLink={async (attachmentId) =>
              (await unwrap(api.GET("/api/v1/admin/support/attachments/{attachment_id}/download", { params: { path: { attachment_id: attachmentId } } }))).url
            }
          />

          <section className="wo-ticket__composer" data-internal={internal} aria-label={internal ? "Add an internal note" : "Reply to the member"}>
            <div className="wo-ticket__composerbar">
              <Switch label="Internal note (only admins see it)" checked={internal} onChange={(e) => setInternal(e.target.checked)} />
              {!internal && (canned.data?.length ?? 0) > 0 ? (
                <Select
                  label="Saved reply"
                  value=""
                  options={[{ value: "", label: "Insert a saved reply…" }, ...(canned.data ?? []).map((c) => ({ value: c.id as string, label: c.title }))]}
                  onChange={(e) => {
                    const chosen = canned.data?.find((c) => c.id === e.target.value);
                    if (chosen) editor.current?.insert(chosen.body);
                  }}
                />
              ) : null}
            </div>
            <RichEditor
              ref={editor}
              label={internal ? "Internal note" : "Reply"}
              placeholder={internal ? "Write a note for other admins. The member never sees it." : "Write your reply. The member is told in the app and by email."}
              onChange={(value, isEmpty) => {
                setHtml(value);
                setEmpty(isEmpty);
              }}
            />
            <Attachments state={files} />
          </section>
        </>
      ) : null}
    </Drawer>
  );
}
