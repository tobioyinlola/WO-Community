import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Flag, Lightbulb, MessageCircle, PartyPopper, Share2, ThumbsUp, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap, unwrapTagged } from "../../api/client";
import { messageOf } from "../../api/errors";
import type { components } from "../../api/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Avatar, Badge, Button, Card, Modal, Select, Tabs, Textarea } from "../../components";
import { htmlToText, textToHtml } from "../../lib/html";
import { humanise, timeAgo } from "../../lib/format";
import { EmptyState, ErrorState, LoadMore, PageHeader, RichText, SkeletonRows } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";
import { ShareDialog } from "../../ui/share/ShareDialog";
import { SharedCard } from "../../ui/share/SharedCard";
import { useToast } from "../../ui/Toast";

type Post = components["schemas"]["Post"];
type CommentT = components["schemas"]["Comment"];
type Category = components["schemas"]["CategoryEnum"];
type Reaction = components["schemas"]["ReactionKindEnum"];
type Scope = "all" | "following" | "mine";

const CATEGORIES: Category[] = ["update", "question", "win", "resource", "event", "opportunity"];
const REACTIONS: Array<{ kind: Reaction; label: string; icon: typeof ThumbsUp }> = [
  { kind: "like", label: "Like", icon: ThumbsUp },
  { kind: "celebrate", label: "Celebrate", icon: PartyPopper },
  { kind: "insightful", label: "Insightful", icon: Lightbulb },
];
const REASONS: Array<{ value: components["schemas"]["ReasonEnum"]; label: string }> = [
  { value: "spam", label: "Spam" },
  { value: "harassment", label: "Harassment" },
  { value: "misinformation", label: "Misinformation" },
  { value: "inappropriate", label: "Inappropriate" },
  { value: "illegal", label: "Illegal" },
  { value: "other", label: "Something else" },
];
const FEED_KEY = ["feed"] as const;

function Composer() {
  const client = useQueryClient();
  const toast = useToast();
  const [category, setCategory] = useState<Category>("update");
  const [text, setText] = useState("");
  const submit = useSubmit(async () => {
    await unwrap(
      api.POST("/api/v1/posts", { body: { category, body: textToHtml(text), images: [] } }),
    );
    setText("");
    toast.show("Posted to the community");
    await client.invalidateQueries({ queryKey: FEED_KEY });
  });
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit.run();
  };
  return (
    <Card>
      <form onSubmit={onSubmit} className="app-stack" noValidate aria-label="Write a post">
        <Textarea
          label="Share with the community"
          placeholder="What are you working on, or what do you need help with?"
          rows={3}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <FormError error={submit.error} />
        <div className="app-cluster" style={{ justifyContent: "space-between" }}>
          <div style={{ minWidth: 200 }}>
            <Select
              label="About"
              value={category}
              onChange={(event) => setCategory(event.target.value as Category)}
              options={CATEGORIES.map((value) => ({ value, label: humanise(value) }))}
            />
          </div>
          <Button type="submit" loading={submit.busy} disabled={!text.trim()}>
            Post
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ReportDialog({ postId, onClose }: { postId: string; onClose: () => void }) {
  const toast = useToast();
  const [reason, setReason] = useState<components["schemas"]["ReasonEnum"]>("spam");
  const [details, setDetails] = useState("");
  const submit = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/posts/{target_id}/reports", {
      params: { path: { target_id: postId } },
      body: { reason, details: details.trim() },
    }));
    toast.show("Thank you. A moderator will take a look.");
    onClose();
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Moderation"
      title="Report this post"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" loading={submit.busy} onClick={() => void submit.run()}>
            Send report
          </Button>
        </>
      }
    >
      <div className="app-stack">
        <FormError error={submit.error} />
        <Select
          label="What is wrong?"
          value={reason}
          onChange={(event) => setReason(event.target.value as typeof reason)}
          options={REASONS}
        />
        <Textarea
          label="Anything we should know? (optional)"
          rows={3}
          value={details}
          onChange={(event) => setDetails(event.target.value)}
        />
      </div>
    </Modal>
  );
}

