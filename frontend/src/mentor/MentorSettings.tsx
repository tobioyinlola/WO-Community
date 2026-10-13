import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { ApiError } from "../api/errors";
import { useSectors, useStages } from "../api/reference";
import type { components } from "../api/schema";
import { Alert, Button, Card, Checkbox, Input, Radio, Select, Switch, Textarea } from "../components";
import { formatDateTime, formatMoney } from "../lib/format";
import { Drawer } from "../ui/Drawer";
import { ErrorState, PageHeader, SkeletonRows, useDocumentTitle } from "../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../ui/forms";
import { useToast } from "../ui/Toast";
import { BookingCalendar, browserZone } from "./BookingCalendar";
import { conflictOf, ConflictDialog, type ConflictSession } from "./Conflicts";
import { fromMinor, hasRanges, summarise, toMinor, weekFrom, weekProblems, windowsFrom, zoneLabel, type Week } from "./model";
import { TimeOff } from "./TimeOff";
import { WeeklyEditor } from "./WeeklyEditor";
import "../styles/mentor.css";

type Setup = components["schemas"]["MentorSetup"];
type Calendar = components["schemas"]["CalendarStatus"];

const LANGUAGES: Array<[string, string]> = [["en", "English"], ["fr", "French"], ["pt", "Portuguese"], ["es", "Spanish"], ["ar", "Arabic"], ["sw", "Swahili"], ["yo", "Yoruba"], ["ig", "Igbo"], ["ha", "Hausa"], ["am", "Amharic"], ["zu", "Zulu"], ["af", "Afrikaans"], ["de", "German"], ["hi", "Hindi"], ["zh", "Chinese"]];
const PROVIDERS: Array<[string, string]> = [["google_meet", "Google Meet"], ["zoom", "Zoom"], ["personal", "My own link"]];

interface Draft {
  week: Week;
  zone: string;
  lengths: number[];
  defaultLength: number;
  buffer: number;
  notice: number;
  maxPerWeek: number;
  windowDays: number;
  accepting: boolean;
  pricing: "free" | "paid";
  currency: string;
  price: string;
  prices: Record<number, string>;
  provider: string;
  link: string;
  about: string;
  expertise: string;
  topics: string;
  languages: string[];
  stages: string[];
  industries: string[];
}

const commas = (list: string[]) => list.join(", ");
const split = (text: string) => text.split(",").map((s) => s.trim()).filter(Boolean);
const toggle = <T,>(list: T[], value: T) => (list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

function toDraft(s: Setup): Draft {
  return {
    week: weekFrom(s.weekly),
    zone: s.timezone,
    lengths: s.session_lengths,
    defaultLength: s.default_length,
    buffer: s.buffer_minutes,
    notice: s.min_notice_hours,
    maxPerWeek: s.max_per_week,
    windowDays: s.booking_window_days,
    accepting: s.accepting_new,
    pricing: s.pricing_mode,
    currency: s.currency || "NGN",
    price: fromMinor(s.default_price_minor),
    prices: Object.fromEntries(s.prices.map((p) => [p.length_minutes, fromMinor(p.price_minor)])),
    provider: s.meeting_provider || "google_meet",
    link: s.personal_link,
    about: s.about,
    expertise: commas(s.expertise),
    topics: commas(s.topics),
    languages: s.languages,
    stages: s.stages,
    industries: s.industries,
  };
}

const hours = (n: number) => (n % 24 === 0 && n >= 24 ? `${n / 24} ${n === 24 ? "day" : "days"}` : `${n} ${n === 1 ? "hour" : "hours"}`);

function CalendarCard() {
  const toast = useToast();
  const client = useQueryClient();
  const [url, setUrl] = useState("");
  const status = useQuery({ queryKey: ["me", "calendar"], queryFn: () => unwrap(api.GET("/api/v1/me/calendar")).catch((e: unknown) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e))), retry: false });
  const cal: Calendar | null | undefined = status.data as Calendar | null | undefined;
  const connect = useSubmit(async () => {
    await unwrap(api.PUT("/api/v1/me/calendar", { body: { feed_url: url.trim() } }));
    setUrl("");
    toast.show("Calendar connected");
    await client.invalidateQueries({ queryKey: ["me", "calendar"] });
    await client.invalidateQueries({ queryKey: ["slots"] });
  });
  const disconnect = async () => {
    await unwrap(api.DELETE("/api/v1/me/calendar"));
    toast.show("Calendar disconnected");
    await client.invalidateQueries({ queryKey: ["me", "calendar"] });
  };
  return (
    <div className="app-stack">
      <p className="body-sm" role="status" style={{ margin: 0 }}>
        <strong>Calendar:</strong> {cal?.connected ? `Connected${cal.host ? ` (${cal.host})` : ""}${cal.status === "error" ? ". The last read failed" : cal.last_synced_at ? `. Last read ${formatDateTime(cal.last_synced_at)}` : ""}` : "Not connected. Times you are already busy will not be offered once it is."}
      </p>
      <FormError error={connect.error} />
      {cal?.connected ? (
        <div>
          <Button variant="ghost" size="sm" onClick={() => void disconnect()}>
            Disconnect calendar
          </Button>
        </div>
      ) : (
        <div className="app-cluster" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: "1 1 280px" }}>
            <Input label="Private calendar address (iCal)" value={url} onChange={(e) => setUrl(e.target.value)} hint="Paste the secret iCal address from Google Calendar, Outlook or Apple Calendar. We read busy time only." error={errorsFrom(connect.error).fields.feed_url} />
          </div>
          <Button variant="secondary" loading={connect.busy} disabled={!url.trim()} onClick={() => void connect.run()}>
            Connect calendar
          </Button>
        </div>
      )}
    </div>
  );
}

