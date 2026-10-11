import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, unwrap } from "../../api/client";
import { ApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, Input, Select } from "../../components";
import { formatDate, formatMoney, humanise } from "../../lib/format";
import { fromMinor, toMinor } from "../../ui/fields";
import { EmptyState, Loaded, SkeletonRows } from "../../ui/blocks";
import { FormError, errorsFrom, useSubmit } from "../../ui/forms";
import { useToast } from "../../ui/Toast";
import { useExport } from "./jobs";
import { packageKey, useWorkspace } from "./Workspace";

type Assumptions = Record<string, unknown> & { drivers?: Record<string, number>; costs?: Record<string, unknown> };
type Salary = { role: string; monthly_minor: number; count: number; start_month: number };
type Fixed = { label: string; monthly_minor: number };
const CURRENCIES = ["NGN", "KES", "GHS", "ZAR", "EGP", "USD"];
const SCENARIOS = ["conservative", "base", "optimistic"] as const;
type Scenario = (typeof SCENARIOS)[number];

const num = (v: unknown, fallback = 0) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);

/** Revenue and cash over 24 months as two lines, drawn with theme tokens so it follows light and dark. */
function Chart({ months, currency }: { months: Array<{ month: number; revenue: number; cash_end: number }>; currency: string }) {
  const W = 640;
  const H = 220;
  const pad = { l: 8, r: 8, t: 12, b: 24 };
  const values = months.flatMap((m) => [m.revenue, m.cash_end, 0]);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const x = (i: number) => pad.l + (i / Math.max(months.length - 1, 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - (v - min) / (max - min || 1)) * (H - pad.t - pad.b);
  const line = (pick: (m: (typeof months)[number]) => number) => months.map((m, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(pick(m)).toFixed(1)}`).join(" ");
  const last = months[months.length - 1];
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Revenue and cash over ${months.length} months. Month ${last?.month} revenue ${formatMoney(last?.revenue ?? 0, currency)}, cash ${formatMoney(last?.cash_end ?? 0, currency)}.`} style={{ width: "100%", height: "auto", display: "block" }}>
        <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} stroke="var(--border-default)" strokeWidth="1" />
        <path d={line((m) => m.cash_end)} fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeDasharray="5 4" />
        <path d={line((m) => m.revenue)} fill="none" stroke="var(--accent-fill)" strokeWidth="3" />
        {[1, 12, 24].filter((n) => n <= months.length).map((n) => (
          <text key={n} x={x(n - 1)} y={H - 6} textAnchor={n === 1 ? "start" : n === 24 ? "end" : "middle"} fill="var(--text-muted)" fontSize="12">Month {n}</text>
        ))}
      </svg>
      <figcaption className="caption app-muted" style={{ marginTop: "var(--space-2)" }}>
        <span style={{ color: "var(--text-primary)" }}>Solid line</span>: revenue. <span style={{ color: "var(--text-primary)" }}>Dashed line</span>: cash in the bank.
      </figcaption>
    </figure>
  );
}

