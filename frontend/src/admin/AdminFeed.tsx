import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import type { components } from "../api/schema";
import { Badge, Button, Card, Input, Select } from "../components";
import { humanise, timeAgo } from "../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, Skeleton, SkeletonCards, useDocumentTitle } from "../ui/blocks";
import { useToast } from "../ui/Toast";
import { ReasonDialog } from "./dialogs";
import { useOffsetList } from "./useOffsetList";

type Post = components["schemas"]["AdminPost"];
type Comment = components["schemas"]["AdminPostComment"];
type PostAction = "pin" | "unpin" | "feature" | "unfeature" | "hide" | "unhide" | "remove";
type CommentAction = "hide" | "unhide" | "remove";
type Acting = { kind: "post"; post: Post; action: PostAction } | { kind: "comment"; comment: Comment; action: CommentAction } | null;

const CATEGORIES = ["update", "question", "win", "resource", "event", "opportunity"] as const;
const STATES = [
  { value: "", label: "Everything" },
  { value: "live", label: "Showing" },
  { value: "hidden", label: "Hidden" },
  { value: "reported", label: "Has open reports" },
  { value: "pinned", label: "Pinned" },
  { value: "featured", label: "Featured" },
];

const VERB: Record<string, string> = {
  pin: "Pin to the top",
  unpin: "Unpin",
  feature: "Feature",
  unfeature: "Stop featuring",
  hide: "Hide",
  unhide: "Show again",
  remove: "Remove",
};
const DONE: Record<string, string> = {
  pin: "Post pinned",
  unpin: "Post unpinned",
  feature: "Post featured",
  unfeature: "Post no longer featured",
  hide: "Hidden from the feed",
  unhide: "Showing in the feed again",
  remove: "Removed",
};

function Stats() {
  const stats = useQuery({ queryKey: ["admin", "feed", "stats"], queryFn: () => unwrap(api.GET("/api/v1/admin/posts/stats")) });
  const s = stats.data;
  const cells: Array<[string, number | undefined]> = [
    ["Posts", s?.posts],
    ["This week", s?.posts_last_7_days],
    ["Comments", s?.comments],
    ["Reactions", s?.reactions],
    ["Hidden", s?.hidden],
    ["Open reports", s?.open_reports],
  ];
  return (
    <dl className="adm-statstrip" aria-label="Feed totals">
      {cells.map(([label, value]) => (
        <div key={label} className="adm-statstrip__cell">
          <dt>{label}</dt>
          <dd>{value === undefined ? <Skeleton width={36} height={22} /> : value.toLocaleString("en-NG")}</dd>
        </div>
      ))}
    </dl>
  );
}

