/**
 * What each role may see in the console. This mirrors `apps/core/rbac.py` so the menu only offers
 * what a person can use. It is a convenience: the API enforces every permission itself.
 */
const MEMBER = ["profile.edit", "feed.post", "jobs.post", "learning.enrol", "toolkit.use"];
const EDITOR = ["admin.access", "editorial.manage", "courses.manage", "jobs.moderate"];
const COMMUNITY_ADMIN = [
  ...EDITOR,
  "members.view",
  "directory.feature",
  "reference.manage",
  "members.approve",
  "members.suspend",
  "members.remove",
  "invitations.manage",
  "mentors.decide",
  "sessions.manage",
  "toolkit.manage",
  "events.manage",
  "campaigns.send",
  "reports.handle",
  "feed.moderate",
  "dashboard.view",
];
const SUPER_ADMIN = [...COMMUNITY_ADMIN, "roles.manage", "audit.read", "settings.manage", "toolkit.settings"];

const BY_ROLE: Record<string, string[]> = {
  member: MEMBER,
  mentor: [...MEMBER, "mentorship.respond"],
  content_editor: EDITOR,
  community_admin: COMMUNITY_ADMIN,
  super_admin: SUPER_ADMIN,
};

export function permissionsFor(roles: readonly string[]): Set<string> {
  return new Set(roles.flatMap((r) => BY_ROLE[r] ?? []));
}

export function isAdmin(roles: readonly string[]): boolean {
  return permissionsFor(roles).has("admin.access");
}

export const ROLE_LABELS: Record<string, string> = {
  member: "Member",
  mentor: "Mentor",
  content_editor: "Content editor",
  community_admin: "Community admin",
  super_admin: "Super admin",
};
