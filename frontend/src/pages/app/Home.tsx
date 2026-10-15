import { useAuth } from "../../auth/AuthProvider";
import { permissionsFor } from "../../admin/permissions";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Circle, MessageCircle, Rocket, ThumbsUp } from "lucide-react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { ReferralCard } from "../../referrals/ReferralCard";
import { Alert, Avatar, Badge, Card, CardText, CardTitle, CardTo, StatTile } from "../../components";
import { formatDate, formatTime, humanise, timeAgo } from "../../lib/format";
import { nameFromEmail, welcomeTitle } from "../../lib/greeting";
import { PageHeader, RichText, Section, Skeleton } from "../../ui/blocks";
import { BannerTicker } from "../../ui/BannerTicker";

const CHECKLIST: Record<string, { label: string; to: string }> = {
  complete_profile: { label: "Complete your profile", to: "/app/me" },
  add_startup: { label: "Add your startup", to: "/app/startups/new" },
  add_traction: { label: "Add your traction", to: "/app/me" },
  set_notification_preferences: { label: "Choose what we email you", to: "/app/settings" },
};

/** Traction belongs to a startup, so that step opens the startup's traction section, or asks for a startup first. */
function stepFor(key: string, startupId: string | undefined): { label: string; to: string } {
  const step = CHECKLIST[key] ?? { label: humanise(key), to: "/app/me" };
  if (key === "add_traction") return { ...step, to: startupId ? `/app/startups/${startupId}/edit#traction` : "/app/startups/new" };
  return step;
}

const REACTION_WORDS: Record<string, string> = { like: "liked", celebrate: "celebrated", insightful: "found insightful" };

function Quiet({ children }: { children: string }) {
  return <p className="body app-muted" style={{ margin: 0 }}>{children}</p>;
}

