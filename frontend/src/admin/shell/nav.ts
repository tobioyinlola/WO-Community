import {
  BarChart3,
  Briefcase,
  FileText,
  GraduationCap,
  LayoutDashboard,
  LifeBuoy,
  Mail,
  Rocket,
  Settings,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";

export type QueueKey = "registrations_awaiting_approval" | "open_reports" | "jobs_awaiting_review" | "wins_awaiting_review" | "support_unanswered" | "mentor_applications_pending";

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
      { id: "mentors", label: "Mentor applications", to: "/admin/mentors", needs: "mentors.decide", badge: "mentor_applications_pending" },
      { id: "mentors-approved", label: "Approved mentors", to: "/admin/mentors/approved", needs: "mentors.decide" },
      { id: "reports", label: "Moderation reports", to: "/admin/reports", needs: "reports.handle", badge: "open_reports" },
    ],
  },
  {
    id: "support",
    label: "Support",
    icon: LifeBuoy,
    children: [
      { id: "support-inbox", label: "Inbox", to: "/admin/support", needs: "support.manage", badge: "support_unanswered", end: true },
      { id: "support-replies", label: "Saved replies", to: "/admin/support/replies", needs: "support.manage" },
    ],
  },
  {
    id: "content",
    label: "Content",
    icon: FileText,
    children: [
      { id: "feed", label: "Posts and feed", to: "/admin/feed", needs: "feed.moderate" },
      { id: "groups", label: "Groups", to: "/admin/groups", needs: "feed.moderate" },
      { id: "news", label: "News and awards", to: "/admin/news", needs: "editorial.manage" },
      { id: "wins", label: "Win submissions", to: "/admin/wins", needs: "editorial.manage", badge: "wins_awaiting_review" },
      { id: "testimonials", label: "Testimonials", to: "/admin/testimonials", needs: "editorial.manage" },
      { id: "events", label: "Events", to: "/admin/events", needs: "events.manage" },
    ],
  },
  {
    id: "jobs",
    label: "Jobs",
    icon: Briefcase,
    children: [
      { id: "jobs-all", label: "All jobs", to: "/admin/jobs", needs: "jobs.moderate", badge: "jobs_awaiting_review" },
    ],
  },
  {
    id: "learning",
    label: "Learning",
    icon: GraduationCap,
    children: [
      { id: "courses", label: "Courses", to: "/admin/courses", needs: "courses.manage" },
      { id: "enrolments", label: "Enrolment requests", to: "/admin/course-requests", needs: "courses.manage" },
      { id: "certificates", label: "Certificates", to: "/admin/certificates", needs: "courses.manage" },
      { id: "certificate-template", label: "Certificate template", to: "/admin/learning/certificate-template", needs: "courses.manage" },
    ],
  },
  {
    id: "mentorship",
    label: "Mentorship",
    icon: UserCheck,
    children: [
      { id: "sessions", label: "Sessions", to: "/admin/sessions", needs: "sessions.manage" },
      { id: "matches", label: "Matches", to: "/admin/matches", needs: "sessions.manage" },
    ],
  },
  {
    id: "toolkit",
    label: "Toolkit",
    icon: Rocket,
    children: [
      { id: "ventures", label: "Ventures", to: "/admin/toolkit/ventures", needs: "toolkit.manage" },
      { id: "toolkit-templates", label: "Templates", to: "/admin/toolkit/templates", needs: "toolkit.manage" },
      { id: "rubric", label: "Scoring rubric", to: "/admin/toolkit/rubric", needs: "toolkit.settings" },
      { id: "ai-usage", label: "AI usage", to: "/admin/toolkit/usage", needs: "toolkit.manage" },
      { id: "quality", label: "Quality queue", to: "/admin/toolkit/quality", needs: "toolkit.manage" },
    ],
  },
  {
    id: "email",
    label: "Email",
    icon: Mail,
    children: [
      { id: "newsletters", label: "Newsletters", to: "/admin/email", needs: "campaigns.send" },
      { id: "segments", label: "Audiences", to: "/admin/email?tab=audiences", needs: "campaigns.send" },
      { id: "templates", label: "Newsletter blocks", to: "/admin/email?tab=templates", needs: "campaigns.send" },
      { id: "subscribers", label: "Newsletter subscribers", to: "/admin/email?tab=subscribers", needs: "campaigns.send" },
      { id: "email-templates", label: "Email templates", to: "/admin/email-templates", needs: "email.templates.manage" },
      { id: "email-health", label: "Email health", to: "/admin/email-health", needs: "email.health" },
    ],
  },
  {
    id: "analytics",
    label: "Analytics",
    icon: BarChart3,
    children: [
      { id: "analytics-overview", label: "Overview", to: "/admin/analytics", needs: "dashboard.view" },
      { id: "funnels", label: "Funnels", to: "/admin/analytics/funnels", needs: "dashboard.view" },
      { id: "reports-analytics", label: "Reports", to: "/admin/analytics/reports", needs: "dashboard.view" },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    icon: Settings,
    children: [
      { id: "settings-main", label: "Settings", to: "/admin/settings" },
      { id: "lists", label: "Lists", to: "/admin/lists", needs: "reference.manage" },
      { id: "audit", label: "Audit log", to: "/admin/audit", needs: "audit.read" },
    ],
  },
];

/** The entries a role may see, with empty groups left out. */
export function visibleNav(have: Set<string>, nav: NavEntry[] = NAV): NavEntry[] {
  const allowed = (leaf: NavLeaf) => !leaf.needs || have.has(leaf.needs);
  const out: NavEntry[] = [];
  for (const entry of nav) {
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
