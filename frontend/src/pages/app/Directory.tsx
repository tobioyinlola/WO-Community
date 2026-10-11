import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe, Linkedin, MapPin } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { useCountries } from "../../api/reference";
import type { components } from "../../api/schema";
import { Alert, Avatar, Badge, Button, Card, CardText, CardTitle, CardTo, Input, Tabs } from "../../components";
import { humanise } from "../../lib/format";
import { EmptyState, Loaded, PageHeader, SkeletonCards, SkeletonRows } from "../../ui/blocks";

type Hit = components["schemas"]["SearchHit"];

const GROUPS: Array<{ key: keyof components["schemas"]["SearchResult"]; label: string; to: (h: Hit) => string }> = [
  { key: "members", label: "Members", to: (h) => `/app/members/${h.id}` },
  { key: "startups", label: "Startups", to: (h) => `/app/startups/${h.id}` },
  { key: "mentors", label: "Mentors", to: (h) => `/app/mentors/${h.id}` },
  { key: "jobs", label: "Jobs", to: (h) => `/app/jobs/${h.id}` },
  { key: "events", label: "Events", to: (h) => `/app/events/${h.id}` },
  { key: "courses", label: "Courses", to: (h) => `/app/learn/${h.id}` },
  { key: "news", label: "News", to: (h) => `/app/news/${h.id}` },
];

