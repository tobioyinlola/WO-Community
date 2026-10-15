import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Download } from "lucide-react";
import { Link } from "react-router-dom";
import { api, downloadFile, unwrap } from "../../api/client";
import { Alert, Button, Card, CardText, CardTitle } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { Loaded, SkeletonRows } from "../../ui/blocks";
import { StatusBadge, packageKey, useWorkspace } from "./Workspace";
import { useToolkitConfig } from "./config";

const OUTPUTS: Record<string, { label: string; to: string; blurb: string }> = {
  score: { label: "Validation score", to: "score", blurb: "How strong the idea looks, and what would make it stronger." },
  plan: { label: "Business plan", to: "plan", blurb: "A 44 section plan written from your answers and cited sources." },
  forecast: { label: "Financial forecast", to: "forecast", blurb: "Two years of revenue, costs and cash you can adjust." },
  deck: { label: "Pitch deck", to: "decks", blurb: "Slides built from your profile, with figures linked to the forecast." },
  prototype: { label: "Prototype", to: "prototypes", blurb: "A clickable mock-up of the product." },
};

const FEATURE: Record<string, string> = { deck: "decks", prototype: "prototypes" };

const STEP_LINKS: Array<[RegExp, string]> = [
  [/profile|required|field/i, "profile"],
  [/score/i, "score"],
  [/forecast/i, "forecast"],
  [/plan/i, "plan"],
  [/deck/i, "decks"],
];

export default function Overview() {
  const { ventureId } = useWorkspace();
  const features = useToolkitConfig().data?.features;
  const query = useQuery({
    queryKey: packageKey(ventureId),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/package", { params: { path: { venture_id: ventureId } } })),
  });
  return (
    <Loaded query={query} skeleton={<SkeletonRows />}>
      {(pkg) => {
        const stateOf = (type: string) => pkg.outputs.find((o) => o.type === type);
        return (
          <div className="app-stack app-stack--lg">
            {!pkg.ready_for_score ? (
              <Alert
                tone="info"
                title="Start with your profile"
                action={<Link className="wo-btn wo-btn--secondary wo-btn--sm" to="profile">Open the profile</Link>}
              >
                Everything is written from it. Still needed: {pkg.missing_required.map((f) => humanise(f).toLowerCase()).join(", ")}.
              </Alert>
            ) : null}
            <div className="app-grid">
              {Object.entries(OUTPUTS).filter(([type]) => features?.[FEATURE[type] ?? type] !== false).map(([type, info]) => {
                const state = stateOf(type);
                return (
                  <Card key={type}>
                    <div className="app-cluster" style={{ justifyContent: "space-between", marginBottom: "var(--space-3)" }}>
                      <CardTitle style={{ margin: 0 }}>{info.label}</CardTitle>
                      <StatusBadge status={state?.status ?? "not_started"} />
                    </div>
                    <CardText>{info.blurb}</CardText>
                    {state?.status === "needs_refresh" && state.stale_fields.length > 0 ? (
                      <p className="caption app-muted" style={{ margin: "var(--space-3) 0 0" }}>
                        You changed {state.stale_fields.map((f) => humanise(f).toLowerCase()).join(", ")} since.
                      </p>
                    ) : null}
                    {state?.last_generated_at ? <p className="caption app-faint" style={{ margin: "var(--space-2) 0 0" }}>Last made {formatDate(state.last_generated_at)}</p> : null}
                    <div style={{ marginTop: "var(--space-4)" }}>
                      <Link className="wo-btn wo-btn--secondary wo-btn--sm" to={info.to}>
                        {state && state.status !== "not_started" ? "Open" : "Get started"}
                        <ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" />
                      </Link>
                    </div>
                  </Card>
                );
              })}
            </div>
            <div className="app-split">
              <Card>
                <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Profile strength</h2>
                <div className="app-meter" role="progressbar" aria-valuenow={pkg.completeness} aria-valuemin={0} aria-valuemax={100} aria-label="Profile strength"><span style={{ width: `${pkg.completeness}%` }} /></div>
                <p className="body-sm app-muted" style={{ margin: "var(--space-2) 0 0" }}>{pkg.completeness}% of the profile is filled in. The more you add, the better everything else gets.</p>
              </Card>
              <Card>
                <h2 className="h4" style={{ margin: "0 0 var(--space-3)" }}>Your data</h2>
                <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-3)" }}>Download everything held about this venture as one file.</p>
                <Button variant="secondary" size="sm" icon={<Download size={16} strokeWidth={1.5} aria-hidden="true" />} onClick={() => void downloadFile(`/api/v1/toolkit/ventures/${ventureId}/export`, "venture-data.json")}>
                  Download my data
                </Button>
              </Card>
            </div>
            {pkg.next_steps.length > 0 ? (
              <section aria-label="Next steps">
                <h2 className="h3" style={{ margin: "0 0 var(--space-3)" }}>What to do next</h2>
                <ul className="app-list">
                  {pkg.next_steps.map((step) => {
                    const target = STEP_LINKS.find(([re]) => re.test(step))?.[1] ?? "profile";
                    return (
                      <li key={step}>
                        <Link className="app-list__item" to={target}>
                          <div className="app-list__main"><p className="app-list__title">{step}</p></div>
                          <ArrowRight size={18} strokeWidth={1.5} aria-hidden="true" />
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ) : null}
          </div>
        );
      }}
    </Loaded>
  );
}
