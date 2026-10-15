import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Briefcase, Globe, Linkedin, MapPin, Presentation } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { messageOf } from "../../api/errors";
import { useCountries, useSectors, useSkills, useStages, withPlaceholder } from "../../api/reference";
import type { components } from "../../api/schema";
import { Alert, Avatar, Badge, Button, Card, CardText, CardTitle, CardTo, Checkbox, Input, Select, Tabs } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { EmptyState, Loaded, PageHeader, Pagination, SkeletonCards, SkeletonRows } from "../../ui/blocks";

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

const PAGE_SIZE = 12;
const SORTS = [
  { value: "newest", label: "Newest first" },
  { value: "name", label: "Name A to Z" },
];

/** A revenue or funding band such as "50k_250k" as words a person can read. */
function band(value: string): string {
  if (value === "none") return "None yet";
  if (value.startsWith("lt_")) return `Under $${value.slice(3)}`;
  if (value.startsWith("gt_")) return `Over $${value.slice(3)}`;
  return `$${value.replace("_", " to ")}`;
}

function tractionChips(items: Array<{ kind: string; value?: unknown }>): string[] {
  const chips: string[] = [];
  for (const t of items) {
    const value = t.value;
    if (value === null || value === undefined || value === "") continue;
    if (t.kind === "users") chips.push(`${Number(value).toLocaleString()} users`);
    else if (t.kind === "revenue_range") chips.push(`${band(String(value))} revenue`);
    else if (t.kind === "funding_range") chips.push(`${band(String(value))} raised`);
    else chips.push(String(value));
  }
  return chips.slice(0, 4);
}

/** Keeps filters in the address, so a filtered view can be shared and the back button works. */
function useFilters() {
  const [params, setParams] = useSearchParams();
  const get = (key: string) => params.get(key) ?? "";
  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  };
  const page = Math.max(1, Number(get("page")) || 1);
  return { get, set, page, params, setParams };
}

export default function DirectoryPage() {
  const filters = useFilters();
  const q = filters.get("q").trim();
  const tab = filters.get("tab") === "startups" ? "startups" : "members";
  const [draft, setDraft] = useState(q);
  useEffect(() => setDraft(q), [q]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    filters.set({ q: draft.trim() });
  };

  return (
    <>
      <PageHeader eyebrow="Directory" title="Find people and startups" lead="Browse the community with filters, or search everything: members, startups, mentors, jobs, events and courses." />
      <form className="app-filterbar" role="search" onSubmit={submit}>
        <div className="app-filterbar__grow">
          <Input label="Search" placeholder="A name, a company, a skill" value={draft} onChange={(e) => setDraft(e.target.value)} />
        </div>
        <Button type="submit" size="lg" style={{ alignSelf: "flex-end" }}>Search</Button>
        {q ? <Button type="button" variant="ghost" size="lg" style={{ alignSelf: "flex-end" }} onClick={() => filters.set({ q: "" })}>Clear</Button> : null}
      </form>
      {q ? <SearchResults q={q} /> : (
        <>
          <div className="app-tabs-scroll">
            <Tabs label="Browse" variant="segment" value={tab} onChange={(id) => filters.setParams(id === "startups" ? { tab: "startups" } : {})} items={[{ id: "members", label: "Members" }, { id: "startups", label: "Startups" }]} />
          </div>
          <div style={{ marginTop: "var(--space-6)" }}>
            {tab === "startups" ? <StartupsBrowser filters={filters} /> : <MembersBrowser filters={filters} />}
          </div>
        </>
      )}
    </>
  );
}

type Filters = ReturnType<typeof useFilters>;

function FilterRow({ children }: { children: ReactNode }) {
  return <div className="app-filterbar app-filterbar--wrap">{children}</div>;
}

