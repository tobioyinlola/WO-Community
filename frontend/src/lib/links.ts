/** Notification links are paths in the API's own naming; map them onto this app's screens. */
export function localLink(link: string): string {
  if (!link) return "/app/notifications";
  if (link.startsWith("/app/") || link.startsWith("/admin")) return link;
  const path = link.replace(/^https?:\/\/[^/]+/, "");
  return path.startsWith("/app") ? path : `/app${path.startsWith("/") ? path : `/${path}`}`;
}
