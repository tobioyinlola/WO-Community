/**
 * The access token lives in memory only. The refresh token is an HttpOnly cookie the browser
 * keeps for us, so nothing a script can read survives a page reload.
 */
let accessToken: string | null = null;
const HINT_KEY = "wo-signed-in";
const listeners = new Set<(token: string | null) => void>();

export function getAccessToken(): string | null {
  return accessToken;
}

/**
 * The refresh cookie cannot be read by script, so a harmless flag records that this browser has
 * signed in. Without it a first time visitor is not sent on a pointless refresh that can only
 * fail. It holds no secret: clearing it just means the next visit starts signed out.
 */
export function mayHaveSession(): boolean {
  try {
    return window.localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return true;
  }
}

function rememberSession(present: boolean): void {
  try {
    if (present) window.localStorage.setItem(HINT_KEY, "1");
    else window.localStorage.removeItem(HINT_KEY);
  } catch {
    // Storage may be blocked; the app still works, it just asks the server every time.
  }
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
  rememberSession(token !== null);
  for (const listener of listeners) listener(token);
}

export function onTokenChange(listener: (token: string | null) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