export default function Home() {
  const profile = useQuery({ queryKey: ["me", "profile"], queryFn: () => unwrap(api.GET("/api/v1/me/profile")) });
  const onboarding = useQuery({ queryKey: ["me", "onboarding"], queryFn: () => unwrap(api.GET("/api/v1/me/onboarding")) });
  const events = useQuery({ queryKey: ["home", "events"], queryFn: () => unwrap(api.GET("/api/v1/events", { params: { query: { when: "upcoming", limit: 8 } } })) });
  const sessions = useQuery({ queryKey: ["home", "sessions"], queryFn: () => unwrap(api.GET("/api/v1/sessions", { params: { query: { state: "upcoming", limit: 2 } } })) });
  const posts = useQuery({ queryKey: ["home", "posts"], queryFn: () => unwrap(api.GET("/api/v1/posts", { params: { query: { limit: 3 } } })) });
  // Comments and reactions show up here without a reload, so the dashboard feels alive.
  const activity = useQuery({
    queryKey: ["home", "activity"],
    queryFn: () => unwrap(api.GET("/api/v1/feed/activity", { params: { query: { limit: 8 } } })),
    refetchInterval: 30_000,
  });
  const myStartups = useQuery({ queryKey: ["me", "startups"], queryFn: () => unwrap(api.GET("/api/v1/me/startups")) });
  const stats = useQuery({ queryKey: ["me", "stats"], queryFn: () => unwrap(api.GET("/api/v1/me/stats")) });
  const { me } = useAuth();
  const ventures = useQuery({ queryKey: ["toolkit", "ventures"], enabled: permissionsFor(me?.roles ?? []).has("toolkit.use"), queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures")) });

  const isMentor = me?.roles.includes("mentor") ?? false;
  const mentorSetup = useQuery({ queryKey: ["me", "mentor", "settings"], enabled: isMentor, retry: false, queryFn: () => unwrap(api.GET("/api/v1/me/mentor/settings")) });
  const needsSchedule = isMentor && mentorSetup.data !== undefined && mentorSetup.data.weekly.length === 0;

  // A cancelled event is not coming up. Ask for a few extra so three remain after leaving those out.
  const comingUp = (events.data?.results ?? []).filter((e) => e.status !== "cancelled").slice(0, 3);
  const first = (profile.data?.full_name ?? "").split(" ")[0];
  const todo = onboarding.data?.items.filter((i) => !i.done) ?? [];
  const score = onboarding.data?.profile_completeness.score ?? 0;

  return (
    <>
      <BannerTicker />
      <PageHeader eyebrow="Home" title={welcomeTitle(first || nameFromEmail(me?.email))} lead="Here is what is happening and what to do next ✨" />

      {needsSchedule ? (
        <Alert tone="info" title="Set up your availability">
          You are an approved mentor, but nobody can book you yet. Choose the times you are free and what you charge, which takes a couple of minutes.{" "}
          <Link className="wo-linkbtn" to="/app/settings/mentorship">
            Set up your availability
          </Link>
        </Alert>
      ) : null}

      {onboarding.data && !onboarding.data.complete ? (
        <Card variant="brand">
          <div className="app-split app-split--even">
            <div>
              <span className="wo-eyebrow">Get started</span>
              <CardTitle style={{ marginTop: "var(--space-3)" }}>Finish setting up</CardTitle>
              <CardText>A complete profile gets you found, and gets you introductions.</CardText>
              <div className="app-meter" style={{ marginTop: "var(--space-4)", background: "var(--border-on-brand)" }} role="progressbar" aria-valuenow={score} aria-valuemin={0} aria-valuemax={100} aria-label="Profile strength">
                <span style={{ width: `${score}%`, background: "var(--text-highlight)" }} />
              </div>
              <p className="caption" style={{ margin: "var(--space-1) 0 0", color: "var(--text-on-brand-muted)" }}>{score}% of your profile</p>
            </div>
            <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {onboarding.data.items.map((item) => {
                const step = stepFor(item.key, myStartups.data?.[0]?.id);
                const Icon = item.done ? CheckCircle2 : Circle;
                return (
                  <li key={item.key}>
                    {item.done ? (
                      <span className="app-cluster" style={{ flexWrap: "nowrap", color: "var(--text-on-brand-muted)" }}><Icon size={20} strokeWidth={1.5} aria-hidden="true" />{step.label}</span>
                    ) : (
                      <Link to={step.to} className="app-cluster" style={{ flexWrap: "nowrap", color: "var(--text-on-brand)", textDecoration: "none", fontWeight: 600 }}>
                        <Icon size={20} strokeWidth={1.5} aria-hidden="true" />{step.label}<ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" style={{ marginLeft: "auto" }} />
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        </Card>
      ) : onboarding.data?.complete && stats.data ? (
        <YourActivity stats={stats.data} />
      ) : null}

      <div className="app-grid" style={{ marginTop: "var(--space-8)" }}>
        <StatTile variant="brand" label="Profile strength" value={`${score}%`} delta={todo.length ? `${todo.length} steps left` : "All set"} />
        <StatTile label="Upcoming events" value={String(comingUp.length)} delta="in the next weeks" />
        <StatTile label="Sessions booked" value={String(sessions.data?.results.length ?? 0)} delta="coming up" />
      </div>

      <div className="app-split" style={{ marginTop: "var(--space-12)" }}>
        <div className="app-stack app-stack--lg">
          <Section title="From the feed" action={<Link className="app-linklike" to="/app/feed">Open the feed</Link>}>
            {posts.isPending ? <Skeleton height={80} /> : posts.data && posts.data.results.length > 0 ? (
              <div className="app-stack">
                {posts.data.results.map((p) => (
                  <Card key={p.id}>
                    <div className="app-post__head">
                      <Avatar name={p.author.name} id={p.author.id} src={p.author.photo?.thumb} size="sm" />
                      <div>
                        <p className="app-post__author">{p.author.name}</p>
                        <p className="caption app-muted" style={{ margin: 0 }}>{timeAgo(p.created_at)}</p>
                      </div>
                      <Badge variant="mentor" className="">{humanise(p.category)}</Badge>
                    </div>
                    <RichText html={p.body} />
                    <p className="caption app-muted" style={{ margin: "var(--space-3) 0 0", display: "flex", gap: "var(--space-4)" }}>
                      <span title="Reactions" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><ThumbsUp size={14} strokeWidth={1.5} aria-hidden="true" />{p.reaction_count}<span className="wo-visually-hidden"> reactions</span></span>
                      <span title="Comments" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><MessageCircle size={14} strokeWidth={1.5} aria-hidden="true" />{p.comment_count}<span className="wo-visually-hidden"> comments</span></span>
                    </p>
                  </Card>
                ))}
              </div>
            ) : <Quiet>The feed is quiet. Share something to get it going.</Quiet>}
          </Section>
          <Section title="Latest activity" action={<Link className="app-linklike" to="/app/feed">Join in</Link>}>
            {activity.isPending ? <Skeleton height={80} /> : activity.data && activity.data.length > 0 ? (
              <ul className="app-list">
                {activity.data.map((a) => (
                  <li key={`${a.kind}-${a.id}`}>
                    <Link className="app-list__item" to="/app/feed">
                      <Avatar name={a.actor.name} id={a.actor.id} src={a.actor.photo?.thumb} size="sm" />
                      <div className="app-list__main">
                        <p className="app-list__title">
                          {a.mine ? "You" : a.actor.name}{" "}
                          {a.kind === "comment" ? "commented on" : `${REACTION_WORDS[a.detail] ?? "reacted to"}`}{" "}
                          {a.post_author}&rsquo;s post
                        </p>
                        <p className="body-sm app-muted" style={{ margin: 0 }}>
                          {a.kind === "comment" && a.detail ? `\u201C${a.detail}\u201D` : a.post_excerpt}
                        </p>
                      </div>
                      <span className="caption app-muted">{timeAgo(a.created_at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <Quiet>No comments or reactions yet.</Quiet>}
          </Section>
        </div>
        <aside className="app-stack app-stack--lg">
          <Section title="Coming up" action={<Link className="app-linklike" to="/app/events">All events</Link>}>
            {comingUp.length > 0 ? (
              <ul className="app-list">
                {comingUp.map((e) => (
                  <li key={e.id}>
                    <Link className="app-list__item" to={`/app/events/${e.id}`}>
                      <div className="app-list__main">
                        <p className="app-list__title">{e.title}</p>
                        <p className="body-sm app-muted" style={{ margin: 0 }}>{formatDate(e.starts_at)}, {formatTime(e.starts_at)}</p>
                      </div>
                      {e.registered ? <Badge variant="success" dot>Going</Badge> : null}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <Quiet>No events are scheduled yet.</Quiet>}
          </Section>
          <Section title="Your referrals">
            <ReferralCard />
          </Section>
          <Section title="Build your venture">
            <CardTo to="/app/launch" variant="accent">
              <span className="app-tile" style={{ marginBottom: "var(--space-3)" }}><Rocket size={22} strokeWidth={1.5} aria-hidden="true" /></span>
              <CardTitle>Launch toolkit</CardTitle>
              <CardText>
                {ventures.data && ventures.data.results.length > 0
                  ? `Continue with ${ventures.data.results[0]?.name ?? "your venture"}.`
                  : "Score your idea, write the plan, model the numbers and build the deck."}
              </CardText>
            </CardTo>
          </Section>
        </aside>
      </div>
    </>
  );
}

type MyStats = components["schemas"]["MyStats"];

/** Once setup is done, the space the checklist used shows the member's own numbers. */
function YourActivity({ stats }: { stats: MyStats }) {
  const recent = (n: number) => (n > 0 ? `+${n} in ${stats.trend_days} days` : `none new in ${stats.trend_days} days`);
  return (
    <Section title="Your activity">
      <div className="app-grid">
        <StatTile variant="brand" label="Followers" value={String(stats.followers)} delta={recent(stats.followers_recent)} />
        <StatTile label="Reactions on your posts" value={String(stats.reactions_received)} delta={recent(stats.reactions_recent)} />
        <StatTile label="Comments on your posts" value={String(stats.comments_received)} delta={recent(stats.comments_recent)} />
        <StatTile label="Posts shared" value={String(stats.posts)} delta="in the feed" />
        <StatTile label="Courses" value={String(stats.courses_completed)} delta={`completed, ${stats.courses_in_progress} in progress`} />
        <StatTile label="Certificates" value={String(stats.certificates)} delta="earned" />
        <StatTile label="Mentoring sessions" value={String(stats.sessions_completed)} delta={`completed, ${stats.sessions_upcoming} coming up`} />
        <StatTile label="Events" value={String(stats.events_attended)} delta={`attended, ${stats.events_upcoming} coming up`} />
      </div>
    </Section>
  );
}
