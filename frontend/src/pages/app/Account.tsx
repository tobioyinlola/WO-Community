import { ReferralCard } from "../../referrals/ReferralCard";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, unwrap, unwrapTagged } from "../../api/client";
import { ApiError, messageOf } from "../../api/errors";
import { useCountries, useSectors, useSkills, useStages, withPlaceholder } from "../../api/reference";
import type { components } from "../../api/schema";
import { Alert, Avatar, Button, Card, ChoiceGroup, Checkbox, Input, Select, Switch, Textarea } from "../../components";
import { uploadFile } from "../../api/upload";
import { formatDateTime, humanise } from "../../lib/format";
import { Loaded, PageHeader, SkeletonRows, TableScroll } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";

type OpenTo = components["schemas"]["OpenToEnum"];
const OPEN_TO: Array<{ value: OpenTo; label: string }> = [
  { value: "hiring", label: "Hiring" },
  { value: "mentoring", label: "Mentoring others" },
  { value: "seeking_mentor", label: "Looking for a mentor" },
  { value: "partnerships", label: "Partnerships" },
];

// The server keeps About you to 500 characters; the counter shows words too, as people think in words.
const BIO_MAX = 500;

function bioCount(text: string): string {
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  return `${words} ${words === 1 ? "word" : "words"} · ${text.length}/${BIO_MAX} characters`;
}

export default function ProfilePage() {
  const client = useQueryClient();
  const toast = useToast();
  const countries = useCountries();
  const skills = useSkills();
  const query = useQuery({ queryKey: ["me", "profile", "tagged"], queryFn: () => unwrapTagged(api.GET("/api/v1/me/profile")) });
  const [f, setF] = useState({ full_name: "", headline: "", bio: "", country: "", city: "", linkedin_url: "", x_url: "", website_url: "", skills: [] as string[], open_to: [] as OpenTo[] });
  const [etag, setEtag] = useState("");

  useEffect(() => {
    const p = query.data?.data;
    if (!p) return;
    setEtag(query.data?.etag ?? "");
    setF({
      full_name: p.full_name ?? "", headline: p.headline ?? "", bio: p.bio ?? "", country: p.country ?? "", city: p.city ?? "",
      linkedin_url: p.linkedin_url ?? "", x_url: p.x_url ?? "", website_url: p.website_url ?? "",
      skills: (p.skills ?? []).map((s) => s.slug), open_to: (p.open_to ?? []) as OpenTo[],
    });
  }, [query.data]);

  const save = useSubmit(async () => {
    const { data, etag: next } = await unwrapTagged(
      api.PATCH("/api/v1/me/profile", { params: { header: { "If-Match": etag } }, body: { ...f, skills: f.skills, open_to: f.open_to } }),
    );
    setEtag(next || etag);
    toast.show("Profile saved");
    client.setQueryData(["me", "profile", "tagged"], { data, etag: next || etag });
    await client.invalidateQueries({ queryKey: ["me", "profile"] });
    await client.invalidateQueries({ queryKey: ["me", "onboarding"] });
  });
  const errors = errorsFrom(save.error).fields;
  const stale = save.error instanceof ApiError && save.error.status === 412;
  const toggle = <T,>(list: T[], value: T) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

  return (
    <>
      <PageHeader eyebrow="You" title="Your profile" lead="This is how other members see you. You decide who can see each part." actions={<Link className="wo-btn wo-btn--secondary" to="/app/settings">Privacy and settings</Link>} />
      <Loaded query={query} skeleton={<SkeletonRows />}>
        {(tagged) => (
          <div className="app-split">
            <form className="app-stack app-stack--lg" noValidate onSubmit={(e) => { e.preventDefault(); void save.run(); }}>
              {stale ? <Alert tone="warning" title="This changed somewhere else" action={<Button size="sm" variant="secondary" onClick={() => void query.refetch()}>Reload</Button>}>Reload to see the latest, then make your change again.</Alert> : <FormError error={save.error} />}
              <div className="app-formgrid">
                <Input label="Full name" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} error={errors.full_name} />
                <Input label="Headline" placeholder="Founder at ..." value={f.headline} onChange={(e) => setF({ ...f, headline: e.target.value })} error={errors.headline} />
                <Select label="Country" options={withPlaceholder(countries.data)} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} error={errors.country} />
                <Input label="City" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} error={errors.city} />
              </div>
              <Textarea label="About you" rows={5} value={f.bio} onChange={(e) => setF({ ...f, bio: e.target.value })} hint={bioCount(f.bio)} error={errors.bio ?? (f.bio.length > BIO_MAX ? `That is ${f.bio.length - BIO_MAX} characters too long. Shorten it to ${BIO_MAX} or fewer.` : undefined)} />
              <div className="app-formgrid">
                <Input label="LinkedIn" value={f.linkedin_url} onChange={(e) => setF({ ...f, linkedin_url: e.target.value })} error={errors.linkedin_url} />
                <Input label="X" value={f.x_url} onChange={(e) => setF({ ...f, x_url: e.target.value })} error={errors.x_url} />
                <div className="app-span"><Input label="Website" value={f.website_url} onChange={(e) => setF({ ...f, website_url: e.target.value })} error={errors.website_url} /></div>
              </div>
              <ChoiceGroup legend="Skills">
                <div className="app-cluster">
                  {(skills.data ?? []).map((s) => (
                    <button key={s.value} type="button" className="app-react" aria-pressed={f.skills.includes(s.value)} onClick={() => setF({ ...f, skills: toggle(f.skills, s.value) })}>{s.label}</button>
                  ))}
                </div>
              </ChoiceGroup>
              <ChoiceGroup legend="I am open to">
                {OPEN_TO.map((o) => <Checkbox key={o.value} label={o.label} checked={f.open_to.includes(o.value)} onChange={() => setF({ ...f, open_to: toggle(f.open_to, o.value) })} />)}
              </ChoiceGroup>
              <div><Button size="lg" type="submit" loading={save.busy}>Save profile</Button></div>
            </form>
            <aside className="app-stack">
              <ProfilePhoto
                name={f.full_name || "You"}
                photo={tagged.data.photo?.large ?? null}
                etag={etag}
                onSaved={(data, next) => {
                  setEtag(next || etag);
                  client.setQueryData(["me", "profile", "tagged"], { data, etag: next || etag });
                  void client.invalidateQueries({ queryKey: ["me"] });
                }}
              />
              <Card>
                <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Profile strength</h2>
                <div className="app-meter" role="progressbar" aria-valuenow={tagged.data.completeness?.score ?? 0} aria-valuemin={0} aria-valuemax={100} aria-label="Profile strength"><span style={{ width: `${tagged.data.completeness?.score ?? 0}%` }} /></div>
                <p className="body-sm app-muted" style={{ margin: "var(--space-2) 0 0" }}>
                  {tagged.data.completeness?.score ?? 0}% complete{tagged.data.completeness?.next_missing_field ? `. Next: add your ${humanise(tagged.data.completeness.next_missing_field).toLowerCase()}.` : "."}
                </p>
              </Card>
              <Card>
                <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Your referrals</h2>
                <ReferralCard />
              </Card>
              <MyStartups />
            </aside>
          </div>
        )}
      </Loaded>
    </>
  );
}