function Comments({ post }: { post: Post }) {
  const client = useQueryClient();
  const { me } = useAuth();
  const key = ["feed", "comments", post.id] as const;
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<CommentT | null>(null);
  const list = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/v1/posts/{post_id}/comments", { params: { path: { post_id: post.id } } })),
  });
  const add = useSubmit(async () => {
    await unwrap(
      api.POST("/api/v1/posts/{post_id}/comments", {
        params: { path: { post_id: post.id } },
        body: { body: textToHtml(draft), parent_id: replyTo?.id ?? null },
      }),
    );
    setDraft("");
    setReplyTo(null);
    await client.invalidateQueries({ queryKey: key });
    await client.invalidateQueries({ queryKey: FEED_KEY });
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/v1/comments/{comment_id}", { params: { path: { comment_id: id } } })),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: key });
      await client.invalidateQueries({ queryKey: FEED_KEY });
    },
  });

  const row = (c: CommentT | components["schemas"]["Reply"], nested = false) => (
    <div className="app-comment" key={c.id} style={nested ? { marginLeft: "var(--space-8)" } : undefined}>
      <Avatar name={c.author.name} id={c.author.id} src={c.author.photo?.thumb} size="sm" />
      <div className="app-comment__body">
        <p className="body-sm" style={{ margin: 0 }}>
          <strong>{c.author.name}</strong> <span className="app-faint">{timeAgo(c.created_at)}</span>
        </p>
        <RichText html={c.body} />
        <div className="app-cluster" style={{ marginTop: "var(--space-1)" }}>
          {!nested ? (
            <button type="button" className="app-linklike" onClick={() => setReplyTo(c as CommentT)}>
              Reply
            </button>
          ) : null}
          {c.mine || me?.roles.includes("super_admin") ? (
            <button type="button" className="app-linklike" onClick={() => remove.mutate(c.id)}>
              Delete
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );

  return (
    <div className="app-comments">
      {list.isPending ? <SkeletonRows count={2} /> : null}
      {list.isError ? <ErrorState error={list.error} onRetry={() => void list.refetch()} /> : null}
      {list.data?.results.map((c) => (
        <div key={c.id} className="app-stack" style={{ gap: "var(--space-2)" }}>
          {row(c)}
          {c.replies.map((r) => row(r, true))}
        </div>
      ))}
      <form
        className="app-stack"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void add.run();
        }}
      >
        {replyTo ? (
          <p className="body-sm app-muted" style={{ margin: 0 }}>
            Replying to {replyTo.author.name}{" "}
            <button type="button" className="app-linklike" onClick={() => setReplyTo(null)}>
              Cancel
            </button>
          </p>
        ) : null}
        <FormError error={add.error} />
        <Textarea
          label="Add a comment"
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
        <div>
          <Button size="sm" type="submit" loading={add.busy} disabled={!draft.trim()}>
            Comment
          </Button>
        </div>
      </form>
    </div>
  );
}

