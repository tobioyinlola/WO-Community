import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { humanise } from "../../lib/format";
import { useToolkitConfig } from "./config";

type Pkg = components["schemas"]["TkPackage"];

export type StepState = "done" | "refresh" | "working" | "failed" | "todo" | "waiting";

export interface Step {
  key: string;
  label: string;
  to: string;
  /** What finishing it gets you, in a line. */
  outcome: string;
  /** The button that starts it. */
  action: string;
  minutes: string;
  output?: string;
  feature?: string;
  state: StepState;
}

/**
 * The order a founder takes an idea through the toolkit, the way a programme would ask for it:
 * describe it, test it, plan it, put numbers on it, then pitch it.
 */
const STEPS: Array<Omit<Step, "state">> = [
  { key: "profile", label: "Describe the venture", to: "profile", outcome: "The answers every other step is written from.", action: "Fill in the profile", minutes: "10 min" },
  { key: "score", label: "Score the idea", to: "score", output: "score", feature: "score", outcome: "How strong the idea looks, and the gaps to close first.", action: "Score my idea", minutes: "1 min" },
  { key: "plan", label: "Write the business plan", to: "plan", output: "plan", feature: "plan", outcome: "A full plan from your answers, every section yours to edit.", action: "Write my plan", minutes: "2 min" },
  { key: "forecast", label: "Model the numbers", to: "forecast", output: "forecast", feature: "forecast", outcome: "Two years of revenue, costs and cash you can adjust.", action: "Start the forecast", minutes: "5 min" },
  { key: "deck", label: "Build the pitch deck", to: "decks", output: "deck", feature: "decks", outcome: "Slides in your words, with figures linked to the forecast.", action: "Create a deck", minutes: "2 min" },
];

/** The tools that sit beside the journey rather than in it. */
export const EXTRAS: Array<{ key: string; label: string; short: string; to: string; blurb: string; feature?: string; needsAi?: boolean }> = [
  { key: "prototype", label: "Prototypes", short: "Prototypes", to: "prototypes", feature: "prototypes", blurb: "A clickable mock-up to test the idea with real people." },
  { key: "partner", label: "Venture partner", short: "Partner", to: "partner", feature: "partner", needsAi: true, blurb: "Talk the venture through with an AI partner that has read all of it." },
  { key: "sharing", label: "Sharing", short: "Sharing", to: "sharing", blurb: "Give a mentor or co-founder a private, read-only link." },
];

function stateOf(pkg: Pkg, output?: string): StepState {
  if (!output) return pkg.ready_for_score ? "done" : "todo";
  const status = pkg.outputs.find((o) => o.type === output)?.status;
  if (status === "ready") return "done";
  if (status === "needs_refresh") return "refresh";
  if (status === "generating") return "working";
  if (status === "failed") return "failed";
  return pkg.ready_for_score ? "todo" : "waiting";
}

export interface Journey {
  steps: Step[];
  done: number;
  /** The one thing to do now: the first step not finished. Null once all are. */
  next: Step | null;
  /** Plain words for what is still missing from the profile. */
  missing: string[];
  pkg: Pkg;
}

export function journeyOf(pkg: Pkg, features?: Record<string, boolean>): Journey {
  const steps = STEPS.filter((s) => !s.feature || features?.[s.feature] !== false).map((s) => ({ ...s, state: stateOf(pkg, s.output) }));
  return {
    steps,
    done: steps.filter((s) => s.state === "done").length,
    next: steps.find((s) => s.state !== "done") ?? null,
    missing: pkg.missing_required.map((f) => humanise(f).toLowerCase()),
    pkg,
  };
}

/** The names the steps go by in the tab row. */
export const SHORT: Record<string, string> = { profile: "Profile", score: "Score", plan: "Business plan", forecast: "Forecast", deck: "Pitch decks" };

export const packageKey = (id: string) => ["toolkit", id, "package"] as const;

export function useJourney(ventureId: string): Journey | null {
  const features = useToolkitConfig().data?.features;
  const query = useQuery({
    queryKey: packageKey(ventureId),
    queryFn: () => unwrap(api.GET("/api/v1/toolkit/ventures/{venture_id}/package", { params: { path: { venture_id: ventureId } } })),
  });
  return query.data ? journeyOf(query.data, features) : null;
}

/** The journey step the page being shown belongs to, if any. */
export function useCurrentStep(journey: Journey | null): Step | null {
  const { pathname } = useLocation();
  const last = pathname.replace(/\/+$/, "").split("/").pop() ?? "";
  return journey?.steps.find((s) => s.to === last) ?? null;
}

export const STATE_LABEL: Record<StepState, string> = {
  done: "Done",
  refresh: "Out of date",
  working: "Working on it",
  failed: "Needs another try",
  todo: "To do",
  waiting: "After the profile",
};
