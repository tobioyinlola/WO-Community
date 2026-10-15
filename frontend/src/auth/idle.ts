/** Signing out after a spell without activity, shared by every open tab through localStorage. */

export const IDLE_LIMIT_MS = 5 * 60 * 1000;
export const IDLE_WARNING_MS = 60 * 1000;

const LAST_ACTIVE = "wo:last-active";
const SIGNED_OUT_IDLE = "wo:signed-out-idle";

function store(kind: "local" | "session"): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null; // storage switched off: the timer still runs within this tab
  }
}

let memoryLastActive = Date.now();

export function markActive(now: number = Date.now()): void {
  memoryLastActive = now;
  store("local")?.setItem(LAST_ACTIVE, String(now));
}

/** When the member last did something, in this tab or any other. */
export function lastActive(): number {
  const stored = Number(store("local")?.getItem(LAST_ACTIVE) ?? "");
  return Number.isFinite(stored) && stored > memoryLastActive ? stored : memoryLastActive;
}

export function idleFor(now: number = Date.now()): number {
  return now - lastActive();
}

/** Remembered for the sign-in page, which says why the member is there. */
export function noteIdleSignOut(): void {
  store("session")?.setItem(SIGNED_OUT_IDLE, "1");
}

export function wasSignedOutIdle(): boolean {
  return store("session")?.getItem(SIGNED_OUT_IDLE) === "1";
}

export function clearIdleSignOutNote(): void {
  store("session")?.removeItem(SIGNED_OUT_IDLE);
}

/** A page opened after a long gap (a closed tab, a sleeping laptop) starts signed out. */
export function staleOnLoad(now: number = Date.now()): boolean {
  const stored = Number(store("local")?.getItem(LAST_ACTIVE) ?? "");
  return Number.isFinite(stored) && stored > 0 && now - stored >= IDLE_LIMIT_MS;
}
