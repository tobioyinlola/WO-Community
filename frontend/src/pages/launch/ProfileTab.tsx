import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, unwrap } from "../../api/client";
import { ApiError } from "../../api/errors";
import { useCountries, useSectors, withPlaceholder } from "../../api/reference";
import { Alert, Button, Card, Input, Modal, Select, Textarea } from "../../components";
import { humanise } from "../../lib/format";
import { ChipSelect, StringList, fromMinor, toMinor } from "../../ui/fields";
import { Loaded, SkeletonRows } from "../../ui/blocks";
import { errorsFrom, FormError, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";
import { packageKey, useWorkspace } from "./Workspace";

type Fields = Record<string, unknown>;

const STAGES = ["idea", "prototype", "launched", "revenue"];
const PRODUCT = ["concept", "in_development", "beta", "live"];
const CUSTOMERS = ["consumers", "businesses", "government", "mixed"];
const REGIONS = ["africa", "north_america", "europe", "latin_america", "middle_east"];
const MODELS = ["subscription", "transaction_fee", "marketplace_commission", "product_sales", "services", "licensing", "advertising", "other"];
const CURRENCIES = ["NGN", "KES", "GHS", "ZAR", "EGP", "USD"];
const PERIODS = ["one_off", "day", "week", "month", "quarter", "year"];
const SUGGESTIBLE = new Set(["one_liner", "startup_idea", "business_concept", "target_customer", "problem", "problem_today", "problem_evidence", "solution", "differentiator", "sales_channel"]);

const opts = (list: string[]) => list.map((v) => ({ value: v, label: humanise(v) }));
const str = (v: unknown) => (typeof v === "string" ? v : "");
const arr = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : []);
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

interface PricePoint {
  label: string;
  amount_minor: number;
  currency: string;
  period: string;
}

function SuggestDialog({ ventureId, field, label, onPick, onClose }: { ventureId: string; field: string; label: string; onPick: (text: string) => void; onClose: () => void }) {
  const [intent, setIntent] = useState("");
  const ask = useSubmit(async () =>
    unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/profile/suggest", { params: { path: { venture_id: ventureId } }, body: { field, intent: intent.trim() } })),
  );
  const [options, setOptions] = useState<string[] | null>(null);
  return (
    <Modal open onClose={onClose} eyebrow="Suggestions" title={`Ways to word ${label.toLowerCase()}`}
      actions={<Button variant="ghost" onClick={onClose}>Close</Button>}>
      <div className="app-stack">
        <p className="body-sm app-muted" style={{ margin: 0 }}>These are only suggestions. Nothing is saved until you choose one and save the profile.</p>
        <FormError error={ask.error} />
        <Input label="What should it stress? (optional)" placeholder="for example: clearer, shorter, more about the customer" value={intent} onChange={(e) => setIntent(e.target.value)} />
        <div><Button size="sm" loading={ask.busy} onClick={async () => { const r = await ask.run(); if (r) setOptions(r.suggestions); }}>Suggest wording</Button></div>
        {options?.map((text) => (
          <Card key={text} variant="white">
            <p className="body" style={{ margin: "0 0 var(--space-3)" }}>{text}</p>
            <Button size="sm" variant="secondary" onClick={() => { onPick(text); onClose(); }}>Use this</Button>
          </Card>
        ))}
        {options && options.length === 0 ? <p className="body app-muted">No suggestions this time. Try adding a note about what to stress.</p> : null}
      </div>
    </Modal>
  );
}

function FillFromText({ ventureId, onApply, onClose }: { ventureId: string; onApply: (fields: Fields) => void; onClose: () => void }) {
  const [text, setText] = useState("");
  const [proposed, setProposed] = useState<Fields | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const ask = useSubmit(async () =>
    unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/profile/fill-from-text", { params: { path: { venture_id: ventureId } }, body: { text: text.trim() } })),
  );
  return (
    <Modal open onClose={onClose} eyebrow="Save time" title="Fill from a few sentences"
      actions={
        proposed ? (
          <>
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button disabled={chosen.length === 0} onClick={() => { onApply(Object.fromEntries(chosen.map((k) => [k, proposed[k]]))); onClose(); }}>Use selected</Button>
          </>
        ) : <Button variant="ghost" onClick={onClose}>Cancel</Button>
      }>
      <div className="app-stack">
        {!proposed ? (
          <>
            <p className="body-sm app-muted" style={{ margin: 0 }}>Describe the venture in your own words. We propose answers; you choose which to keep.</p>
            <FormError error={ask.error} />
            <Textarea label="Tell us about it" rows={6} value={text} onChange={(e) => setText(e.target.value)} />
            <div><Button loading={ask.busy} disabled={text.trim().length < 20} onClick={async () => { const r = await ask.run(); if (r) { setProposed(r.proposed); setChosen(Object.keys(r.proposed)); } }}>Propose answers</Button></div>
          </>
        ) : Object.keys(proposed).length === 0 ? (
          <p className="body app-muted">Nothing could be taken from that. Try adding who it is for and what problem it solves.</p>
        ) : (
          Object.entries(proposed).map(([key, value]) => (
            <label key={key} className="wo-check" style={{ alignItems: "flex-start" }}>
              <input type="checkbox" checked={chosen.includes(key)} onChange={() => setChosen(chosen.includes(key) ? chosen.filter((k) => k !== key) : [...chosen, key])} />
              <strong>{humanise(key)}</strong>
              <span className="body-sm" style={{ display: "block" }}>{typeof value === "string" ? value : JSON.stringify(value)}</span>
            </label>
          ))
        )}
      </div>
    </Modal>
  );
}

