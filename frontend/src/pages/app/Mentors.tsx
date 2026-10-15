import { BookingCalendar, dayLabel, priceText, type PickedSlot } from "../../mentor/BookingCalendar";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Globe, Star, Video } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import { compact, useCursorList } from "../../api/hooks";
import { FriendlyError, messageOf } from "../../api/errors";
import type { components } from "../../api/schema";
import { Alert, Avatar, Badge, Button, Card, CardText, CardTitle, CardTo, ChoiceGroup, Input, Modal, Select, Tabs, Textarea } from "../../components";
import { useSectors, useStages } from "../../api/reference";
import { DownloadButton } from "../../ui/DownloadButton";
import { formatDate, formatDateTime, humanise, plural } from "../../lib/format";
import { EmptyState, LoadMore, Loaded, PageHeader, SkeletonCards, SkeletonRows } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";

type Mentor = components["schemas"]["Mentor"];
type Session = components["schemas"]["MentoringSession"];

function MentorCard({ mentor, reasons }: { mentor: Mentor; reasons?: string[] }) {
  return (
    <CardTo to={`/app/mentors/${mentor.id}`}>
      <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
        <Avatar name={mentor.name} id={mentor.id} src={mentor.photo?.thumb} shape="arch" size="lg" />
        <div style={{ minWidth: 0 }}>
          <CardTitle>{mentor.name}</CardTitle>
          <CardText>{[mentor.current_role, mentor.company].filter(Boolean).join(", ")}</CardText>
          <ul className="app-meta" style={{ marginTop: "var(--space-2)" }}>
            <li>{mentor.years_experience} years</li>
            {mentor.rating_average ? (
              <li><Star size={14} strokeWidth={1.5} aria-hidden="true" />{mentor.rating_average.toFixed(1)} ({mentor.rating_count})</li>
            ) : null}
          </ul>
        </div>
      </div>
      <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
        {mentor.expertise.slice(0, 4).map((e) => <Badge key={e} variant="mentor">{e}</Badge>)}
      </div>
      {reasons && reasons.length > 0 ? <p className="caption app-muted" style={{ margin: "var(--space-3) 0 0" }}>{reasons.join(". ")}</p> : null}
    </CardTo>
  );
}

