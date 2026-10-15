import { getAccessToken } from "../api/session";

/** The unverified claims in the access token, used only to decide what to show, never to allow anything. */
export function tokenClaims(): Record<string, unknown> {
  const token = getAccessToken();
  const part = token?.split(".")[1];
  if (!part) return {};
  try {
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return {};
  }
}

/** Seconds since this session last passed a second step, or null if it never did. */
export function mfaAgeSeconds(): number | null {
  const at = tokenClaims().mfa_at;
  return typeof at === "number" ? Math.max(0, Date.now() / 1000 - at) : null;
}

/** The console asks for the authenticator code once a day (the server's MFA_SESSION_MAX_AGE). */
export const MFA_DAY_SECONDS = 24 * 60 * 60;