export default function ProfileTab() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const countries = useCountries();
  const sectors = useSectors();
  const query = useQuery({
    queryKey: ["toolkit", ventureId, "profile"],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/profile", { params: { path: { venture_id: ventureId } } })),
  });
  const [draft, setDraft] = useState<Fields>({});
  const [version, setVersion] = useState(0);
  const [suggest, setSuggest] = useState<{ field: string; label: string } | null>(null);
  const [filling, setFilling] = useState(false);

  useEffect(() => {
    if (!query.data) return;
    setDraft(query.data.fields);
    setVersion(query.data.version);
  }, [query.data]);

  const changed = useMemo(() => {
    const original = query.data?.fields ?? {};
    return Object.keys({ ...original, ...draft }).filter((k) => JSON.stringify(original[k] ?? null) !== JSON.stringify(draft[k] ?? null));
  }, [query.data, draft]);
  const set = (key: string, value: unknown) => setDraft((d) => ({ ...d, [key]: value }));

  const save = useSubmit(async () => {
    const patch: Fields = {};
    for (const key of changed) {
      const v = draft[key];
      patch[key] = v === undefined || v === "" ? null : v;
    }
    const result = await unwrap(api.PATCH("/api/v1/toolkit/ventures/{venture_id}/profile", { params: { path: { venture_id: ventureId } }, body: { fields: patch, base_version: version } }));
    client.setQueryData(["toolkit", ventureId, "profile"], result.profile);
    await client.invalidateQueries({ queryKey: packageKey(ventureId) });
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
    toast.show("Profile saved");
  });
  const errors = errorsFrom(save.error).fields;
  const stale = save.error instanceof ApiError && save.error.status === 409;
  const text = (key: string, label: string, props: { rows?: number; hint?: string } = {}) => (
    <div className="app-stack" style={{ gap: "var(--space-1)" }}>
      <Textarea label={label} rows={props.rows ?? 3} hint={props.hint} value={str(draft[key])} onChange={(e) => set(key, e.target.value)} error={errors[key]} />
      {SUGGESTIBLE.has(key) ? <div><button type="button" className="app-linklike" onClick={() => setSuggest({ field: key, label })}><Sparkles size={14} strokeWidth={1.5} aria-hidden="true" /> Suggest wording</button></div> : null}
    </div>
  );

  const prices = (Array.isArray(draft.price_points) ? draft.price_points : []) as PricePoint[];
  const traction = obj(draft.traction);
  const funding = obj(draft.funding);
  const setObj = (key: string, current: Record<string, unknown>, field: string, value: unknown) => {
    const next = { ...current, [field]: value };
    if (value === "" || value === null) delete next[field];
    set(key, Object.keys(next).length ? next : null);
  };
  const regions = arr(draft.target_regions);

  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(profile) => (
        <form className="app-split" noValidate onSubmit={(e) => { e.preventDefault(); void save.run(); }}>
          <div className="app-stack app-stack--lg">
            {stale ? (
              <Alert tone="warning" title="This changed somewhere else" action={<Button size="sm" variant="secondary" onClick={() => void query.refetch()}>Reload</Button>}>
                Reload to see the latest, then make your change again.
              </Alert>
            ) : <FormError error={save.error} />}
            <div className="app-cluster">
              <Button variant="secondary" size="sm" icon={<Sparkles size={16} strokeWidth={1.5} aria-hidden="true" />} onClick={() => setFilling(true)}>Fill from a few sentences</Button>
            </div>
            <Card>
              <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>The venture</h2>
              <div className="app-stack">
                <div className="app-formgrid">
                  <Input label="Name" value={str(draft.name)} onChange={(e) => set("name", e.target.value)} error={errors.name} />
                  <Input label="One line description" maxLength={160} value={str(draft.one_liner)} onChange={(e) => set("one_liner", e.target.value)} error={errors.one_liner} />
                  <Select label="Country" options={withPlaceholder(countries.data)} value={str(draft.country)} onChange={(e) => set("country", e.target.value)} error={errors.country} />
                  <Input label="City" value={str(draft.city)} onChange={(e) => set("city", e.target.value)} error={errors.city} />
                  <Select label="Sector" options={withPlaceholder(sectors.data)} value={str(draft.sector)} onChange={(e) => set("sector", e.target.value)} error={errors.sector} />
                  <Select label="Stage" options={[{ value: "", label: "Choose one" }, ...opts(STAGES)]} value={str(draft.stage)} onChange={(e) => set("stage", e.target.value)} error={errors.stage} />
                  <Select label="Product status" options={[{ value: "", label: "Choose one" }, ...opts(PRODUCT)]} value={str(draft.product_status)} onChange={(e) => set("product_status", e.target.value)} error={errors.product_status} />
                </div>
                {SUGGESTIBLE.has("one_liner") ? <div><button type="button" className="app-linklike" onClick={() => setSuggest({ field: "one_liner", label: "One line description" })}><Sparkles size={14} strokeWidth={1.5} aria-hidden="true" /> Suggest wording</button></div> : null}
              </div>
            </Card>
            <Card>
              <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>The idea</h2>
              <div className="app-stack">
                {text("startup_idea", "The idea in a few sentences", { rows: 4, hint: "At least 20 characters." })}
                {text("business_concept", "How the business works (optional)")}
                {text("target_customer", "Who is it for?")}
                <div className="app-formgrid">
                  <Select label="Type of customer" options={[{ value: "", label: "Choose one" }, ...opts(CUSTOMERS)]} value={str(draft.customer_type)} onChange={(e) => set("customer_type", e.target.value)} error={errors.customer_type} />
                  <Input label="How many could you reach?" type="number" min={0} value={typeof draft.estimated_customers === "number" ? String(draft.estimated_customers) : ""} onChange={(e) => set("estimated_customers", e.target.value === "" ? null : Number(e.target.value))} error={errors.estimated_customers} />
                </div>
                <ChipSelect legend="Where will you sell?" options={opts(REGIONS)} value={regions} onChange={(v) => set("target_regions", v)} error={errors.target_regions} />
                {regions.includes("africa") ? (
                  <ChipSelect
                    legend="Which African countries?"
                    options={(countries.data ?? []).filter((c) => ["NG", "KE", "GH", "ZA", "EG", "TZ", "UG", "RW", "SN", "CI", "ET", "MA", "DZ", "TN", "CM", "ZM", "ZW", "BW", "NA", "MZ"].includes(c.value))}
                    value={arr(draft.target_countries)}
                    onChange={(v) => set("target_countries", v)}
                    error={errors.target_countries}
                  />
                ) : null}
              </div>
            </Card>
            <Card>
              <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Problem and solution</h2>
              <div className="app-stack">
                {text("problem", "The problem", { rows: 4, hint: "At least 20 characters." })}
                {text("problem_today", "How people cope today")}
                {text("problem_evidence", "What shows the problem is real")}
                {text("solution", "Your solution", { rows: 4, hint: "At least 20 characters." })}
                {text("differentiator", "What makes you different")}
                <StringList label="How it works" max={10} value={arr(draft.how_it_works)} onChange={(v) => set("how_it_works", v)} placeholder="One step" error={errors.how_it_works} />
                <StringList label="Key features" max={6} value={arr(draft.key_features)} onChange={(v) => set("key_features", v)} placeholder="One feature" error={errors.key_features} />
              </div>
            </Card>
            <Card>
              <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Business model</h2>
              <div className="app-stack">
                <ChipSelect legend="How will you earn?" options={opts(MODELS)} value={arr(draft.revenue_models)} onChange={(v) => set("revenue_models", v)} error={errors.revenue_models} />
                <div className="app-stack">
                  <span className="wo-label">Prices</span>
                  {prices.map((p, i) => (
                    <div key={i} className="app-formgrid" style={{ gridTemplateColumns: "2fr 1.4fr 1fr 1fr auto", alignItems: "end" }}>
                      <Input label="Name" value={p.label} onChange={(e) => set("price_points", prices.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                      <Input label="Amount" inputMode="decimal" value={fromMinor(p.amount_minor)} onChange={(e) => set("price_points", prices.map((x, j) => (j === i ? { ...x, amount_minor: toMinor(e.target.value) ?? 0 } : x)))} />
                      <Select label="Currency" options={CURRENCIES.map((c) => ({ value: c, label: c }))} value={p.currency} onChange={(e) => set("price_points", prices.map((x, j) => (j === i ? { ...x, currency: e.target.value } : x)))} />
                      <Select label="Per" options={opts(PERIODS)} value={p.period} onChange={(e) => set("price_points", prices.map((x, j) => (j === i ? { ...x, period: e.target.value } : x)))} />
                      <Button variant="ghost" onClick={() => set("price_points", prices.filter((_, j) => j !== i))} aria-label={`Remove price ${p.label}`}>Remove</Button>
                    </div>
                  ))}
                  {errors.price_points ? <p className="wo-error" style={{ margin: 0 }}><span aria-hidden="true">!</span>{errors.price_points}</p> : null}
                  <div><Button variant="secondary" size="sm" onClick={() => set("price_points", [...prices, { label: "", amount_minor: 0, currency: str(traction.currency) || "NGN", period: "month" }])}>Add a price</Button></div>
                </div>
                {text("sales_channel", "How customers will find and buy", { rows: 2 })}
              </div>
            </Card>
            <Card>
              <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Traction and funding</h2>
              <div className="app-stack">
                <div className="app-formgrid">
                  <Input label="Users or customers" type="number" min={0} value={typeof traction.users === "number" ? String(traction.users) : ""} onChange={(e) => setObj("traction", traction, "users", e.target.value === "" ? "" : Number(e.target.value))} error={errors["traction.users"]} />
                  <Input label="Pilots" type="number" min={0} value={typeof traction.pilots === "number" ? String(traction.pilots) : ""} onChange={(e) => setObj("traction", traction, "pilots", e.target.value === "" ? "" : Number(e.target.value))} />
                  <Input label="Partnerships" type="number" min={0} value={typeof traction.partnerships === "number" ? String(traction.partnerships) : ""} onChange={(e) => setObj("traction", traction, "partnerships", e.target.value === "" ? "" : Number(e.target.value))} />
                  <Input label="Revenue to date" inputMode="decimal" value={fromMinor(traction.revenue_minor)} onChange={(e) => setObj("traction", traction, "revenue_minor", toMinor(e.target.value) ?? "")} error={errors["traction.revenue_minor"]} />
                  <Select label="Currency of revenue" options={CURRENCIES.map((c) => ({ value: c, label: c }))} value={str(traction.currency) || "NGN"} onChange={(e) => setObj("traction", traction, "currency", e.target.value)} />
                </div>
                <div className="app-formgrid">
                  <Input label="How much are you raising?" inputMode="decimal" value={fromMinor(funding.amount_minor)} onChange={(e) => setObj("funding", funding, "amount_minor", toMinor(e.target.value) ?? "")} error={errors["funding.amount_minor"]} />
                  <Select label="Currency" options={CURRENCIES.map((c) => ({ value: c, label: c }))} value={str(funding.currency) || "NGN"} onChange={(e) => setObj("funding", funding, "currency", e.target.value)} />
                </div>
                <StringList label="What the money is for" max={8} value={arr(funding.use_of_funds)} onChange={(v) => setObj("funding", funding, "use_of_funds", v.length ? v : "")} placeholder="for example: hiring two engineers" />
              </div>
            </Card>
            <CompetitorsAndTeam />
          </div>
          <aside className="app-stack" style={{ position: "sticky", top: "calc(var(--header-height) + var(--space-4))" }}>
            <Card>
              <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Profile strength</h2>
              <div className="app-meter" role="progressbar" aria-valuenow={profile.completeness} aria-valuemin={0} aria-valuemax={100} aria-label="Profile strength"><span style={{ width: `${profile.completeness}%` }} /></div>
              <p className="body-sm app-muted" style={{ margin: "var(--space-2) 0 var(--space-4)" }}>
                {profile.missing_required.length > 0 ? `Still needed for a score: ${profile.missing_required.map((f) => humanise(f).toLowerCase()).join(", ")}.` : "You have what is needed for a score."}
              </p>
              <Button size="lg" type="submit" loading={save.busy} disabled={changed.length === 0} style={{ width: "100%" }}>
                {changed.length === 0 ? "Saved" : `Save ${changed.length} change${changed.length > 1 ? "s" : ""}`}
              </Button>
              <p className="caption app-faint" style={{ margin: "var(--space-3) 0 0" }}>Saving marks anything made from the changed answers as out of date, so you know to refresh it.</p>
            </Card>
          </aside>
          {suggest ? <SuggestDialog ventureId={ventureId} field={suggest.field} label={suggest.label} onClose={() => setSuggest(null)} onPick={(t) => set(suggest.field, t)} /> : null}
          {filling ? <FillFromText ventureId={ventureId} onClose={() => setFilling(false)} onApply={(f) => setDraft((d) => ({ ...d, ...f }))} /> : null}
        </form>
      )}
    </Loaded>
  );
}

