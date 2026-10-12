import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Lightbulb, PartyPopper, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { useCursorList } from "../../api/hooks";
import { messageOf } from "../../api/errors";
import type { components } from "../../api/schema";
import { useAuth } from "../../auth/AuthProvider";
import { Alert, Avatar, Badge, Button, Card, CardText, CardTitle, CardTo, Tabs, Textarea } from "../../components";
import { formatDate, humanise, timeAgo } from "../../lib/format";
import { localLink } from "../../lib/links";
import { textToHtml } from "../../lib/html";
import { EmptyState, Loaded, LoadMore, PageHeader, RichText, SkeletonCards, SkeletonRows } from "../../ui/blocks";
import { FormError, useSubmit } from "../../ui/forms";

type Notification = components["schemas"]["NotificationItem"];
type Item = components["schemas"]["EditorialItem"];
type Reaction = components["schemas"]["ReactionKindEnum"];

export function NotificationsPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const list = useCursorList<Notification, components["schemas"]["NotificationList"]>(["notifications", "list", unreadOnly], (cursor) =>
    unwrap(api.GET("/api/v1/notifications", { params: { query: { limit: 20, ...(unreadOnly ? { unread: true } : {}), ...(cursor ? { cursor } : {}) } } })),
  );
  const unread = list.query.data?.pages[0]?.unread_count ?? 0;
  const mark = useMutation({
    mutationFn: (body: { ids?: string[]; all?: boolean }) => unwrap(api.POST("/api/v1/notifications/read", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });
  return (
    <>
      <PageHeader
        eyebrow="Notifications"
        title="Notifications"
        lead={unread > 0 ? `${unread} unread` : "You are all caught up."}
        actions={unread > 0 ? <Button variant="secondary" loading={mark.isPending} onClick={() => mark.mutate({ all: true })}>Mark all as read</Button> : undefined}
      />
      <div className="app-tabs-scroll">
        <Tabs label="Which notifications" variant="segment" value={unreadOnly ? "unread" : "all"} onChange={(id) => setUnreadOnly(id === "unread")} items={[{ id: "all", label: "All" }, { id: "unread", label: "Unread" }]} />
      </div>
      {list.query.isPending ? <SkeletonRows /> : null}
      {list.query.isError ? <Alert tone="danger" title="We could not load notifications">{messageOf(list.query.error)}</Alert> : null}
      {list.isEmpty ? <EmptyState title={unreadOnly ? "Nothing unread" : "No notifications yet"} icon={<Bell size={22} strokeWidth={1.5} />}>Replies, mentions, mentoring requests and reminders show up here.</EmptyState> : null}
      {list.items.length > 0 ? (
        <ul className="app-list">
          {list.items.map((n) => (
            <li key={n.id}>
              <button
                type="button"
                className="app-list__item"
                style={{ width: "100%", border: 0, textAlign: "left", background: n.read ? "transparent" : "var(--bg-brand-soft)", cursor: "pointer", font: "inherit", color: "inherit" }}
                onClick={() => {
                  if (!n.read) mark.mutate({ ids: [n.id] });
                  navigate(localLink(n.link));
                }}
              >
                <div className="app-list__main">
                  <p className="app-list__title" style={{ fontWeight: n.read ? 400 : 700 }}>{n.title}</p>
                  <p className="body-sm app-muted" style={{ margin: 0 }}>{timeAgo(n.created_at)}</p>
                </div>
                {!n.read ? <Badge variant="info" dot>New</Badge> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}

const REACTIONS: Array<{ kind: Reaction; label: string; icon: typeof ThumbsUp }> = [
  { kind: "like", label: "Like", icon: ThumbsUp },
  { kind: "celebrate", label: "Celebrate", icon: PartyPopper },
  { kind: "insightful", label: "Insightful", icon: Lightbulb },
];

export function NewsPage() {
  const list = useCursorList<Item>(["editorial"], (cursor) =>
    unwrap(api.GET("/api/v1/editorial", { params: { query: { limit: 12, ...(cursor ? { cursor } : {}) } } })),
  );
  return (
    <>
      <PageHeader eyebrow="News" title="Community news" lead="Awards, funding, partnerships and announcements from members and the team." />
      {list.query.isPending ? <SkeletonCards /> : null}
      {list.query.isError ? <Alert tone="danger" title="We could not load news">{messageOf(list.query.error)}</Alert> : null}
      {list.isEmpty ? <EmptyState title="Nothing published yet">Check back soon.</EmptyState> : null}
      <div className="app-grid">
        {list.items.map((item) => (
          <CardTo key={item.id} to={`/app/news/${item.id}`}>
            <Badge variant="operator">{humanise(item.type)}</Badge>
            <CardTitle style={{ marginTop: "var(--space-3)" }}>{item.title}</CardTitle>
            <CardText>{item.excerpt}</CardText>
            <p className="caption app-faint" style={{ margin: "var(--space-3) 0 0" }}>{formatDate(item.published_at)} &middot; {item.comment_count} comments</p>
          </CardTo>
        ))}
      </div>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}

export function NewsStory() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const { me } = useAuth();
  const [draft, setDraft] = useState("");
  const item = useQuery({ queryKey: ["editorial", id], queryFn: () => unwrap(api.GET("/api/v1/editorial/{item_id}", { params: { path: { item_id: id } } })) });
  const comments = useQuery({ queryKey: ["editorial", id, "comments"], queryFn: () => unwrap(api.GET("/api/v1/editorial/{item_id}/comments", { params: { path: { item_id: id } } })) });
  const react = useMutation({
    mutationFn: (kind: Reaction) => {
      const mine = item.data?.my_reactions.includes(kind);
      return mine
        ? unwrap(api.DELETE("/api/v1/editorial/{item_id}/reactions/{kind}", { params: { path: { item_id: id, kind } } }))
        : unwrap(api.POST("/api/v1/editorial/{item_id}/reactions", { params: { path: { item_id: id } }, body: { kind } }));
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["editorial", id] }),
  });
  const add = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/editorial/{item_id}/comments", { params: { path: { item_id: id } }, body: { body: textToHtml(draft) } }));
    setDraft("");
    await client.invalidateQueries({ queryKey: ["editorial", id] });
  });
  const remove = useMutation({
    mutationFn: (commentId: string) => unwrap(api.DELETE("/api/v1/editorial-comments/{comment_id}", { params: { path: { comment_id: commentId } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["editorial", id] }),
  });
  return (
    <Loaded query={item} skeleton={<SkeletonRows />}>
      {(story) => (
        <>
          <PageHeader eyebrow={humanise(story.type)} title={story.title} lead={formatDate(story.published_at)} />
          <div className="wo-container--narrow app-stack app-stack--lg" style={{ maxWidth: 780 }}>
            <Card><RichText html={story.body} /></Card>
            {story.external_url ? <a className="app-link" href={story.external_url} target="_blank" rel="noopener noreferrer nofollow">Read more</a> : null}
            <div className="app-cluster">
              {REACTIONS.map(({ kind, label, icon: Icon }) => (
                <button key={kind} type="button" className="app-react" aria-pressed={story.my_reactions.includes(kind)} aria-label={`${label}, ${story.reactions[kind] ?? 0}`} onClick={() => react.mutate(kind)}>
                  <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
                  {(story.reactions[kind] ?? 0) || label}
                </button>
              ))}
            </div>
            {story.comments_enabled ? (
              <section aria-label="Comments" className="app-stack">
                <h2 className="h4" style={{ margin: 0 }}>Comments</h2>
                {comments.data?.results.map((c) => (
                  <div className="app-comment" key={c.id}>
                    <Avatar name={c.author.name} id={c.author.id} size="sm" />
                    <div className="app-comment__body">
                      <p className="body-sm" style={{ margin: 0 }}><strong>{c.author.name}</strong> <span className="app-faint">{timeAgo(c.created_at)}</span></p>
                      <RichText html={c.body} />
                      {c.mine || me?.roles.includes("super_admin") ? <button type="button" className="app-linklike" onClick={() => remove.mutate(c.id)}>Delete</button> : null}
                    </div>
                  </div>
                ))}
                <form className="app-stack" noValidate onSubmit={(e) => { e.preventDefault(); void add.run(); }}>
                  <FormError error={add.error} />
                  <Textarea label="Add a comment" rows={2} value={draft} onChange={(e) => setDraft(e.target.value)} />
                  <div><Button size="sm" type="submit" loading={add.busy} disabled={!draft.trim()}>Comment</Button></div>
                </form>
              </section>
            ) : null}
            <Link className="app-link" to="/app/news">All news</Link>
          </div>
        </>
      )}
    </Loaded>
  );
}