type Profile = components["schemas"]["Profile"];
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
const PHOTO_MAX_BYTES = 5 * 1024 * 1024;

function ProfilePhoto({ name, photo, etag, onSaved }: { name: string; photo: string | null; etag: string; onSaved: (data: Profile, etag: string) => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setProblem("");
    if (!PHOTO_TYPES.includes(file.type)) return setProblem("Choose a JPEG, PNG or WebP image.");
    if (file.size > PHOTO_MAX_BYTES) return setProblem("That image is larger than 5 MB. Choose a smaller one.");
    setBusy(true);
    try {
      const uploaded = await uploadFile(file, "profile_photo");
      const { data, etag: next } = await unwrapTagged(
        api.PUT("/api/v1/me/profile/photo", { params: { header: { "If-Match": etag } }, body: { upload_id: uploaded.id } }),
      );
      onSaved(data, next);
      toast.show("Photo updated");
    } catch (error) {
      setProblem(error instanceof ApiError && error.status === 412 ? "Your profile changed somewhere else. Reload the page and try again." : messageOf(error));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    setProblem("");
    try {
      const { data, etag: next } = await unwrapTagged(api.DELETE("/api/v1/me/profile/photo", { params: { header: { "If-Match": etag } } }));
      onSaved(data, next);
      toast.show("Photo removed");
    } catch (error) {
      setProblem(messageOf(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Your photo</h2>
      <div className="app-cluster">
        <Avatar name={name} src={photo ?? undefined} size="xl" />
        <div className="app-stack">
          <label className="wo-btn wo-btn--secondary wo-btn--sm" aria-disabled={busy || undefined}>
            {busy ? "Uploading…" : photo ? "Change photo" : "Upload photo"}
            <input className="wo-visually-hidden" type="file" accept={PHOTO_TYPES.join(",")} disabled={busy} onChange={(e) => { void choose(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
          {photo ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void remove()}>Remove</Button> : null}
        </div>
      </div>
      <p className="body-sm app-muted" style={{ margin: "var(--space-2) 0 0" }}>JPEG, PNG or WebP, up to 5 MB.</p>
      {problem ? <p className="body-sm" role="alert" style={{ margin: "var(--space-2) 0 0", color: "var(--danger-text)" }}>{problem}</p> : null}
    </Card>
  );
}

function MyStartups() {
  const query = useQuery({ queryKey: ["me", "startups"], queryFn: () => unwrap(api.GET("/api/v1/me/startups")) });
  return (
    <Card>
      <div className="app-section__head" style={{ marginBottom: "var(--space-3)" }}>
        <h2 className="h4" style={{ margin: 0 }}>Your startups</h2>
        <Link className="app-linklike" to="/app/startups/new">Add</Link>
      </div>
      <Loaded query={query} skeleton={<SkeletonRows count={1} />} isEmpty={(d) => d.length === 0} empty={<p className="body-sm app-muted">You have not added a startup yet.</p>}>
        {(items) => <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>{items.map((s) => <li key={s.id}><Link className="app-link" to={`/app/startups/${s.id}`}>{s.name}</Link></li>)}</ul>}
      </Loaded>
    </Card>
  );
}

export function StartupForm() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  const countries = useCountries();
  const sectors = useSectors();
  const stages = useStages();
  const existing = useQuery({ queryKey: ["startups", id, "tagged"], enabled: editing, queryFn: () => unwrapTagged(api.GET("/api/v1/startups/{startup_id}", { params: { path: { startup_id: id ?? "" } } })) });
  const [f, setF] = useState({ name: "", pitch: "", country: "", city: "", sector: "", stage: "", description: "", website_url: "", pitch_deck_url: "", directory_opt_in: false });
  const [etag, setEtag] = useState("");
  useEffect(() => {
    const s = existing.data?.data;
    if (!s) return;
    setEtag(existing.data?.etag ?? "");
    setF({ name: s.name ?? "", pitch: s.pitch ?? "", country: s.country ?? "", city: s.city ?? "", sector: s.sector?.slug ?? "", stage: s.stage?.slug ?? "", description: s.description ?? "", website_url: s.website_url ?? "", pitch_deck_url: s.pitch_deck_url ?? "", directory_opt_in: Boolean(s.directory_opt_in) });
  }, [existing.data]);
  const save = useSubmit(async () => {
    const body = { name: f.name.trim(), pitch: f.pitch.trim(), country: f.country, city: f.city.trim(), sector: f.sector, stage: f.stage, description: f.description.trim(), website_url: f.website_url.trim(), pitch_deck_url: f.pitch_deck_url.trim() };
    const result = editing
      ? await unwrap(api.PATCH("/api/v1/startups/{startup_id}", { params: { path: { startup_id: id ?? "" }, header: { "If-Match": etag } }, body: { ...body, directory_opt_in: f.directory_opt_in } }))
      : await unwrap(api.POST("/api/v1/startups", { body }));
    await client.invalidateQueries({ queryKey: ["startups"] });
    await client.invalidateQueries({ queryKey: ["me", "startups"] });
    toast.show(editing ? "Startup saved" : "Startup added");
    navigate(`/app/startups/${result.id}`);
  });
  const errors = errorsFrom(save.error).fields;
  return (
    <>
      <PageHeader eyebrow="Startup" title={editing ? "Edit your startup" : "Add a startup"} />
      <form className="app-stack app-stack--lg" style={{ maxWidth: 720 }} noValidate onSubmit={(e) => { e.preventDefault(); void save.run(); }}>
        <FormError error={save.error} />
        <Input label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} error={errors.name} />
        <Textarea label="What does it do?" hint="One sentence, up to 160 characters." maxLength={160} rows={2} value={f.pitch} onChange={(e) => setF({ ...f, pitch: e.target.value })} error={errors.pitch} />
        <div className="app-formgrid">
          <Select label="Sector" options={withPlaceholder(sectors.data)} value={f.sector} onChange={(e) => setF({ ...f, sector: e.target.value })} error={errors.sector} />
          <Select label="Stage" options={withPlaceholder(stages.data)} value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })} error={errors.stage} />
          <Select label="Country" options={withPlaceholder(countries.data)} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} error={errors.country} />
          <Input label="City" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} error={errors.city} />
        </div>
        <Textarea label="More detail (optional)" rows={5} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} error={errors.description} />
        <Input label="Website (optional)" value={f.website_url} onChange={(e) => setF({ ...f, website_url: e.target.value })} error={errors.website_url} />
        <Input label="Pitch deck link (optional)" hint="A link to your deck, for example on Google Drive, DocSend or Pitch." value={f.pitch_deck_url} onChange={(e) => setF({ ...f, pitch_deck_url: e.target.value })} error={errors.pitch_deck_url} />
        {editing ? <Switch label="Show this startup in the public directory" checked={f.directory_opt_in} onChange={(e) => setF({ ...f, directory_opt_in: e.target.checked })} /> : null}
        <div className="app-cluster">
          <Button size="lg" type="submit" loading={save.busy}>{editing ? "Save" : "Add startup"}</Button>
          <Link className="wo-btn wo-btn--ghost" to="/app/me">Cancel</Link>
        </div>
      </form>
      {editing && id ? <TractionEditor startupId={id} /> : null}
    </>
  );
}