export default function MentorsPage() {
  const [q, setQ] = useState("");
  const [expertise, setExpertise] = useState("");
  const [available, setAvailable] = useState(false);
  const recommended = useQuery({
    queryKey: ["mentors", "recommended"],
    queryFn: () => unwrap(api.GET("/api/v1/mentors/recommended", { params: { query: { limit: 3 } } })),
  });
  const list = useCursorList<Mentor>(["mentors", q, expertise, available], (cursor) =>
    unwrap(api.GET("/api/v1/mentors", { params: { query: { limit: 12, ...(cursor ? { cursor } : {}), ...compact({ q: q.trim(), expertise: expertise.trim() }), ...(available ? { available: true } : {}) } } })),
  );
  const filtering = Boolean(q.trim() || expertise.trim() || available);

  return (
    <>
      <PageHeader
        eyebrow="Mentors"
        title="Find a mentor"
        lead="Vetted people who have built what you are building. Book a conversation."
        actions={
          <>
            <Link className="wo-btn wo-btn--secondary" to="/app/mentors/sessions">My sessions</Link>
            <Link className="wo-btn wo-btn--ghost" to="/app/mentors/become">Become a mentor</Link>
          </>
        }
      />
      {!filtering && recommended.data && recommended.data.length > 0 ? (
        <section className="app-section" style={{ marginTop: 0, marginBottom: "var(--space-12)" }} aria-labelledby="rec">
          <h2 className="h3" id="rec" style={{ margin: "0 0 var(--space-4)" }}>Suggested for you</h2>
          <div className="app-grid">
            {recommended.data.map((m) => <MentorCard key={m.id} mentor={m} reasons={m.reasons.map((r) => r.text ?? "").filter(Boolean)} />)}
          </div>
        </section>
      ) : null}
      <div className="app-filterbar" role="search" aria-label="Filter mentors">
        <div className="app-filterbar__grow"><Input label="Search" placeholder="Name, role or company" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <Input label="Expertise" placeholder="pricing, hiring" value={expertise} onChange={(e) => setExpertise(e.target.value)} />
        <label className="wo-check" style={{ alignSelf: "flex-end", minHeight: 52 }}>
          <input type="checkbox" checked={available} onChange={(e) => setAvailable(e.target.checked)} />
          Has times free
        </label>
      </div>
      {list.query.isPending ? <SkeletonCards /> : null}
      {list.query.isError ? <Alert tone="danger" title="We could not load mentors">{messageOf(list.query.error)}</Alert> : null}
      {list.isEmpty ? <EmptyState title="No mentors match">Try fewer filters.</EmptyState> : null}
      <div className="app-grid">{list.items.map((m) => <MentorCard key={m.id} mentor={m} />)}</div>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}

function BookDialog({ mentor, slot, onClose }: { mentor: Mentor; slot: PickedSlot; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [topic, setTopic] = useState("");
  const [message, setMessage] = useState("");
  const submit = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/sessions", { body: { mentor_id: mentor.id, starts_at: slot.starts_at, length_minutes: slot.length, topic: topic.trim(), message: message.trim() } }));
    await client.invalidateQueries({ queryKey: ["sessions"] });
    await client.invalidateQueries({ queryKey: ["mentors"] });
    toast.show(`Request sent to ${mentor.name}`);
    onClose();
    navigate("/app/mentors/sessions");
  });
  return (
    <Modal
      open
      onClose={onClose}
      eyebrow="Mentorship"
      title="Request this session"
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button loading={submit.busy} disabled={!topic.trim() || !message.trim()} onClick={() => void submit.run()}>Send request</Button>
        </>
      }
    >
      <div className="app-stack">
        <p className="body" style={{ margin: 0 }}>
          {dayLabel(slot.local_date)} at {slot.local_time} ({slot.timezone.replace(/_/g, " ")}) with {mentor.name}, {slot.length} minutes. {priceText(slot.price)}.
        </p>
        {slot.price?.payment === "arranged" ? <Alert tone="info" title="Payment arranged directly">The mentor confirms your request and you settle the fee with them. Nothing is charged here.</Alert> : null}
        <FormError error={submit.error} />
        <Input label="What do you want help with?" value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={120} error={errorsFrom(submit.error).fields.topic} />
        <Textarea label="Tell them about you and what you hope to cover" rows={3} value={message} onChange={(e) => setMessage(e.target.value)} error={errorsFrom(submit.error).fields.message ?? errorsFrom(submit.error).fields.starts_at} />
      </div>
    </Modal>
  );
}

export function MentorDetail() {
  const { id = "" } = useParams();
  const [picked, setPicked] = useState<PickedSlot | null>(null);
  const mentor = useQuery({ queryKey: ["mentors", "one", id], queryFn: () => unwrap(api.GET("/api/v1/mentors/{user_id}", { params: { path: { user_id: id } } })) });
  return (
    <Loaded query={mentor} skeleton={<SkeletonRows />}>
      {(m) => (
        <>
          <PageHeader eyebrow="Mentor" title={m.name} lead={[m.current_role, m.company].filter(Boolean).join(", ")} />
          <div className="app-split">
            <div className="app-stack app-stack--lg">
              <Card>
                <div className="app-stack">
                  <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
                    <Avatar name={m.name} id={m.id} src={m.photo?.thumb} shape="arch" size="xl" />
                    <div className="app-stack">
                      <p className="body-lg" style={{ margin: 0 }}>{m.headline}</p>
                      <ul className="app-meta">
                        <li>{m.years_experience} years of experience</li>
                        <li><Clock size={14} strokeWidth={1.5} aria-hidden="true" />{m.session_minutes} minute sessions</li>
                        <li><Globe size={14} strokeWidth={1.5} aria-hidden="true" />{m.languages.map((l) => l.name).join(", ")}</li>
                        {m.rating_average ? <li><Star size={14} strokeWidth={1.5} aria-hidden="true" />{m.rating_average.toFixed(1)} from {plural(m.rating_count, "rating")}</li> : null}
                      </ul>
                    </div>
                  </div>
                  {m.about ? <p className="body" style={{ margin: 0 }}>{m.about}</p> : null}
                  <div className="app-cluster">
                    {m.expertise.map((e) => <Badge key={e} variant="mentor">{e}</Badge>)}
                    {m.industries.map((i) => <Badge key={i.slug}>{i.name}</Badge>)}
                  </div>
                </div>
              </Card>
            </div>
            <aside>
              <Card>
                <h2 className="h4" style={{ margin: "0 0 var(--space-4)" }}>Book a time</h2>
                {m.paused ? <Alert tone="info" title="Not taking requests right now" /> : null}
                {m.paused ? null : <BookingCalendar mentorId={id} onPick={setPicked} />}
              </Card>
            </aside>
          </div>
          {picked ? <BookDialog mentor={m} slot={picked} onClose={() => setPicked(null)} /> : null}
        </>
      )}
    </Loaded>
  );
}

