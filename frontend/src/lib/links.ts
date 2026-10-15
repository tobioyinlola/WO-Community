// Paths in notifications name things the way the API does; these are the screens they open.
// The server applies the same rules to the links in emails (notifications/notify.py, app_path).
const SCREENS: Array<[RegExp, string]> = [
  [/^\/home\/?$/, "/app"],
  [/^\/sessions\/[^/?#]+/, "/app/mentors/sessions"],
  [/^\/posts\/[^/?#]+/, "/app/feed"],
  [/^\/mentoring\/application/, "/app/mentors/become"],
];

/** Notification links are paths in the API's own naming; map them onto this app's screens. */
export function localLink(link: string): string {
  if (!link) return "/app/notifications";
  if (link.startsWith("/app/") || link.startsWith("/admin")) return link;
  const raw = link.replace(/^https?:\/\/[^/]+/, "");
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  if (path === "/app" || path.startsWith("/app/") || path.startsWith("/admin")) return path;
  for (const [pattern, screen] of SCREENS) if (pattern.test(path)) return screen;
  return `/app${path}`;
}
