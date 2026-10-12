import {
  BarChart3,
  Briefcase,
  FileText,
  GraduationCap,
  LayoutDashboard,
  Mail,
  Rocket,
  Settings,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

export type QueueKey = "registrations_awaiting_approval" | "open_reports" | "jobs_awaiting_review" | "wins_awaiting_review";

export interface NavLeaf {
  id: string;
  label: string;
  /** Path, optionally with a query so two entries can share a page. */
  to: string;
  /** The permission a role needs to see it. Everything is visible to an admin when omitted. */
  needs?: string;
  badge?: QueueKey;
  /** Not built yet: listed so the map of the console is complete, and marked as such. */
  soon?: boolean;
  end?: boolean;
}

export interface NavGroup {
  id: string;
  label: string;
  icon: LucideIcon;
  children: NavLeaf[];
}

export interface NavTop extends NavLeaf {
  icon: LucideIcon;
}

export type NavEntry = NavTop | NavGroup;

export const isGroup = (entry: NavEntry): entry is NavGroup => "children" in entry;

export const NAV: NavEntry[] = [
  { id: "dashboard", label: "Dashboard", to: "/admin", icon: LayoutDashboard, needs: "dashboard.view", end: true },
  {
    id: "members",
    label: "Members",
    icon: Users,
    children: [
      { id: "members-all", label: "All members", to: "/admin/members", needs: "members.view" },
      { id: "approvals", label: "Approvals", to: "/admin/approvals", needs: "members.approve", badge: "registrations_awaiting_approval" },
      { id: "invitations", label: "Invitations", to: "/admin/invitations", needs: "invitations.manage" },
      { id: "mentors", label: "Mentors", to: "/admin/mentors", needs: "mentors.decide" },
      { id: "reports", label: "Moderation reports", to: "/admin/reports", needs: "reports.handle", badge: "open_reports" },
    ],
  },
  {
    id: "content",
    label: "Content",
    icon: FileText,
    children: [
      { id: "feed", label: "Posts and feed", to: "/admin/feed", needs: "feed.moderate", soon: true },
      { id: "news", label: "News and awards", to: "/admin/news", needs: "editorial.manage" },
      { id: "wins", label: "Win submissions", to: "/admin/wins", needs: "editorial.manage", badge: "wins_awaiting_review" },
      { id: "events", label: "Events", to: "/admin/events", needs: "events.manage" },
    ],
  },
  {
    id: "jobs",
    label: "Jobs",
    icon: Briefcase,
    children: [
      { id: "jobs-all", label: "All jobs", to: "/admin/jobs", needs: "jobs.moderate", badge: "jobs_awaiting_review" },
      { id: "job-applications", label: "Applications", to: "/admin/job-applications", needs: "jobs.moderate", soon: true },
    ],
  },
  {
    id: "learning",
    label: "Learning",
    icon: GraduationCap,
    children: [
      { id: "courses", label: "Courses", to: "/admin/courses", needs: "courses.manage" },
      { id: "enrolments", label: "Enrolments", to: "/admin/enrolments", needs: "courses.manage", soon: true },
    ],
  },
  {
    id: "mentorship",
    label: "Mentorship",
    icon: UserCheck,
    children: [
      { id: "sessions", label: "Sessions", to: "/admin/sessions", needs: "sessions.manage", soon: true },
      { id: "matches", label: "Matches", to: "/admin/matches", needs: "sessions.manage", soon: true },
    ],
  },
  {
    id: "toolkit",
    label: "Toolkit",
    icon: Rocket,
    children: [
      { id: "ventures", label: "Ventures", to: "/admin/toolkit/ventures", needs: "toolkit.manage", soon: true },
      { id: "toolkit-templates", label: "Templates", to: "/admin/toolkit/templates", needs: "toolkit.manage", soon: true },
      { id: "rubric", label: "Scoring rubric", to: "/admin/toolkit/rubric", needs: "toolkit.settings", soon: true },
      { id: "ai-usage", label: "AI usage", to: "/admin/toolkit/usage", needs: "toolkit.manage", soon: true },
      { id: "quality", label: "Quality queue", to: "/admin/toolkit/quality", needs: "toolkit.manage", soon: true },
    ],
  },
  {
    id: "email",
    label: "Email",
    icon: Mail,
    children: [
      { id: "newsletters", label: "Newsletters", to: "/admin/email", needs: "campaigns.send" },
      { id: "segments", label: "Audiences", to: "/admin/email?tab=audiences", needs: "campaigns.send" },
      { id: "templates", label: "Templates", to: "/admin/email?tab=templates", needs: "campaigns.send" },
    ],
  },
  {
    id: "analytics",
    label: "Analytics",
    icon: BarChart3,
    children: [
      { id: "analytics-overview", label: "Overview", to: "/admin/analytics", needs: "dashboard.view", soon: true },
      { id: "funnels", label: "Funnels", to: "/admin/analytics/funnels", needs: "dashboard.view", soon: true },
      { id: "reports-analytics", label: "Reports", to: "/admin/analytics/reports", needs: "dashboard.view", soon: true },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    icon: Settings,
    children: [
      { id: "settings-main", label: "Settings", to: "/admin/settings" },
      { id: "lists", label: "Lists", to: "/admin/lists", needs: "reference.manage" },
      { id: "audit", label: "Audit log", to: "/admin/audit", needs: "audit.read", soon: true },
    ],
  },
];

/** The entries a role may see, with empty groups left out. */
export function visibleNav(have: Set<string>): NavEntry[] {
  const allowed = (leaf: NavLeaf) => !leaf.needs || have.has(leaf.needs);
  const out: NavEntry[] = [];
  for (const entry of NAV) {
    if (isGroup(entry)) {
      const children = entry.children.filter(allowed);
      if (children.length > 0) out.push({ ...entry, children });
    } else if (allowed(entry)) {
      out.push(entry);
    }
  }
  return out;
}

/** Every page a role can open, flat, for the command palette. */
export function flatNav(have: Set<string>): Array<NavLeaf & { group: string }> {
  return visibleNav(have).flatMap((entry) =>
    isGroup(entry) ? entry.children.map((c) => ({ ...c, group: entry.label })) : [{ ...entry, group: "" }],
  );
}

/** Whether a nav target is the page being shown, comparing the query too when the target has one. */
export function isCurrent(to: string, pathname: string, search: string, end = false): boolean {
  const [path, query] = to.split("?");
  if (query) return pathname === path && new URLSearchParams(search).get("tab") === new URLSearchParams(query).get("tab");
  if (path === pathname) return !(path === "/admin/email" && new URLSearchParams(search).get("tab"));
  return !end && pathname.startsWith(`${path}/`);
}