const STATES: Array<{ id: "upcoming" | "pending" | "past" | "all"; label: string }> = [
  { id: "upcoming", label: "Upcoming" },
  { id: "pending", label: "Waiting" },
  { id: "past", label: "Past" },
  { id: "all", label: "All" },
];

function SessionCard({ session }: { session: Session }) {
  const client = useQueryClient();
  const toast = useToast();
  const other = session.role === "mentor" ? session.mentee : session.mentor;
  const [dialog, setDialog] = useState<"decline" | "cancel" | "feedback" | null>(null);
  const [reason, setReason] = useState("");
  const [stars, setStars] = useState(5);
  const [comment, setComment] = useState("");
  const refresh = () => client.invalidateQueries({ queryKey: ["sessions"] });
  const act = useMutation({
    mutationFn: (what: "accept" | "accept-reschedule") =>
      what === "accept"
        ? unwrap(api.POST("/api/v1/sessions/{session_id}/accept", { params: { path: { session_id: session.id } } }))
        : unwrap(api.POST("/api/v1/sessions/{session_id}/reschedule/accept", { params: { path: { session_id: session.id } } })),
    onSuccess: async () => { toast.show("Done"); await refresh(); },
    onError: (e) => toast.show(messageOf(e)),
  });
  const withReason = useSubmit(async () => {
    if (dialog === "decline") await unwrap(api.POST("/api/v1/sessions/{session_id}/decline", { params: { path: { session_id: session.id } }, body: { reason: reason.trim() } }));
    else await unwrap(api.POST("/api/v1/sessions/{session_id}/cancel", { params: { path: { session_id: session.id } }, body: { reason: reason.trim() } }));
    setDialog(null);
    setReason("");
    await refresh();
  });
  const feedback = useSubmit(async () => {
    await unwrap(api.PUT("/api/v1/sessions/{session_id}/feedback", { params: { path: { session_id: session.id } }, body: { stars, comment: comment.trim(), outcome: "held" } }));
    toast.show("Thank you for the feedback");
    setDialog(null);
    await refresh();
  });
  const tone = session.status === "confirmed" ? "success" : session.status === "requested" ? "warning" : session.status === "completed" ? "info" : "danger";
  return (
    <Card>
      <div className="app-cluster" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
        <Avatar name={other.name} id={other.id} src={other.photo?.thumb} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="app-cluster" style={{ marginBottom: "var(--space-1)" }}>
            <Badge variant={tone} dot>{humanise(session.status)}</Badge>
            <span className="caption app-muted">{session.role === "mentor" ? "You are mentoring" : "You are the mentee"}</span>
          </div>
          <CardTitle>{session.topic || "Mentoring session"}</CardTitle>
          <p className="body" style={{ margin: 0 }}>with {other.name}</p>
          <p className="body-sm app-muted" style={{ margin: "var(--space-1) 0 0" }}>{formatDateTime(session.starts_at)}</p>
          <p className="caption app-muted" style={{ margin: 0 }}>{session.length_minutes} minutes · {priceText(session.price)}{session.price?.payment === "arranged" ? " · Payment arranged directly" : ""}</p>
          {session.proposal ? (
            <Alert tone="info" title={session.proposal.by_me ? "You suggested a new time" : "A new time was suggested"}>
              {formatDateTime(session.proposal.starts_at)}
            </Alert>
          ) : null}
          {session.meeting.url && session.status === "confirmed" ? (
            <p style={{ margin: "var(--space-3) 0 0" }}>
              <a className="app-link" href={session.meeting.url} target="_blank" rel="noopener noreferrer"><Video size={14} strokeWidth={1.5} aria-hidden="true" /> Join the meeting</a>
            </p>
          ) : null}
          <div className="app-cluster" style={{ marginTop: "var(--space-4)" }}>
            {session.actions.accept ? <Button size="sm" loading={act.isPending} onClick={() => act.mutate("accept")}>Accept</Button> : null}
            {session.actions.answer_reschedule ? <Button size="sm" loading={act.isPending} onClick={() => act.mutate("accept-reschedule")}>Accept new time</Button> : null}
            {session.actions.decline ? <Button size="sm" variant="secondary" onClick={() => setDialog("decline")}>Decline</Button> : null}
            {session.actions.cancel ? <Button size="sm" variant="secondary" onClick={() => setDialog("cancel")}>{session.status === "requested" && session.role === "mentee" ? "Withdraw" : "Cancel"}</Button> : null}
            {session.feedback.can_give && !session.feedback.mine ? <Button size="sm" variant="secondary" onClick={() => setDialog("feedback")}>Give feedback</Button> : null}
            {session.status === "confirmed" ? (
              <DownloadButton size="sm" variant="ghost" path={`/api/v1/sessions/${session.id}/calendar.ics`} filename="mentoring-session.ics">Add to calendar</DownloadButton>
            ) : null}
          </div>
        </div>
      </div>
      {dialog === "decline" || dialog === "cancel" ? (
        <Modal open onClose={() => setDialog(null)} eyebrow="Mentorship" title={dialog === "decline" ? "Decline this request?" : "Cancel this session?"}
          actions={<><Button variant="ghost" onClick={() => setDialog(null)}>Keep it</Button><Button variant="danger" loading={withReason.busy} onClick={() => void withReason.run()}>{dialog === "decline" ? "Decline" : "Cancel session"}</Button></>}>
          <div className="app-stack">
            <FormError error={withReason.error} />
            <Textarea label={dialog === "decline" ? "Tell them why" : "Reason (optional)"} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </Modal>
      ) : null}
      {dialog === "feedback" ? (
        <Modal open onClose={() => setDialog(null)} eyebrow="Mentorship" title="How did it go?"
          actions={<><Button variant="ghost" onClick={() => setDialog(null)}>Not now</Button><Button loading={feedback.busy} onClick={() => void feedback.run()}>Send feedback</Button></>}>
          <div className="app-stack">
            <FormError error={feedback.error} />
            {session.role === "mentee" ? (
              <Select label="Rating" value={String(stars)} onChange={(e) => setStars(Number(e.target.value))} options={[5, 4, 3, 2, 1].map((n) => ({ value: String(n), label: `${n} star${n > 1 ? "s" : ""}` }))} />
            ) : null}
            <Textarea label="Comments (optional)" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
        </Modal>
      ) : null}
    </Card>
  );
}