function StartupsBrowser({ filters }: { filters: Filters }) {
  const countries = useCountries();
  const sectors = useSectors();
  const stages = useStages();
  const country = filters.get("country");
  const sector = filters.get("sector");
  const stage = filters.get("stage");
  const city = filters.get("city");
  const hiring = filters.get("hiring") === "1";
  const sort = filters.get("sort") === "name" ? "name" : "newest";
  const [cityDraft, setCityDraft] = useState(city);
  useEffect(() => setCityDraft(city), [city]);

  const query = useQuery({
    queryKey: ["browse", "startups", { country, sector, stage, city, hiring, sort, page: filters.page }],
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/directory/startups", {
          params: { query: { country: country || undefined, sector: sector || undefined, stage: stage || undefined, city: city || undefined, hiring: hiring || undefined, sort, page: filters.page, page_size: PAGE_SIZE } },
        }),
      ),
  });
  const active = [country, sector, stage, city, hiring ? "1" : ""].some(Boolean);

  return (
    <>
      <FilterRow>
        <Select label="Sector" options={withPlaceholder(sectors.data, "All sectors")} value={sector} onChange={(e) => filters.set({ sector: e.target.value })} />
        <Select label="Stage" options={withPlaceholder(stages.data, "All stages")} value={stage} onChange={(e) => filters.set({ stage: e.target.value })} />
        <Select label="Country" options={withPlaceholder(countries.data, "All countries")} value={country} onChange={(e) => filters.set({ country: e.target.value })} />
        <form onSubmit={(e) => { e.preventDefault(); filters.set({ city: cityDraft.trim() }); }}>
          <Input label="City" placeholder="Any city" value={cityDraft} onChange={(e) => setCityDraft(e.target.value)} onBlur={() => cityDraft.trim() !== city && filters.set({ city: cityDraft.trim() })} />
        </form>
        <Select label="Sort" options={SORTS} value={sort} onChange={(e) => filters.set({ sort: e.target.value === "newest" ? "" : e.target.value })} />
        <div className="app-filterbar__check">
          <Checkbox label="Hiring now" checked={hiring} onChange={(e) => filters.set({ hiring: e.target.checked ? "1" : "" })} />
        </div>
        {active ? <Button variant="ghost" size="sm" onClick={() => filters.setParams(new URLSearchParams({ tab: "startups" }))}>Clear filters</Button> : null}
      </FilterRow>
      <Loaded
        query={query}
        skeleton={<SkeletonCards count={6} />}
        isEmpty={(d) => d.results.length === 0}
        empty={<EmptyState title="No startups match">{active ? "Try removing a filter." : "Startups appear here when their founders share them with members."}</EmptyState>}
      >
        {(data) => (
          <>
            <div className="app-grid app-grid--wide" aria-busy={query.isFetching}>
              {data.results.map((s) => <StartupCard key={s.id} startup={s} countries={countries.data} />)}
            </div>
            <Pagination page={data.page} pages={data.pages} count={data.count} noun={data.count === 1 ? "startup" : "startups"} onPage={(page) => { filters.set({ page: page > 1 ? String(page) : "" }); window.scrollTo({ top: 0 }); }} />
          </>
        )}
      </Loaded>
    </>
  );
}

type BrowseStartup = components["schemas"]["BrowseStartup"];

function StartupCard({ startup: s, countries }: { startup: BrowseStartup; countries?: Array<{ value: string; label: string }> }) {
  const place = [s.city, countries?.find((c) => c.value === s.country)?.label ?? s.country].filter(Boolean).join(", ");
  const chips = tractionChips(s.traction);
  return (
    <Card className="app-startupcard">
      <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
        <Avatar name={s.name} id={s.id} src={s.logo?.thumb as string | undefined} size="lg" />
        <div style={{ minWidth: 0 }}>
          <h2 className="h4" style={{ margin: 0 }}><Link className="app-cardlink" to={`/app/startups/${s.id}`}>{s.name}</Link></h2>
          <p className="body-sm app-muted" style={{ margin: "var(--space-1) 0 0" }}>{s.pitch}</p>
        </div>
      </div>
      <div className="app-cluster">
        {s.sector ? <Badge variant="operator">{s.sector.name}</Badge> : null}
        {s.stage ? <Badge>{s.stage.name}</Badge> : null}
        {s.featured ? <Badge variant="solid">Featured</Badge> : null}
        {s.open_jobs_count > 0 ? <Badge variant="success" dot>Hiring{s.open_jobs_count > 1 ? ` ${s.open_jobs_count} roles` : ""}</Badge> : null}
      </div>
      {s.description ? <p className="body-sm app-clamp" style={{ margin: 0 }}>{s.description}</p> : null}
      {chips.length > 0 ? (
        <ul className="app-chips" aria-label="Traction">
          {chips.map((c) => <li key={c}>{c}</li>)}
        </ul>
      ) : null}
      <ul className="app-meta">
        {place ? <li><MapPin size={16} strokeWidth={1.5} aria-hidden="true" />{place}</li> : null}
        {s.year_founded ? <li>Founded {s.year_founded}</li> : null}
      </ul>
      {s.website_url || s.pitch_deck_url || s.open_jobs_count > 0 ? (
        <div className="app-cluster app-startupcard__links">
          {s.website_url ? <a className="app-link" href={s.website_url} target="_blank" rel="noopener noreferrer nofollow"><Globe size={14} strokeWidth={1.5} aria-hidden="true" /> Website</a> : null}
          {s.pitch_deck_url ? <a className="app-link" href={s.pitch_deck_url} target="_blank" rel="noopener noreferrer nofollow"><Presentation size={14} strokeWidth={1.5} aria-hidden="true" /> Pitch deck</a> : null}
          {s.open_jobs_count > 0 ? <Link className="app-link" to={`/app/jobs/${s.open_jobs[0]?.id}`}><Briefcase size={14} strokeWidth={1.5} aria-hidden="true" /> {s.open_jobs[0]?.title}{s.open_jobs_count > 1 ? ` +${s.open_jobs_count - 1}` : ""}</Link> : null}
        </div>
      ) : null}
    </Card>
  );
}