export default function MentorSettings() {
  useDocumentTitle("Mentorship settings");
  const client = useQueryClient();
  const toast = useToast();
  const sectors = useSectors();
  const stages = useStages();
  const query = useQuery({ queryKey: ["me", "mentor", "settings"], queryFn: () => unwrap(api.GET("/api/v1/me/mentor/settings")), retry: false });
  const [draft, setDraft] = useState<Draft | null>(null);
  const [base, setBase] = useState<Draft | null>(null);
  const [version, setVersion] = useState<unknown>(null);
  const [conflict, setConflict] = useState<ConflictSession[] | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const resetAfterSave = useRef(false);

  const dirty = useMemo(() => Boolean(draft && base && JSON.stringify(draft) !== JSON.stringify(base)), [draft, base]);
  // Fresh data from the server replaces the form only when there is nothing unsaved in it (or right after a
  // save), so adding a day off never throws away edits made above it.
  if (query.data && version !== query.data) {
    setVersion(query.data);
    const fresh = toDraft(query.data);
    setBase(fresh);
    if (!dirty || resetAfterSave.current) setDraft(fresh);
    resetAfterSave.current = false;
  }
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const setup = query.data;

  // Warn before leaving with unsaved changes.
  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const problems = draft ? weekProblems(draft.week, Math.min(...draft.lengths, 60)) : [];
  const blocking: string[] = [];
  if (draft) {
    if (problems.some(Boolean)) blocking.push("Fix the highlighted times.");
    if (draft.accepting && !hasRanges(draft.week)) blocking.push("Add at least one time range, or turn off accepting new mentees.");
    if (draft.lengths.length === 0) blocking.push("Offer at least one session length.");
    if (draft.pricing === "paid" && !toMinor(draft.price)) blocking.push("Enter a price above zero, or choose free.");
    if (draft.provider === "personal" && !draft.link.trim()) blocking.push("Add the link people should join.");
  }

  const save = useSubmit(async (acknowledge: boolean = false) => {
    if (!draft || !base) return;
    const weeklyChanged = JSON.stringify([draft.week, draft.zone]) !== JSON.stringify([base.week, base.zone]);
    const prices = draft.pricing === "paid" ? draft.lengths.flatMap((n) => (toMinor(draft.prices[n] ?? "") ? [{ length_minutes: n, price_minor: toMinor(draft.prices[n] ?? "")! }] : [])) : [];
    const putWeekly = () => unwrap(api.PUT("/api/v1/me/mentor/availability", { body: { weekly: windowsFrom(draft.week), timezone: draft.zone, acknowledge } }));
    const putSettings = () =>
      unwrap(
        api.PUT("/api/v1/me/mentor/settings", {
          body: {
            session_lengths: draft.lengths,
            default_length: draft.lengths.includes(draft.defaultLength) ? draft.defaultLength : draft.lengths[0],
            buffer_minutes: draft.buffer,
            min_notice_hours: draft.notice,
            max_per_week: draft.maxPerWeek,
            booking_window_days: draft.windowDays,
            accepting_new: draft.accepting,
            pricing_mode: draft.pricing,
            currency: draft.pricing === "paid" ? draft.currency : "",
            default_price_minor: draft.pricing === "paid" ? toMinor(draft.price) : null,
            prices,
            meeting_provider: draft.provider,
            personal_link: draft.provider === "personal" ? draft.link.trim() : "",
            about: draft.about.trim(),
            expertise: split(draft.expertise),
            topics: split(draft.topics),
            languages: draft.languages as never,
            stages: draft.stages,
            industries: draft.industries,
            acknowledge,
          },
        }),
      );
    try {
      // Switching mentoring off goes first, so an empty week is allowed; otherwise the week goes first.
      if (!draft.accepting) {
        await putSettings();
        if (weeklyChanged) await putWeekly();
      } else {
        if (weeklyChanged) await putWeekly();
        await putSettings();
      }
    } catch (error) {
      const sessions = conflictOf(error);
      if (sessions) {
        setConflict(sessions);
        return;
      }
      throw error;
    }
    setConflict(null);
    toast.show("Changes saved");
    resetAfterSave.current = true;
    setVersion(null);
    await client.invalidateQueries({ queryKey: ["me", "mentor"] });
    await client.invalidateQueries({ queryKey: ["slots"] });
  });
  const errors = errorsFrom(save.error).fields;

  if (query.isPending) return <SkeletonRows />;
  if (query.isError || !setup || !draft || !base) {
    return query.error instanceof ApiError && query.error.status === 403 ? (
      <Alert tone="info" title="Mentorship settings are for approved mentors">
        Apply to become a mentor from the Mentors page. Once you are approved, this section opens.
      </Alert>
    ) : (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  }

  const zone = zoneLabel(draft.zone);
  const lengthsOffered = draft.lengths.slice().sort((a, b) => a - b);
  const money = toMinor(draft.price);

  return (
    <div className="wo-mentorset">
      <PageHeader
        eyebrow="Settings"
        title="Mentorship"
        lead="Set when you can be booked, for how long and at what price. Mentees see times in their own zone."
        actions={
          <Button variant="secondary" icon={<Eye size={16} strokeWidth={1.5} />} onClick={() => setPreviewing(true)}>
            Preview as mentee
          </Button>
        }
      />
      {!setup.accepting_new ? (
        <Alert tone="warning" title="You are not accepting new mentees">
          Your schedule is kept, and nobody can book until you turn this on in Mentoring profile below.
        </Alert>
      ) : null}
      <FormError error={save.error} listFields />

      <Card>
        <h2 className="h3" id="availability">Availability</h2>
        <WeeklyEditor week={draft.week} onChange={(w) => set("week", w)} zone={draft.zone} onZone={(z) => set("zone", z)} minimum={Math.min(...draft.lengths, 60)} />
        {errors.weekly ? <p className="wo-error" role="alert">{errors.weekly}</p> : null}
      </Card>

      <Card>
        <h2 className="h3" id="sessions">Session settings</h2>
        <div className="app-stack">
          <fieldset className="wo-fieldset">
            <legend className="wo-label">Lengths you offer</legend>
            <div className="app-cluster">
              {setup.options.lengths.map((n) => (
                <Checkbox
                  key={n}
                  label={`${n} minutes`}
                  checked={draft.lengths.includes(n)}
                  onChange={() => {
                    const next = toggle(draft.lengths, n).sort((a, b) => a - b);
                    setDraft((d) => (d ? { ...d, lengths: next, defaultLength: next.includes(d.defaultLength) ? d.defaultLength : (next[0] ?? d.defaultLength) } : d));
                  }}
                />
              ))}
            </div>
            {errors.session_lengths ? <p className="wo-error" role="alert">{errors.session_lengths}</p> : null}
          </fieldset>
          <div className="app-formgrid">
            <Select label="Usual length" options={lengthsOffered.map((n) => ({ value: String(n), label: `${n} minutes` }))} value={String(draft.defaultLength)} onChange={(e) => set("defaultLength", Number(e.target.value))} />
            <Select label="Buffer between sessions" options={setup.options.buffers.map((n) => ({ value: String(n), label: n === 0 ? "None" : `${n} minutes` }))} value={String(draft.buffer)} onChange={(e) => set("buffer", Number(e.target.value))} />
            <Select label="Minimum notice" options={setup.options.notice_hours.map((n) => ({ value: String(n), label: hours(n) }))} value={String(draft.notice)} onChange={(e) => set("notice", Number(e.target.value))} />
            <Select label="Booking window" hint="How far ahead people can book." options={setup.options.window_days.map((n) => ({ value: String(n), label: `${n} days` }))} value={String(draft.windowDays)} onChange={(e) => set("windowDays", Number(e.target.value))} />
            <Input label="Most sessions a week" type="number" min={1} max={20} value={String(draft.maxPerWeek)} onChange={(e) => set("maxPerWeek", Math.max(1, Math.min(20, Number(e.target.value) || 1)))} error={errors.max_per_week} />
          </div>
        </div>
      </Card>

      <Card>
        <h2 className="h3" id="timeoff">Time off and extra time</h2>
        <TimeOff items={setup.exceptions} zone={draft.zone} onChanged={async () => { setVersion(null); await client.invalidateQueries({ queryKey: ["me", "mentor"] }); }} />
      </Card>

      <Card>
        <h2 className="h3" id="pricing">Pricing</h2>
        <div className="app-stack">
          <div className="app-cluster" role="radiogroup" aria-label="Pricing">
            <Radio name="pricing" label="Free" checked={draft.pricing === "free"} onChange={() => set("pricing", "free")} />
            <Radio name="pricing" label="Paid" checked={draft.pricing === "paid"} onChange={() => set("pricing", "paid")} />
          </div>
          {draft.pricing === "paid" ? (
            <>
              <div className="app-formgrid">
                <Select label="Currency" options={setup.options.currencies.map((c) => ({ value: c, label: c }))} value={draft.currency} onChange={(e) => set("currency", e.target.value)} error={errors.currency} />
                <Input label="Price per session" inputMode="decimal" value={draft.price} onChange={(e) => set("price", e.target.value)} hint="The usual price, in whole units." error={errors.default_price_minor} />
              </div>
              <fieldset className="wo-fieldset">
                <legend className="wo-label">A different price for a length (optional)</legend>
                <div className="app-formgrid">
                  {lengthsOffered.map((n) => (
                    <Input key={n} label={`${n} minutes`} inputMode="decimal" placeholder={draft.price} value={draft.prices[n] ?? ""} onChange={(e) => set("prices", { ...draft.prices, [n]: e.target.value })} />
                  ))}
                </div>
              </fieldset>
              <Alert tone="info" title="Payment is arranged directly">
                Online payment is not switched on. Mentees ask for a paid session, you confirm it, and you settle the fee with them. The price is shown so they know what to expect, and notices say "Payment arranged directly".
              </Alert>
              <div className="wo-pricepreview" aria-label="How mentees will see your price">
                <p className="caption app-muted" style={{ margin: 0 }}>How mentees will see it</p>
                {lengthsOffered.map((n) => {
                  const own = toMinor(draft.prices[n] ?? "") ?? money;
                  return (
                    <p key={n} style={{ margin: 0 }}>
                      {n} minutes: <strong>{own ? formatMoney(own, draft.currency) : "Set a price"}</strong>
                    </p>
                  );
                })}
              </div>
            </>
          ) : (
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              Mentees see "Free" on each time.
            </p>
          )}
        </div>
      </Card>

      <Card>
        <h2 className="h3" id="meeting">Meeting</h2>
        <div className="app-stack">
          <div className="app-cluster" role="radiogroup" aria-label="Where sessions happen">
            {PROVIDERS.filter(([id]) => id === "personal" || setup.meeting_providers.includes(id)).map(([id, label]) => (
              <Radio key={id} name="provider" label={label} checked={draft.provider === id} onChange={() => set("provider", id)} />
            ))}
          </div>
          {draft.provider === "personal" ? (
            <Input label="Your meeting link" value={draft.link} onChange={(e) => set("link", e.target.value)} hint="Used for every confirmed session." error={errors.personal_link} />
          ) : (
            <p className="body-sm app-muted" style={{ margin: 0 }}>
              A meeting is made for each confirmed session and its link is sent to you both.
            </p>
          )}
          <CalendarCard />
        </div>
      </Card>

      <Card>
        <h2 className="h3" id="profile">Mentoring profile</h2>
        <div className="app-stack">
          <Switch label="Accepting new mentees" checked={draft.accepting} onChange={(e) => set("accepting", e.target.checked)} />
          <p className="caption app-muted" style={{ margin: 0 }}>
            Turn this off to pause booking without losing your schedule. Sessions already agreed carry on.
          </p>
          <Textarea label="About you" rows={4} maxLength={1000} value={draft.about} onChange={(e) => set("about", e.target.value)} error={errors.about} />
          <Input label="Expertise" hint="Separate with commas. Up to 8." value={draft.expertise} onChange={(e) => set("expertise", e.target.value)} error={errors.expertise} />
          <Input label="Topics you like to cover" hint="Separate with commas. Up to 10." value={draft.topics} onChange={(e) => set("topics", e.target.value)} error={errors.topics} />
          <fieldset className="wo-fieldset">
            <legend className="wo-label">Languages</legend>
            <div className="app-cluster">
              {LANGUAGES.map(([code, name]) => (
                <Checkbox key={code} label={name} checked={draft.languages.includes(code)} onChange={() => set("languages", toggle(draft.languages, code))} />
              ))}
            </div>
            {errors.languages ? <p className="wo-error" role="alert">{errors.languages}</p> : null}
          </fieldset>
          <fieldset className="wo-fieldset">
            <legend className="wo-label">Stages you mentor</legend>
            <div className="app-cluster">
              {(stages.data ?? []).map((o) => (
                <Checkbox key={o.value} label={o.label} checked={draft.stages.includes(o.value)} onChange={() => set("stages", toggle(draft.stages, o.value))} />
              ))}
            </div>
          </fieldset>
          <fieldset className="wo-fieldset">
            <legend className="wo-label">Sectors you mentor</legend>
            <div className="app-cluster">
              {(sectors.data ?? []).map((o) => (
                <Checkbox key={o.value} label={o.label} checked={draft.industries.includes(o.value)} onChange={() => set("industries", toggle(draft.industries, o.value))} />
              ))}
            </div>
          </fieldset>
        </div>
      </Card>

      {dirty ? (
        <div className="wo-savebar" role="region" aria-label="Unsaved changes">
          <p className="wo-savebar__text" role="status">
            {blocking[0] ?? "You have unsaved changes."}
          </p>
          <div className="app-cluster" style={{ flexWrap: "nowrap" }}>
            <Button variant="ghost" onClick={() => setDraft(base)}>
              Discard
            </Button>
            <Button loading={save.busy} disabled={blocking.length > 0} onClick={() => void save.run(false)}>
              Save changes
            </Button>
          </div>
        </div>
      ) : null}

      {conflict ? <ConflictDialog sessions={conflict} onKeep={() => save.run(true).then(() => undefined)} onClose={() => setConflict(null)} /> : null}

      <Drawer open={previewing} onOpenChange={setPreviewing} size="lg" eyebrow="Preview" title="As a mentee sees it" subtitle={`Your times, shown in the viewer's own zone. ${summarise(draft.week, zone)}`}>
        <div className="app-stack">
          {dirty ? (
            <Alert tone="warning" title="Unsaved changes">
              The preview shows what is saved. Save your changes to see them here.
            </Alert>
          ) : null}
          <BookingCalendar mentorId="me" initialZone={browserZone()} />
        </div>
      </Drawer>
    </div>
  );
}