export function PostCard({ post, startOpen = false }: { post: Post; startOpen?: boolean }) {
  const client = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(startOpen);
  const [reporting, setReporting] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [edit, setEdit] = useState("");

  const react = useMutation({
    mutationFn: async (kind: Reaction) => {
      const mine = post.my_reactions.includes(kind);
      return mine
        ? unwrap(api.DELETE("/api/v1/posts/{target_id}/reactions/{kind}", { params: { path: { target_id: post.id, kind } } }))
        : unwrap(api.POST("/api/v1/posts/{target_id}/reactions", { params: { path: { target_id: post.id } }, body: { kind } }));
    },
    onSuccess: () => client.invalidateQueries({ queryKey: FEED_KEY }),
    onError: (error) => toast.show(messageOf(error)),
  });
  const remove = useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/v1/posts/{post_id}", { params: { path: { post_id: post.id } } })),
    onSuccess: () => {
      toast.show("Post deleted");
      return client.invalidateQueries({ queryKey: FEED_KEY });
    },
  });
  const save = useSubmit(async () => {
    // Edits carry the version they were made from, so two tabs cannot overwrite each other.
    const { etag } = await unwrapTagged(
      api.GET("/api/v1/posts/{post_id}", { params: { path: { post_id: post.id } } }),
    );
    await unwrap(
      api.PATCH("/api/v1/posts/{post_id}", {
        params: { path: { post_id: post.id }, header: { "If-Match": etag } },
        body: { body: textToHtml(edit) },
      }),
    );
    setEditing(false);
    await client.invalidateQueries({ queryKey: FEED_KEY });
  });

  return (
    <Card aria-label={`Post by ${post.author.name}`}>
      <article>
        <div className="app-post__head">
          <Avatar name={post.author.name} id={post.author.id} src={post.author.photo?.thumb} />
          <div className="app-post__who">
            <p className="app-post__author">
              {post.author.slug ? (
                <Link className="app-link" to={`/app/members/${post.author.id}`} style={{ textDecoration: "none" }}>
                  {post.author.name}
                </Link>
              ) : (
                post.author.name
              )}
            </p>
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              {post.author.headline ? `${post.author.headline} · ` : ""}
              {timeAgo(post.created_at)}
              {post.edited_at ? " · edited" : ""}
            </p>
          </div>
          <div className="app-post__badges">
            {post.official ? <Badge variant="solid">Official</Badge> : null}
            {post.pinned ? <Badge variant="solid">Pinned</Badge> : null}
            <Badge variant="mentor">{humanise(post.category)}</Badge>
          </div>
        </div>
        {editing ? (
          <div className="app-stack">
            <FormError error={save.error} />
            <Textarea label="Edit your post" rows={4} value={edit} onChange={(event) => setEdit(event.target.value)} />
            <div className="app-cluster">
              <Button size="sm" loading={save.busy} onClick={() => void save.run()} disabled={!edit.trim()}>
                Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <RichText html={post.body} />
        )}
        {post.shared ? <SharedCard card={post.shared} /> : null}
        {post.shared_gone ? <p className="wo-sharecard wo-sharecard--gone">The course or event shared here is no longer available.</p> : null}
        {post.previews.map((p) => (
          <a key={p.url} className="wo-card" href={p.url} target="_blank" rel="noopener noreferrer nofollow" style={{ display: "block", marginTop: "var(--space-3)", textDecoration: "none", color: "inherit" }}>
            <strong>{p.title || p.url}</strong>
            {p.description ? <p className="body-sm app-muted" style={{ margin: "var(--space-1) 0 0" }}>{p.description}</p> : null}
          </a>
        ))}
        <div className="app-post__bar">
          {REACTIONS.map(({ kind, label, icon: Icon }) => {
            const count = post.reactions[kind] ?? 0;
            return (
              <button
                key={kind}
                type="button"
                className="app-react"
                aria-pressed={post.my_reactions.includes(kind)}
                aria-label={`${label}, ${count}`}
                disabled={react.isPending}
                onClick={() => react.mutate(kind)}
              >
                <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
                {count > 0 ? count : label}
              </button>
            );
          })}
          <button type="button" className="app-react" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            <MessageCircle size={16} strokeWidth={1.5} aria-hidden="true" />
            {post.comment_count > 0 ? `${post.comment_count} comments` : "Comment"}
          </button>
          {post.shareable ? (
            <button type="button" className="app-react" onClick={() => setSharing(true)}>
              <Share2 size={16} strokeWidth={1.5} aria-hidden="true" />
              Share
            </button>
          ) : null}
          <span style={{ marginLeft: "auto" }} className="app-cluster">
            {post.mine ? (
              <>
                <button type="button" className="app-linklike" onClick={() => { setEdit(htmlToText(post.body)); setEditing(true); }}>
                  Edit
                </button>
                <button type="button" className="app-iconbtn" aria-label="Delete post" onClick={() => remove.mutate()}>
                  <Trash2 size={18} strokeWidth={1.5} />
                </button>
              </>
            ) : (
              <button type="button" className="app-iconbtn" aria-label="Report post" onClick={() => setReporting(true)}>
                <Flag size={18} strokeWidth={1.5} />
              </button>
            )}
          </span>
        </div>
        {open && post.comments_enabled ? <Comments post={post} /> : null}
        {open && !post.comments_enabled ? <p className="body-sm app-muted" style={{ margin: "var(--space-3) 0 0" }}>Comments are turned off for this post.</p> : null}
        {reporting ? <ReportDialog postId={post.id} onClose={() => setReporting(false)} /> : null}
        {sharing ? <ShareDialog kind="post" refId={post.id} onClose={() => setSharing(false)} /> : null}
      </article>
    </Card>
  );
}

