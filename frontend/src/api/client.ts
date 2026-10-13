import createClient from "openapi-fetch";
import type { paths } from "./schema";
import { ApiError, type Problem } from "./errors";
import { getAccessToken, mayHaveSession, setAccessToken } from "./session";

/** Empty means "same origin": the dev server proxies /api, and production serves both together. */
/**
 * Where the API lives. Production builds must set VITE_API_URL (see vite.config.ts); in
 * development it is empty and requests go to the same origin, where Vite forwards /api.
 */
export const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").replace(/\/+$/, "");

const REFRESH_PATH = "/api/v1/auth/refresh";
// The API refuses cookie based calls (refresh, log out) that do not carry this header, so a page
// on another site cannot trigger them. Browsers will not add it to a cross site form post.
const REQUESTED_WITH = "wo-web";
// Paths where a 401 means "wrong credentials", not "your session ended".
const NO_RETRY = ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"];

let refreshing: Promise<boolean> | null = null;

interface Refreshed {
  access_token: string;
}

/** Asks for a new access token using the refresh cookie. One call at a time, shared by all. */
export function refreshSession(): Promise<boolean> {
  if (!getAccessToken() && !mayHaveSession()) return Promise.resolve(false);
  refreshing ??= (async () => {
    try {
      const response = await fetch(API_BASE + REFRESH_PATH, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json", "X-Requested-With": REQUESTED_WITH },
      });
      if (!response.ok) {
        setAccessToken(null);
        return false;
      }
      const body = (await response.json()) as Refreshed;
      setAccessToken(body.access_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

function authorised(request: Request): Request {
  const headers = new Headers(request.headers);
  headers.set("X-Requested-With", REQUESTED_WITH);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return new Request(request, { headers });
}

/** Adds the token, and if the server says it has expired, renews it once and tries again. */
export async function authFetch(input: Request): Promise<Response> {
  const spare = input.clone();
  const response = await fetch(authorised(input), { credentials: "include" });
  const path = new URL(input.url, window.location.origin).pathname;
  if (response.status !== 401 || NO_RETRY.includes(path)) return response;
  if (!(await refreshSession())) return response;
  return fetch(authorised(spare), { credentials: "include" });
}

export const api = createClient<paths>({ baseUrl: API_BASE, fetch: authFetch });

/** The problem the server described. The client has already read the body, so use what it parsed. */
function problemOf(error: unknown, response: Response): Problem {
  if (error && typeof error === "object") return error as Problem;
  if (typeof error === "string" && error) return { status: response.status, detail: error };
  return { status: response.status, detail: response.statusText };
}

interface Result<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Returns the data, or throws an `ApiError` describing what the server said. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, problemOf(error, response));
  return data as T;
}

/** The data together with the ETag that must come back in `If-Match` when it is edited. */
export interface Tagged<T> {
  data: T;
  etag: string;
}

export async function unwrapTagged<T>(call: Promise<Result<T>>): Promise<Tagged<T>> {
  const { data, error, response } = await call;
  if (!response.ok) throw new ApiError(response.status, problemOf(error, response));
  return { data: data as T, etag: response.headers.get("ETag") ?? "" };
}

/** Saves a file the API serves behind sign in (calendar files, PDFs) as a download. */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await authFetch(new Request(new URL(API_BASE + path, window.location.origin)));
  if (!response.ok) {
    let problem: Problem = { status: response.status, detail: response.statusText };
    try {
      problem = (await response.json()) as Problem;
    } catch {
      // not a problem document; keep the status text
    }
    throw new ApiError(response.status, problem);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
