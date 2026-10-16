import { ArrowRight, Check, Clock, Download, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { downloadFile } from "../../api/client";
import { Button } from "../../components";
import { formatDate, humanise } from "../../lib/format";
import { SkeletonRows } from "../../ui/blocks";
import { useAiEnabled, useToolkitConfig } from "./config";
import { EXTRAS, STATE_LABEL, useJourney, type Step } from "./journey";
import { useWorkspace } from "./Workspace";

/** What each extra tool's button says. The words avoid the tab names, so each tab keeps a name of its own. */
const EXTRA_ACTION: Record<string, string> = { prototype: "Make a mock-up", partner: "Start a conversation", sharing: "Invite someone" };

/**
 * The venture's home: the one thing to do now, the whole path with where each step stands, and
 * the tools beside it. A founder should never have to work out what comes next.
 */
export default function Overview() {
  const { ventureId } = useWorkspace();
  const journey = useJourney(ventureId);
  const config = useToolkitConfig().data;
  const ai = useAiEnabled();
  if (!journey) return <SkeletonRows />;
  const { steps, next, done, pkg } = journey;
  const extras = EXTRAS.filter((t) => (!t.feature || config?.features[t.feature] !== false) && !(t.needsAi && config?.ai_enabled === false));
  const percent = Math.round((done / Math.max(1, steps.length)) * 100);

  return (
    <div className="app-stack app-stack--lg">
      <section className="tk-hero wo-on-brand" aria-labelledby="tk-next">
        <div className="tk-hero__body">
          <p className="tk-hero__eyebrow">{next ? `Step ${steps.indexOf(next) + 1} of ${steps.length}` : "All steps done"}</p>
          <h2 className="tk-hero__title" id="tk-next">{next ? nextTitle(next) : "Your venture pack is complete"}</h2>
          <p className="tk-hero__text">{next ? nextText(next, journey.missing, ai) : "Keep it current: when something changes, update the profile and refresh anything marked out of date."}</p>
          {next ? (
            <Link className="wo-btn wo-btn--accent" to={next.to}>
              {next.state === "refresh" ? "Refresh it" : next.state === "failed" ? "Try again" : next.state === "working" ? "See progress" : next.key === "profile" && pkg.completeness > 0 ? "Carry on with the profile" : next.action}
              <ArrowRight size={18} strokeWidth={1.75} aria-hidden="true" />
            </Link>
          ) : null}
          {next ? <p className="tk-hero__time"><Clock size={14} strokeWidth={1.75} aria-hidden="true" /> About {next.minutes}</p> : null}
        </div>
        <div className="tk-hero__ring" role="img" aria-label={`${done} of ${steps.length} steps done`} style={{ ["--pct" as string]: `${percent}%` }}>
          <span><strong>{done}</strong>/{steps.length}</span>
          <small>steps done</small>
        </div>
      </section>

      <section aria-labelledby="tk-path">
        <h2 className="h3" id="tk-path" style={{ margin: "0 0 var(--space-4)" }}>Your path</h2>
        <ol className="tk-path">
          {steps.map((step, i) => {
            const output = pkg.outputs.find((o) => o.type === step.output);
            const isNext = next?.key === step.key;
            return (
              <li key={step.key} className={`tk-path__step tk-path__step--${step.state}${isNext ? " tk-path__step--next" : ""}`}>
                <span className="tk-path__marker" aria-hidden="true">
                  {step.state === "done" ? <Check size={16} strokeWidth={2.5} /> : step.state === "refresh" ? <RefreshCw size={14} strokeWidth={2} /> : i + 1}
                </span>
                <div className="tk-path__main">
                  <p className="tk-path__title" id={`tk-step-${step.key}`}>
                    {step.label}
                    <span className={`tk-path__state tk-path__state--${step.state}`}>{STATE_LABEL[step.state]}</span>
                  </p>
                  <p className="tk-path__text">
                    {step.key === "profile"
                      ? journey.missing.length
                        ? `${pkg.completeness}% filled in. Still needed: ${journey.missing.join(", ")}.`
                        : `${pkg.completeness}% filled in. The more you add, the better every later step reads.`
                      : step.state === "refresh" && output?.stale_fields.length
                        ? `You changed ${output.stale_fields.map((f) => humanise(f).toLowerCase()).join(", ")} since it was made.`
                        : step.outcome}
                  </p>
                  {step.key === "profile" ? (
                    <div className="app-meter tk-path__meter" aria-hidden="true"><span style={{ width: `${pkg.completeness}%` }} /></div>
                  ) : output?.last_generated_at ? (
                    <p className="caption app-faint" style={{ margin: "var(--space-1) 0 0" }}>Last made {formatDate(output.last_generated_at)}</p>
                  ) : null}
                </div>
                <Link className={`wo-btn wo-btn--sm ${isNext ? "wo-btn--primary" : "wo-btn--ghost"}`} to={step.to} aria-describedby={`tk-step-${step.key}`}>
                  {step.state === "done" ? "Open" : step.state === "refresh" ? "Refresh" : step.state === "waiting" ? "Preview" : "Start"}
                </Link>
              </li>
            );
          })}
        </ol>
      </section>

      {extras.length ? (
        <section aria-labelledby="tk-more">
          <h2 className="h3" id="tk-more" style={{ margin: "0 0 var(--space-2)" }}>When you need them</h2>
          <p className="body-sm app-muted" style={{ margin: "0 0 var(--space-4)" }}>Tools that sit beside the path. Use them at any point.</p>
          <div className="tk-extras">
            {extras.map((t) => (
              <div key={t.key} className="tk-extra">
                <h3 className="h4" style={{ margin: 0 }}>{t.label}</h3>
                <p className="body-sm app-muted" style={{ margin: 0, flex: 1 }}>{t.blurb}</p>
                <Link className="app-linklike tk-extra__link" to={t.to}>{EXTRA_ACTION[t.key] ?? "Open"} <ArrowRight size={14} strokeWidth={1.75} aria-hidden="true" /></Link>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <div className="tk-footnote">
        <span>Everything held about this venture can be downloaded as one file.</span>
        <Button variant="ghost" size="sm" icon={<Download size={16} strokeWidth={1.5} aria-hidden="true" />} onClick={() => void downloadFile(`/api/v1/toolkit/ventures/${ventureId}/export`, "venture-data.json")}>
          Download my data
        </Button>
      </div>
    </div>
  );
}

function nextTitle(step: Step): string {
  if (step.state === "refresh") return `Bring your ${step.label.replace(/^\w+ the /i, "").toLowerCase()} up to date`;
  if (step.state === "failed") return `${step.label}: give it another try`;
  if (step.state === "working") return `${step.label}: working on it`;
  return step.label;
}

function nextText(step: Step, missing: string[], ai: boolean): string {
  if (step.state === "refresh") return "You changed the profile since it was made, so it no longer matches. Refreshing keeps any edits you made by hand.";
  if (step.state === "failed") return "The last attempt did not finish. Nothing you wrote was lost.";
  if (step.state === "working") return "It is being made now. You can leave this page and come back.";
  if (step.key === "profile") {
    const still = missing.length ? ` ${missing.length} answer${missing.length > 1 ? "s" : ""} left before the score unlocks.` : "";
    return `${step.outcome}${still}${ai ? " Short on time? Describe it in a few sentences and we fill in the rest for you to check." : ""}`;
  }
  return step.outcome;
}