function MembersBrowser({ filters }: { filters: Filters }) {
  const countries = useCountries();
  const skills = useSkills();
  const country = filters.get("country");
  const skill = filters.get("skill");
  const sort = filters.get("sort") === "name" ? "name" : "newest";
  const query = useQuery({
    queryKey: ["browse", "members", { country, skill, sort, page: filters.page }],
    placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/v1/directory/members", { params: { query: { country: country || undefined, skill: skill || undefined, sort, page: filters.page, page_size: PAGE_SIZE } } })),
  });
  const active = Boolean(country || skill);
  return (
    <>
      <FilterRow>
        <Select label="Country" options={withPlaceholder(countries.data, "All countries")} value={country} onChange={(e) => filters.set({ country: e.target.value })} />
        <Select label="Skill" options={withPlaceholder(skills.data, "Any skill")} value={skill} onChange={(e) => filters.set({ skill: e.target.value })} />
        <Select label="Sort" options={SORTS} value={sort} onChange={(e) => filters.set({ sort: e.target.value === "newest" ? "" : e.target.value })} />
        {active ? <Button variant="ghost" size="sm" onClick={() => filters.setParams(new URLSearchParams())}>Clear filters</Button> : null}
      </FilterRow>
      <Loaded
        query={query}
        skeleton={<SkeletonCards count={6} />}
        isEmpty={(d) => d.results.length === 0}
        empty={<EmptyState title="No members match">{active ? "Try removing a filter." : "Members appear here when they share their profile with the community."}</EmptyState>}
      >
        {(data) => (
          <>
            <div className="app-grid" aria-busy={query.isFetching}>
              {data.results.map((m) => (
                <CardTo key={m.id} to={`/app/members/${m.id}`}>
                  <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
                    <Avatar name={m.name} id={m.id} src={m.photo?.thumb as string | undefined} shape="arch" size="lg" />
                    <div style={{ minWidth: 0 }}>
                      <CardTitle>{m.name}</CardTitle>
                      <CardText>{m.headline}</CardText>
                      {m.city || m.country ? <p className="caption app-muted" style={{ margin: "var(--space-2) 0 0" }}>{[m.city, countries.data?.find((c) => c.value === m.country)?.label ?? m.country].filter(Boolean).join(", ")}</p> : null}
                    </div>
                  </div>
                  {m.skills.length > 0 ? <div className="app-cluster" style={{ marginTop: "var(--space-3)" }}>{m.skills.slice(0, 3).map((k) => <Badge key={k.slug} variant="operator">{k.name}</Badge>)}</div> : null}
                </CardTo>
              ))}
            </div>
            <Pagination page={data.page} pages={data.pages} count={data.count} noun={data.count === 1 ? "member" : "members"} onPage={(page) => { filters.set({ page: page > 1 ? String(page) : "" }); window.scrollTo({ top: 0 }); }} />
          </>
        )}
      </Loaded>
    </>
  );
}

function SearchResults({ q }: { q: string }) {
  const [only, setOnly] = useState("all");
  const search = useQuery({
    queryKey: ["search", q],
    queryFn: () => unwrap(api.GET("/api/v1/search", { params: { query: { q, limit: 12 } } })),
    enabled: q.length >= 2,
  });
  const groups = GROUPS.filter((g) => (search.data?.[g.key]?.length ?? 0) > 0);
  const shown = only === "all" ? groups : groups.filter((g) => g.key === only);
  return (
    <>
      {q.length < 2 ? <EmptyState title="Keep typing">Search needs at least two characters.</EmptyState> : null}
      {q.length >= 2 && search.isPending ? <SkeletonCards count={3} /> : null}
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
  const certificates = useQuery({ queryKey: ["members", id, "certificates"], queryFn: () => unwrap(api.GET("/api/v1/members/{user_id}/certificates", { params: { path: { user_id: id } } })) });

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
              {certificates.data && certificates.data.length > 0 ? (
                <Card>
                  <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Certificates</h2>
                  <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                    {certificates.data.map((c) => (
                      <li key={c.number}>
                        <p className="body" style={{ margin: 0 }}>{c.course_title}</p>
                        <p className="caption app-muted" style={{ margin: 0 }}>
                          {formatDate(c.issued_at)} · <Link className="app-link" to={`/verify/${c.number}`}>Verify {c.number}</Link>
                        </p>
                      </li>
                    ))}
                  </ul>
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
  const openJobs = useQuery({
    queryKey: ["startups", id, "jobs"],
    queryFn: () => unwrap(api.GET("/api/v1/jobs", { params: { query: { startup_id: id, limit: 5 } } })),
  });
  const roles = openJobs.data?.results ?? [];
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
                  {s.pitch_deck_url ? <li><Presentation size={16} strokeWidth={1.5} aria-hidden="true" /><a className="app-link" href={s.pitch_deck_url} target="_blank" rel="noopener noreferrer nofollow">Pitch deck</a></li> : null}
                </ul>
              </Card>
              {roles.length > 0 ? (
                <Card>
                  <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Open roles</h2>
                  <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                    {roles.map((job) => (
                      <li key={job.id}>
                        <Link className="app-link" to={`/app/jobs/${job.id}`}><Briefcase size={14} strokeWidth={1.5} aria-hidden="true" /> {job.title}</Link>
                        {job.location ? <p className="caption app-muted" style={{ margin: 0 }}>{job.location}</p> : null}
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : null}
            </aside>
          </div>
        </>
      )}
    </Loaded>
  );
}
