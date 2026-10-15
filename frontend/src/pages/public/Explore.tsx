import { useQuery } from "@tanstack/react-query";
import { MapPin } from "lucide-react";
import { useSearchParams, Link } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { Avatar, Badge, Card, CardText, CardTitle, Tabs } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { EmptyState, Loaded, PageHeader, SkeletonCards } from "../../ui/blocks";

const TABS = [
  { id: "startups", label: "Startups" },
  { id: "founders", label: "Members" },
  { id: "jobs", label: "Jobs" },
  { id: "events", label: "Events" },
  { id: "courses", label: "Courses" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function JoinPrompt() {
  return (
    <p className="body app-muted" style={{ marginTop: "var(--space-8)" }}>
      Want the full picture, with contact details and introductions?{" "}
      <Link className="app-link" to="/register">
        Request access
      </Link>
      .
    </p>
  );
}

/** Visitors see a preview of ten; the rest of the directory is for members. */
function SeeMore({ what }: { what: "startups" | "members" }) {
  return (
    <section className="explore-more wo-on-brand" aria-label={`See all ${what}`}>
      <div>
        <h2 className="h3" style={{ margin: 0 }}>
          You&rsquo;re seeing 10 {what}. Join to see them all.
        </h2>
        <p className="body" style={{ margin: "var(--space-2) 0 0", color: "var(--text-on-brand-muted)" }}>
          Members can browse every {what === "startups" ? "startup" : "member"} in the community, filter the directory and
          ask for introductions.
        </p>
      </div>
      <div className="app-cluster">
        <Link className="wo-btn wo-btn--accent" to="/register">
          Request access
        </Link>
        <Link className="wo-btn wo-btn--on-brand" to="/login">
          Sign in
        </Link>
      </div>
    </section>
  );
}

function Startups() {
  const query = useQuery({
    queryKey: ["public", "startups"],
    queryFn: () => unwrap(api.GET("/api/v1/public/startups", { params: { query: { limit: 10 } } })),
  });
  return (
    <Loaded
      query={query}
      skeleton={<SkeletonCards />}
      isEmpty={(d) => d.results.length === 0}
      empty={<EmptyState title="No startups listed yet">Startups appear here when their founders choose to be found.</EmptyState>}
    >
      {(data) => (
        <>
          <div className="app-grid">
            {data.results.map((s) => (
              <Card key={s.slug}>
                <div className="app-cluster" style={{ marginBottom: "var(--space-3)" }}>
                  <Badge variant="operator">{s.sector.name}</Badge>
                  <Badge>{s.stage.name}</Badge>
                </div>
                <CardTitle>{s.name}</CardTitle>
                <CardText>{s.pitch}</CardText>
                <ul className="app-meta" style={{ marginTop: "var(--space-3)" }}>
                  <li>
                    <MapPin size={16} strokeWidth={1.5} aria-hidden="true" />
                    {s.city}, {s.country}
                  </li>
                </ul>
              </Card>
            ))}
          </div>
          {data.has_more ? <SeeMore what="startups" /> : null}
        </>
      )}
    </Loaded>
  );
}

function Founders() {
  const query = useQuery({
    queryKey: ["public", "founders"],
    queryFn: () => unwrap(api.GET("/api/v1/public/founders", { params: { query: { limit: 10 } } })),
  });
  return (
    <Loaded
      query={query}
      skeleton={<SkeletonCards />}
      isEmpty={(d) => d.results.length === 0}
      empty={<EmptyState title="No members listed yet">Members who make their profile public appear here.</EmptyState>}
    >
      {(data) => (
        <>
          <div className="app-grid">
            {data.results.map((f) => (
              <Card key={f.slug}>
                <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
                  <Avatar name={f.full_name} id={f.slug} src={f.photo?.thumb} shape="arch" size="lg" />
                  <div>
                    <CardTitle>{f.full_name}</CardTitle>
                    <CardText>{f.headline}</CardText>
                    <div className="app-cluster" style={{ marginTop: "var(--space-3)" }}>
                      {f.badges.map((b) => (
                        <Badge key={b} variant="founder">
                          {humanise(b)}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
          {data.has_more ? <SeeMore what="members" /> : null}
        </>
      )}
    </Loaded>
  );
}

function Jobs() {
  const query = useQuery({
    queryKey: ["public", "jobs"],
    queryFn: () => unwrap(api.GET("/api/v1/public/jobs", { params: { query: { limit: 30 } } })),
  });
  return (
    <Loaded
      query={query}
      isEmpty={(d) => d.results.length === 0}
      empty={<EmptyState title="No open roles right now">New roles are posted by members every week.</EmptyState>}
    >
      {(data) => (
        <ul className="app-list">
          {data.results.map((j) => (
            <li className="app-list__item" key={j.slug}>
              <div className="app-list__main">
                <p className="app-list__title">{j.title}</p>
                <ul className="app-meta">
                  <li>{j.organisation}</li>
                  <li>{j.location || "Location not set"}</li>
                  {j.remote ? <li>Remote friendly</li> : null}
                </ul>
              </div>
              <Badge variant="pro">{humanise(j.type)}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Loaded>
  );
}

function Events() {
  const query = useQuery({
    queryKey: ["public", "events"],
    queryFn: () => unwrap(api.GET("/api/v1/public/events", { params: { query: { limit: 30 } } })),
  });
  return (
    <Loaded
      query={query}
      isEmpty={(d) => d.results.length === 0}
      empty={<EmptyState title="No events announced">Demo days, workshops and meetups appear here.</EmptyState>}
    >
      {(data) => (
        <ul className="app-list">
          {data.results.map((e) => (
            <li className="app-list__item" key={e.slug}>
              <div className="app-list__main">
                <p className="app-list__title">{e.title}</p>
                <ul className="app-meta">
                  <li>{formatDate(e.starts_at)}</li>
                  {e.location ? <li>{e.location}</li> : null}
                </ul>
              </div>
              <Badge variant="investor">{humanise(e.type)}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Loaded>
  );
}

function Courses() {
  const query = useQuery({
    queryKey: ["public", "courses"],
    queryFn: () => unwrap(api.GET("/api/v1/public/courses", { params: { query: { limit: 30 } } })),
  });
  return (
    <Loaded
      query={query}
      skeleton={<SkeletonCards />}
      isEmpty={(d) => d.results.length === 0}
      empty={<EmptyState title="No free courses yet">Members get the whole catalogue.</EmptyState>}
    >
      {(data) => (
        <div className="app-grid">
          {data.results.map((c) => (
            <Card key={c.slug}>
              <div className="app-cluster" style={{ marginBottom: "var(--space-3)" }}>
                <Badge variant="mentor">{humanise(c.level)}</Badge>
                <Badge>{c.category}</Badge>
              </div>
              <CardTitle>{c.title}</CardTitle>
              <CardText>{c.excerpt}</CardText>
              <ul className="app-meta" style={{ marginTop: "var(--space-3)" }}>
                <li>{c.instructor}</li>
                <li>{c.lesson_count} lessons</li>
              </ul>
            </Card>
          ))}
        </div>
      )}
    </Loaded>
  );
}

const VIEWS: Record<TabId, () => JSX.Element> = {
  startups: Startups,
  founders: Founders,
  jobs: Jobs,
  events: Events,
  courses: Courses,
};

export function Explore() {
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "startups") as TabId;
  const View = VIEWS[tab];
  return (
    <div className="wo-container" style={{ padding: "var(--space-12) var(--page-margin) var(--space-24)" }}>
      <PageHeader
        eyebrow="Explore"
        title="See what the community is building"
        lead="A public window into WO Community. Members see much more."
      />
      <div className="app-tabs-scroll">
        <Tabs
          label="What to explore"
          value={tab}
          onChange={(id) => setParams({ tab: id }, { replace: true })}
          items={TABS.map((t) => ({ id: t.id, label: t.label }))}
        />
      </div>
      <View />
      <JoinPrompt />
    </div>
  );
}