type TractionItem = components["schemas"]["TractionItemRequest"];
const REVENUE_BANDS = ["none", "lt_1k", "1k_10k", "10k_50k", "50k_250k", "gt_250k"];
const FUNDING_BANDS = ["none", "lt_50k", "50k_250k", "250k_1m", "1m_5m", "gt_5m"];
const TEXT_KINDS = [
  { kind: "milestone", label: "Milestones", placeholder: "Launched in Ghana" },
  { kind: "award", label: "Awards", placeholder: "Winner, Lagos Startup Week 2026" },
  { kind: "partner", label: "Partners", placeholder: "Flutterwave" },
] as const;

/** A revenue or funding band such as "50k_250k" as words a person can read. */
function bandLabel(value: string): string {
  if (value === "none") return "None yet";
  if (value.startsWith("lt_")) return `Under $${value.slice(3)}`;
  if (value.startsWith("gt_")) return `Over $${value.slice(3)}`;
  return `$${value.replace("_", " to ")}`;
}

/** Users, revenue and funding bands, and lists of milestones, awards and partners, saved together. */
function TractionEditor({ startupId }: { startupId: string }) {
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({ queryKey: ["startups", startupId, "traction"], queryFn: () => unwrapTagged(api.GET("/api/v1/startups/{startup_id}", { params: { path: { startup_id: startupId } } })) });
  const [users, setUsers] = useState("");
  const [revenue, setRevenue] = useState("");
  const [funding, setFunding] = useState("");
  const [texts, setTexts] = useState<Record<string, string[]>>({ milestone: [], award: [], partner: [] });
  const [visibility, setVisibility] = useState<string>("public");

  useEffect(() => {
    const items = query.data?.data.traction ?? [];
    const of = (kind: string) => items.filter((t) => t.kind === kind).map((t) => String(t.value ?? ""));
    setUsers(of("users")[0] ?? "");
    setRevenue(of("revenue_range")[0] ?? "");
    setFunding(of("funding_range")[0] ?? "");
    setTexts({ milestone: of("milestone"), award: of("award"), partner: of("partner") });
    if (items[0]) setVisibility(items[0].visibility);
  }, [query.data]);

  const save = useSubmit(async () => {
    const vis = visibility as TractionItem["visibility"];
    const metrics: TractionItem[] = [];
    if (users.trim()) metrics.push({ kind: "users", value: Number(users), visibility: vis });
    if (revenue) metrics.push({ kind: "revenue_range", value: revenue, visibility: vis });
    if (funding) metrics.push({ kind: "funding_range", value: funding, visibility: vis });
    for (const { kind } of TEXT_KINDS) for (const text of texts[kind] ?? []) if (text.trim()) metrics.push({ kind, value: text.trim(), visibility: vis });
    await unwrap(api.PUT("/api/v1/startups/{startup_id}/traction", { params: { path: { startup_id: startupId }, header: { "If-Match": query.data?.etag ?? "" } }, body: { metrics } }));
    toast.show("Traction saved");
    await client.invalidateQueries({ queryKey: ["startups"] });
    await client.invalidateQueries({ queryKey: ["me", "onboarding"] });
  });
  // The dashboard's "Add your traction" link lands here.
  const loaded = Boolean(query.data);
  useEffect(() => {
    if (loaded && window.location.hash === "#traction") document.getElementById("traction")?.scrollIntoView({ block: "start" });
  }, [loaded]);
  const stale = save.error instanceof ApiError && save.error.status === 412;
  const usersError = users.trim() && (!/^\d+$/.test(users.trim())) ? "Enter a whole number, without commas." : undefined;

  return (
    <section id="traction" style={{ maxWidth: 720, marginTop: "var(--space-12)" }}>
      <Card>
        <h2 className="h3" style={{ margin: "0 0 var(--space-2)" }}>Traction</h2>
        <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-4)" }}>Show what you have achieved. Revenue and funding are shared as ranges, never exact figures.</p>
        <Loaded query={query} skeleton={<SkeletonRows count={3} />}>
          {() => (
            <form className="app-stack" noValidate onSubmit={(e) => { e.preventDefault(); if (!usersError) void save.run(); }}>
              {stale ? <Alert tone="warning" title="This startup changed somewhere else" action={<Button size="sm" variant="secondary" onClick={() => void query.refetch()}>Reload</Button>}>Reload to see the latest, then save again.</Alert> : <FormError error={save.error} />}
              <div className="app-formgrid">
                <Input label="Users or customers" inputMode="numeric" value={users} onChange={(e) => setUsers(e.target.value)} error={usersError} />
                <Select label="Revenue to date" options={[{ value: "", label: "Not shared" }, ...REVENUE_BANDS.map((b) => ({ value: b, label: bandLabel(b) }))]} value={revenue} onChange={(e) => setRevenue(e.target.value)} />
                <Select label="Funding raised" options={[{ value: "", label: "Not shared" }, ...FUNDING_BANDS.map((b) => ({ value: b, label: bandLabel(b) }))]} value={funding} onChange={(e) => setFunding(e.target.value)} />
                <Select label="Who can see your traction" options={LEVELS.map((l) => ({ value: l, label: l === "public" ? "Anyone" : l === "members" ? "Members only" : "Only you and your team" }))} value={visibility} onChange={(e) => setVisibility(e.target.value)} />
              </div>
              {TEXT_KINDS.map(({ kind, label, placeholder }) => (
                <ChoiceGroup key={kind} legend={label}>
                  <div className="app-stack">
                    {(texts[kind] ?? []).map((text, i) => (
                      <div className="app-cluster" key={i} style={{ flexWrap: "nowrap" }}>
                        <div style={{ flex: 1 }}><Input label={`${label} ${i + 1}`} placeholder={placeholder} maxLength={300} value={text} onChange={(e) => setTexts({ ...texts, [kind]: (texts[kind] ?? []).map((t, j) => (j === i ? e.target.value : t)) })} /></div>
                        <Button size="sm" variant="ghost" onClick={() => setTexts({ ...texts, [kind]: (texts[kind] ?? []).filter((_, j) => j !== i) })}>Remove</Button>
                      </div>
                    ))}
                    <div><Button size="sm" variant="secondary" onClick={() => setTexts({ ...texts, [kind]: [...(texts[kind] ?? []), ""] })}>Add {label.toLowerCase().replace(/s$/, "")}</Button></div>
                  </div>
                </ChoiceGroup>
              ))}
              <div><Button size="lg" type="submit" loading={save.busy}>Save traction</Button></div>
            </form>
          )}
        </Loaded>
      </Card>
    </section>
  );
}

