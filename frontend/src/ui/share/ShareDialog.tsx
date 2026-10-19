import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Linkedin, Mail, MessageCircle, Share2, Twitter } from "lucide-react";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Alert, Button, Checkbox, Modal, Textarea } from "../../components";
import { textToHtml } from "../../lib/html";
import { SkeletonRows } from "../blocks";
import { FormError, useSubmit } from "../forms";
import { useToast } from "../Toast";
import { SharedCard } from "./SharedCard";

export type ShareKind = "course" | "event" | "post";

/** The address to share outside the platform: chat apps and social sites draw a preview from it. */
export function shareLink(kind: ShareKind, ref: string): string {
  return `${window.location.origin}/s/${kind}/${encodeURIComponent(ref)}`;
}

const NOUN: Record<ShareKind, string> = { course: "course", event: "event", post: "post" };
// The feed category a shared course or event is filed under.
const CATEGORY = { course: "resource", event: "event" } as const;

/**
 * Share a course, an event or a post: to the community feed (courses and events), or outside the
 * platform by link. Someone who is not a member who opens the link sees a short brief and is
 * invited to join.
 */
export function ShareDialog({
  kind,
  refId,
  onClose,
  team = false,
  feed = true,
}: {
  kind: ShareKind;
  refId: string;
  onClose: () => void;
  /** From the admin console: post with admin options (official marker, pin). The post carries the admin's own name. */
  team?: boolean;
  /** Whether posting to the feed is offered (an admin may only be allowed to share links). */
  feed?: boolean;
}) {
  const client = useQueryClient();
  const toast = useToast();
  const card = useQuery({
    queryKey: ["share-card", kind, refId],
    queryFn: () => unwrap(api.GET("/api/v1/public/share/{kind}/{ref}", { params: { path: { kind, ref: refId } } })),
    retry: false,
  });
  const [message, setMessage] = useState("");
  const [official, setOfficial] = useState(false);
  const [pin, setPin] = useState(false);
  const [copied, setCopied] = useState(false);
  const link = shareLink(kind, refId);
  const toFeed = feed && kind !== "post";

  const post = useSubmit(async () => {
    if (kind === "post") return;
    const body = { category: CATEGORY[kind], body: message.trim() ? textToHtml(message.trim()) : "", share: { kind, ref: refId } };
    if (team) {
      await unwrap(api.POST("/api/v1/admin/posts", { body: { ...body, official, pin, comments_enabled: true, audience_roles: [] } }));
      await client.invalidateQueries({ queryKey: ["admin", "posts"] });
    } else {
      await unwrap(api.POST("/api/v1/posts", { body }));
    }
    await client.invalidateQueries({ queryKey: ["feed"] });
    toast.show(pin ? "Shared to the community feed and pinned" : "Shared to the community feed");
    onClose();
  });

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      toast.show("Link copied");
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      toast.show("Select the link and copy it");
    }
  };
  const native = async () => {
    try {
      await navigator.share({ title: card.data?.title, url: link });
    } catch {
      /* closing the share sheet is not an error */
    }
  };

  const title = card.data?.title ?? "";
  const text = encodeURIComponent(title ? `${title} on WO Community` : "On WO Community");
  const url = encodeURIComponent(link);
  const outside = [
    { label: "WhatsApp", icon: MessageCircle, href: `https://wa.me/?text=${text}%20${url}` },
    { label: "LinkedIn", icon: Linkedin, href: `https://www.linkedin.com/sharing/share-offsite/?url=${url}` },
    { label: "X", icon: Twitter, href: `https://x.com/intent/post?text=${text}&url=${url}` },
    { label: "Email", icon: Mail, href: `mailto:?subject=${text}&body=${text}%0A%0A${url}` },
  ];

  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Share"
      title={`Share this ${NOUN[kind]}`}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>{toFeed ? "Cancel" : "Done"}</Button>
          {toFeed && card.isSuccess ? (
            <Button loading={post.busy} icon={<Share2 size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => void post.run()}>
              Post to the feed
            </Button>
          ) : null}
        </>
      }
    >
      <div className="app-stack">
        {card.isPending ? <SkeletonRows count={2} /> : null}
        {card.isError ? (
          <Alert tone="warning" title={`This ${NOUN[kind]} cannot be shared yet`}>
            {kind === "post" ? "Only posts that every member can see can be shared." : "It can be shared once it is published."}
          </Alert>
        ) : null}
        {card.data ? (
          <>
            <SharedCard card={card.data} link={false} compact />
            {toFeed ? (
              <section className="wo-share__section" aria-labelledby="share-feed">
                <h3 className="wo-share__h" id="share-feed">In the community feed</h3>
                <FormError error={post.error} />
                <Textarea
                  label="Add a few words (optional)"
                  rows={3}
                  maxLength={2000}
                  placeholder={kind === "course" ? "Why is this course worth taking?" : "Who should come along?"}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
                {team ? (
                  <div className="app-stack" style={{ gap: "var(--space-2)" }}>
                    <Checkbox label="Mark as an official announcement" checked={official} onChange={(e) => setOfficial(e.target.checked)} />
                    <Checkbox label="Pin it to the top of the feed" checked={pin} onChange={(e) => setPin(e.target.checked)} />
                  </div>
                ) : null}
                <p className="caption app-muted" style={{ margin: 0 }}>Members see the {NOUN[kind]} as a card they can open{kind === "course" ? " and enrol from" : " and register from"}.</p>
              </section>
            ) : null}
            <section className="wo-share__section" aria-labelledby="share-out">
              <h3 className="wo-share__h" id="share-out">Outside the platform</h3>
              <div className="wo-share__link">
                <label className="wo-visually-hidden" htmlFor="share-link">Link to share</label>
                <input id="share-link" className="wo-input" readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
                <Button variant="secondary" icon={copied ? <Check size={16} strokeWidth={2} aria-hidden="true" /> : <Copy size={16} strokeWidth={1.75} aria-hidden="true" />} onClick={() => void copy()}>
                  {copied ? "Copied" : "Copy"}
                </Button>
              </div>
              <div className="wo-share__apps">
                {outside.map(({ label, icon: Icon, href }) => (
                  <a key={label} className="wo-share__app" href={href} target="_blank" rel="noopener noreferrer">
                    <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
                    {label}
                  </a>
                ))}
                {typeof navigator.share === "function" ? (
                  <button type="button" className="wo-share__app" onClick={() => void native()}>
                    <Share2 size={18} strokeWidth={1.75} aria-hidden="true" />
                    More
                  </button>
                ) : null}
              </div>
              <p className="caption app-muted" style={{ margin: 0 }}>
                People who are not members see a short preview, and are asked to become a member to see it all.
              </p>
            </section>
          </>
        ) : null}
      </div>
    </Modal>
  );
}