export function SessionsPage() {
  const [state, setState] = useState<(typeof STATES)[number]["id"]>("upcoming");
  const list = useCursorList<Session>(["sessions", state], (cursor) =>
    unwrap(api.GET("/api/v1/sessions", { params: { query: { state, limit: 20, ...(cursor ? { cursor } : {}) } } })),
  );
  return (
    <>
      <PageHeader eyebrow="Mentors" title="My sessions" lead="Requests, confirmed times and past conversations." actions={<Link className="wo-btn wo-btn--primary" to="/app/mentors">Find a mentor</Link>} />
      <div className="app-tabs-scroll">
        <Tabs label="Which sessions" value={state} onChange={(id) => setState(id as typeof state)} items={STATES.map((s) => ({ id: s.id, label: s.label }))} />
      </div>
      {list.query.isPending ? <SkeletonRows /> : null}
      {list.query.isError ? <Alert tone="danger" title="We could not load sessions">{messageOf(list.query.error)}</Alert> : null}
      {list.isEmpty ? <EmptyState title="No sessions here" action={<Link className="wo-btn wo-btn--primary" to="/app/mentors">Find a mentor</Link>}>Book a mentor and the details appear here.</EmptyState> : null}
      <div className="app-stack">{list.items.map((s) => <SessionCard key={s.id} session={s} />)}</div>
      <LoadMore hasNext={list.hasNext} loading={list.loadingMore} onClick={list.loadMore} />
    </>
  );
}

