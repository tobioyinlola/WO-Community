import {
  BookOpen,
  Briefcase,
  CalendarDays,
  FileText,
  LayoutGrid,
  LifeBuoy,
  Newspaper,
  Rocket,
  Rows3,
  UserCheck,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";

export type Scope = "member" | "admin";

export interface Hit {
  /** Unique within the list, for keys and `aria-activedescendant`. */
  key: string;
  group: string;
  type: string;
  title: string;
  subtitle: string;
  to: string;
}

export interface QuickLink {
  label: string;
  to: string;
  /** Extra words that should find it, such as "billing" for Settings. */
  keywords?: string;
  kind?: "Page" | "Action";
}

/** The order groups appear in, and the heading of each. */
export const GROUP_LABELS: Record<string, string> = {
  members: "Members",
  startups: "Startups",
  courses: "Courses",
  mentors: "Mentors",
  jobs: "Jobs",
  events: "Events",
  news: "News and awards",
  approvals: "Approvals",
  tickets: "Support tickets",
  ventures: "Ventures",
  pages: "Pages",
};

export const MEMBER_ORDER = ["members", "startups", "courses", "mentors", "jobs", "events", "news", "pages"];
export const ADMIN_ORDER = ["members", "approvals", "tickets", "courses", "jobs", "events", "ventures", "pages"];

const TYPE_TAG: Record<string, string> = {
  member: "Member",
  startup: "Startup",
  course: "Course",
  mentor: "Mentor",
  job: "Job",
  event: "Event",
  news: "News",
  approval: "Approval",
  ticket: "Ticket",
  venture: "Venture",
  page: "Page",
  action: "Action",
};

export const tagOf = (type: string): string => TYPE_TAG[type] ?? type;

const TYPE_ICON: Record<string, LucideIcon> = {
  member: UserRound,
  startup: Rocket,
  course: BookOpen,
  mentor: UserCheck,
  job: Briefcase,
  event: CalendarDays,
  news: Newspaper,
  approval: Users,
  ticket: LifeBuoy,
  venture: Rows3,
  page: LayoutGrid,
  action: FileText,
};

export const iconOf = (type: string): LucideIcon => TYPE_ICON[type] ?? LayoutGrid;

/** Where a member area result opens. */
export function memberTarget(type: string, id: string): string {
  switch (type) {
    case "member":
      return `/app/members/${id}`;
    case "startup":
      return `/app/startups/${id}`;
    case "job":
      return `/app/jobs/${id}`;
    case "event":
      return `/app/events/${id}`;
    case "news":
      return `/app/news/${id}`;
    case "mentor":
      return `/app/mentors/${id}`;
    case "course":
      return `/app/learn/${id}`;
    default:
      return "/app";
  }
}

/** Splits text around the matched words so the match can be marked. Case and accents are ignored. */
export function highlightParts(text: string, term: string): Array<{ text: string; match: boolean }> {
  const words = term
    .trim()
    .split(/\s+/)
    .filter((w) => w.length >= 2)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (words.length === 0 || !text) return [{ text, match: false }];
  const pattern = new RegExp(`(${words.join("|")})`, "i");
  // With one capture group, split alternates plain text and matched text, starting with plain.
  return text
    .split(pattern)
    .map((part, index) => ({ text: part, match: index % 2 === 1 }))
    .filter((part) => part.text !== "");
}

/** Pages and actions that match what was typed, or the first few when nothing was typed. */
export function matchLinks(links: QuickLink[], term: string, limit: number): QuickLink[] {
  const needle = term.trim().toLowerCase();
  if (!needle) return links.slice(0, limit);
  return links
    .filter((l) => `${l.label} ${l.keywords ?? ""}`.toLowerCase().includes(needle))
    .slice(0, limit);
}

export const MEMBER_LINKS: QuickLink[] = [
  { label: "Home", to: "/app", keywords: "dashboard welcome" },
  { label: "Your profile", to: "/app/me", keywords: "photo bio account" },
  { label: "Settings", to: "/app/settings", keywords: "password notifications privacy mentorship" },
  { label: "Notifications", to: "/app/notifications", keywords: "alerts unread" },
  { label: "Launch toolkit", to: "/app/launch", keywords: "venture plan forecast deck score" },
  { label: "My learning", to: "/app/learn", keywords: "courses progress certificates" },
  { label: "Mentoring sessions", to: "/app/mentors/sessions", keywords: "booked calendar" },
  { label: "My support requests", to: "/app/support", keywords: "contact help ticket problem" },
];