export default function FeedPage() {
  const [scope, setScope] = useState<Scope>("all");
  const [category, setCategory] = useState<Category | "">("");
  const [sort, setSort] = useState<"newest" | "engaged">("newest");

  const query = useInfiniteQuery({
    queryKey: [...FEED_KEY, scope, category, sort],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/posts", {
          params: { query: { scope, sort, limit: 10, ...(category ? { category } : {}), ...(pageParam ? { cursor: pageParam } : {}) } },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const pages = query.data?.pages ?? [];
  const pinned = scope === "all" && !category ? (pages[0]?.pinned ?? []) : [];
  const posts = pages.flatMap((p) => p.results);

  return (
    <>
      <PageHeader eyebrow="Feed" title="Community feed" lead="Updates, questions and wins from people building across Africa." />
      <div className="app-split">
        <div className="app-stack app-stack--lg">
          <Composer />
          <div className="app-filterbar" style={{ marginBottom: 0 }}>
            <Tabs
              label="Whose posts"
              variant="segment"
              value={scope}
              onChange={(id) => setScope(id as Scope)}
              items={[
                { id: "all", label: "Everyone" },
                { id: "following", label: "Following" },
                { id: "mine", label: "Mine" },
              ]}
            />
            <div style={{ minWidth: 170 }}>
              <Select
                label="Topic"
                value={category}
                onChange={(event) => setCategory(event.target.value as Category | "")}
                options={[{ value: "", label: "All topics" }, ...CATEGORIES.map((c) => ({ value: c, label: humanise(c) }))]}
              />
            </div>
            <div style={{ minWidth: 150 }}>
              <Select
                label="Order"
                value={sort}
                onChange={(event) => setSort(event.target.value as typeof sort)}
                options={[
                  { value: "newest", label: "Newest" },
                  { value: "engaged", label: "Most engaged" },
                ]}
              />
            </div>
          </div>
          {query.isPending ? <SkeletonRows /> : null}
          {query.isError ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
          {pinned.map((post) => (
            <PostCard key={`pin-${post.id}`} post={post} />
          ))}
          {posts.map((post) => (
            <PostCard key={post.id} post={post} />
          ))}
          {query.isSuccess && posts.length === 0 && pinned.length === 0 ? (
            <EmptyState title={scope === "following" ? "Nothing from people you follow yet" : "No posts yet"}>
              {scope === "following"
                ? "Follow members and startups from the directory to see their posts here."
                : "Be the first to share something."}
            </EmptyState>
          ) : null}
          <LoadMore hasNext={Boolean(query.hasNextPage)} loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()} />
        </div>
        <aside className="app-stack" aria-label="Suggestions">
          <FollowSuggestions />
        </aside>
      </div>
    </>
  );
}

function FollowSuggestions() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["follow-suggestions"],
    queryFn: () => unwrap(api.GET("/api/v1/me/follow-suggestions")),
  });
  const follow = useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/follows", { body: { type: "member", id } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["follow-suggestions"] }),
  });
  if (!query.data || query.data.length === 0) return null;
  return (
    <Card>
      <h2 className="h4" style={{ margin: "0 0 var(--space-4)" }}>
        People to follow
      </h2>
      <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {query.data.slice(0, 5).map((s) => (
          <li key={s.id} className="app-cluster" style={{ flexWrap: "nowrap" }}>
            <Avatar name={s.name} id={s.id} src={s.image?.thumb} size="sm" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <Link className="app-link" to={`/app/members/${s.id}`} style={{ textDecoration: "none", fontWeight: 600 }}>
                {s.name}
              </Link>
              <p className="caption app-muted" style={{ margin: 0 }}>
                {s.headline}
              </p>
            </div>
            <Button size="sm" variant="secondary" onClick={() => follow.mutate(s.id)} loading={follow.isPending && follow.variables === s.id}>
              Follow
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** One post on its own page: where a shared link to a post leads a member. */
export function PostPage() {
  const { postId = "" } = useParams();
  const query = useQuery({
    queryKey: [...FEED_KEY, "post", postId],
    queryFn: () => unwrap(api.GET("/api/v1/posts/{post_id}", { params: { path: { post_id: postId } } })),
  });
  return (
    <>
      <PageHeader eyebrow="Feed" title="Post" />
      <div className="app-stack" style={{ maxWidth: 720 }}>
        {query.isPending ? <SkeletonRows /> : null}
        {query.isError ? <ErrorState error={query.error} /> : null}
        {query.data ? <PostCard post={query.data} startOpen /> : null}
        <Link className="app-link" to="/app/feed">Back to the feed</Link>
      </div>
    </>
  );
}