function CompetitorsAndTeam() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const competitors = useQuery({ queryKey: ["toolkit", ventureId, "competitors"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/competitors", { params: { path: { venture_id: ventureId } } })) });
  const team = useQuery({ queryKey: ["toolkit", ventureId, "team"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/team", { params: { path: { venture_id: ventureId } } })) });
  const [c, setC] = useState({ name: "", website: "", differentiator: "" });
  const [t, setT] = useState({ name: "", role: "", linkedin: "", is_founder: false });
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId] });
  };
  const addC = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/competitors", { params: { path: { venture_id: ventureId } }, body: { name: c.name.trim(), website: c.website.trim(), differentiator: c.differentiator.trim() } }));
    setC({ name: "", website: "", differentiator: "" });
    await refresh();
  });
  const addT = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/team", { params: { path: { venture_id: ventureId } }, body: { name: t.name.trim(), role: t.role.trim(), linkedin: t.linkedin.trim(), is_founder: t.is_founder } }));
    setT({ name: "", role: "", linkedin: "", is_founder: false });
    await refresh();
  });
  const delC = useMutation({ mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}/competitors/{competitor_id}", { params: { path: { venture_id: ventureId, competitor_id: id } } })), onSuccess: refresh });
  const delT = useMutation({ mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/toolkit/ventures/{venture_id}/team/{member_id}", { params: { path: { venture_id: ventureId, member_id: id } } })), onSuccess: refresh });
  return (
    <>
      <Card>
        <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Competitors</h2>
        <div className="app-stack">
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {competitors.data?.map((x) => (
              <li key={x.id} className="app-cluster" style={{ flexWrap: "nowrap" }}>
                <span style={{ flex: 1 }}><strong>{x.name}</strong>{x.differentiator ? <span className="app-muted"> &mdash; {x.differentiator}</span> : null}</span>
                <Button variant="ghost" size="sm" onClick={() => delC.mutate(x.id)} aria-label={`Remove ${x.name}`}>Remove</Button>
              </li>
            ))}
          </ul>
          <FormError error={addC.error} />
          <div className="app-formgrid">
            <Input label="Competitor name" value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} />
            <Input label="Website" value={c.website} onChange={(e) => setC({ ...c, website: e.target.value })} />
            <div className="app-span"><Input label="How are you different?" value={c.differentiator} onChange={(e) => setC({ ...c, differentiator: e.target.value })} /></div>
          </div>
          <div><Button variant="secondary" size="sm" loading={addC.busy} disabled={!c.name.trim()} onClick={() => void addC.run()}>Add competitor</Button></div>
        </div>
      </Card>
      <Card>
        <h2 className="h3" style={{ margin: "0 0 var(--space-4)" }}>Team</h2>
        <div className="app-stack">
          <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {team.data?.map((x) => (
              <li key={x.id} className="app-cluster" style={{ flexWrap: "nowrap" }}>
                <span style={{ flex: 1 }}><strong>{x.name}</strong> <span className="app-muted">{x.role}{x.is_founder ? ", founder" : ""}</span></span>
                <Button variant="ghost" size="sm" onClick={() => delT.mutate(x.id)} aria-label={`Remove ${x.name}`}>Remove</Button>
              </li>
            ))}
          </ul>
          <FormError error={addT.error} />
          <div className="app-formgrid">
            <Input label="Name" value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} />
            <Input label="Role" value={t.role} onChange={(e) => setT({ ...t, role: e.target.value })} />
            <Input label="LinkedIn (optional)" value={t.linkedin} onChange={(e) => setT({ ...t, linkedin: e.target.value })} />
            <label className="wo-check" style={{ alignSelf: "end", minHeight: 52 }}><input type="checkbox" checked={t.is_founder} onChange={(e) => setT({ ...t, is_founder: e.target.checked })} />A founder</label>
          </div>
          <div><Button variant="secondary" size="sm" loading={addT.busy} disabled={!t.name.trim() || !t.role.trim()} onClick={() => void addT.run()}>Add team member</Button></div>
        </div>
      </Card>
    </>
  );
}