export function BecomeMentor() {
  const summary = useQuery({ queryKey: ["me", "mentoring"], queryFn: () => unwrap(api.GET("/api/v1/me/mentoring")) });
  return (
    <>
      <PageHeader eyebrow="Mentors" title="Become a mentor" lead="Share what you know with founders who are a few steps behind you." />
      <Loaded query={summary} skeleton={<SkeletonRows count={2} />}>
        {(s) => (
          <div className="wo-container--narrow app-stack" style={{ maxWidth: 720 }}>
            {s.is_mentor ? (
              <Alert tone="success" title="You are a mentor">Set your times and profile in your settings.</Alert>
            ) : s.application_status && s.application_status !== "declined" && s.application_status !== "withdrawn" ? (
              <Alert tone="info" title={`Your application: ${humanise(s.application_status)}`}>An admin will email you when there is a decision.</Alert>
            ) : s.can_apply ? (
              <MentorApplicationForm />
            ) : (
              <Alert tone="warning" title="You cannot apply just yet">{s.can_apply_after ? `You can apply again on ${formatDate(s.can_apply_after)}.` : "Check back later."}</Alert>
            )}
          </div>
        )}
      </Loaded>
    </>
  );
}

const APPLY_LANGUAGES: Array<[string, string]> = [["en", "English"], ["fr", "French"], ["pt", "Portuguese"], ["es", "Spanish"], ["ar", "Arabic"], ["sw", "Swahili"], ["yo", "Yoruba"], ["ig", "Igbo"], ["ha", "Hausa"], ["am", "Amharic"], ["zu", "Zulu"], ["af", "Afrikaans"], ["de", "German"], ["hi", "Hindi"], ["zh", "Chinese"]];
const MIN_MOTIVATION = 50;
const MAX_MOTIVATION = 1500;

/** Problems that can be seen before sending, worded like the server's own, so a member fixes them all at once. */
function checkApplication(f: { expertise: string; years: string; role: string; company: string; linkedin: string; hours: string; motivation: string; industries: string[]; stages: string[]; languages: string[] }): Record<string, string> {
  const errors: Record<string, string> = {};
  const areas = f.expertise.split(",").map((s) => s.trim()).filter(Boolean);
  if (areas.length === 0 || areas.length > 8) errors.expertise = "Give 1 to 8 areas, separated by commas.";
  else if (areas.some((a) => a.length < 2 || a.length > 50)) errors.expertise = "Each area must be 2 to 50 characters.";
  const years = Number(f.years);
  if (!f.years || !Number.isInteger(years) || years < 1 || years > 60) errors.years_experience = "Enter a whole number of years, from 1 to 60.";
  const hours = Number(f.hours);
  if (!Number.isInteger(hours) || hours < 1 || hours > 40) errors.weekly_hours = "Enter a whole number of hours, from 1 to 40.";
  if (!f.role.trim()) errors.current_role = "Enter your current role.";
  if (!f.company.trim()) errors.company = "Enter your company.";
  if (!/^(https?:\/\/)?([a-z0-9-]+\.)*linkedin\.com\/.+/i.test(f.linkedin.trim())) errors.linkedin_url = "Paste the full address of your LinkedIn profile, for example https://www.linkedin.com/in/your-name";
  if (f.industries.length === 0) errors.industries = "Choose at least one industry.";
  if (f.stages.length === 0) errors.stages = "Choose at least one stage.";
  if (f.languages.length === 0) errors.languages = "Choose at least one language.";
  const motivation = f.motivation.trim().length;
  if (motivation < MIN_MOTIVATION) errors.motivation = `Write at least ${MIN_MOTIVATION} characters (${MIN_MOTIVATION - motivation} more to go).`;
  else if (motivation > MAX_MOTIVATION) errors.motivation = `Keep it to ${MAX_MOTIVATION} characters (${motivation - MAX_MOTIVATION} too many).`;
  return errors;
}

class CheckFailed extends FriendlyError {}

