import { useQuery } from "@tanstack/react-query";
import { Check, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useOutletContext, useParams } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Alert, Badge, Button, Modal } from "../../components";
import { Loaded, PageHeader, SkeletonRows } from "../../ui/blocks";
import { useToolkitConfig } from "./config";
import { EXTRAS, SHORT, STATE_LABEL, useCurrentStep, useJourney, type Journey } from "./journey";
import { useDeleteVenture } from "./Ventures";

export type Venture = components["schemas"]["TkVenture"];
export type Package = components["schemas"]["TkPackage"];

interface WorkspaceContext {
  ventureId: string;
  venture: Venture;
}

export function useWorkspace(): WorkspaceContext {
  return useOutletContext<WorkspaceContext>();
}

export { packageKey } from "./journey";

export default function Workspace() {
  const { ventureId = "" } = useParams();
  const [confirm, setConfirm] = useState(false);
  const remove = useDeleteVenture(ventureId);
  const config = useToolkitConfig();
  const journey = useJourney(ventureId);
  // The partner is all AI conversation, so it goes when AI is off.
  const extras = EXTRAS.filter(
    (t) => (!t.feature || config.data?.features[t.feature] !== false) && !(t.needsAi && config.data?.ai_enabled === false),
  );
  const venture = useQuery({
    queryKey: ["toolkit", ventureId],
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}", { params: { path: { venture_id: ventureId } } })),
  });
  return (
    <Loaded query={venture} skeleton={<SkeletonRows />}>
      {(v) => (
        <>
          <PageHeader
            eyebrow="Launch toolkit"
            title={v.name}
            lead={
              journey
                ? journey.next
                  ? `${journey.done} of ${journey.steps.length} steps done. Private to you unless you share it.`
                  : "Every step is done. Private to you unless you share it."
                : "Private to you. Nothing here is shown to other members unless you share it."
            }
            actions={<Button variant="ghost" onClick={() => setConfirm(true)}>Delete</Button>}
          />
          <JourneyNav journey={journey} extras={extras} />
          {config.data?.ai_enabled === false ? (
            <Alert tone="info" title="AI writing is off for now">
              Every tool here works without it: your score is worked out from your answers, the business plan lays out each
              section for you to write, and decks, forecasts and prototypes start from templates. Buttons that would ask the
              AI are hidden until it is switched on.
            </Alert>
          ) : null}
          <WaitingFor journey={journey} />
          <Outlet context={{ ventureId, venture: v } satisfies WorkspaceContext} />
          <NextStep journey={journey} />
          {confirm ? (
            <Modal
              open
              onClose={() => setConfirm(false)}
              eyebrow="Launch toolkit"
              title={`Delete ${v.name}?`}
              actions={
                <>
                  <Button variant="ghost" onClick={() => setConfirm(false)}>Keep it</Button>
                  <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Delete venture</Button>
                </>
              }
            >
              It is hidden at once and erased for good after 14 days. You can restore it until then.
            </Modal>
          ) : null}
        </>
      )}
    </Loaded>
  );
}

/**
 * The venture's sections as a numbered path: the five steps in the order to take them, each marked
 * when done, then the tools that sit beside the path.
 */
function JourneyNav({ journey, extras }: { journey: Journey | null; extras: typeof EXTRAS }) {
  return (
    <nav className="tk-journey" aria-label="Venture sections">
      <div className="tk-journey__track">
        <NavLink to="" end className="tk-journey__home">Overview</NavLink>
        <ol className="tk-journey__steps">
          {(journey?.steps ?? []).map((step, i) => (
            <li key={step.key}>
              <NavLink
                to={step.to}
                title={`Step ${i + 1}: ${STATE_LABEL[step.state]}`}
                className={`tk-journey__step tk-journey__step--${step.state}${journey?.next?.key === step.key ? " tk-journey__step--next" : ""}`}
              >
                <span className="tk-journey__num" aria-hidden="true">{step.state === "done" ? <Check size={14} strokeWidth={2.5} /> : i + 1}</span>
                <span>{SHORT[step.key] ?? step.label}</span>
              </NavLink>
            </li>
          ))}
        </ol>
        {extras.length ? (
          <ul className="tk-journey__extras" aria-label="More tools">
            {extras.map((t) => (
              <li key={t.key}>
                <NavLink to={t.to} className="tk-journey__extra">{t.short}</NavLink>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </nav>
  );
}

/** On a step that is written from the profile, while the profile still lacks what it needs. */
function WaitingFor({ journey }: { journey: Journey | null }) {
  const current = useCurrentStep(journey);
  if (!journey || current?.state !== "waiting") return null;
  const left = journey.missing.length;
  return (
    <Alert tone="info" title="Finish the profile first" action={<Link className="wo-btn wo-btn--secondary wo-btn--sm" to="profile">Finish the profile</Link>}>
      This step is written from your profile, which still needs {left} answer{left > 1 ? "s" : ""}: {journey.missing.join(", ")}.
    </Alert>
  );
}

/** Under a finished step, the way on to the next one, so no one has to work out where to go. */
function NextStep({ journey }: { journey: Journey | null }) {
  const current = useCurrentStep(journey);
  if (!journey || !current || current.state !== "done") return null;
  const index = journey.steps.indexOf(current);
  const following = journey.steps.slice(index + 1).find((s) => s.state !== "done") ?? journey.next;
  if (!following) {
    return (
      <aside className="tk-nextstep tk-nextstep--complete" aria-label="Next step">
        <p><strong>Every step is done.</strong> When the venture changes, update the profile and refresh anything marked out of date.</p>
        <Link className="wo-btn wo-btn--secondary wo-btn--sm" to="">See every step</Link>
      </aside>
    );
  }
  return (
    <aside className="tk-nextstep" aria-label="Next step">
      <p>
        <span className="tk-nextstep__done"><Check size={16} strokeWidth={2.5} aria-hidden="true" /> {SHORT[current.key]} done.</span>{" "}
        Next, <strong>{following.label.toLowerCase()}</strong>: {following.outcome.charAt(0).toLowerCase() + following.outcome.slice(1)}
      </p>
      <Link className="wo-btn wo-btn--primary wo-btn--sm" to={following.to}>
        Continue <ChevronRight size={16} strokeWidth={2} aria-hidden="true" />
      </Link>
    </aside>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { v: "success" | "warning" | "info" | "danger" | "neutral"; t: string }> = {
    ready: { v: "success", t: "Ready" },
    needs_refresh: { v: "warning", t: "Out of date" },
    generating: { v: "info", t: "Working" },
    failed: { v: "danger", t: "Failed" },
    not_started: { v: "neutral", t: "Not started" },
  };
  const s = map[status] ?? { v: "neutral" as const, t: status };
  return <Badge variant={s.v} dot>{s.t}</Badge>;
}
