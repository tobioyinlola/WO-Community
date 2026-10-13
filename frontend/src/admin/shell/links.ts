import type { QuickLink } from "../../shell/searchModel";
import { flatNav } from "./nav";

interface Action {
  label: string;
  to: string;
  needs: string;
  keywords: string;
}

const ACTIONS: Action[] = [
  { label: "Approve the next request", to: "/admin/approvals?next=1", needs: "members.approve", keywords: "open oldest waiting" },
  { label: "Invite someone", to: "/admin/invitations", needs: "invitations.manage", keywords: "invitation send member" },
  { label: "Add course", to: "/admin/courses?new=1", needs: "courses.manage", keywords: "new course learning" },
  { label: "Write a story", to: "/admin/news?new=1", needs: "editorial.manage", keywords: "news draft" },
  { label: "Create an event", to: "/admin/events?new=1", needs: "events.manage", keywords: "draft" },
  { label: "Write a newsletter", to: "/admin/email?new=1", needs: "campaigns.send", keywords: "email draft" },
];

/** The pages and quick actions a role may use, offered by the search field. */
export function adminLinks(permissions: Set<string>): QuickLink[] {
  const actions: QuickLink[] = ACTIONS.filter((a) => permissions.has(a.needs)).map((a) => ({ label: a.label, to: a.to, keywords: a.keywords, kind: "Action" }));
  const pages: QuickLink[] = flatNav(permissions)
    .filter((p) => !p.soon)
    .map((p) => ({ label: p.label, to: p.to, keywords: p.group, kind: "Page" }));
  return [...actions, ...pages];
}