const GROUP_LABELS: Record<string, string> = { comments: "Comments and replies", follows: "New followers", news: "Community news", news_digest: "News digest", mentions: "Mentions", mentorship: "Mentoring", approvals: "Approvals", moderation: "Moderation", jobs: "Jobs", learning: "Learning", event_reminders: "Event reminders", newsletter: "Newsletter" };
const LEVELS = ["public", "members", "private"] as const;
const AREA_LABELS: Record<string, string> = { basics: "Name, headline and photo", bio: "About you", location: "Country and city", skills: "Skills", links: "Links", open_to: "What you are open to" };

export function SettingsPage() {
  const client = useQueryClient();
  const toast = useToast();
  const prefs = useQuery({ queryKey: ["me", "prefs"], queryFn: () => unwrap(api.GET("/api/v1/me/notification-preferences")) });
  const visibility = useQuery({ queryKey: ["me", "visibility"], queryFn: async () => (await unwrap(api.GET("/api/v1/me/visibility"))) as unknown as Record<string, string> });
  const sessions = useQuery({ queryKey: ["me", "sessions"], queryFn: () => unwrap(api.GET("/api/v1/me/sessions")) });
  const setPref = useMutation({
    mutationFn: (next: Record<string, Record<string, boolean>>) => unwrap(api.PUT("/api/v1/me/notification-preferences", { body: { preferences: next } })),
    onSuccess: async () => { toast.show("Saved"); await client.invalidateQueries({ queryKey: ["me", "prefs"] }); },
    onError: (e) => toast.show(messageOf(e)),
  });
  const setVis = useMutation({
    mutationFn: (change: Record<string, string>) => unwrap(api.PATCH("/api/v1/me/visibility", { body: change as never })),
    onSuccess: async () => { toast.show("Saved"); await client.invalidateQueries({ queryKey: ["me", "visibility"] }); },
    onError: (e) => toast.show(messageOf(e)),
  });
  const revoke = useMutation({
    mutationFn: (sessionId: string) => unwrap(api.DELETE("/api/v1/me/sessions/{session_id}", { params: { path: { session_id: sessionId } } })),
    onSuccess: async () => { toast.show("Signed out of that device"); await client.invalidateQueries({ queryKey: ["me", "sessions"] }); },
  });

  return (
    <>
      <PageHeader eyebrow="You" title="Settings" lead="Who sees what, what we email you, and where you are signed in." />
      <div className="app-stack app-stack--lg" style={{ maxWidth: 820 }}>
        <Card>
          <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Who can see your profile</h2>
          <Loaded query={visibility} skeleton={<SkeletonRows count={3} />}>
            {(levels) => (
              <div className="app-stack">
                {Object.entries(levels).map(([area, level]) => (
                  <Select key={area} label={AREA_LABELS[area] ?? humanise(area)} value={level} onChange={(e) => setVis.mutate({ [area]: e.target.value })} options={LEVELS.map((l) => ({ value: l, label: l === "public" ? "Anyone" : l === "members" ? "Members only" : "Only me" }))} />
                ))}
              </div>
            )}
          </Loaded>
        </Card>
        <Card>
          <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Notifications</h2>
          <Loaded query={prefs} skeleton={<SkeletonRows count={3} />}>
            {(data) => (
              <TableScroll label="Notification settings">
              <table className="app-table" style={{ width: "100%" }}>
                <thead><tr><th scope="col">What</th><th>In the app</th><th>By email</th></tr></thead>
                <tbody>
                  {Object.entries(data.preferences).map(([group, channels]) => (
                    <tr key={group}>
                      <td>{GROUP_LABELS[group] ?? humanise(group)}</td>
                      {(["in_app", "email"] as const).map((channel) => (
                        <td key={channel}>
                          <Switch label={<span className="wo-visually-hidden">{`${GROUP_LABELS[group] ?? group} ${channel === "email" ? "by email" : "in the app"}`}</span>} checked={Boolean(channels[channel])} onChange={(e) => setPref.mutate({ ...data.preferences, [group]: { ...channels, [channel]: e.target.checked } })} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              </TableScroll>
            )}
          </Loaded>
        </Card>
        <Card>
          <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Where you are signed in</h2>
          <Loaded query={sessions} skeleton={<SkeletonRows count={2} />} isEmpty={(d) => d.length === 0} empty={<p className="body app-muted">No other devices.</p>}>
            {(items) => (
              <ul className="app-list">
                {items.map((s) => (
                  <li className="app-list__item" key={s.id}>
                    <div className="app-list__main">
                      <p className="app-list__title">{s.user_agent || "A device"}</p>
                      <p className="body-sm app-muted" style={{ margin: 0 }}>Last used {formatDateTime(s.last_used_at)}</p>
                    </div>
                    <Button size="sm" variant="secondary" loading={revoke.isPending && revoke.variables === s.id} onClick={() => revoke.mutate(s.id)}>Sign out</Button>
                  </li>
                ))}
              </ul>
            )}
          </Loaded>
        </Card>
        <EmptyStateHint />
      </div>
    </>
  );
}

function EmptyStateHint() {
  return (
    <p className="body-sm app-muted">
      To change your password, use <Link className="app-link" to="/forgot-password">Reset password</Link>. We email you a link.
    </p>
  );
}