function MentorApplicationForm() {
  const client = useQueryClient();
  const toast = useToast();
  const sectors = useSectors();
  const stages = useStages();
  const [f, setF] = useState({ expertise: "", years: "", role: "", company: "", linkedin: "", hours: "2", motivation: "", accept: false, industries: [] as string[], stages: [] as string[], languages: ["en"] as string[] });
  const [local, setLocal] = useState<Record<string, string>>({});
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((c) => ({ ...c, [k]: v }));
  const toggle = (k: "industries" | "stages" | "languages", value: string, max: number) => setF((c) => {
    const list = c[k];
    if (list.includes(value)) return { ...c, [k]: list.filter((v) => v !== value) };
    return list.length >= max ? c : { ...c, [k]: [...list, value] };
  });
  const submit = useSubmit(async () => {
    const problems = checkApplication(f);
    setLocal(problems);
    if (Object.keys(problems).length) throw new CheckFailed("Some answers need fixing. Look for the messages under each field.");
    let linkedin = f.linkedin.trim();
    if (!/^https?:\/\//i.test(linkedin)) linkedin = `https://${linkedin}`;
    await unwrap(api.POST("/api/v1/mentor-applications", { body: {
      expertise: f.expertise.split(",").map((s) => s.trim()).filter(Boolean),
      years_experience: Number(f.years),
      current_role: f.role.trim(),
      company: f.company.trim(),
      linkedin_url: linkedin,
      industries: f.industries,
      stages: f.stages,
      languages: f.languages as never,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Africa/Lagos",
      weekly_hours: Number(f.hours),
      motivation: f.motivation.trim(),
      accept_conduct: f.accept,
    } }));
    toast.show("Application sent");
    await client.invalidateQueries({ queryKey: ["me", "mentoring"] });
  });
  // The server's word wins over the local check when both have something to say.
  const errors = { ...local, ...errorsFrom(submit.error).fields };
  const chips = (k: "industries" | "stages" | "languages", options: Array<{ value: string; label: string }>, max: number) => (
    <div className="app-cluster">
      {options.map((o) => (
        <button key={o.value} type="button" className="app-react" aria-pressed={f[k].includes(o.value)} onClick={() => toggle(k, o.value, max)}>{o.label}</button>
      ))}
    </div>
  );
  const fieldError = (message?: string) => (message ? <p className="body-sm" role="alert" style={{ margin: 0, color: "var(--danger-text)" }}>{message}</p> : null);
  return (
    <form className="app-stack app-stack--lg" noValidate onSubmit={(e) => { e.preventDefault(); void submit.run(); }}>
      {submit.error instanceof CheckFailed ? <Alert tone="danger" title="Some answers need fixing">Look for the messages under each field, fix them, then send again.</Alert> : <FormError error={submit.error} />}
      <Input label="Your areas of expertise" hint="1 to 8 areas, separated by commas: pricing, hiring, fundraising" value={f.expertise} onChange={(e) => set("expertise", e.target.value)} error={errors.expertise} />
      <div className="app-formgrid">
        <Input label="Years of experience" hint="1 to 60" type="number" min={1} max={60} value={f.years} onChange={(e) => set("years", e.target.value)} error={errors.years_experience} />
        <Input label="Hours a week you can give" hint="1 to 40" type="number" min={1} max={40} value={f.hours} onChange={(e) => set("hours", e.target.value)} error={errors.weekly_hours} />
        <Input label="Current role" value={f.role} onChange={(e) => set("role", e.target.value)} error={errors.current_role} />
        <Input label="Company" value={f.company} onChange={(e) => set("company", e.target.value)} error={errors.company} />
      </div>
      <Input label="LinkedIn profile" hint="For example https://www.linkedin.com/in/your-name" value={f.linkedin} onChange={(e) => set("linkedin", e.target.value)} error={errors.linkedin_url} />
      <ChoiceGroup legend="Industries you know best (up to 5)">
        {chips("industries", sectors.data ?? [], 5)}
        {fieldError(errors.industries)}
      </ChoiceGroup>
      <ChoiceGroup legend="Startup stages you can help with (up to 4)">
        {chips("stages", stages.data ?? [], 4)}
        {fieldError(errors.stages)}
      </ChoiceGroup>
      <ChoiceGroup legend="Languages you can mentor in (up to 5)">
        {chips("languages", APPLY_LANGUAGES.map(([value, label]) => ({ value, label })), 5)}
        {fieldError(errors.languages)}
      </ChoiceGroup>
      <Textarea label="Why do you want to mentor?" hint={`${f.motivation.trim().length}/${MAX_MOTIVATION} characters, at least ${MIN_MOTIVATION}`} rows={4} value={f.motivation} onChange={(e) => set("motivation", e.target.value)} error={errors.motivation} />
      <label className="wo-check"><input type="checkbox" checked={f.accept} onChange={(e) => set("accept", e.target.checked)} />I will follow the mentor code of conduct</label>
      {fieldError(errors.accept_conduct ?? errors.timezone)}
      <div><Button size="lg" type="submit" loading={submit.busy} disabled={!f.accept}>Send application</Button></div>
    </form>
  );
}
