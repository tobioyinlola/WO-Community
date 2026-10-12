import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { StatusChip } from "../../admin/kit/TableBits";
import { Alert, Button, Textarea } from "../../components";
import { formatDate } from "../../lib/format";
import { Attachments, useAttachments } from "../../support/Attachments";
import { MESSAGE_MAX, STATUS_TONE } from "../../support/constants";
import { Thread, type ThreadMessage } from "../../support/Thread";
import { ErrorState, PageHeader, SkeletonRows, useDocumentTitle } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";

/** One request: the conversation, a reply box, and what to do once it is resolved. */
export function SupportTicketPage() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const [reply, setReply] = useState("");
  const [comment, setComment] = useState("");
  const files = useAttachments();

  const ticket = useQuery({
    queryKey: ["support", "ticket", id],
    queryFn: () => unwrap(api.GET("/api/v1/support/tickets/{ticket_id}", { params: { path: { ticket_id: id } } })),
    refetchInterval: 30_000,
  });
  useDocumentTitle(ticket.data ? `${ticket.data.reference}: ${ticket.data.subject}` : "Support request");

  const refresh = () => Promise.all([client.invalidateQueries({ queryKey: ["support"] }), client.invalidateQueries({ queryKey: ["notifications"] })]);

  const send = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/support/tickets/{ticket_id}/messages", { params: { path: { ticket_id: id } }, body: { message: reply, attachments: files.ids } }));
    setReply("");
    files.reset();
    await refresh();
  });
  const reopen = useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/support/tickets/{ticket_id}/reopen", { params: { path: { ticket_id: id } } })),
    onSuccess: refresh,
  });
  const rate = useMutation({
    mutationFn: (satisfaction: "up" | "down") =>
      unwrap(api.POST("/api/v1/support/tickets/{ticket_id}/feedback", { params: { path: { ticket_id: id } }, body: { satisfaction, comment } })),
    onSuccess: refresh,
  });

  if (ticket.isPending) return <SkeletonRows />;
  if (ticket.isError || !ticket.data) return <ErrorState error={ticket.error} onRetry={() => void ticket.refetch()} />;
  const t = ticket.data;
  const messages = t.messages as unknown as ThreadMessage[];
  const resolved = t.status === "resolved";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send.run();
  };

  return (
    <>
      <PageHeader
        eyebrow={t.reference}
        title={t.subject}
        lead={`${t.category_label} · opened ${formatDate(t.created_at)}`}
        actions={<StatusChip tone={STATUS_TONE[t.status]}>{t.status_label}</StatusChip>}
      />
      <p>
        <Link to="/app/support" className="wo-linkbtn">
          All my requests
        </Link>
      </p>

      {t.status === "awaiting_member" ? (
        <Alert tone="warning" title="Support is waiting for your reply">
          Answer below so we can keep going.
        </Alert>
      ) : null}
      {resolved ? (
        <Alert tone="success" title="This request is resolved">
          {t.can_reopen ? "If it is not sorted, you can reopen it for 14 days after it was resolved." : "It was resolved more than 14 days ago. Start a new request if you still need help."}
          {t.can_reopen ? (
            <div style={{ marginTop: "var(--space-3)" }}>
              <Button variant="secondary" loading={reopen.isPending} onClick={() => reopen.mutate()}>
                Reopen
              </Button>
            </div>
          ) : null}
        </Alert>
      ) : null}
      {reopen.isError ? (
        <Alert tone="danger" title="We could not reopen it">
          {messageOf(reopen.error)}
        </Alert>
      ) : null}

      <Thread
        messages={messages}
        fetchLink={async (attachmentId) => (await unwrap(api.GET("/api/v1/support/attachments/{attachment_id}/download", { params: { path: { attachment_id: attachmentId } } }))).url}
      />

      {resolved ? (
        <section className="wo-feedback" aria-labelledby="fb-title">
          <h2 id="fb-title" className="wo-feedback__title">
            Was this helpful?
          </h2>
          {t.satisfaction ? <p role="status">Thank you for telling us{t.satisfaction === "up" ? ": glad it helped." : ": we are sorry it did not help."}</p> : null}
          <Textarea label="Anything to add? (optional)" rows={2} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
          <div className="wo-feedback__actions">
            <Button variant="secondary" icon={<ThumbsUp size={16} strokeWidth={1.5} />} aria-pressed={t.satisfaction === "up"} loading={rate.isPending} onClick={() => rate.mutate("up")}>
              Yes
            </Button>
            <Button variant="secondary" icon={<ThumbsDown size={16} strokeWidth={1.5} />} aria-pressed={t.satisfaction === "down"} loading={rate.isPending} onClick={() => rate.mutate("down")}>
              No
            </Button>
          </div>
        </section>
      ) : (
        <form className="wo-form wo-reply" onSubmit={submit} noValidate>
          <Textarea
            label="Your reply"
            rows={5}
            value={reply}
            maxLength={MESSAGE_MAX}
            onChange={(e) => setReply(e.target.value)}
            hint="Replies are read inside WO Community. Please do not answer the notification email."
            required
          />
          <Attachments state={files} />
          <FormError error={send.error} listFields />
          <div>
            <Button type="submit" loading={send.busy || files.busy} disabled={reply.trim() === ""}>
              Send reply
            </Button>
          </div>
        </form>
      )}
    </>
  );
}