export default function DirectoryPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [draft, setDraft] = useState(q);
  const [only, setOnly] = useState("all");

  const search = useQuery({
    queryKey: ["search", q],
    queryFn: () => unwrap(api.GET("/api/v1/search", { params: { query: { q, limit: 12 } } })),
    enabled: q.trim().length > 0,
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setParams(draft.trim() ? { q: draft.trim() } : {});
  };
  const groups = GROUPS.filter((g) => (search.data?.[g.key]?.length ?? 0) > 0);
  const shown = only === "all" ? groups : groups.filter((g) => g.key === only);

  return (
    <>
      <PageHeader eyebrow="Directory" title="Find people and startups" lead="Search members, startups, mentors, jobs, events and courses in one place." />
      <form className="app-filterbar" role="search" onSubmit={submit}>
        <div className="app-filterbar__grow">
          <Input label="Search" placeholder="A name, a company, a skill" value={draft} onChange={(e) => setDraft(e.target.value)} />
        </div>
        <Button type="submit" size="lg" style={{ alignSelf: "flex-end" }}>Search</Button>
      </form>
      {!q.trim() ? <Browse /> : null}
      {q.trim() && search.isPending ? <SkeletonCards count={3} /> : null}
      {search.isError ? <Alert tone="danger" title="Search did not work">{messageOf(search.error)}</Alert> : null}
      {search.isSuccess && groups.length === 0 ? <EmptyState title={`Nothing found for "${q}"`}>Try a shorter word or check the spelling.</EmptyState> : null}
      {groups.length > 1 ? (
        <div className="app-tabs-scroll">
          <Tabs label="Narrow the results" variant="segment" value={only} onChange={setOnly} items={[{ id: "all", label: "All" }, ...groups.map((g) => ({ id: g.key, label: g.label }))]} />
        </div>
      ) : null}
      {shown.map((group) => (
        <section key={group.key} className="app-section" style={{ marginTop: 0, marginBottom: "var(--space-8)" }} aria-label={group.label}>
          <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>{group.label}</h2>
          <div className="app-grid">
            {(search.data?.[group.key] ?? []).map((hit) => (
              <CardTo key={hit.id} to={group.to(hit)}>
                <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
                  {group.key === "members" || group.key === "mentors" ? <Avatar name={hit.title} id={hit.id} size="md" /> : null}
                  <div style={{ minWidth: 0 }}>
                    <CardTitle>{hit.title}</CardTitle>
                    <CardText>{hit.subtitle}</CardText>
                  </div>
                </div>
              </CardTo>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}

/** With nothing typed, offer a way in: the people the member might want to know. */
function Browse() {
  const suggestions = useQuery({ queryKey: ["follow-suggestions"], queryFn: () => unwrap(api.GET("/api/v1/me/follow-suggestions")) });
  const mine = useQuery({ queryKey: ["me", "startups"], queryFn: () => unwrap(api.GET("/api/v1/me/startups")) });
  return (
    <div className="app-stack app-stack--lg">
      <Loaded query={suggestions} skeleton={<SkeletonCards count={3} />} isEmpty={(d) => d.length === 0} empty={<EmptyState title="Start with a search">Type a name, a company or a skill above.</EmptyState>}>
        {(items) => (
          <section aria-label="People you may know">
            <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>People you may want to know</h2>
            <div className="app-grid">
              {items.map((s) => (
                <CardTo key={s.id} to={`/app/members/${s.id}`}>
                  <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
                    <Avatar name={s.name} id={s.id} src={s.image?.thumb} shape="arch" size="lg" />
                    <div>
                      <CardTitle>{s.name}</CardTitle>
                      <CardText>{s.headline}</CardText>
                      <p className="caption app-muted" style={{ margin: "var(--space-2) 0 0" }}>{s.reasons.join(". ")}</p>
                    </div>
                  </div>
                </CardTo>
              ))}
            </div>
          </section>
        )}
      </Loaded>
      {mine.data && mine.data.length > 0 ? (
        <section aria-label="Your startups">
          <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Your startups</h2>
          <div className="app-grid">
            {mine.data.map((s) => (
              <CardTo key={s.id} to={`/app/startups/${s.id}`}>
                <CardTitle>{s.name}</CardTitle>
                <CardText>{s.pitch}</CardText>
              </CardTo>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

export function MemberPage() {
  const { id = "" } = useParams();
  const client = useQueryClient();
  const countries = useCountries();
  const query = useQuery({ queryKey: ["members", id], queryFn: () => unwrap(api.GET("/api/v1/members/{user_id}", { params: { path: { user_id: id } } })) });
  const following = useQuery({ queryKey: ["me", "following"], queryFn: () => unwrap(api.GET("/api/v1/me/following")) });
  const isFollowing = Boolean(following.data?.results.some((m) => m.type === "member" && m.id === id));
  const follow = useMutation({
    mutationFn: () =>
      isFollowing
        ? unwrap(api.DELETE("/api/v1/follows/{kind}/{target_id}", { params: { path: { kind: "member", target_id: id } } }))
        : unwrap(api.POST("/api/v1/follows", { body: { type: "member", id } })),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["me", "following"] });
      await client.invalidateQueries({ queryKey: ["follow-suggestions"] });
    },
  });
  const country = (code?: string) => countries.data?.find((c) => c.value === code)?.label ?? code;

  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(p) => (
        <>
          <PageHeader eyebrow="Member" title={p.full_name ?? "Member"} lead={p.headline} actions={<Button variant={isFollowing ? "secondary" : "primary"} loading={follow.isPending} onClick={() => follow.mutate()}>{isFollowing ? "Following" : "Follow"}</Button>} />
          <div className="app-split">
            <Card>
              <div className="app-stack app-stack--lg">
                <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
                  <Avatar name={p.full_name ?? "Member"} id={p.user_id} src={p.photo?.large} shape="arch" size="xl" />
                  <ul className="app-meta" style={{ flexDirection: "column", gap: "var(--space-2)" }}>
                    {p.city || p.country ? <li><MapPin size={16} strokeWidth={1.5} aria-hidden="true" />{[p.city, country(p.country)].filter(Boolean).join(", ")}</li> : null}
                    {p.linkedin_url ? <li><Linkedin size={16} strokeWidth={1.5} aria-hidden="true" /><a className="app-link" href={p.linkedin_url} target="_blank" rel="noopener noreferrer nofollow">LinkedIn</a></li> : null}
                    {p.website_url ? <li><Globe size={16} strokeWidth={1.5} aria-hidden="true" /><a className="app-link" href={p.website_url} target="_blank" rel="noopener noreferrer nofollow">Website</a></li> : null}
                  </ul>
                </div>
                {p.bio ? <p className="body" style={{ margin: 0 }}>{p.bio}</p> : null}
                {p.skills && p.skills.length > 0 ? (
                  <div className="app-cluster">{p.skills.map((s) => <Badge key={s.slug} variant="operator">{s.name}</Badge>)}</div>
                ) : null}
              </div>
            </Card>
            <aside className="app-stack">
              {p.open_to && p.open_to.length > 0 ? (
                <Card>
                  <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Open to</h2>
                  <ul className="site-bullets">{p.open_to.map((o) => <li key={o}><span className="wo-plus" aria-hidden="true" /><span className="body">{humanise(o)}</span></li>)}</ul>
                </Card>
              ) : null}
              {p.badges.map((b) => <Badge key={b} variant="success" dot>{humanise(b)}</Badge>)}
            </aside>
          </div>
        </>
      )}
    </Loaded>
  );
}

export function StartupPage() {
  const { id = "" } = useParams();
  const query = useQuery({ queryKey: ["startups", id], queryFn: () => unwrap(api.GET("/api/v1/startups/{startup_id}", { params: { path: { startup_id: id } } })) });
  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(s) => (
        <>
          <PageHeader eyebrow="Startup" title={s.name ?? "Startup"} lead={s.pitch} actions={s.owner_id ? <Link className="wo-btn wo-btn--secondary" to={`/app/startups/${s.id}/edit`}>Edit</Link> : undefined} />
          <div className="app-split">
            <Card>
              <div className="app-stack app-stack--lg">
                <div className="app-cluster">
                  {s.sector ? <Badge variant="operator">{s.sector.name}</Badge> : null}
                  {s.stage ? <Badge>{s.stage.name}</Badge> : null}
                  {s.featured ? <Badge variant="solid">Featured</Badge> : null}
                </div>
                {s.description ? <p className="body" style={{ margin: 0 }}>{s.description}</p> : null}
                {s.traction.length > 0 ? (
                  <div>
                    <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Traction</h2>
                    <dl className="app-kv">{s.traction.map((t, i) => <><dt key={`k${i}`}>{humanise(String(t.kind))}</dt><dd key={`v${i}`}>{String(t.value ?? "")}</dd></>)}</dl>
                  </div>
                ) : null}
              </div>
            </Card>
            <aside className="app-stack">
              <Card>
                <ul className="app-meta" style={{ flexDirection: "column", gap: "var(--space-2)" }}>
                  {s.city || s.country ? <li><MapPin size={16} strokeWidth={1.5} aria-hidden="true" />{[s.city, s.country].filter(Boolean).join(", ")}</li> : null}
                  {s.year_founded ? <li>Founded {s.year_founded}</li> : null}
                  {s.website_url ? <li><Globe size={16} strokeWidth={1.5} aria-hidden="true" /><a className="app-link" href={s.website_url} target="_blank" rel="noopener noreferrer nofollow">Website</a></li> : null}
                </ul>
              </Card>
            </aside>
          </div>
        </>
      )}
    </Loaded>
  );
}