function Comments({ postId, onAct }: { postId: string; onAct: (c: Comment, a: CommentAction) => void }) {
  const detail = useQuery({ queryKey: ["admin", "feed", "post", postId], queryFn: () => unwrap(api.GET("/api/v1/admin/posts/{post_id}", { params: { path: { post_id: postId } } })) });
  if (detail.isPending) return <Skeleton height={48} />;
  if (detail.isError) return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;
  const comments = detail.data.comments;
  if (comments.length === 0) return <p className="body-sm app-muted" style={{ margin: 0 }}>No comments on this post.</p>;
  return (
    <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {comments.map((c) => (
        <li key={c.id} className="adm-commentrow" data-reply={c.parent_id ? "true" : undefined}>
          <div style={{ minWidth: 0 }}>
            <p className="body-sm" style={{ margin: 0 }}>
              <strong>{c.author.name}</strong> <span className="app-muted">· {timeAgo(c.created_at)}</span>
              {c.hidden ? <> <Badge variant="warning">Hidden</Badge></> : null}
            </p>
            <p className="body" style={{ margin: "2px 0 0", overflowWrap: "anywhere" }}>{c.text}</p>
          </div>
          <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
            {c.hidden ? (
              <Button size="sm" variant="secondary" onClick={() => onAct(c, "unhide")}>Show</Button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => onAct(c, "hide")}>Hide</Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => onAct(c, "remove")}>Remove</Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function AdminFeed() {
  useDocumentTitle("Posts and feed");
  const client = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [category, setCategory] = useState("");
  const [state, setState] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [acting, setActing] = useState<Acting>(null);

  const list = useOffsetList<Post>(["admin", "feed", "posts", term, category, state], (offset, limit) =>
    unwrap(
      api.GET("/api/v1/admin/posts", {
        params: {
          query: {
            limit,
            offset,
            ...(term ? { q: term } : {}),
            ...(category ? { category: category as (typeof CATEGORIES)[number] } : {}),
            ...(state ? { state: state as "live" | "hidden" | "pinned" | "featured" | "reported" } : {}),
          },
        },
      }),
    ),
  );
  const refresh = () => client.invalidateQueries({ queryKey: ["admin", "feed"] });

  const act = async (target: NonNullable<Acting>, reason: string) => {
    if (target.kind === "post") {
      await unwrap(api.POST(`/api/v1/admin/posts/{post_id}/${target.action}`, { params: { path: { post_id: target.post.id } }, body: { reason } }));
      toast.show(DONE[target.action] ?? "Done");
    } else {
      await unwrap(api.POST(`/api/v1/admin/comments/{comment_id}/${target.action}`, { params: { path: { comment_id: target.comment.id } }, body: { reason } }));
      toast.show(target.action === "remove" ? "Comment removed" : target.action === "hide" ? "Comment hidden" : "Comment showing again");
    }
    await refresh();
  };
  const quick = async (post: Post, action: PostAction) => {
    await unwrap(api.POST(`/api/v1/admin/posts/{post_id}/${action}`, { params: { path: { post_id: post.id } }, body: { reason: "" } }));
    toast.show(DONE[action] ?? "Done");
    await refresh();
  };

  return (
    <>
      <PageHeader eyebrow="Content" title="Posts and feed" lead="Everything members have shared. Pin what matters, hide what does not belong, and look inside any conversation." />
      <Stats />
      <form className="app-formgrid" style={{ margin: "var(--space-6) 0", alignItems: "end" }} role="search" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <Input label="Search posts or authors" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="Category" options={[{ value: "", label: "All categories" }, ...CATEGORIES.map((c) => ({ value: c, label: humanise(c) }))]} value={category} onChange={(e) => setCategory(e.target.value)} />
        <Select label="Show" options={STATES} value={state} onChange={(e) => setState(e.target.value)} />
        <div><Button type="submit" variant="secondary">Search</Button></div>
      </form>

      {list.query.isPending ? <SkeletonCards count={3} /> : list.query.isError ? (
        <ErrorState error={list.query.error} onRetry={() => void list.query.refetch()} />
      ) : list.isEmpty ? (
        <EmptyState title="No posts match">Try a different search or filter.</EmptyState>
      ) : (
        <>
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {list.items.map((p) => (
              <li key={p.id}>
                <Card>
                  <div className="app-cluster" style={{ justifyContent: "space-between" }}>
                    <div className="app-cluster">
                      <Badge variant="neutral">{humanise(p.category)}</Badge>
                      {p.pinned ? <Badge variant="info">Pinned</Badge> : null}
                      {p.featured ? <Badge variant="success">Featured</Badge> : null}
                      {p.hidden ? <Badge variant="warning" dot>Hidden</Badge> : null}
                      {p.open_reports > 0 ? <Badge variant="danger" dot>{p.open_reports} open report{p.open_reports === 1 ? "" : "s"}</Badge> : null}
                    </div>
                    <span className="caption app-muted">{timeAgo(p.created_at)}</span>
                  </div>
                  <p className="body-sm" style={{ margin: "var(--space-3) 0 var(--space-1)" }}>
                    <strong>{p.author.name}</strong> <span className="app-muted adm-wrap">{p.author.email}</span>
                  </p>
                  <p className="body" style={{ margin: 0, overflowWrap: "anywhere" }}>{p.excerpt || "No text"}</p>
                  <p className="caption app-muted" style={{ margin: "var(--space-2) 0 0" }}>
                    {p.reaction_count} reaction{p.reaction_count === 1 ? "" : "s"} · {p.comment_count} comment{p.comment_count === 1 ? "" : "s"}
                  </p>
                  <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
                    <Button size="sm" variant="secondary" onClick={() => void quick(p, p.pinned ? "unpin" : "pin")}>{p.pinned ? "Unpin" : "Pin"}</Button>
                    <Button size="sm" variant="secondary" onClick={() => void quick(p, p.featured ? "unfeature" : "feature")}>{p.featured ? "Unfeature" : "Feature"}</Button>
                    <Button size="sm" variant="secondary" onClick={() => setActing({ kind: "post", post: p, action: p.hidden ? "unhide" : "hide" })}>{p.hidden ? "Show again" : "Hide"}</Button>
                    <Button size="sm" variant="ghost" onClick={() => setActing({ kind: "post", post: p, action: "remove" })}>Remove</Button>
                    <Button size="sm" variant="ghost" aria-expanded={open === p.id} onClick={() => setOpen(open === p.id ? null : p.id)}>
                      {open === p.id ? "Hide comments" : `Comments (${p.comment_count})`}
                    </Button>
                  </div>
                  {open === p.id ? (
                    <div style={{ marginTop: "var(--space-4)" }}>
                      <Comments postId={p.id} onAct={(comment, action) => setActing({ kind: "comment", comment, action })} />
                    </div>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
          <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
        </>
      )}

      {acting ? (
        <ReasonDialog
          title={`${VERB[acting.action]} this ${acting.kind}?`}
          confirmLabel={VERB[acting.action] ?? "Confirm"}
          tone={acting.action === "remove" || acting.action === "hide" ? "danger" : "primary"}
          required={acting.action === "remove" || acting.action === "hide"}
          intro={acting.action === "remove" ? "It is gone for everyone, including the author." : acting.action === "hide" ? "It disappears from the feed. The author can still see it." : undefined}
          onConfirm={(reason) => act(acting, reason)}
          onClose={() => setActing(null)}
        />
      ) : null}
    </>
  );
}