export default function ForecastTab() {
  const { ventureId } = useWorkspace();
  const client = useQueryClient();
  const toast = useToast();
  const [scenario, setScenario] = useState<Scenario>("base");
  const [draft, setDraft] = useState<Assumptions | null>(null);
  const [version, setVersion] = useState(0);
  const [proposals, setProposals] = useState<Awaited<ReturnType<typeof suggestCall>> | null>(null);

  const forecast = useQuery({
    queryKey: ["toolkit", ventureId, "forecast"],
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/forecast", { params: { path: { venture_id: ventureId } } }));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
  const templates = useQuery({ queryKey: ["toolkit", "forecast-templates"], queryFn: () => unwrap(api.GET("/api/v1/toolkit/forecast-templates")), staleTime: 3_600_000 });
  const result = useQuery({
    queryKey: ["toolkit", ventureId, "forecast", "result", scenario, forecast.data?.version],
    enabled: Boolean(forecast.data),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/forecast/result", { params: { path: { venture_id: ventureId }, query: { scenario } } })),
  });
  const scenarios = useQuery({
    queryKey: ["toolkit", ventureId, "forecast", "scenarios", forecast.data?.version],
    enabled: Boolean(forecast.data),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/forecast/scenarios", { params: { path: { venture_id: ventureId } } })),
  });
  const sensitivity = useQuery({
    queryKey: ["toolkit", ventureId, "forecast", "sensitivity", forecast.data?.version],
    enabled: Boolean(forecast.data),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/forecast/sensitivity", { params: { path: { venture_id: ventureId } } })),
  });
  const versions = useQuery({
    queryKey: ["toolkit", ventureId, "forecast", "versions", forecast.data?.version],
    enabled: Boolean(forecast.data),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/forecast/versions", { params: { path: { venture_id: ventureId } } })),
  });

  useEffect(() => {
    if (!forecast.data) return;
    setDraft(forecast.data.assumptions as Assumptions);
    setVersion(forecast.data.version);
  }, [forecast.data]);

  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["toolkit", ventureId, "forecast"] });
    await client.invalidateQueries({ queryKey: packageKey(ventureId) });
  };
  const start = useSubmit(async () => {
    await unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/forecast", { params: { path: { venture_id: ventureId } }, body: {} }));
    await refresh();
  });
  const save = useSubmit(async () => {
    if (!draft) return;
    await unwrap(api.PUT("/api/v1/toolkit/ventures/{venture_id}/forecast", { params: { path: { venture_id: ventureId } }, body: { assumptions: draft as never, base_version: version } }));
    toast.show("Forecast saved");
    await refresh();
  });
  const suggestCall = () => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/forecast/suggest", { params: { path: { venture_id: ventureId } } }));
  const suggest = useSubmit(async () => setProposals(await suggestCall()));
  const exporter = useExport((format) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/forecast/export", { params: { path: { venture_id: ventureId } }, body: { format: format as "xlsx" | "pdf" } })));
  const restore = useMutation({
    mutationFn: (v: number) => unwrap(api.POST("/api/v1/toolkit/ventures/{venture_id}/forecast/versions/{version}/restore", { params: { path: { venture_id: ventureId, version: v } } })),
    onSuccess: async () => { toast.show("Earlier version restored"); await refresh(); },
  });

  const template = templates.data?.find((t) => t.template === draft?.template);
  const currency = String(draft?.currency ?? forecast.data?.currency ?? "NGN");
  const drivers = draft?.drivers ?? {};
  const costs = (draft?.costs ?? {}) as Record<string, unknown>;
  const salaries = (Array.isArray(costs.salaries) ? costs.salaries : []) as Salary[];
  const fixed = (Array.isArray(costs.fixed) ? costs.fixed : []) as Fixed[];
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(forecast.data?.assumptions), [draft, forecast.data]);
  const errors = errorsFrom(save.error).fields;
  const stale = save.error instanceof ApiError && save.error.status === 409;

  const setDriver = (name: string, value: number) => setDraft((d) => (d ? { ...d, drivers: { ...(d.drivers ?? {}), [name]: value } } : d));
  const setCost = (name: string, value: unknown) => setDraft((d) => (d ? { ...d, costs: { ...(d.costs ?? {}), [name]: value } } : d));
  const money = (v: number | undefined) => fromMinor(v ?? 0);

  return (
    <Loaded
      query={forecast}
      skeleton={<SkeletonRows />}
      isEmpty={(d) => !d}
      empty={
        <EmptyState title="Model your first two years" icon={<TrendingUp size={22} strokeWidth={1.5} />} action={<Button loading={start.busy} onClick={() => void start.run()}>Start the forecast</Button>}>
          We begin from your profile: the revenue model, the price and the money you plan to raise. You adjust every number.
          <div style={{ marginTop: "var(--space-3)" }}><FormError error={start.error} /></div>
        </EmptyState>
      }
    >
      {() => (
        <div className="app-stack app-stack--lg">
          <div className="app-cluster" style={{ justifyContent: "space-between" }}>
            <div role="group" aria-label="Scenario" className="app-cluster">
              {SCENARIOS.map((s) => (
                <button key={s} type="button" className="app-react" aria-pressed={scenario === s} onClick={() => setScenario(s)}>{humanise(s)}</button>
              ))}
            </div>
            <div className="app-cluster">
              <Button variant="secondary" size="sm" loading={exporter.busy} onClick={() => void exporter.run("xlsx")}>Download spreadsheet</Button>
              <Button variant="secondary" size="sm" loading={exporter.busy} onClick={() => void exporter.run("pdf")}>Download PDF</Button>
            </div>
          </div>
          <FormError error={exporter.error} />

          <Loaded query={result} skeleton={<SkeletonRows />}>
            {(r) => {
              const s = r.summary as Record<string, number | null>;
              const stat = (label: string, value: string) => (
                <Card key={label}><p className="caption app-muted" style={{ margin: 0 }}>{label}</p><p className="h3" style={{ margin: "var(--space-1) 0 0" }}>{value}</p></Card>
              );
              return (
                <div className="app-stack">
                  {r.warnings.map((w) => <Alert key={w.code} tone={w.severity === "error" ? "danger" : "warning"} title={w.severity === "error" ? "Needs fixing" : "Worth a look"}>{w.message}</Alert>)}
                  <div className="app-grid">
                    {stat("Year 1 revenue", formatMoney(num(s.revenue_year1), r.currency))}
                    {stat("Year 2 revenue", formatMoney(num(s.revenue_year2), r.currency))}
                    {stat("Lowest cash", formatMoney(num(s.lowest_cash), r.currency))}
                    {stat("Break even", s.break_even_month ? `Month ${s.break_even_month}` : "Not within 24 months")}
                    {stat("Cash runs out", s.cash_out_month ? `Month ${s.cash_out_month}` : "It lasts")}
                    {stat("More funding needed", formatMoney(num(s.extra_funding_needed), r.currency))}
                  </div>
                  <Card><Chart months={r.months} currency={r.currency} /></Card>
                  <details>
                    <summary>See the 24 months as a table</summary>
                    <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
                      <table className="app-table">
                        <caption className="wo-visually-hidden">Monthly forecast</caption>
                        <thead><tr><th scope="col">Month</th><th scope="col">Revenue</th><th scope="col">Costs</th><th scope="col">Net income</th><th scope="col">Cash</th></tr></thead>
                        <tbody>
                          {r.months.map((m) => (
                            <tr key={m.month}><th scope="row">{m.month}</th><td>{formatMoney(m.revenue, r.currency)}</td><td>{formatMoney(m.cogs + m.opex, r.currency)}</td><td>{formatMoney(m.net_income, r.currency)}</td><td>{formatMoney(m.cash_end, r.currency)}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                </div>
              );
            }}
          </Loaded>

          {scenarios.data ? (
            <Card>
              <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Three ways it could go</h2>
              <div style={{ overflowX: "auto" }}>
                <table className="app-table">
                  <thead><tr><th scope="col">Scenario</th><th scope="col">Year 2 revenue</th><th scope="col">Lowest cash</th><th scope="col">Break even</th></tr></thead>
                  <tbody>
                    {SCENARIOS.map((name) => {
                      const row = scenarios.data[name] as Record<string, number | null>;
                      return <tr key={name}><th scope="row">{humanise(name)}</th><td>{formatMoney(num(row.revenue_year2), scenarios.data.currency)}</td><td>{formatMoney(num(row.lowest_cash), scenarios.data.currency)}</td><td>{row.break_even_month ? `Month ${row.break_even_month}` : "Not within 24 months"}</td></tr>;
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : null}

          {sensitivity.data && sensitivity.data.length > 0 ? (
            <Card>
              <h2 className="h4" style={{ margin: "0 0 var(--space-2)" }}>What moves the result most</h2>
              <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-3)" }}>Each row nudges one number and shows how much year 2 revenue changes.</p>
              <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: "var(--space-2)" }}>
                {sensitivity.data.slice(0, 6).map((row) => (
                  <li key={row.assumption} className="app-cluster" style={{ justifyContent: "space-between" }}><span>{humanise(row.assumption)}</span><Badge variant="neutral">{formatMoney(Math.abs(row.impact), currency)}</Badge></li>
                ))}
              </ul>
            </Card>
          ) : null}

          <form className="app-stack app-stack--lg" noValidate onSubmit={(e) => { e.preventDefault(); void save.run(); }}>
            <h2 className="h3" style={{ margin: 0 }}>Your assumptions</h2>
            {stale ? <Alert tone="warning" title="This changed somewhere else" action={<Button size="sm" variant="secondary" onClick={() => void forecast.refetch()}>Reload</Button>}>Reload to see the latest.</Alert> : <FormError error={save.error} />}
            {draft ? (
              <>
                <Card>
                  <div className="app-formgrid">
                    <Select label="Revenue model" options={(templates.data ?? []).map((t) => ({ value: t.template, label: t.label }))} value={String(draft.template ?? "")} onChange={(e) => setDraft({ ...draft, template: e.target.value })} hint={template?.help} />
                    <Select label="Currency" options={CURRENCIES.map((c) => ({ value: c, label: c }))} value={currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value })} />
                    <Input label="Cash at the start" inputMode="decimal" value={fromMinor(draft.opening_cash_minor)} onChange={(e) => setDraft({ ...draft, opening_cash_minor: toMinor(e.target.value) ?? 0 })} error={errors["opening_cash_minor"]} />
                    <Input label="Tax rate (%)" type="number" min={0} max={100} value={String(num(draft.tax_rate_pct))} onChange={(e) => setDraft({ ...draft, tax_rate_pct: Number(e.target.value) })} />
                  </div>
                </Card>
                {template ? (
                  <Card>
                    <h3 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Revenue drivers</h3>
                    <div className="app-formgrid">
                      {template.drivers.map((d) => (
                        <Input
                          key={d.name}
                          label={d.label}
                          hint={d.help}
                          inputMode="decimal"
                          value={d.kind === "money" ? money(drivers[d.name]) : String(drivers[d.name] ?? d.default)}
                          onChange={(e) => setDriver(d.name, d.kind === "money" ? (toMinor(e.target.value) ?? 0) : Number(e.target.value))}
                          error={errors[`drivers.${d.name}`]}
                        />
                      ))}
                    </div>
                  </Card>
                ) : null}
                <Card>
                  <h3 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Costs</h3>
                  <div className="app-stack">
                    <div className="app-formgrid">
                      <Input label="Cost of goods (% of revenue)" type="number" min={0} max={100} value={String(num(costs.cogs_pct))} onChange={(e) => setCost("cogs_pct", Number(e.target.value))} error={errors["costs.cogs_pct"]} />
                      <Input label="Marketing each month" inputMode="decimal" value={fromMinor(costs.marketing_monthly_minor)} onChange={(e) => setCost("marketing_monthly_minor", toMinor(e.target.value) ?? 0)} />
                      <Input label="Marketing growth each month (%)" type="number" min={0} max={100} value={String(num(costs.marketing_growth_pct_month))} onChange={(e) => setCost("marketing_growth_pct_month", Number(e.target.value))} />
                      <Input label="Yearly pay rise (%)" type="number" min={0} max={100} value={String(num(costs.annual_raise_pct))} onChange={(e) => setCost("annual_raise_pct", Number(e.target.value))} />
                    </div>
                    <h4 className="h5" style={{ margin: 0 }}>Salaries</h4>
                    {salaries.map((row, i) => (
                      <div key={i} className="app-formgrid" style={{ gridTemplateColumns: "2fr 1.5fr 1fr 1fr auto", alignItems: "end" }}>
                        <Input label="Role" value={row.role} onChange={(e) => setCost("salaries", salaries.map((x, j) => (j === i ? { ...x, role: e.target.value } : x)))} />
                        <Input label="Monthly pay" inputMode="decimal" value={fromMinor(row.monthly_minor)} onChange={(e) => setCost("salaries", salaries.map((x, j) => (j === i ? { ...x, monthly_minor: toMinor(e.target.value) ?? 0 } : x)))} />
                        <Input label="People" type="number" min={1} value={String(row.count)} onChange={(e) => setCost("salaries", salaries.map((x, j) => (j === i ? { ...x, count: Number(e.target.value) } : x)))} />
                        <Input label="From month" type="number" min={1} max={24} value={String(row.start_month)} onChange={(e) => setCost("salaries", salaries.map((x, j) => (j === i ? { ...x, start_month: Number(e.target.value) } : x)))} />
                        <Button variant="ghost" aria-label={`Remove ${row.role || "role"}`} onClick={() => setCost("salaries", salaries.filter((_, j) => j !== i))}>Remove</Button>
                      </div>
                    ))}
                    <div><Button variant="secondary" size="sm" onClick={() => setCost("salaries", [...salaries, { role: "", monthly_minor: 0, count: 1, start_month: 1 }])}>Add a role</Button></div>
                    <h4 className="h5" style={{ margin: 0 }}>Fixed costs</h4>
                    {fixed.map((row, i) => (
                      <div key={i} className="app-formgrid" style={{ gridTemplateColumns: "2fr 1.5fr auto", alignItems: "end" }}>
                        <Input label="Cost" value={row.label} onChange={(e) => setCost("fixed", fixed.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                        <Input label="Each month" inputMode="decimal" value={fromMinor(row.monthly_minor)} onChange={(e) => setCost("fixed", fixed.map((x, j) => (j === i ? { ...x, monthly_minor: toMinor(e.target.value) ?? 0 } : x)))} />
                        <Button variant="ghost" aria-label={`Remove ${row.label || "cost"}`} onClick={() => setCost("fixed", fixed.filter((_, j) => j !== i))}>Remove</Button>
                      </div>
                    ))}
                    <div><Button variant="secondary" size="sm" onClick={() => setCost("fixed", [...fixed, { label: "", monthly_minor: 0 }])}>Add a cost</Button></div>
                  </div>
                </Card>
              </>
            ) : null}
            <div className="app-cluster">
              <Button type="submit" loading={save.busy} disabled={!dirty}>{dirty ? "Save and recalculate" : "Saved"}</Button>
              <Button type="button" variant="secondary" loading={suggest.busy} onClick={() => void suggest.run()}>Suggest typical numbers</Button>
            </div>
          </form>

          <FormError error={suggest.error} />
          {proposals ? (
            <Card>
              <h2 className="h4" style={{ margin: "0 0 var(--space-2)" }}>Suggestions from sourced benchmarks</h2>
              <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-3)" }}>{proposals.message || "Use the ones that fit. Prices and volumes are never suggested."}</p>
              {proposals.proposals.length === 0 ? <p className="body-sm">Nothing to suggest right now.</p> : (
                <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {proposals.proposals.map((p) => (
                    <li key={p.name} className="app-stack" style={{ gap: "var(--space-1)" }}>
                      <strong>{humanise(p.name)}: {p.value}{p.current !== null ? ` (now ${p.current})` : ""}</strong>
                      <span className="body-sm">{p.rationale} {p.source_name ? <span className="app-muted">Source: {p.source_name}</span> : null}</span>
                      <div><Button size="sm" variant="secondary" onClick={() => { if (p.name in (draft?.drivers ?? {})) setDriver(p.name, p.value); else setCost(p.name, p.value); }}>Use {p.value}</Button></div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          ) : null}

          {versions.data && versions.data.length > 0 ? (
            <Card>
              <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Earlier versions</h2>
              <ul className="app-stack" style={{ listStyle: "none", margin: 0, padding: 0, gap: "var(--space-2)" }}>
                {versions.data.slice(0, 6).map((v) => (
                  <li key={v.version} className="app-cluster" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
                    <span className="body-sm">Version {v.version}{v.note ? `, ${v.note}` : ""} <span className="app-faint">{formatDate(v.created_at)}</span></span>
                    <Button size="sm" variant="ghost" onClick={() => restore.mutate(v.version)}>Restore</Button>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>
      )}
    </Loaded>
  );
}
